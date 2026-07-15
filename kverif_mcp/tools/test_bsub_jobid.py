#!/usr/bin/env python3
"""测试 LSF bsub 是否能正常提交作业并获取 job ID。

用法：
    python test_bsub_jobid.py
    python test_bsub_jobid.py --bsub "bsub" --queue normal

验证：
    1. bsub -I 启动一个简单命令（echo + sleep）
    2. 解析 stderr 中的 Job <id>
    3. 用 bkill 清理
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time

# ---------------------------------------------------------------------------
# Job ID 解析
# ---------------------------------------------------------------------------

# LSF 典型输出: "Job <123456> is submitted to queue <normal>."
_JOB_RE = re.compile(r"Job\s+<(?P<job_id>\d+)>\s+is\s+submitted")
# 备选：bsub 某些版本可能只有数字
_JOB_ID_FALLBACK = re.compile(r"<(\d+)>")


def parse_lsf_job_id(text: str) -> str | None:
    """从 bsub 输出解析 job ID。"""
    m = _JOB_RE.search(text)
    if m:
        return m.group("job_id")
    m = _JOB_ID_FALLBACK.search(text)
    if m:
        return m.group(1)
    return None


# ---------------------------------------------------------------------------
# bsub 测试
# ---------------------------------------------------------------------------


def test_bsub(bsub_cmd: str, queue: str | None = None) -> dict:
    """启动一个 bsub -I 作业，检查是否能获取 job ID。

    返回结果 dict，包含 success、job_id、stdout、stderr、elapsed 等字段。
    """
    result = {
        "success": False,
        "bsub_cmd": bsub_cmd,
        "job_id": None,
        "stdout": "",
        "stderr": "",
        "exit_code": None,
        "elapsed_ms": 0,
        "error": None,
    }

    # 构建命令：bsub -I 启动一个短作业
    cmd = [bsub_cmd, "-I"]
    if queue:
        cmd.extend(["-q", queue])
    cmd.append("echo HELLO_FROM_BSUB && sleep 1")

    print(f"[*] 启动 bsub: {' '.join(cmd)}")
    started = time.time()

    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        result["elapsed_ms"] = int((time.time() - started) * 1000)
        result["error"] = "bsub timed out after 30s"
        return result
    except FileNotFoundError:
        result["elapsed_ms"] = int((time.time() - started) * 1000)
        result["error"] = f"bsub not found: {bsub_cmd}"
        return result

    result["elapsed_ms"] = int((time.time() - started) * 1000)
    result["exit_code"] = proc.returncode
    result["stdout"] = proc.stdout
    result["stderr"] = proc.stderr

    # 从 stderr 解析 job ID
    job_id = parse_lsf_job_id(proc.stderr)
    if job_id:
        result["success"] = True
        result["job_id"] = job_id
        return result

    # 如果 stderr 没有，试试 stdout
    job_id = parse_lsf_job_id(proc.stdout)
    if job_id:
        result["success"] = True
        result["job_id"] = job_id
        return result

    result["error"] = "Could not parse job ID from bsub output"
    return result


def test_bkill(bsub_cmd: str, job_id: str, bkill_cmd: str = "bkill") -> bool:
    """尝试 bkill 一个 job ID。"""
    print(f"\n[*] 清理 job: {bkill_cmd} {job_id}")
    try:
        proc = subprocess.run(
            [bkill_cmd, job_id],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10,
        )
        print(f"    stdout: {proc.stdout.strip()}")
        if proc.stderr.strip():
            print(f"    stderr: {proc.stderr.strip()}")
        return proc.returncode == 0
    except Exception as exc:
        print(f"    bkill failed: {exc}")
        return False


# ---------------------------------------------------------------------------
# bsub -J 命名作业测试
# ---------------------------------------------------------------------------


def test_bsub_j_name(bsub_cmd: str, job_name: str, queue: str | None = None) -> dict:
    """测试 bsub -J 命名作业，并用 bkill -J 清理。"""
    result = {
        "success": False,
        "job_name": job_name,
        "stdout": "",
        "stderr": "",
        "bkill_success": False,
        "error": None,
    }

    cmd = [bsub_cmd, "-I", "-J", job_name]
    if queue:
        cmd.extend(["-q", queue])
    cmd.append("echo HELLO_J_NAMED && sleep 1")

    print(f"\n[*] 启动命名作业: {' '.join(cmd)}")

    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        result["error"] = "timeout"
        return result
    except FileNotFoundError:
        result["error"] = f"bsub not found: {bsub_cmd}"
        return result

    result["stdout"] = proc.stdout
    result["stderr"] = proc.stderr

    job_id = parse_lsf_job_id(proc.stderr) or parse_lsf_job_id(proc.stdout)
    if job_id:
        result["success"] = True
        print(f"    job_id={job_id}")

    # 用 bkill -J 清理
    bkill_cmd = "bkill"
    try:
        proc2 = subprocess.run(
            [bkill_cmd, "-J", job_name],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10,
        )
        result["bkill_success"] = proc2.returncode == 0
        result["bkill_output"] = proc2.stdout.strip() + " " + proc2.stderr.strip()
    except Exception as exc:
        result["bkill_output"] = str(exc)

    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="Test LSF bsub job submission and job ID parsing")
    parser.add_argument("--bsub", default="bsub", help="bsub command (default: bsub)")
    parser.add_argument("--queue", "-q", help="LSF queue name")
    args = parser.parse_args()

    print("=" * 60)
    print("LSF bsub Job ID 测试")
    print("=" * 60)

    # --- Test 1: 基本 bsub -I ---
    print("\n--- Test 1: 基本 bsub -I ---")
    r = test_bsub(args.bsub, args.queue)
    print(f"  success:      {r['success']}")
    print(f"  job_id:       {r['job_id']}")
    print(f"  exit_code:    {r['exit_code']}")
    print(f"  elapsed_ms:   {r['elapsed_ms']}")
    print(f"  stdout tail:  {r['stdout'].strip()[-200:]}")
    print(f"  stderr tail:  {r['stderr'].strip()[-200:]}")
    if r["error"]:
        print(f"  error:        {r['error']}")

    if r["success"]:
        test_bkill(args.bsub, r["job_id"])

    # --- Test 2: bsub -J 命名 ---
    print("\n--- Test 2: bsub -J 命名 ---")
    r2 = test_bsub_j_name(args.bsub, "kdebug_test_job", args.queue)
    print(f"  success:      {r2['success']}")
    print(f"  bkill -J:     {r2['bkill_success']}")
    print(f"  stdout tail:  {r2['stdout'].strip()[-200:]}")
    print(f"  stderr tail:  {r2['stderr'].strip()[-200:]}")
    if r2["error"]:
        print(f"  error:        {r2['error']}")

    # --- Summary ---
    print("\n" + "=" * 60)
    all_ok = r["success"] and r2["success"] and r2["bkill_success"]
    if all_ok:
        print("所有测试通过 — bsub + bkill 正常工作")
    else:
        print("部分测试失败 — 见上方详情")
        if not r["success"]:
            print("  - 基本 bsub -I 失败或无法解析 job ID")
        if not r2["success"]:
            print("  - bsub -J 命名失败")
        if not r2["bkill_success"]:
            print("  - bkill -J 清理失败")
    print("=" * 60)

    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
