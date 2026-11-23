"""Fronta úloh na pozadí pro GUI.

- úlohy běží postupně (výchozí 1 pracovní vlákno), protože sdílejí API limity a SKU registr,
- každá úloha má stav, průběh v %, zprávu, log a historii (data/jobs_history.json),
- výstup `print()` a `sys.stderr` z vlákna úlohy se zachytává do logu úlohy a zároveň
  se dál vypisuje do konzole (stávající kód tak funguje beze změny),
- log každé úlohy se ukládá do logs/jobs/<id>.log (jde stáhnout z GUI),
- zrušení je kooperativní: úloha se zastaví při nejbližším `check_cancel()`
  (viz src/progress.py), čekající úloha se zruší ihned.

Import modulu nemá vedlejší efekty; zachytávání výstupu se zapne až při vytvoření JobManageru.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
import traceback
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from . import progress

PROJECT_ROOT = Path(__file__).resolve().parent.parent
HISTORY_PATH = PROJECT_ROOT / "data" / "jobs_history.json"
LOG_DIR = PROJECT_ROOT / "logs" / "jobs"

MAX_LOG_LINES = 3000      # v paměti; úplný log je v souboru
MAX_HISTORY = 100

QUEUED, RUNNING, DONE, FAILED, CANCELLED = "queued", "running", "done", "failed", "cancelled"
ACTIVE_STATES = (QUEUED, RUNNING)
STATUS_LABELS = {
    QUEUED: "ve frontě",
    RUNNING: "běží",
    DONE: "hotovo",
    FAILED: "chyba",
    CANCELLED: "zrušeno",
}


def _fmt(ts: Optional[float]) -> str:
    return datetime.fromtimestamp(ts).strftime("%d.%m.%Y %H:%M:%S") if ts else ""


class Job:
    def __init__(self, job_id: str, name: str, log_dir: Path):
        self.id = job_id
        self.name = name
        self.status = QUEUED
        self.progress = 0.0
        self.message = ""
        self.error: Optional[str] = None
        self.result: Optional[Any] = None
        self.created = time.time()
        self.started: Optional[float] = None
        self.finished: Optional[float] = None
        self.cancel_event = threading.Event()
        self.log: List[str] = []
        self.log_total = 0
        self.log_path = log_dir / f"{job_id}.log"
        self._fh = None
        self._lock = threading.Lock()

    # -- log --------------------------------------------------------------
    def add_log(self, line: str) -> None:
        stamped = f"{datetime.now().strftime('%H:%M:%S')}  {line}"
        with self._lock:
            self.log.append(stamped)
            self.log_total += 1
            if len(self.log) > MAX_LOG_LINES:
                del self.log[: len(self.log) - MAX_LOG_LINES]
            try:
                if self._fh is None:
                    self.log_path.parent.mkdir(parents=True, exist_ok=True)
                    self._fh = open(self.log_path, "a", encoding="utf-8")
                self._fh.write(stamped + "\n")
                self._fh.flush()
            except OSError:
                pass

    def close_log(self) -> None:
        with self._lock:
            if self._fh is not None:
                try:
                    self._fh.close()
                except OSError:
                    pass
                self._fh = None

    # -- průběh -----------------------------------------------------------
    def set_progress(self, percent: Optional[float], message: Optional[str]) -> None:
        if percent is not None:
            try:
                self.progress = max(0.0, min(100.0, float(percent)))
            except (TypeError, ValueError):
                pass
        if message:
            self.message = str(message)

    # -- serializace ------------------------------------------------------
    def to_dict(self, with_log: bool = False, log_tail: int = 400) -> Dict[str, Any]:
        end = self.finished or time.time()
        duration = int(end - self.started) if self.started else 0
        data: Dict[str, Any] = {
            "id": self.id,
            "name": self.name,
            "status": self.status,
            "status_label": STATUS_LABELS.get(self.status, self.status),
            "active": self.status in ACTIVE_STATES,
            "progress": int(round(self.progress)),
            "message": self.message,
            "error": self.error,
            "result": self.result,
            "created": self.created,
            "created_str": _fmt(self.created),
            "started_str": _fmt(self.started),
            "finished_str": _fmt(self.finished),
            "duration": duration,
            "cancel_requested": self.cancel_event.is_set(),
        }
        if with_log:
            with self._lock:
                data["log"] = list(self.log[-log_tail:])
                data["log_truncated"] = self.log_total > len(data["log"])
        return data

    def to_history(self) -> Dict[str, Any]:
        d = self.to_dict()
        d["log_path"] = str(self.log_path)
        d["started"] = self.started
        d["finished"] = self.finished
        return d

    @classmethod
    def from_history(cls, d: Dict[str, Any], log_dir: Path) -> "Job":
        job = cls(str(d.get("id", "")), str(d.get("name", "")), log_dir)
        job.status = d.get("status", FAILED)
        job.progress = float(d.get("progress", 0) or 0)
        job.message = d.get("message") or ""
        job.error = d.get("error")
        job.result = d.get("result")
        job.created = float(d.get("created") or time.time())
        job.started = d.get("started")
        job.finished = d.get("finished")
        if d.get("log_path"):
            job.log_path = Path(d["log_path"])
        return job


# ---------------------------------------------------------------------------
# Zachytávání stdout/stderr podle vlákna
# ---------------------------------------------------------------------------
_sinks: Dict[int, Job] = {}
_sinks_lock = threading.Lock()


class _ThreadRouter:
    """Náhrada sys.stdout/sys.stderr: výstup vláken úloh jde do logu úlohy a zároveň do původního proudu."""

    def __init__(self, original):
        self._original = original
        self._buffers: Dict[int, str] = {}
        self._buf_lock = threading.Lock()

    def write(self, text):
        ident = threading.get_ident()
        with _sinks_lock:
            job = _sinks.get(ident)
        if job is not None and text:
            with self._buf_lock:
                buf = self._buffers.get(ident, "") + text
                *lines, rest = buf.split("\n")
                self._buffers[ident] = rest
            for line in lines:
                job.add_log(line.rstrip("\r"))
        if self._original is not None:
            try:
                return self._original.write(text)
            except (OSError, ValueError):
                return len(text)
        return len(text)

    def flush_thread(self, ident: int) -> None:
        with self._buf_lock:
            rest = self._buffers.pop(ident, "")
        if rest.strip():
            with _sinks_lock:
                job = _sinks.get(ident)
            if job is not None:
                job.add_log(rest.rstrip("\r"))

    def flush(self):
        if self._original is not None:
            try:
                self._original.flush()
            except (OSError, ValueError):
                pass

    def isatty(self):
        return False

    def __getattr__(self, name):
        return getattr(self._original, name)


_routers: Dict[str, _ThreadRouter] = {}


def install_capture() -> None:
    """Zajistí, že sys.stdout a sys.stderr jsou směrovače podle vlákna.

    Je idempotentní; volá se při každém spuštění úlohy, takže přežije i situaci, kdy někdo jiný
    (např. pytest) proudy mezitím vyměnil.
    """
    for stream_name in ("stdout", "stderr"):
        current = getattr(sys, stream_name)
        if isinstance(current, _ThreadRouter):
            _routers[stream_name] = current
        else:
            router = _ThreadRouter(current)
            setattr(sys, stream_name, router)
            _routers[stream_name] = router


def _flush_routers(ident: int) -> None:
    for router in list(_routers.values()):
        router.flush_thread(ident)


# ---------------------------------------------------------------------------
# Správce úloh
# ---------------------------------------------------------------------------
class JobManager:
    def __init__(self, max_workers: int = 1, history_path: Path = HISTORY_PATH, log_dir: Path = LOG_DIR):
        self._history_path = Path(history_path)
        self._log_dir = Path(log_dir)
        self._lock = threading.RLock()
        self._jobs: Dict[str, Job] = {}
        self._order: List[str] = []   # od nejstarší po nejnovější
        self._futures: Dict[str, Future] = {}
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="job")
        self._load_history()
        install_capture()

    # -- historie ---------------------------------------------------------
    def _load_history(self) -> None:
        try:
            items = json.loads(self._history_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if not isinstance(items, list):
            return
        for d in items:
            if not isinstance(d, dict) or not d.get("id"):
                continue
            job = Job.from_history(d, self._log_dir)
            if job.status in ACTIVE_STATES:  # zůstalo z předchozího běhu aplikace
                job.status = FAILED
                job.error = "Úloha byla přerušena ukončením aplikace."
            self._jobs[job.id] = job
            self._order.append(job.id)

    def _save_history(self) -> None:
        with self._lock:
            ids = self._order[-MAX_HISTORY:]
            payload = [self._jobs[i].to_history() for i in ids]
        try:
            self._history_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._history_path.with_name(self._history_path.name + ".tmp")
            tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
            tmp.replace(self._history_path)
        except OSError:
            pass

    def _save_history_with_status(self, job: Job, final_status: str) -> None:
        with self._lock:
            ids = self._order[-MAX_HISTORY:]
            payload = []
            for i in ids:
                j = self._jobs[i]
                d = j.to_history()
                if j.id == job.id:
                    d["status"] = final_status
                    d["status_label"] = STATUS_LABELS.get(final_status, final_status)
                    d["active"] = final_status in ACTIVE_STATES
                payload.append(d)
        try:
            self._history_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._history_path.with_name(self._history_path.name + ".tmp")
            tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
            tmp.replace(self._history_path)
        except OSError:
            pass
        finally:
            job.status = final_status

    # -- veřejné API ------------------------------------------------------
    def submit(self, name: str, func: Callable[..., Any], args: tuple = (),
               kwargs: Optional[dict] = None) -> Job:
        job_id = datetime.now().strftime("%y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:4]
        job = Job(job_id, name, self._log_dir)
        with self._lock:
            self._jobs[job_id] = job
            self._order.append(job_id)
            # Z paměti vyřaď nejstarší dokončené úlohy nad limit
            while len(self._order) > MAX_HISTORY:
                oldest = self._order[0]
                if self._jobs[oldest].status in ACTIVE_STATES:
                    break
                self._order.pop(0)
                self._jobs.pop(oldest, None)
                self._futures.pop(oldest, None)
            self._futures[job_id] = self._executor.submit(self._run, job, func, args, kwargs or {})
        self._save_history()
        return job

    def get(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)

    def list(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        with self._lock:
            ids = list(reversed(self._order))
            if limit:
                ids = ids[:limit]
            return [self._jobs[i].to_dict() for i in ids]

    def active_count(self) -> int:
        with self._lock:
            return sum(1 for j in self._jobs.values() if j.status in ACTIVE_STATES)

    def cancel(self, job_id: str) -> bool:
        """Zruší úlohu. Čekající ihned, běžící při nejbližším bezpečném bodě. Vrací False, pokud už skončila."""
        with self._lock:
            job = self._jobs.get(job_id)
            future = self._futures.get(job_id)
        if job is None or job.status not in ACTIVE_STATES:
            return False
        job.cancel_event.set()
        if future is not None and future.cancel():   # ještě nezačala
            self._finish(job, CANCELLED, message="Zrušeno před spuštěním.")
        else:
            job.add_log("Zrušení požadováno, úloha se zastaví při nejbližším kroku…")
        return True

    # -- běh úlohy --------------------------------------------------------
    def _finish(self, job: Job, status: str, error: Optional[str] = None, message: Optional[str] = None) -> None:
        job.finished = time.time()
        if error:
            job.error = error
        if message:
            job.message = message
        if status == DONE:
            job.progress = 100.0
        job.close_log()
        self._save_history_with_status(job, status)

    def _run(self, job: Job, func: Callable[..., Any], args: tuple, kwargs: dict) -> None:
        ident = threading.get_ident()
        if job.cancel_event.is_set():
            self._finish(job, CANCELLED, message="Zrušeno před spuštěním.")
            return
        install_capture()
        job.status = RUNNING
        job.started = time.time()
        with _sinks_lock:
            _sinks[ident] = job
        self._save_history()
        progress.bind(job.set_progress, job.cancel_event)
        status, error = DONE, None
        try:
            result = func(*args, **kwargs)
            if result is False:
                status, error = FAILED, "Úloha skončila neúspěchem (podrobnosti jsou v logu)."
            elif isinstance(result, (str, int, float)):
                job.result = result
        except progress.Cancelled:
            status = CANCELLED
            job.add_log("Úloha byla zrušena.")
        except Exception as exc:  # noqa: BLE001 - chybu ukážeme uživateli a zapíšeme do logu
            status, error = FAILED, f"{type(exc).__name__}: {exc}"
            job.add_log(traceback.format_exc())
        finally:
            progress.unbind()
            _flush_routers(ident)
            with _sinks_lock:
                _sinks.pop(ident, None)
        self._finish(job, status, error=error)


_manager: Optional[JobManager] = None
_manager_lock = threading.Lock()


def get_manager() -> JobManager:
    """Líně vytvořený singleton (import modulu nemá vedlejší efekty)."""
    global _manager
    with _manager_lock:
        if _manager is None:
            _manager = JobManager()
        return _manager
