"""Split-terminal console manager with in-app scrollback.

Features:
  - Fixed bottom 2 rows: status bar + prompt (never overwritten by logs)
  - Scrolling log region above, backed by a rolling log_buffer
  - Mouse-wheel scroll (SGR mouse tracking, mode 1000+1006)
  - PageUp / PageDown scroll by one screen
  - Esc clears the current input buffer
  - New logs arriving while scrolled up are buffered with a "N new below"
    indicator in the status bar; jumping back to bottom replays them
  - Resize-aware (SIGWINCH)
  - Falls back to plain print/input on non-TTY (systemd, redirected output)

NOTE: enabling mouse tracking intercepts normal clicks. Hold SHIFT while
dragging to select text (standard terminal behavior). On exit the terminal
is restored via the atexit handler; if you ever see a garbled terminal,
run `reset` or `stty sane`.
"""

import atexit
import logging
import os
import re
import select
import shutil
import signal
import sys
import threading
import termios
import time
import tty
from collections import defaultdict, deque
from typing import Callable, Deque, Dict, Optional


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
                 log_history: int = 5000, scroll_step: int = 3):
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

        # Enable SGR mouse tracking (1000 = basic, 1006 = SGR coords)
        self._raw_write('\033[?1000h\033[?1006h')
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
            line = _sanitize(raw_line)
            self.log_buffer.append(line)

            if self.scroll_offset == 0:
                with self.lock:
                    self._raw_write('\0337')                    # save cursor
                    self._raw_write(f'\033[{self.scroll_bottom};1H')
                    self._raw_write(line[:self.cols] + '\n')    # scrolls region
                    self._raw_write('\0338')                    # restore cursor
            else:
                self.pending_new_logs += 1

    def _redraw_log_region(self):
        """Repaint the scroll region from log_buffer at current scroll_offset."""
        visible_height = self.scroll_bottom
        total = len(self.log_buffer)
        end_idx = total - self.scroll_offset
        start_idx = max(0, end_idx - visible_height)
        visible = list(self.log_buffer)[start_idx:end_idx]
        while len(visible) < visible_height:
            visible.insert(0, '')

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

    def _handle_mouse(self, seq: bytes):
        """Handle SGR mouse event: \033[<button;x;yM or m."""
        try:
            s = seq.decode('ascii', errors='ignore')
            if not s.startswith('[<') or len(s) < 5:
                return
            body = s[2:-1]
            parts = body.split(';')
            if len(parts) != 3:
                return
            button = int(parts[0])
            if button == 64:        # scroll up
                self._handle_scroll('up')
            elif button == 65:      # scroll down
                self._handle_scroll('down')
            # other buttons ignored
        except Exception:
            pass

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
        """Read the remainder of an escape sequence after ESC."""
        buf = b''
        deadline = time.time() + 0.05
        while time.time() < deadline:
            try:
                ready, _, _ = select.select([fd], [], [], 0.005)
                if not ready:
                    if buf:
                        break
                    continue
                chunk = os.read(fd, 64)
                if not chunk:
                    break
                buf += chunk
                last = buf[-1:]
                if last.isalpha() or last in (b'~', b'\x07'):
                    break
            except Exception:
                break
        return buf

    def _handle_key(self, ch: bytes, fd: int):
        with self.lock:
            if ch in (b'\r', b'\n'):
                line = self.input_buffer
                self.input_buffer = ""
                self.cursor_pos = 0

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
                pass

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
        if seq in (b'[A', b'OA', b'[B', b'OB'):
            return   # Up/Down not bound (no history yet)
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
                self._raw_write('\033[?1006l\033[?1000l')
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