"""Split-terminal console manager with in-app scrollback.

Features:
  - Fixed bottom 2 rows: status bar + prompt (never overwritten by logs)
  - Scrolling log region above, backed by a rolling log_buffer
  - Mouse-wheel scroll (SGR mouse tracking, mode 1000+1006)
  - PageUp / PageDown scroll by one screen
  - Esc clears the current input buffer
  - Up/Down arrows walk through command history, persisted in botbash.history
    (override the location with FOLDA_HISTORY_FILE)
  - Tab completes commands/arguments via the `completer` callback
  - Hold right mouse button and drag over the log area to select text; on
    release the selection is copied to the clipboard. A right click without
    dragging copies everything currently visible in the log area.
  - New logs arriving while scrolled up are buffered with a "N new below"
    indicator in the status bar; jumping back to bottom replays them
  - Resize-aware (SIGWINCH)
  - Falls back to plain print/input on non-TTY (systemd, redirected output)

NOTE: enabling mouse tracking intercepts normal clicks. Hold SHIFT while
dragging to use the terminal's own text selection instead. Clipboard copy
uses the OSC 52 escape (needs terminal support; Windows Terminal, iTerm2,
kitty, WezTerm, tmux with set-clipboard on) plus wl-copy/xclip/xsel/pbcopy
when one is installed. On exit the terminal is restored via the atexit
handler; if you ever see a garbled terminal, run `reset` or `stty sane`.
"""

import atexit
import base64
import logging
import os
import re
import select
import shutil
import signal
import subprocess
import sys
import threading
import termios
import time
import tty
from collections import defaultdict, deque
from typing import Callable, Deque, Dict, List, Optional, Tuple

HISTORY_FILE_DEFAULT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), 'botbash.history'
)


# ---------- sanitization ----------
_ANSI_RE = re.compile(r'\x1b\[[0-9;?]*[a-zA-Z]|\x1b\][^\x07]*\x07')
_CTRL_RE = re.compile(r'[\x00-\x08\x0b-\x1f\x7f]')   # keep \t and \n


def _sanitize(s: str) -> str:
    s = _ANSI_RE.sub('', s)
    s = _CTRL_RE.sub('', s)
    return s


