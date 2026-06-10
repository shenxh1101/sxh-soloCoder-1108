import os
import sys
import json
import signal
import threading
import time
from typing import Dict, List, Optional
from datetime import datetime

from .config import ServerConfig
from .recorder import SSHRecorder


class SessionInfo:
    def __init__(self, session_id: str, server: ServerConfig, recorder: SSHRecorder, thread: threading.Thread):
        self.session_id = session_id
        self.server = server
        self.recorder = recorder
        self.thread = thread
        self.started_at = time.time()
        self.log_file: Optional[str] = None


class ConcurrentSessionManager:
    def __init__(self, log_dir: str = "logs"):
        self.log_dir = log_dir
        self._sessions: Dict[str, SessionInfo] = {}
        self._lock = threading.Lock()
        self._shutdown = False

    def list_sessions(self) -> List[Dict]:
        with self._lock:
            result = []
            for sid, info in self._sessions.items():
                result.append({
                    "session_id": sid,
                    "host": info.server.host,
                    "user": info.server.user,
                    "port": info.server.port,
                    "started_at": datetime.fromtimestamp(info.started_at).strftime("%Y-%m-%d %H:%M:%S"),
                    "is_alive": info.thread.is_alive(),
                    "log_file": info.log_file or info.recorder.log_file,
                })
            return result

    def start_session(
        self,
        server: ServerConfig,
        session_id: Optional[str] = None,
    ) -> str:
        if session_id is None:
            session_id = datetime.now().strftime("%Y%m%d_%H%M%S") + f"_{server.user}@{server.host}"

        with self._lock:
            if session_id in self._sessions:
                raise ValueError(f"Session {session_id} already exists")

        recorder = SSHRecorder(server, log_dir=self.log_dir)

        def run_session():
            try:
                recorder.run()
            except Exception as e:
                sys.stderr.write(f"Session {session_id} error: {e}\n")

        thread = threading.Thread(target=run_session, daemon=True, name=f"ssh-{session_id}")

        info = SessionInfo(session_id, server, recorder, thread)
        with self._lock:
            self._sessions[session_id] = info

        thread.start()
        time.sleep(0.5)
        info.log_file = recorder.log_file

        return session_id

    def stop_session(self, session_id: str) -> bool:
        with self._lock:
            info = self._sessions.get(session_id)
            if not info:
                return False
            try:
                info.recorder.logger.end_session()
            except Exception:
                pass
        return True

    def add_bookmark(self, session_id: str, name: str, description: str = "") -> bool:
        with self._lock:
            info = self._sessions.get(session_id)
            if not info:
                return False
            try:
                info.recorder.add_bookmark(name, description)
                return True
            except Exception:
                return False

    def stop_all(self) -> None:
        with self._lock:
            self._shutdown = True
            for info in self._sessions.values():
                try:
                    info.recorder.logger.end_session()
                except Exception:
                    pass

    def cleanup_finished(self) -> int:
        removed = 0
        with self._lock:
            to_remove = [sid for sid, info in self._sessions.items() if not info.thread.is_alive()]
            for sid in to_remove:
                del self._sessions[sid]
                removed += 1
        return removed

    def save_status(self, status_file: str) -> None:
        status = {
            "updated_at": time.time(),
            "sessions": self.list_sessions(),
        }
        os.makedirs(os.path.dirname(os.path.abspath(status_file)) or ".", exist_ok=True)
        with open(status_file, "w", encoding="utf-8") as f:
            json.dump(status, f, indent=2, ensure_ascii=False)

    @staticmethod
    def load_status(status_file: str) -> Optional[Dict]:
        if not os.path.exists(status_file):
            return None
        try:
            with open(status_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None
