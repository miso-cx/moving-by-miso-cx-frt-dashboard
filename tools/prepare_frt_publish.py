# -*- coding: utf-8 -*-
"""배포용 정적 폴더 준비: ops_dashboard.html → index.html + raw CSV."""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS_DIR = ROOT / "docs" / "frt"
SRC_HTML = DOCS_DIR / "ops_dashboard.html"
PUBLISH = DOCS_DIR / "_publish"


def prepare() -> Path:
    if not SRC_HTML.is_file():
        raise FileNotFoundError(f"대시보드 없음: {SRC_HTML} — 먼저 build_frt_ops_dashboard.py 실행")

    if PUBLISH.exists():
        shutil.rmtree(PUBLISH)
    PUBLISH.mkdir(parents=True)

    shutil.copy2(SRC_HTML, PUBLISH / "index.html")

    raw_src = DOCS_DIR / "daily" / "raw"
    if raw_src.is_dir():
        shutil.copytree(raw_src, PUBLISH / "daily" / "raw")

    return PUBLISH


def main() -> int:
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except (AttributeError, OSError):
            pass
    out = prepare()
    print(f"publish ready: {out}")
    print(f"  index.html ← {SRC_HTML.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
