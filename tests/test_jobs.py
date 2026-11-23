"""Testy fronty úloh na pozadí (bez sítě)."""

import json
import threading
import time

from src import jobs, progress


def _manager(tmp_path, workers=1):
    return jobs.JobManager(max_workers=workers, history_path=tmp_path / "history.json", log_dir=tmp_path / "logs")


def _wait(job, timeout=5.0):
    end = time.time() + timeout
    while job.status in jobs.ACTIVE_STATES and time.time() < end:
        time.sleep(0.02)
    assert job.status not in jobs.ACTIVE_STATES, "úloha se nedokončila včas"
    return job


def test_progress_helpers_are_noops_outside_a_job():
    progress.report(10, "nic")
    progress.check_cancel()
    assert progress.is_cancelled() is False


def test_success_captures_output_and_progress(tmp_path):
    def work():
        progress.report(50, "půl cesty")
        print("ahoj z úlohy")
        return "výsledek"

    job = _wait(_manager(tmp_path).submit("test", work))
    assert job.status == jobs.DONE
    assert job.progress == 100
    assert job.message == "půl cesty"
    assert job.result == "výsledek"
    assert any("ahoj z úlohy" in line for line in job.log)
    log_file = tmp_path / "logs" / f"{job.id}.log"
    assert log_file.read_text(encoding="utf-8").count("ahoj z úlohy") == 1


def test_exception_marks_failed_and_logs_traceback(tmp_path):
    def boom():
        raise ValueError("kaboom")

    job = _wait(_manager(tmp_path).submit("test", boom))
    assert job.status == jobs.FAILED
    assert "ValueError: kaboom" in job.error
    assert any("Traceback" in line for line in job.log)


def test_false_result_is_a_failure(tmp_path):
    job = _wait(_manager(tmp_path).submit("test", lambda: False))
    assert job.status == jobs.FAILED
    assert job.error


def test_cancel_running_job(tmp_path):
    started = threading.Event()

    def loop():
        started.set()
        for _ in range(500):
            progress.check_cancel()
            time.sleep(0.01)

    manager = _manager(tmp_path)
    job = manager.submit("loop", loop)
    assert started.wait(2)
    assert manager.cancel(job.id) is True
    _wait(job)
    assert job.status == jobs.CANCELLED


def test_cancelled_is_not_swallowed_by_except_exception(tmp_path):
    def work():
        try:
            raise progress.Cancelled()
        except Exception:  # noqa: BLE001 - Cancelled nesmí být zachycen
            return "swallowed"

    job = _wait(_manager(tmp_path).submit("test", work))
    assert job.status == jobs.CANCELLED


def test_cancel_queued_job_never_runs(tmp_path):
    release = threading.Event()
    ran = []
    manager = _manager(tmp_path)
    first = manager.submit("první", lambda: release.wait(5))
    second = manager.submit("druhá", lambda: ran.append(1))

    deadline = time.time() + 2
    while first.status != jobs.RUNNING and time.time() < deadline:
        time.sleep(0.01)

    assert manager.cancel(second.id) is True
    assert second.status == jobs.CANCELLED
    release.set()
    _wait(first)
    time.sleep(0.1)
    assert ran == []


def test_cancel_finished_job_returns_false(tmp_path):
    manager = _manager(tmp_path)
    job = _wait(manager.submit("test", lambda: None))
    assert manager.cancel(job.id) is False
    assert manager.cancel("neexistuje") is False


def test_history_is_persisted_and_unfinished_jobs_marked_failed(tmp_path):
    manager = _manager(tmp_path)
    job = _wait(manager.submit("hotová", lambda: None))

    history_file = tmp_path / "history.json"
    data = json.loads(history_file.read_text(encoding="utf-8"))
    data.append({**data[0], "id": "zombie", "status": "running"})
    history_file.write_text(json.dumps(data), encoding="utf-8")

    restored = {j["id"]: j for j in _manager(tmp_path).list()}
    assert restored[job.id]["status"] == jobs.DONE
    assert restored["zombie"]["status"] == jobs.FAILED
    assert "přerušena" in restored["zombie"]["error"]
