import os
import sys
import select
import signal
import socket
import threading
import getpass
import platform
from typing import Optional, Callable

import paramiko

from .storage import SessionLogger
from .config import ServerConfig

_IS_WINDOWS = platform.system() == "Windows"

if not _IS_WINDOWS:
    import tty
    import termios
    import fcntl
else:
    tty = None
    termios = None
    fcntl = None


class SSHRecorder:
    def __init__(
        self,
        server: ServerConfig,
        log_dir: str = "logs",
        rotate_daily: bool = True,
        term: str = "xterm-256color",
    ):
        self.server = server
        self.logger = SessionLogger(log_dir=log_dir, rotate_daily=rotate_daily)
        self.term = term
        self._client: Optional[paramiko.SSHClient] = None
        self._channel: Optional[paramiko.Channel] = None
        self._running = False
        self._original_tty_attrs = None
        self._log_file: Optional[str] = None
        self._on_bookmark: Optional[Callable] = None

    @property
    def log_file(self) -> Optional[str]:
        return self._log_file

    def _get_pty_size(self):
        if _IS_WINDOWS or termios is None:
            try:
                cols = os.get_terminal_size().columns
                rows = os.get_terminal_size().lines
                return rows, cols
            except Exception:
                return 24, 80
        try:
            import struct

            s = struct.pack("HHHH", 0, 0, 0, 0)
            result = fcntl.ioctl(sys.stdout.fileno(), termios.TIOCGWINSZ, s)
            rows, cols, _, _ = struct.unpack("HHHH", result)
            return rows, cols
        except Exception:
            return 24, 80

    def _connect(self) -> None:
        self._client = paramiko.SSHClient()
        self._client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        connect_kwargs = {
            "hostname": self.server.host,
            "port": self.server.port,
            "username": self.server.user,
            "timeout": 30,
            "allow_agent": True,
            "look_for_keys": True,
        }

        if self.server.password:
            connect_kwargs["password"] = self.server.password

        if self.server.key_file:
            key_file = os.path.expanduser(self.server.key_file)
            if os.path.exists(key_file):
                try:
                    pkey = paramiko.RSAKey.from_private_key_file(
                        key_file, password=self.server.passphrase
                    )
                    connect_kwargs["pkey"] = pkey
                    connect_kwargs["look_for_keys"] = False
                except paramiko.ssh_exception.PasswordRequiredException:
                    passphrase = getpass.getpass("Enter passphrase for key: ")
                    pkey = paramiko.RSAKey.from_private_key_file(key_file, password=passphrase)
                    connect_kwargs["pkey"] = pkey
                    connect_kwargs["look_for_keys"] = False
                except Exception:
                    pass

        if "password" not in connect_kwargs and "pkey" not in connect_kwargs:
            password = getpass.getpass(f"{self.server.user}@{self.server.host}'s password: ")
            connect_kwargs["password"] = password

        self._client.connect(**connect_kwargs)

        rows, cols = self._get_pty_size()
        transport = self._client.get_transport()
        self._channel = transport.open_session()
        self._channel.get_pty(self.term, cols, rows)
        self._channel.invoke_shell()
        self._channel.setblocking(0)

    def _resize_handler(self, signum, frame):
        if self._channel is not None:
            rows, cols = self._get_pty_size()
            try:
                self._channel.resize_pty(cols, rows)
            except Exception:
                pass

    def _read_ssh_output(self) -> None:
        while self._running:
            try:
                if self._channel is None:
                    break
                if self._channel.exit_status_ready():
                    if not self._channel.recv_ready():
                        break

                r, _, _ = select.select([self._channel], [], [], 0.1)
                if r:
                    data = self._channel.recv(4096)
                    if not data:
                        break
                    self.logger.write_output(data)
                    try:
                        sys.stdout.buffer.write(data)
                        sys.stdout.flush()
                    except Exception:
                        pass
            except socket.timeout:
                continue
            except Exception:
                if self._running:
                    break

    def _read_user_input(self) -> None:
        while self._running:
            try:
                if self._channel is None:
                    break
                r, _, _ = select.select([sys.stdin], [], [], 0.1)
                if r:
                    data = sys.stdin.buffer.read(1024)
                    if not data:
                        break
                    self.logger.write_input(data)
                    if data == b"\x1b":
                        pass
                    self._channel.send(data)
            except Exception:
                if self._running:
                    break

    def add_bookmark(self, name: str, description: str = "") -> None:
        self.logger.add_bookmark(name, description)
        sys.stdout.write(f"\r\n\x1b[33m[Bookmark added: {name}]\x1b[0m\r\n")
        sys.stdout.flush()

    def run(self) -> int:
        self._log_file = self.logger.start_session(
            host=self.server.host,
            user=self.server.user,
            port=self.server.port,
        )

        sys.stderr.write(f"Recording session to: {self._log_file}\r\n")
        sys.stderr.flush()

        try:
            self._connect()
        except Exception as e:
            sys.stderr.write(f"Connection failed: {e}\r\n")
            self.logger.end_session()
            return 1

        try:
            if not _IS_WINDOWS and termios is not None and tty is not None:
                self._original_tty_attrs = termios.tcgetattr(sys.stdin)
                tty.setraw(sys.stdin.fileno())
                tty.setcbreak(sys.stdin.fileno())
        except (termios.error if termios else Exception, Exception):
            self._original_tty_attrs = None

        if not _IS_WINDOWS and hasattr(signal, "SIGWINCH"):
            signal.signal(signal.SIGWINCH, self._resize_handler)

        self._running = True

        output_thread = threading.Thread(target=self._read_ssh_output, daemon=True)
        input_thread = threading.Thread(target=self._read_user_input, daemon=True)

        output_thread.start()
        input_thread.start()

        exit_code = 0
        try:
            while self._running:
                if self._channel is not None and self._channel.exit_status_ready():
                    exit_code = self._channel.recv_exit_status()
                    self._running = False
                    break
                output_thread.join(timeout=0.1)
                input_thread.join(timeout=0.1)
                if not output_thread.is_alive() and not input_thread.is_alive():
                    break
        except KeyboardInterrupt:
            pass
        finally:
            self._running = False
            try:
                if self._channel is not None:
                    self._channel.close()
            except Exception:
                pass
            try:
                if self._client is not None:
                    self._client.close()
            except Exception:
                pass
            if self._original_tty_attrs is not None and not _IS_WINDOWS and termios is not None:
                try:
                    termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self._original_tty_attrs)
                except Exception:
                    pass
            self.logger.end_session()
            sys.stderr.write(f"\r\nSession recording saved to: {self._log_file}\r\n")
            sys.stderr.flush()

        return exit_code
