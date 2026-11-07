"""Split-terminal console manager.

Reserves the bottom two terminal rows as a static status bar + input line.
Log output and command echo scroll in the upper region (ANSI DECSTBM).
Falls back to plain stdout if stdin/stdout is not a TTY.
"""

import atexit
import logging
import os
import re
import select
import shutil
import sys
import threading
import termios
import tty
from collections import defaultdict, deque
from typing import Callable, Deque, Dict, Optional


class ConsoleManager:
    """Fixed input/status area at the bottom, scrolling log area above."""

    GUILD_RE = re.compile(r'\bguild (\d+)\b')

    def __init__(self, prompt: str = "FoldaTunez> ", guild_log_size: int = 500):
        self.prompt = prompt
        self.guild_log_size = guild_log_size

        # Original streams (never overwritten)
        self.real_stdout = sys.stdout
        self.real_stderr = sys.stderr

        self.lock = threading.RLock()
        self.input_buffer = ""
        self.cursor_pos = 0
        self.running = True

        # Per-guild log buffers + filter
        self.guild_logs: Dict[int, Deque[str]] = defaultdict(
            lambda: deque(maxlen=self.guild_log_size)
        )
        self.guild_filter: Optional[int] = None

        # Async integration (set by start())
        self.loop = None
        self.on_command: Optional[Callable[[str], None]] = None
        self.status_callback: Optional[Callable[[], str]] = None

        self._enabled = bool(sys.stdout.isatty() and sys.stdin.isatty())
        self._reader_thread: Optional[threading.Thread] = None

        if self._enabled:
            self._setup_terminal()

    # ----- terminal setup -----
    def _update_size(self):
        size = shutil.get_terminal_size(fallback=(80, 24))
        self.rows = max(4, size.lines)
        self.cols = max(20, size.columns)
        self.scroll_bottom = self.rows - 2
        self.status_row = self.rows - 1
        self.input_row = self.rows

    def _setup_terminal(self):
        self._update_size()
        # Set scroll region: lines 1..scroll_bottom scroll; last 2 rows static
        self._raw_write(f'\033[1;{self.scroll_bottom}r')
        self._raw_write('\033[2J')
        self._raw_write(f'\033[{self.scroll_bottom};1H')
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

    # ----- rendering -----
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
        with self.lock:
            self._raw_write(f'\033[{self.status_row};1H')
            self._raw_write('\033[2K')
            self._raw_write(status[:self.cols])

    def update_status(self):
        if self._enabled:
            self._render_status()

    def write_log(self, msg: str):
        """Write one line into the scrolling region."""
        if not self._enabled:
            print(msg)
            return
        with self.lock:
            self._raw_write('\0337')                        # save cursor
            self._raw_write(f'\033[{self.scroll_bottom};1H')
            self._raw_write(msg + '\n')                     # scrolls region
            self._raw_write('\0338')                        # restore cursor

    def add_guild_log(self, guild_id: int, msg: str):
        self.guild_logs[guild_id].append(msg)

    # ----- async integration -----
    def start(self, loop, on_command: Callable[[str], None]):
        self.loop = loop
        self.on_command = on_command
        if not self._enabled:
            return
        self._reader_thread = threading.Thread(
            target=self._read_loop, name="console-reader", daemon=True
        )
        self._reader_thread.start()

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

    def _handle_key(self, ch: bytes, fd: int):
        with self.lock:
            if ch in (b'\r', b'\n'):
                line = self.input_buffer
                self.input_buffer = ""
                self.cursor_pos = 0
                self.write_log(f'{self.prompt}{line}')
                self._render_input()
                if self.on_command:
                    try:
                        self.loop.call_soon_threadsafe(self.on_command, line)
                    except Exception:
                        pass
            elif ch in (b'\x7f', b'\x08'):                  # Backspace
                if self.cursor_pos > 0:
                    self.input_buffer = (
                        self.input_buffer[: self.cursor_pos - 1]
                        + self.input_buffer[self.cursor_pos:]
                    )
                    self.cursor_pos -= 1
                    self._render_input()
            elif ch == b'\x03':                              # Ctrl+C
                self.write_log(f'{self.prompt}{self.input_buffer}^C')
                self.input_buffer = ""
                self.cursor_pos = 0
                self._render_input()
            elif ch == b'\x04':                              # Ctrl+D
                if not self.input_buffer:
                    self.write_log("[EOF - type 'exit' to quit]")
                elif self.cursor_pos < len(self.input_buffer):
                    self.input_buffer = (
                        self.input_buffer[: self.cursor_pos]
                        + self.input_buffer[self.cursor_pos + 1:]
                    )
                    self._render_input()
            elif ch == b'\x1b':                              # Escape sequence
                try:
                    ready, _, _ = select.select([fd], [], [], 0.02)
                    rest = os.read(fd, 8) if ready else b''
                except Exception:
                    rest = b''
                if rest in (b'[D', b'OD'):                   # Left
                    if self.cursor_pos > 0:
                        self.cursor_pos -= 1
                        self._render_input()
                elif rest in (b'[C', b'OC'):                 # Right
                    if self.cursor_pos < len(self.input_buffer):
                        self.cursor_pos += 1
                        self._render_input()
                elif rest in (b'[H', b'[1~', b'OH'):         # Home
                    self.cursor_pos = 0
                    self._render_input()
                elif rest in (b'[F', b'[4~', b'OF'):         # End
                    self.cursor_pos = len(self.input_buffer)
                    self._render_input()
                # Up/Down intentionally ignored (no history yet)
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

    # ----- teardown -----
    def cleanup(self):
        if not self._enabled:
            return
        self.running = False
        try:
            # Reset scroll region and move cursor below
            self._raw_write('\033[r')
            self._raw_write(f'\033[{self.rows};1H\n')
        except Exception:
            pass


class _ConsoleWriter:
    """File-like wrapper that funnels writes through ConsoleManager.write_log."""

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
    """Logging handler: writes to console, buffers per-guild lines."""

    def __init__(self, console: ConsoleManager):
        super().__init__()
        self.console = console

    def emit(self, record):
        try:
            msg = self.format(record)
            # Buffer to per-guild log if the message mentions a guild
            m = ConsoleManager.GUILD_RE.search(record.getMessage())
            if m:
                self.console.add_guild_log(int(m.group(1)), msg)
            # Apply guild filter if active
            if self.console.guild_filter is not None:
                if not m or int(m.group(1)) != self.console.guild_filter:
                    return
            self.console.write_log(msg)
        except Exception:
            pass