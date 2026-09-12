#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
sync_repo.py: 知识库自动 Git 暂存、提交与 GitHub 推送脚本
功能:
1. 检查技能仓库内是否有新知识、新解包策略或脚本改进
2. 自动格式化 Git Commit 信息
3. 安全推送到 GitHub 远端公开仓库
"""

import sys
import subprocess
import argparse
from pathlib import Path

def run_git(args, cwd):
    result = subprocess.run(["git"] + args, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return result.returncode, result.stdout.strip(), result.stderr.strip()

def main():
    parser = argparse.ArgumentParser(description="自动提交并同步经验知识库至 GitHub")
    parser.add_argument("--engine", default="", help="新增或修改的游戏引擎/格式名称")
    parser.add_argument("--note", default="", help="经验或策略修改备注")
    args = parser.parse_args()

    repo_dir = Path(__file__).resolve().parent.parent

    # 1. 检查是否有变动
    code, status_out, _ = run_git(["status", "--porcelain"], repo_dir)
    if not status_out:
        print("[*] No changes detected in the knowledge base. Repository is already clean.")
        return

    print(f"[*] Detected changes in repo:\n{status_out}")

    # 2. 构造 Commit 信息
    if args.engine:
        commit_msg = f"feat(recipe): add/update extractor for {args.engine}"
        if args.note:
            commit_msg += f" ({args.note})"
    elif args.note:
        commit_msg = f"update(knowledge): {args.note}"
    else:
        commit_msg = "feat(knowledge): update game extraction recipes and scripts"

    # 3. 暂存所有改动
    run_git(["add", "."], repo_dir)

    # 4. 执行 Commit
    code, commit_out, commit_err = run_git(["commit", "-m", commit_msg], repo_dir)
    if code != 0:
        print(f"[-] Git commit failed: {commit_err}")
        return
    print(f"[+] Committed: {commit_msg}")

    # 5. 检查远端并 Push
    code, remote_out, _ = run_git(["remote", "-v"], repo_dir)
    if "origin" in remote_out:
        print("[*] Pushing to GitHub remote origin...")
        # 尝试推送到当前分支
        code, branch_out, _ = run_git(["branch", "--show-current"], repo_dir)
        current_branch = branch_out or "master"
        code, push_out, push_err = run_git(["push", "origin", current_branch], repo_dir)
        if code == 0:
            print(f"[+] Successfully pushed updates to GitHub ({current_branch})!")
        else:
            print(f"[-] Git push failed (may need credentials or initial push): {push_err}")
    else:
        print("[!] Note: No remote origin configured yet. Local commit completed.")

if __name__ == "__main__":
    main()
