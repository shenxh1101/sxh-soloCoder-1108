import os
import sys
import time
import threading
from typing import List, Optional, Dict, Any

from .storage import SessionReader, SessionLogEntry


class PlaybackController:
    def __init__(
        self,
        log_file: str,
        speed: float = 1.0,
        show_input: bool = True,
    ):
        self.reader = SessionReader(log_file)
        self.entries = self.reader.get_all_entries()
        self.speed = speed
        self.show_input = show_input
        self._paused = False
        self._stop = False
        self._jump_to_idx: Optional[int] = None
        self._current_idx = 0
        self._lock = threading.Lock()
        self._speed_lock = threading.Lock()
        self._elapsed = 0.0

    @property
    def is_paused(self) -> bool:
        with self._lock:
            return self._paused

    def toggle_pause(self) -> None:
        with self._lock:
            self._paused = not self._paused

    def stop(self) -> None:
        with self._lock:
            self._stop = True

    def set_speed(self, speed: float) -> None:
        with self._speed_lock:
            self.speed = max(0.1, min(speed, 100.0))

    def get_speed(self) -> float:
        with self._speed_lock:
            return self.speed

    def jump_to_index(self, idx: int) -> None:
        with self._lock:
            self._jump_to_idx = max(0, min(idx, len(self.entries) - 1))

    def jump_by_seconds(self, seconds: float) -> None:
        target_elapsed = self._elapsed + seconds
        total = 0.0
        target_idx = 0
        for i, entry in enumerate(self.entries):
            if total >= target_elapsed:
                target_idx = i
                break
            total += entry.delay
        self.jump_to_index(target_idx)

    def list_bookmarks(self) -> List[Dict[str, Any]]:
        bookmarks = self.reader.get_bookmarks()
        if not bookmarks:
            return []
        total_delay = 0.0
        result = []
        entry_idx = 0
        for bm in bookmarks:
            while entry_idx < len(self.entries) and self.entries[entry_idx].timestamp < bm["timestamp"]:
                total_delay += self.entries[entry_idx].delay
                entry_idx += 1
            result.append({
                "name": bm.get("name", ""),
                "description": bm.get("description", ""),
                "timestamp": bm["timestamp"],
                "time_offset": total_delay,
                "entry_index": entry_idx,
            })
        return result

    def jump_to_bookmark(self, bookmark_name: str) -> bool:
        for bm in self.list_bookmarks():
            if bm["name"] == bookmark_name:
                self.jump_to_index(bm["entry_index"])
                return True
        return False

    def _format_time(self, seconds: float) -> str:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        if h > 0:
            return f"{h:02d}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"

    def _print_status(self) -> None:
        total_duration = sum(e.delay for e in self.entries)
        progress = (self._elapsed / total_duration * 100) if total_duration > 0 else 0
        speed = self.get_speed()
        status = "PAUSED" if self.is_paused else "PLAYING"
        sys.stderr.write(
            f"\r\x1b[K[{status}] {self._format_time(self._elapsed)} / "
            f"{self._format_time(total_duration)} "
            f"({progress:.1f}%) x{speed:.1f} "
            f"[Space=Pause, F/B=Seek, +/-=Speed, Q=Quit]"
        )
        sys.stderr.flush()

    def play(self) -> None:
        sys.stderr.write(f"Playing: {self.reader.log_file}\r\n")
        if self.reader.metadata:
            meta = self.reader.metadata
            sys.stderr.write(
                f"Session: {meta.user}@{meta.host}:{meta.port}\r\n"
            )
        sys.stderr.write("Press any key to start playback...\r\n")
        sys.stderr.flush()

        total_duration = sum(e.delay for e in self.entries)
        self._elapsed = 0.0
        self._current_idx = 0

        while self._current_idx < len(self.entries):
            with self._lock:
                if self._stop:
                    break
                if self._jump_to_idx is not None:
                    self._current_idx = self._jump_to_idx
                    self._jump_to_idx = None
                    self._elapsed = sum(e.delay for e in self.entries[:self._current_idx])
                    sys.stdout.write("\x1b[2J\x1b[H")
                    sys.stdout.flush()
                if self._paused:
                    time.sleep(0.05)
                    self._print_status()
                    continue

            if self._current_idx >= len(self.entries):
                break

            entry = self.entries[self._current_idx]

            if self.show_input or entry.stream == "o":
                try:
                    sys.stdout.buffer.write(entry.data)
                    sys.stdout.flush()
                except Exception:
                    try:
                        sys.stdout.write(entry.data.decode("utf-8", errors="replace"))
                        sys.stdout.flush()
                    except Exception:
                        pass

            speed = self.get_speed()
            delay = entry.delay / speed if speed > 0 else 0

            start_wait = time.time()
            while (time.time() - start_wait) < delay:
                with self._lock:
                    if self._stop:
                        return
                    if self._jump_to_idx is not None:
                        break
                    if self._paused:
                        time.sleep(0.05)
                        start_wait += 0.05
                        continue
                remaining = delay - (time.time() - start_wait)
                if remaining <= 0:
                    break
                time.sleep(min(0.05, remaining))

            self._elapsed += entry.delay
            self._current_idx += 1
            self._print_status()

        sys.stderr.write("\r\nPlayback completed.\r\n")
        sys.stderr.flush()


