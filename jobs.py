import fcntl
import json
import time
from config import JOBS_DIR


def write_job(job_id: str, **fields) -> dict:
    JOBS_DIR.mkdir(exist_ok=True)
    path = JOBS_DIR / f"{job_id}.json"
    data = json.loads(path.read_text()) if path.exists() else {"id": job_id}
    data.update(fields)
    path.write_text(json.dumps(data))
    return data


def read_job(job_id: str) -> dict | None:
    path = JOBS_DIR / f"{job_id}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def acquire_synthesis_lock():
    """Block until no other synthesis is running. Returns the lock file handle."""
    JOBS_DIR.mkdir(exist_ok=True)
    lock_file = open(JOBS_DIR / "synthesis.lock", "w")
    fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
    return lock_file


def release_synthesis_lock(lock_file) -> None:
    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
    lock_file.close()


def cleanup_old_jobs(max_age_secs: int = 86400) -> None:
    if not JOBS_DIR.exists():
        return
    now = time.time()
    for p in JOBS_DIR.glob("*.json"):
        try:
            if now - p.stat().st_mtime > max_age_secs:
                p.unlink(missing_ok=True)
        except Exception:
            pass
