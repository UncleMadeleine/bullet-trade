"""
Live 实例互斥锁。

为实盘运行提供跨平台文件锁，避免重复启动与 runtime 目录并发写入。
"""

from __future__ import annotations

import json
import os
import socket
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from filelock import FileLock, Timeout


DEFAULT_CONFIG_DIR = ".bullet-trade"
DEFAULT_LOCK_DIR = "live-locks"


class LiveLockBusyError(RuntimeError):
    """Live 互斥锁冲突。"""


def _base_home() -> Path:
    override = os.environ.get("BULLET_TRADE_HOME")
    if override:
        return Path(override).expanduser()
    return Path.home()


def get_live_lock_dir() -> Path:
    return _base_home() / DEFAULT_CONFIG_DIR / DEFAULT_LOCK_DIR


def build_lock_metadata(**extra: Any) -> Dict[str, Any]:
    metadata = {
        "pid": os.getpid(),
        "host": socket.gethostname(),
        "started_at": datetime.now().isoformat(timespec="seconds"),
    }
    for key, value in extra.items():
        if value in (None, "", [], {}, ()):
            continue
        metadata[key] = value
    return metadata


def read_lock_metadata(path: Path) -> Dict[str, Any]:
    try:
        if not path.exists():
            return {}
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except Exception:
        return {}
    return {}


def _write_lock_metadata(path: Path, metadata: Dict[str, Any]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(metadata, handle, ensure_ascii=False, indent=2, sort_keys=True)
    os.replace(tmp, path)


class ManagedLiveLock:
    """持有跨平台文件锁与配套元数据。"""

    def __init__(
        self,
        *,
        lock_path: Path,
        metadata_path: Path,
        metadata: Dict[str, Any],
        busy_message: str,
    ) -> None:
        self.lock_path = lock_path
        self.metadata_path = metadata_path
        self.metadata = dict(metadata)
        self.busy_message = busy_message
        self._lock = FileLock(str(lock_path))
        self._acquired = False

    def acquire(self) -> None:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._lock.acquire(timeout=0)
        except Timeout as exc:
            existing = read_lock_metadata(self.metadata_path)
            raise LiveLockBusyError(self._format_busy_message(existing)) from exc
        try:
            _write_lock_metadata(self.metadata_path, self.metadata)
            self._acquired = True
        except Exception:
            try:
                self._lock.release()
            except Exception:
                pass
            raise

    def release(self) -> None:
        try:
            if self.metadata_path.exists():
                self.metadata_path.unlink()
        except Exception:
            pass
        try:
            if self._acquired:
                self._lock.release()
        except Exception:
            pass
        finally:
            self._acquired = False

    def _format_busy_message(self, existing: Dict[str, Any]) -> str:
        details = {
            "pid": existing.get("pid"),
            "host": existing.get("host"),
            "strategy_path": existing.get("strategy_path"),
            "runtime_dir": existing.get("runtime_dir"),
            "broker_type": existing.get("broker_type"),
            "account_identity": existing.get("account_identity"),
            "started_at": existing.get("started_at"),
        }
        suffix = ", ".join(f"{key}={value}" for key, value in details.items() if value not in (None, ""))
        if suffix:
            return f"{self.busy_message}: {suffix}"
        return self.busy_message