class ConsoleManager:
    """Fixed input/status area at the bottom, scrollable log area above."""

    GUILD_RE = re.compile(r'\bguild (\d+)\b')

    def __init__(self, prompt: str = "FoldaTunez> ", guild_log_size: int = 500,
                 log_history: int = 5000, scroll_step: int = 3,
                 history_file: Optional[str] = None, history_size: int = 1000):
        self.prompt = prompt
        self.guild_log_size = guild_log_size
        self.scroll_step = scroll_step

        self.real_stdout = sys.stdout
        self.real_stderr = sys.stderr

        self.lock = threading.RLock()
        self.input_buffer = ""
        self.cursor_pos = 0
        self.running = True

        # Log buffer + scrolling
        self.log_buffer: Deque[str] = deque(maxlen=log_history)
        self.scroll_offset = 0            # 0 = live/bottom, N = scrolled up N lines
        self.pending_new_logs = 0
        self.mouse_enabled = False

        # Per-guild log buffers + filter
        self.guild_logs: Dict[int, Deque[str]] = defaultdict(
            lambda: deque(maxlen=self.guild_log_size)
        )
        self.guild_filter: Optional[int] = None

        # Async integration
        self.loop = None
        self.on_command: Optional[Callable[[str], None]] = None
        self.status_callback: Optional[Callable[[], str]] = None
        # completer(text_before_cursor) -> (token_start_index, candidates)
        self.completer: Optional[Callable[[str], Tuple[int, List[str]]]] = None

        # Command history (Up/Down), persisted to disk
        self.history_file = (
            history_file or os.getenv('FOLDA_HISTORY_FILE') or HISTORY_FILE_DEFAULT
        )
        self.history_size = history_size
        self.history: List[str] = []
        self._hist_idx = 0
        self._hist_stash = ""
        self._load_history()

        # Right-button drag selection (copy to clipboard)
        self._sel_active = False
        self._sel_moved = False
        self._sel_anchor = (1, 1)
        self._sel_cur = (1, 1)
        self._sel_lines: List[str] = []
        self._flash_text = ""
        self._flash_until = 0.0

        self._enabled = bool(sys.stdout.isatty() and sys.stdin.isatty())
        self._reader_thread: Optional[threading.Thread] = None

        if self._enabled:
            self._setup_terminal()

    # ---------- terminal geometry ----------
    def _update_size(self):
        size = shutil.get_terminal_size(fallback=(80, 24))
        self.rows = max(4, size.lines)
        self.cols = max(20, size.columns)
        self.scroll_bottom = self.rows - 2
        self.status_row = self.rows - 1
        self.input_row = self.rows

    def _setup_terminal(self):
        self._update_size()

        # Scroll region: rows 1..scroll_bottom scroll; last 2 stay put
        self._raw_write(f'\033[1;{self.scroll_bottom}r')
        self._raw_write('\033[2J')
        self._raw_write(f'\033[{self.scroll_bottom};1H')

        # SGR mouse tracking (1002 = press/release + drag motion, 1006 = SGR coords)
        self._raw_write('\033[?1002h\033[?1006h')
        self.mouse_enabled = True

        self._render_input()
        self._render_status()

        # Redirect stdout/stderr into the console
        sys.stdout = _ConsoleWriter(self, sys.__stdout__)
        sys.stderr = _ConsoleWriter(self, sys.__stderr__)
        atexit.register(self.cleanup)

    def _raw_write(self, s: str):
        try:
            self.real_stdout.write(s)
            self.real_stdout.flush()
        except Exception:
            pass

    # ---------- rendering ----------
    def _render_input(self):
        with self.lock:
            self._raw_write(f'\033[{self.input_row};1H')
            self._raw_write('\033[2K')
            line = self.prompt + self.input_buffer
            if len(line) > self.cols:
                line = line[-(self.cols - 1):]
            self._raw_write(line)
            col = min(len(self.prompt) + self.cursor_pos + 1, self.cols)
            self._raw_write(f'\033[{self.input_row};{col}H')

    def _render_status(self):
        if not self.status_callback:
            return
        try:
            status = self.status_callback() or ""
        except Exception:
            status = ""

        if self.scroll_offset > 0:
            total = len(self.log_buffer)
            extra = f"[SCROLLED up {self.scroll_offset}/{total}"
            if self.pending_new_logs:
                extra += f" | {self.pending_new_logs} new below"
            extra += "] "
            status = extra + status

        if self._flash_text and time.time() < self._flash_until:
            status = f"[{self._flash_text}] " + status

        with self.lock:
            self._raw_write(f'\033[{self.status_row};1H')
            self._raw_write('\033[2K')
            self._raw_write(status[:self.cols])

    def update_status(self):
        if self._enabled:
            self._render_status()

    # ---------- log output ----------
    def write_log(self, msg: str):
        if not self._enabled:
            print(msg)
            return

        for raw_line in msg.split('\n'):
            line = _sanitize(raw_line).expandtabs(8)   # keeps screen columns == string indexes
            self.log_buffer.append(line)

            if self.scroll_offset == 0 and not self._sel_active:
                with self.lock:
                    self._raw_write('\0337')                    # save cursor
                    self._raw_write(f'\033[{self.scroll_bottom};1H')
                    self._raw_write(line[:self.cols] + '\n')    # scrolls region
                    self._raw_write('\0338')                    # restore cursor
            else:
                self.pending_new_logs += 1

    def _visible_lines(self) -> List[str]:
        """Lines currently shown in the scroll region (index 0 = row 1)."""
        visible_height = self.scroll_bottom
        total = len(self.log_buffer)
        end_idx = total - self.scroll_offset
        start_idx = max(0, end_idx - visible_height)
        visible = list(self.log_buffer)[start_idx:end_idx]
        while len(visible) < visible_height:
            visible.insert(0, '')
        return visible

    def _redraw_log_region(self):
        """Repaint the scroll region from log_buffer at current scroll_offset."""
        visible = self._visible_lines()

        with self.lock:
            buf = ['\0337']                                     # save cursor
            for i, line in enumerate(visible):
                row = i + 1
                buf.append(f'\033[{row};1H\033[2K')
                buf.append(line[:self.cols])
            buf.append('\0338')                                 # restore cursor
            self._raw_write(''.join(buf))

    # ---------- scrolling ----------
    def _handle_scroll(self, direction: str, lines: Optional[int] = None):
        if not self._enabled:
            return
        if lines is None:
            lines = self.scroll_step

        max_offset = max(0, len(self.log_buffer) - self.scroll_bottom)

        if direction == 'up':
            new_offset = min(max_offset, self.scroll_offset + lines)
        else:
            new_offset = max(0, self.scroll_offset - lines)

        if new_offset == self.scroll_offset:
            return

        self.scroll_offset = new_offset
        self._redraw_log_region()
        self._render_status()

        if new_offset == 0:
            self.pending_new_logs = 0

    _MOUSE_RE = re.compile(r'\x1b?\[<(\d+);(\d+);(\d+)([Mm])')

    def _handle_mouse(self, seq: bytes):
        """Handle SGR mouse events: ESC [ < button ; x ; y (M press/motion | m release)."""
        s = seq.decode('ascii', errors='ignore')
        for m in self._MOUSE_RE.finditer(s):
            try:
                code, x, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
                self._mouse_event(code, x, y, m.group(4) == 'M')
            except Exception:
                pass

    def _mouse_event(self, code: int, x: int, y: int, pressed: bool):
        motion = bool(code & 32)
        base = code & ~(4 | 8 | 16 | 32)     # strip shift/meta/ctrl/motion bits
        if base == 64:                        # wheel up
            self._handle_scroll('up')
        elif base == 65:                      # wheel down
            self._handle_scroll('down')
        elif base == 2:                       # right button
            if not pressed:
                self._sel_finish()
            elif motion:
                self._sel_update(y, x)
            else:
                self._sel_start(y, x)

    # ---------- right-button selection + clipboard ----------
    def _clamp_pos(self, row: int, col: int) -> Tuple[int, int]:
        return (max(1, min(row, self.scroll_bottom)), max(1, min(col, self.cols)))

    def _sel_start(self, row: int, col: int):
        if row > self.scroll_bottom:          # ignore presses on status/prompt rows
            return
        self._sel_lines = self._visible_lines()
        self._sel_anchor = self._sel_cur = self._clamp_pos(row, col)
        self._sel_active = True
        self._sel_moved = False

    def _sel_update(self, row: int, col: int):
        if not self._sel_active:
            return
        pos = self._clamp_pos(row, col)
        if pos == self._sel_cur:
            return
        self._sel_cur = pos
        if pos != self._sel_anchor:
            self._sel_moved = True
        self._paint_selection()

    def _sel_bounds(self) -> Tuple[Tuple[int, int], Tuple[int, int]]:
        a, b = self._sel_anchor, self._sel_cur
        return (a, b) if a <= b else (b, a)

    def _paint_selection(self):
        (sr, sc), (er, ec) = self._sel_bounds()
        buf = ['\0337']
        for i, raw in enumerate(self._sel_lines):
            row = i + 1
            text = raw[:self.cols]
            if sr <= row <= er and text:
                a = sc if row == sr else 1
                b = ec if row == er else len(text)
                a, b = max(1, a), min(len(text), b)
                if a <= b:
                    text = text[:a - 1] + '\033[7m' + text[a - 1:b] + '\033[0m' + text[b:]
            buf.append(f'\033[{row};1H\033[2K{text}')
        buf.append('\0338')
        self._raw_write(''.join(buf))

    def _selected_text(self) -> str:
        lines = self._sel_lines
        if not self._sel_moved:               # plain right click: whole visible console
            out = [ln.rstrip() for ln in lines]
        else:
            (sr, sc), (er, ec) = self._sel_bounds()
            out = []
            for row in range(sr, er + 1):
                text = lines[row - 1] if row - 1 < len(lines) else ''
                a = sc if row == sr else 1
                b = ec if row == er else len(text)
                out.append(text[a - 1:b].rstrip())
        while out and not out[0]:
            out.pop(0)
        while out and not out[-1]:
            out.pop()
        return '\n'.join(out)

    def _sel_finish(self):
        if not self._sel_active:
            return
        text = self._selected_text()
        self._sel_active = False
        self._sel_moved = False
        self._sel_lines = []
        if self.scroll_offset == 0:
            self.pending_new_logs = 0
        self._redraw_log_region()             # clears highlight, replays held logs
        if text:
            self._copy_to_clipboard(text)
            n = text.count('\n') + 1
            self._flash(f"copied {n} line{'s' if n != 1 else ''}")
        else:
            self._flash("nothing to copy")

    def _flash(self, text: str, seconds: float = 3.0):
        self._flash_text = text
        self._flash_until = time.time() + seconds
        self._render_status()

    def _copy_to_clipboard(self, text: str):
        # OSC 52 works over SSH/tmux; the local tools cover terminals without it
        data = base64.b64encode(text.encode('utf-8')).decode('ascii')
        self._raw_write(f'\033]52;c;{data}\007')
        for cmd in (['wl-copy'], ['xclip', '-selection', 'clipboard'],
                    ['xsel', '--clipboard', '--input'], ['pbcopy']):
            if not shutil.which(cmd[0]):
                continue
            try:
                r = subprocess.run(
                    cmd, input=text.encode('utf-8'), timeout=2,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
                if r.returncode == 0:
                    return
            except (OSError, subprocess.SubprocessError):
                continue

    # ---------- history ----------
    def _load_history(self):
        path = self.history_file
        try:
            if not os.path.exists(path):
                with open(path, 'a', encoding='utf-8'):
                    pass
            os.chmod(path, 0o600)             # commands may contain tokens/urls
            with open(path, 'r', encoding='utf-8', errors='replace') as f:
                lines = [ln.rstrip('\n') for ln in f if ln.strip()]
            self.history = lines[-self.history_size:]
            if len(lines) > self.history_size:
                self._rewrite_history()
        except OSError:
            self.history = []
        self._hist_idx = len(self.history)

    def _rewrite_history(self):
        try:
            with open(self.history_file, 'w', encoding='utf-8') as f:
                f.writelines(ln + '\n' for ln in self.history)
        except OSError:
            pass

    def _add_history(self, line: str):
        line = line.strip()
        if line and (not self.history or self.history[-1] != line):
            self.history.append(line)
            try:
                with open(self.history_file, 'a', encoding='utf-8') as f:
                    f.write(line + '\n')
            except OSError:
                pass
            if len(self.history) > self.history_size:
                self.history = self.history[-self.history_size:]
                self._rewrite_history()
        self._hist_idx = len(self.history)
        self._hist_stash = ""

    def _history_prev(self):
        if not self.history or self._hist_idx == 0:
            return
        if self._hist_idx == len(self.history):
            self._hist_stash = self.input_buffer
        self._hist_idx -= 1
        self._set_input(self.history[self._hist_idx])

    def _history_next(self):
        if self._hist_idx >= len(self.history):
            return
        self._hist_idx += 1
        if self._hist_idx == len(self.history):
            self._set_input(self._hist_stash)
        else:
            self._set_input(self.history[self._hist_idx])

    def _set_input(self, text: str):
        self.input_buffer = text
        self.cursor_pos = len(text)
        self._render_input()

    # ---------- tab completion ----------
    def _complete(self):
        if not self.completer:
            return
        before = self.input_buffer[:self.cursor_pos]
        after = self.input_buffer[self.cursor_pos:]
        try:
            start, cands = self.completer(before)
        except Exception:
            return
        if not cands:
            return

        token = before[start:]
        lowered = [c.lower() for c in cands]
        common = cands[0][:len(os.path.commonprefix(lowered))]

        if len(cands) == 1:
            new_token = cands[0]
            # keep the cursor inside an unclosed-quote token otherwise add a separator
            if not (new_token.startswith('"') and not new_token.endswith('"')):
                new_token += ' '
        elif len(common) > len(token):
            new_token = common
        else:
            self.write_log('  '.join(cands))
            return

        self.input_buffer = before[:start] + new_token + after
        self.cursor_pos = start + len(new_token)
        self._render_input()

    def add_guild_log(self, guild_id: int, msg: str):
        self.guild_logs[guild_id].append(msg)

    # ---------- async integration ----------
    def start(self, loop, on_command: Callable[[str], None]):
        self.loop = loop
        self.on_command = on_command
        if not self._enabled:
            return

        # Resize handler via SIGWINCH
        try:
            signal.signal(signal.SIGWINCH, self._on_resize)
        except Exception:
            pass

        self._reader_thread = threading.Thread(
            target=self._read_loop, name="console-reader", daemon=True
        )
        self._reader_thread.start()

    def _on_resize(self, signum, frame):
        try:
            if self.loop:
                self.loop.call_soon_threadsafe(self._handle_resize)
            else:
                self._handle_resize()
        except Exception:
            pass

    def _handle_resize(self):
        if not self._enabled:
            return
        self._update_size()
        with self.lock:
            self._raw_write(f'\033[1;{self.scroll_bottom}r')
            self._raw_write('\033[2J')
            self._raw_write(f'\033[{self.scroll_bottom};1H')
        self._redraw_log_region()
        self._render_status()
        self._render_input()

    # ---------- input reader ----------
    def _read_loop(self):
        fd = sys.stdin.fileno()
        try:
            old_settings = termios.tcgetattr(fd)
        except Exception:
            return
        try:
            tty.setcbreak(fd)
            while self.running:
                try:
                    ch = os.read(fd, 1)
                except OSError:
                    break
                if not ch:
                    break
                self._handle_key(ch, fd)
        finally:
            try:
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
            except Exception:
                pass

    def _read_escape_seq(self, fd) -> bytes:
        """Read the remainder of an escape sequence after ESC (one sequence only)."""
        def nxt() -> bytes:
            try:
                ready, _, _ = select.select([fd], [], [], 0.05)
                return os.read(fd, 1) if ready else b''
            except Exception:
                return b''

        first = nxt()
        if not first:
            return b''                        # bare Esc
        buf = first
        if first == b'[':                     # CSI: params/intermediates, then a final byte 0x40-0x7e
            while len(buf) < 64:
                c = nxt()
                if not c:
                    break
                buf += c
                if 0x40 <= c[0] <= 0x7e:
                    break
        elif first == b'O':                   # SS3 (e.g. ESC O A)
            buf += nxt()
        elif first == b']':                   # OSC, terminated by BEL
            while len(buf) < 256:
                c = nxt()
                if not c:
                    break
                buf += c
                if c == b'\x07':
                    break
        return buf

    def _handle_key(self, ch: bytes, fd: int):
        with self.lock:
            if ch in (b'\r', b'\n'):
                line = self.input_buffer
                self.input_buffer = ""
                self.cursor_pos = 0
                self._add_history(line)

                # Enter always jumps to bottom so the user sees the result
                if self.scroll_offset > 0:
                    self.scroll_offset = 0
                    self.pending_new_logs = 0
                    self._redraw_log_region()

                self.write_log(f'{self.prompt}{line}')
                self._render_input()
                self._render_status()

                if self.on_command and line.strip():
                    try:
                        self.loop.call_soon_threadsafe(self.on_command, line)
                    except Exception:
                        pass

            elif ch in (b'\x7f', b'\x08'):
                if self.cursor_pos > 0:
                    self.input_buffer = (
                        self.input_buffer[: self.cursor_pos - 1]
                        + self.input_buffer[self.cursor_pos:]
                    )
                    self.cursor_pos -= 1
                    self._render_input()

            elif ch == b'\x03':
                self.write_log(f'{self.prompt}{self.input_buffer}^C')
                self.input_buffer = ""
                self.cursor_pos = 0
                self._render_input()

            elif ch == b'\x04':
                if not self.input_buffer:
                    self.write_log("[EOF - type 'exit' to quit]")
                elif self.cursor_pos < len(self.input_buffer):
                    self.input_buffer = (
                        self.input_buffer[: self.cursor_pos]
                        + self.input_buffer[self.cursor_pos + 1:]
                    )
                    self._render_input()

            elif ch == b'\x1b':
                seq = self._read_escape_seq(fd)
                if not seq:
                    self._cancel_input()
                elif seq.startswith(b'[<'):
                    self._handle_mouse(seq)
                else:
                    self._handle_escape(seq)

            elif ch == b'\t':
                self._complete()

            else:
                try:
                    text = ch.decode('utf-8', errors='ignore')
                except Exception:
                    return
                if text and text.isprintable():
                    self.input_buffer = (
                        self.input_buffer[: self.cursor_pos]
                        + text
                        + self.input_buffer[self.cursor_pos:]
                    )
                    self.cursor_pos += 1
                    self._render_input()

    def _handle_escape(self, seq: bytes):
        if seq in (b'[A', b'OA'):
            self._history_prev()
            return
        if seq in (b'[B', b'OB'):
            self._history_next()
            return
        if seq in (b'[C', b'OC'):
            if self.cursor_pos < len(self.input_buffer):
                self.cursor_pos += 1
                self._render_input()
            return
        if seq in (b'[D', b'OD'):
            if self.cursor_pos > 0:
                self.cursor_pos -= 1
                self._render_input()
            return
        if seq in (b'[H', b'OH', b'[1~'):
            self.cursor_pos = 0
            self._render_input()
            return
        if seq in (b'[F', b'OF', b'[4~'):
            self.cursor_pos = len(self.input_buffer)
            self._render_input()
            return
        if seq == b'[3~':
            if self.cursor_pos < len(self.input_buffer):
                self.input_buffer = (
                    self.input_buffer[: self.cursor_pos]
                    + self.input_buffer[self.cursor_pos + 1:]
                )
                self._render_input()
            return
        if seq == b'[5~':                    # PageUp
            self._handle_scroll('up', self.scroll_bottom)
            return
        if seq == b'[6~':                    # PageDown
            self._handle_scroll('down', self.scroll_bottom)
            return
        if seq == b'[1;5H':                  # Ctrl+Home -> top of buffer
            self._handle_scroll('up', len(self.log_buffer))
            return
        if seq == b'[1;5F':                  # Ctrl+End -> jump to bottom
            self._handle_scroll('down', len(self.log_buffer))
            return

    def _cancel_input(self):
        if self.input_buffer:
            self.input_buffer = ""
            self.cursor_pos = 0
            self._render_input()

    # ---------- teardown ----------
    def cleanup(self):
        if not self._enabled:
            return
        self.running = False
        try:
            if self.mouse_enabled:
                self._raw_write('\033[?1006l\033[?1002l\033[?1000l')
                self.mouse_enabled = False
            self._raw_write('\033[r')                        # reset scroll region
            self._raw_write(f'\033[{self.rows};1H\n')        # park cursor below
        except Exception:
            pass


class _ConsoleWriter:
    """File-like wrapper routing writes through ConsoleManager.write_log."""

    def __init__(self, console: ConsoleManager, fallback):
        self.console = console
        self.fallback = fallback
        self.buffer = ""

    def write(self, s):
        self.buffer += s
        while '\n' in self.buffer:
            line, self.buffer = self.buffer.split('\n', 1)
            self.console.write_log(line)

    def flush(self):
        if self.buffer:
            self.console.write_log(self.buffer)
            self.buffer = ""

    def isatty(self):
        return self.fallback.isatty() if self.fallback else False

    def fileno(self):
        return self.fallback.fileno() if self.fallback else -1

    def close(self):
        self.flush()


class ConsoleLogHandler(logging.Handler):
    """Logging handler: console output + per-guild buffering + filter."""

    def __init__(self, console: ConsoleManager):
        super().__init__()
        self.console = console

    def emit(self, record):
        try:
            msg = self.format(record)
            m = ConsoleManager.GUILD_RE.search(record.getMessage())
            if m:
                self.console.add_guild_log(int(m.group(1)), msg)
            if self.console.guild_filter is not None:
                if not m or int(m.group(1)) != self.console.guild_filter:
                    return
            self.console.write_log(msg)
        except Exception:
            pass