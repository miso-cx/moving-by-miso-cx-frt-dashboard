# -*- coding: utf-8 -*-
"""
FRT ops 대시보드 시간별 갱신 (스케줄러용).

- 중복 실행 방지 (lock, 최대 15분)
- 결과를 docs/frt/refresh_status.json 에 기록

사용:
  python tools/refresh_frt_ops_dashboard.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS_DIR = ROOT / "docs" / "frt"
LOCK = DOCS_DIR / ".refresh.lock"
STATUS = DOCS_DIR / "refresh_status.json"
LOG = DOCS_DIR / "refresh.log"
BUILDER = ROOT / "tools" / "build_frt_ops_dashboard.py"
KST = timezone(timedelta(hours=9))
LOCK_MAX_SEC = 15 * 60


def log(msg: str) -> None:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    line = f"{datetime.now(tz=KST).isoformat()} {msg}\n"
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line)
    print(msg, flush=True)


def write_status(ok: bool, detail: str, skipped: bool = False) -> None:
    payload = {
        "last_run": datetime.now(tz=KST).isoformat(),
        "ok": ok,
        "skipped": skipped,
        "detail": detail,
        "interval_minutes": 30,
        "dashboard": str(DOCS_DIR / "ops_dashboard.html"),
    }
    STATUS.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def acquire_lock() -> bool:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    if LOCK.exists():
        age = time.time() - LOCK.stat().st_mtime
        if age < LOCK_MAX_SEC:
            return False
        log(f"stale lock removed (age={int(age)}s)")
    LOCK.write_text(str(os.getpid()), encoding="utf-8")
    return True


def release_lock() -> None:
    if LOCK.exists():
        LOCK.unlink(missing_ok=True)


def main() -> int:
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except (AttributeError, OSError):
            pass

    if not acquire_lock():
        msg = "skip: previous refresh still running or ran recently"
        log(msg)
        write_status(ok=True, detail=msg, skipped=True)
        return 0

    log("refresh start")
    try:
        proc = subprocess.run(
            [sys.executable, str(BUILDER)],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "unknown error")[:2000]
            log(f"refresh failed: {err}")
            write_status(ok=False, detail=err)
            return proc.returncode
        log("refresh ok")
        detail = "ops_dashboard.html rebuilt"
        if os.environ.get("FRT_AUTO_DEPLOY", "").strip().lower() in ("1", "true", "yes"):
            mode = os.environ.get("FRT_DEPLOY_TARGET", "github").strip().lower()
            deploy_script = (
                ROOT / "tools" / "deploy_frt_github.py"
                if mode == "github"
                else ROOT / "tools" / "deploy_frt_dashboard.py"
            )
            dep_args = [sys.executable, str(deploy_script), "--deploy"]
            if mode != "github":
                pass  # netlify deploy_frt_dashboard.py
            dep = subprocess.run(
                dep_args,
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            if dep.returncode != 0:
                err = (dep.stderr or dep.stdout or "deploy failed")[:2000]
                log(f"deploy failed: {err}")
                write_status(ok=False, detail=f"build ok; deploy failed: {err}")
                return dep.returncode
            log("deploy ok")
            detail = "ops_dashboard.html rebuilt + deployed"
        write_status(ok=True, detail=detail)
        return 0
    finally:
        release_lock()


if __name__ == "__main__":
    raise SystemExit(main())
