import os
import json
import time
import threading
from datetime import datetime, date
from typing import Optional, List, Dict, Any


class SessionLogEntry:
    __slots__ = ("timestamp", "delay", "stream", "data")

    def __init__(self, timestamp: float, delay: float, stream: str, data: bytes):
        self.timestamp = timestamp
        self.delay = delay
        self.stream = stream
        self.data = data

    def to_dict(self) -> Dict[str, Any]:
        return {
            "t": self.timestamp,
            "d": self.delay,
            "s": self.stream,
            "data": self.data.decode("utf-8", errors="replace"),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SessionLogEntry":
        return cls(
            timestamp=d["t"],
            delay=d["d"],
            stream=d["s"],
            data=d["data"].encode("utf-8", errors="replace"),
        )

    def to_line(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_line(cls, line: str) -> "SessionLogEntry":
        return cls.from_dict(json.loads(line.strip()))


class SessionMetadata:
    def __init__(
        self,
        session_id: str,
        host: str,
        user: str,
        port: int = 22,
        started_at: Optional[float] = None,
    ):
        self.session_id = session_id
        self.host = host
        self.user = user
        self.port = port
        self.started_at = started_at or time.time()
        self.ended_at: Optional[float] = None
        self.bookmarks: List[Dict[str, Any]] = []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "host": self.host,
            "user": self.user,
            "port": self.port,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "bookmarks": self.bookmarks,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SessionMetadata":
        meta = cls(
            session_id=d["session_id"],
            host=d["host"],
            user=d["user"],
            port=d.get("port", 22),
            started_at=d.get("started_at"),
        )
        meta.ended_at = d.get("ended_at")
        meta.bookmarks = d.get("bookmarks", [])
        return meta


class SessionLogger:
    def __init__(
        self,
        log_dir: str = "logs",
        rotate_daily: bool = True,
    ):
        self.log_dir = os.path.abspath(log_dir)
        self.rotate_daily = rotate_daily
        os.makedirs(self.log_dir, exist_ok=True)

        self._lock = threading.Lock()
        self._start_time: Optional[float] = None
        self._last_write_time: Optional[float] = None
        self._current_date: Optional[date] = None
        self._metadata: Optional[SessionMetadata] = None
        self._log_file: Optional[str] = None
        self._meta_file: Optional[str] = None
        self._fp = None

    def start_session(
        self,
        host: str,
        user: str,
        port: int = 22,
        session_id: Optional[str] = None,
    ) -> str:
        self._start_time = time.time()
        self._last_write_time = self._start_time
        self._current_date = date.today()

        if session_id is None:
            session_id = datetime.fromtimestamp(self._start_time).strftime(
                "%Y%m%d_%H%M%S"
            ) + f"_{user}@{host}"

        self._metadata = SessionMetadata(
            session_id=session_id,
            host=host,
            user=user,
            port=port,
            started_at=self._start_time,
        )

        self._log_file = self._build_log_path(session_id)
        self._meta_file = self._log_file + ".meta.json"
        self._fp = open(self._log_file, "a", encoding="utf-8", buffering=1)
        self._save_metadata()
        return self._log_file

    def _build_log_path(self, session_id: str) -> str:
        date_str = self._current_date.strftime("%Y-%m-%d") if self._current_date else "unknown"
        date_dir = os.path.join(self.log_dir, date_str)
        os.makedirs(date_dir, exist_ok=True)
        safe_id = session_id.replace("/", "_").replace("\\", "_")
        return os.path.join(date_dir, f"session-{safe_id}.log")

    def _check_rotate(self) -> None:
        if not self.rotate_daily:
            return
        today = date.today()
        if today != self._current_date:
            self._current_date = today
            if self._fp is not None:
                self._fp.close()
            self._log_file = self._build_log_path(self._metadata.session_id)
            self._meta_file = self._log_file + ".meta.json"
            self._fp = open(self._log_file, "a", encoding="utf-8", buffering=1)
            self._save_metadata()

    def write(self, stream: str, data: bytes) -> None:
        if self._fp is None:
            raise RuntimeError("Session not started")
        with self._lock:
            self._check_rotate()
            now = time.time()
            delay = now - (self._last_write_time or self._start_time)
            entry = SessionLogEntry(
                timestamp=now,
                delay=max(0.0, delay),
                stream=stream,
                data=data,
            )
            self._fp.write(entry.to_line() + "\n")
            self._last_write_time = now

    def write_output(self, data: bytes) -> None:
        self.write("o", data)

    def write_input(self, data: bytes) -> None:
        self.write("i", data)

    def add_bookmark(self, name: str, description: str = "") -> None:
        if self._metadata is None:
            return
        bookmark = {
            "name": name,
            "description": description,
            "timestamp": time.time(),
            "offset": self._fp.tell() if self._fp else 0,
        }
        self._metadata.bookmarks.append(bookmark)
        self._save_metadata()

    def _save_metadata(self) -> None:
        if self._meta_file and self._metadata:
            with open(self._meta_file, "w", encoding="utf-8") as mf:
                json.dump(self._metadata.to_dict(), mf, indent=2, ensure_ascii=False)

    def end_session(self) -> None:
        if self._metadata is not None:
            self._metadata.ended_at = time.time()
            self._save_metadata()
        if self._fp is not None:
            self._fp.close()
            self._fp = None

    @property
    def current_log_file(self) -> Optional[str]:
        return self._log_file


class SessionReader:
    def __init__(self, log_file: str):
        self.log_file = os.path.abspath(log_file)
        self.meta_file = self.log_file + ".meta.json"
        self.metadata: Optional[SessionMetadata] = None
        self._load_metadata()

    def _load_metadata(self) -> None:
        if os.path.exists(self.meta_file):
            with open(self.meta_file, "r", encoding="utf-8") as f:
                self.metadata = SessionMetadata.from_dict(json.load(f))

    def iter_entries(self):
        with open(self.log_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield SessionLogEntry.from_line(line)
                except (json.JSONDecodeError, KeyError):
                    continue

    def get_all_entries(self) -> List[SessionLogEntry]:
        return list(self.iter_entries())

    def get_output_text(self) -> str:
        parts = []
        for entry in self.iter_entries():
            if entry.stream == "o":
                parts.append(entry.data.decode("utf-8", errors="replace"))
        return "".join(parts)

    def get_bookmarks(self) -> List[Dict[str, Any]]:
        if self.metadata:
            return self.metadata.bookmarks
        return []

    @staticmethod
    def find_logs(log_dir: str = "logs") -> List[str]:
        results = []
        for root, _, files in os.walk(log_dir):
            for name in files:
                if name.startswith("session-") and name.endswith(".log"):
                    results.append(os.path.join(root, name))
        results.sort(reverse=True)
        return results
