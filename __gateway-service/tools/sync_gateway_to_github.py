#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
⚡ ULTRA-FAST 1-CLICK GATEWAY SYNC & PUSH TOOL
==============================================
Synchronizes the entire `__gateway-service` directory with GitHub staging repository
and pushes cleanly to BOTH branches: `genspark_ai_developer` and `main`.
Built by request of Eng. Zizo (Voice #108).

Usage:
    py tools/sync_gateway_to_github.py [--test] [--msg "commit message"]
"""

import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SRC_DIR = Path(__file__).resolve().parent.parent
STAGING_REPO = Path(r"C:\Users\pc\.gemini\antigravity-ide\brain\e99e9a00-4eb1-46f4-ab06-ae74ae78830a\scratch\staging_repo")
DST_DIR = STAGING_REPO / "__gateway-service"

IGNORE_DIRS = {"__pycache__", ".pytest_cache", ".ruff_cache", ".git"}
IGNORE_EXTS = {".pyc", ".lock"}


def run_git(cmd, check=True):
    res = subprocess.run(cmd, cwd=STAGING_REPO, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if check and res.returncode != 0:
        print(f"[-] Git command failed: {' '.join(cmd)}")
        if res.stderr:
            print(res.stderr)
        raise RuntimeError(f"Exit code {res.returncode}")
    return res


def sync_files():
    t0 = time.time()
    print(f"[*] Fast-mirroring {SRC_DIR} ➡️ {DST_DIR} ...")
    
    # 1. Remove deleted files
    if DST_DIR.exists():
        for dst_file in list(DST_DIR.rglob("*")):
            if dst_file.is_file():
                if any(p in dst_file.parts for p in IGNORE_DIRS) or dst_file.suffix in IGNORE_EXTS:
                    continue
                rel = dst_file.relative_to(DST_DIR)
                src_file = SRC_DIR / rel
                if not src_file.exists():
                    dst_file.unlink()
    
    # 2. Copy/update files
    count = 0
    for src_file in SRC_DIR.rglob("*"):
        if src_file.is_file():
            if any(p in src_file.parts for p in IGNORE_DIRS) or src_file.suffix in IGNORE_EXTS:
                continue
            rel = src_file.relative_to(SRC_DIR)
            dst_file = DST_DIR / rel
            dst_file.parent.mkdir(parents=True, exist_ok=True)
            if not dst_file.exists() or dst_file.stat().st_size != src_file.stat().st_size or dst_file.read_bytes() != src_file.read_bytes():
                shutil.copy2(src_file, dst_file)
                count += 1

    print(f"[+] Files synchronized in {time.time() - t0:.2f}s ({count} files updated).")


def main():
    parser = argparse.ArgumentParser(description="Ultra-Fast Gateway GitHub Sync")
    parser.add_argument("--test", action="store_true", help="Run pytest suite before pushing")
    parser.add_argument("--msg", default="feat(gateway): fast sync __gateway-service to github", help="Commit message")
    args = parser.parse_args()

    print("\n" + "=" * 60)
    print("🚀 ULTRA-FAST GATEWAY GITHUB SYNCHRONIZER (1-CLICK)")
    print("=" * 60)

    # 1. Mirror
    sync_files()

    # 2. Optional test
    if args.test:
        print("[*] Running hermetic pytest suite ...")
        t_test = time.time()
        res_test = subprocess.run(["py", "-3.13", "-m", "pytest", "tests/"], cwd=DST_DIR, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if res_test.returncode != 0:
            print("[-] Test suite failed! Aborting push.")
            print(res_test.stdout)
            sys.exit(1)
        print(f"[+] Tests verified green in {time.time() - t_test:.2f}s.")

    # 3. Commit & push on genspark_ai_developer
    print("[*] Pushing to [genspark_ai_developer] ...")
    run_git(["git", "checkout", "genspark_ai_developer"])
    run_git(["git", "add", "__gateway-service"])
    status = run_git(["git", "status", "-s"], check=False).stdout.strip()
    if status:
        run_git(["git", "commit", "-m", args.msg])
        run_git(["git", "push", "origin", "genspark_ai_developer"])
        print("[+] Successfully pushed to genspark_ai_developer!")
    else:
        print("[!] No changes to push on genspark_ai_developer.")

    # 4. Sync & push on main
    print("[*] Pushing to [main] ...")
    run_git(["git", "checkout", "main"])
    run_git(["git", "pull", "origin", "main"], check=False)
    run_git(["git", "checkout", "genspark_ai_developer", "--", "__gateway-service"])
    run_git(["git", "add", "__gateway-service"])
    status_main = run_git(["git", "status", "-s"], check=False).stdout.strip()
    if status_main:
        run_git(["git", "commit", "-m", args.msg])
        run_git(["git", "push", "origin", "main"])
        print("[+] Successfully pushed to main!")
    else:
        print("[!] No changes to push on main.")

    # 5. Return to default branch
    run_git(["git", "checkout", "genspark_ai_developer"])

    print("=" * 60)
    print("✅ COMPLETED! Both branches on GitHub are 100% updated in seconds!")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
