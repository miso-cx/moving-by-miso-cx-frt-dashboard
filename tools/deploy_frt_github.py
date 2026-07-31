# -*- coding: utf-8 -*-
"""
FRT 대시보드 → GitHub Pages (gh-pages 브랜치).

흐름: build(선택) → prepare → gh-pages 브랜치에 push

사전 준비:
  1. GitHub private 저장소 생성
  2. git init && git remote add origin https://github.com/USER/REPO.git
  3. main 브랜치 첫 push (선택, 소스 보관용)
  4. GitHub → Settings → Pages → Deploy from branch → gh-pages / root

사용:
  python tools/deploy_frt_github.py --build --deploy
  python tools/deploy_frt_github.py --deploy

환경변수:
  GITHUB_REMOTE  — remote 이름 (기본 origin)
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS_DIR = ROOT / "docs" / "frt"
PUBLISH = DOCS_DIR / "_publish"
WORKTREE = ROOT / ".deploy" / "gh-pages"
BUILDER = ROOT / "tools" / "build_frt_ops_dashboard.py"
PREPARE = ROOT / "tools" / "prepare_frt_publish.py"
KST = timezone(timedelta(hours=9))
BRANCH = "gh-pages"


def run(cmd: list[str], cwd: Path | None = None) -> str:
    proc = subprocess.run(
        cmd,
        cwd=str(cwd or ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"{' '.join(cmd)}\n{(proc.stderr or proc.stdout or '')[:2000]}"
        )
    return (proc.stdout or "").strip()


def ensure_git_repo() -> None:
    if not (ROOT / ".git").is_dir():
        raise RuntimeError(
            "git 저장소가 없습니다.\n"
            "  git init\n"
            "  git remote add origin https://github.com/USER/REPO.git"
        )
    remotes = run(["git", "remote"])
    if not remotes:
        raise RuntimeError(
            "git remote가 없습니다.\n"
            "  git remote add origin https://github.com/USER/REPO.git"
        )


def run_build() -> None:
    proc = subprocess.run(
        [sys.executable, str(BUILDER)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "build failed")[:2000])
    print(proc.stdout or "build ok")


def run_prepare() -> Path:
    proc = subprocess.run(
        [sys.executable, str(PREPARE)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "prepare failed")[:2000])
    print(proc.stdout.strip())
    return PUBLISH


def _clean_worktree_contents() -> None:
    for child in WORKTREE.iterdir():
        if child.name == ".git":
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def _copy_publish() -> None:
    for item in PUBLISH.iterdir():
        dest = WORKTREE / item.name
        if item.is_dir():
            shutil.copytree(item, dest, dirs_exist_ok=True)
        else:
            shutil.copy2(item, dest)


def deploy_gh_pages(remote: str) -> str:
    ensure_git_repo()

    # 기존 worktree 정리 (경로 표기 차이 \ vs / 를 고려해 항상 시도)
    try:
        run(["git", "worktree", "remove", "--force", str(WORKTREE)])
    except RuntimeError:
        pass
    run(["git", "worktree", "prune"])

    WORKTREE.parent.mkdir(parents=True, exist_ok=True)
    has_remote_branch = False
    try:
        heads = run(["git", "ls-remote", "--heads", remote, BRANCH])
        has_remote_branch = bool(heads.strip())
    except RuntimeError:
        has_remote_branch = False

    if has_remote_branch:
        run(["git", "fetch", remote, BRANCH])
        run(["git", "worktree", "add", "-B", BRANCH, str(WORKTREE), f"{remote}/{BRANCH}"])
    else:
        run(["git", "worktree", "add", "-B", BRANCH, str(WORKTREE)])

    _clean_worktree_contents()
    _copy_publish()

    msg = f"deploy {datetime.now(tz=KST).strftime('%Y-%m-%d %H:%M KST')}"
    run(["git", "add", "-A"], cwd=WORKTREE)
    status = run(["git", "status", "--porcelain"], cwd=WORKTREE)
    if not status:
        print("no changes to deploy")
    else:
        run(["git", "commit", "-m", msg], cwd=WORKTREE)
        run(["git", "push", remote, BRANCH], cwd=WORKTREE)

    # Pages URL 추정
    url_remote = run(["git", "remote", "get-url", remote])
    pages_url = _guess_pages_url(url_remote)
    return pages_url


def _guess_pages_url(remote_url: str) -> str:
    """https://github.com/user/repo → https://user.github.io/repo/"""
    url = remote_url.strip()
    for prefix in ("git@", "https://", "http://"):
        if url.startswith(prefix):
            break
    if url.startswith("git@"):
        # git@github.com:user/repo.git
        path = url.split(":", 1)[-1]
    else:
        path = url.split("github.com/", 1)[-1]
    path = path.removesuffix(".git").strip("/")
    if "/" not in path:
        return f"https://github.com/{path} (Pages URL은 Settings에서 확인)"
    user, repo = path.split("/", 1)
    return f"https://{user}.github.io/{repo}/"


def main() -> int:
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except (AttributeError, OSError):
            pass

    ap = argparse.ArgumentParser(description="FRT 대시보드 GitHub Pages 배포")
    ap.add_argument("--build", action="store_true", help="배포 전 DB에서 HTML 재생성")
    ap.add_argument("--deploy", action="store_true", help="gh-pages 브랜치 push")
    args = ap.parse_args()

    remote = os.environ.get("GITHUB_REMOTE", "origin")

    try:
        if args.build:
            print("building dashboard ...")
            run_build()
        run_prepare()
        if args.deploy:
            print(f"deploying to GitHub Pages ({remote}/{BRANCH}) ...")
            url = deploy_gh_pages(remote)
            status = {
                "last_deploy": datetime.now(tz=KST).isoformat(),
                "pages_url": url,
                "branch": BRANCH,
                "remote": remote,
            }
            (DOCS_DIR / "deploy_status.json").write_text(
                json.dumps(status, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print(f"\n팀 공유 URL (Pages 활성화 후): {url}")
            print("GitHub → Settings → Pages → gh-pages / root 확인")
        else:
            print("\n로컬 미리보기: docs/frt/_publish/index.html")
            print("배포: python tools/deploy_frt_github.py --deploy")
        return 0
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