class InteractivePlayer:
    def __init__(self, controller: PlaybackController):
        self.controller = controller
        self._thread: Optional[threading.Thread] = None

    def _handle_keyboard(self) -> None:
        import platform
        if platform.system() == "Windows":
            import msvcrt
            try:
                while True:
                    if self.controller._stop:
                        break
                    if msvcrt.kbhit():
                        ch = msvcrt.getwch()
                        if ch == "q" or ch == "Q" or ch == "\x03":
                            self.controller.stop()
                            break
                        elif ch == " ":
                            self.controller.toggle_pause()
                        elif ch == "+" or ch == "=":
                            self.controller.set_speed(self.controller.get_speed() * 1.5)
                        elif ch == "-" or ch == "_":
                            self.controller.set_speed(self.controller.get_speed() / 1.5)
                        elif ch == "f" or ch == "F":
                            self.controller.jump_by_seconds(5)
                        elif ch == "b" or ch == "B":
                            self.controller.jump_by_seconds(-5)
            except Exception:
                pass
            return

        try:
            import tty
            import termios
            import select

            fd = sys.stdin.fileno()
            old_settings = termios.tcgetattr(fd)
            try:
                tty.setcbreak(fd)
                while True:
                    if self.controller._stop:
                        break
                    r, _, _ = select.select([sys.stdin], [], [], 0.1)
                    if r:
                        ch = sys.stdin.read(1)
                        if ch == "q" or ch == "Q" or ch == "\x03":
                            self.controller.stop()
                            break
                        elif ch == " ":
                            self.controller.toggle_pause()
                        elif ch == "+" or ch == "=":
                            self.controller.set_speed(self.controller.get_speed() * 1.5)
                        elif ch == "-" or ch == "_":
                            self.controller.set_speed(self.controller.get_speed() / 1.5)
                        elif ch == "f" or ch == "F":
                            self.controller.jump_by_seconds(5)
                        elif ch == "b" or ch == "B":
                            self.controller.jump_by_seconds(-5)
                        elif ch == "B":
                            bookmarks = self.controller.list_bookmarks()
                            if bookmarks:
                                sys.stderr.write("\r\nBookmarks:\r\n")
                                for i, bm in enumerate(bookmarks):
                                    sys.stderr.write(
                                        f"  {i + 1}. {bm['name']} - {bm['description']} "
                                        f"({self.controller._format_time(bm['time_offset'])})\r\n"
                                    )
                                sys.stderr.write("Select bookmark number: ")
                                sys.stderr.flush()
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        except Exception:
            pass

    def run(self) -> None:
        self._thread = threading.Thread(target=self._handle_keyboard, daemon=True)
        self._thread.start()
        try:
            self.controller.play()
        finally:
            self.controller.stop()
