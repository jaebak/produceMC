#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import re
import sys
import tarfile
import threading
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional, Tuple


ROOT_JOB_RE = re.compile(r"^(?P<prefix>.+)__job_(?P<job>\d+)\.root$")
ERROR_PATTERNS = [
    re.compile(r"\bFatal Exception\b", re.IGNORECASE),
    re.compile(r"\bBegin Fatal Exception\b", re.IGNORECASE),
    re.compile(r"\b----- Begin Fatal Exception\b", re.IGNORECASE),
    re.compile(r"\bAn exception of category\b", re.IGNORECASE),
    re.compile(r"\bSegmentation fault\b", re.IGNORECASE),
    re.compile(r"\bSIGSEGV\b", re.IGNORECASE),
    # re.compile(r"\bAborted\b", re.IGNORECASE),
    re.compile(r"\bstack trace\b", re.IGNORECASE),
    re.compile(r"\bTraceback \(most recent call last\)\b", re.IGNORECASE),
]


def find_root_files(input_folder: Path, verbose: bool = True) -> Dict[Path, str]:
    """Top-level scan first; if none found, recurse. Prints progress while searching."""
    root_files: Dict[Path, str] = {}

    if verbose:
        print(f"[INFO] Searching for ROOT files in: {input_folder}", flush=True)
        print("[INFO] First: scanning top-level...", flush=True)

    for p in input_folder.iterdir():
        if p.is_file():
            m = ROOT_JOB_RE.match(p.name)
            if m:
                job = m.group("job")
                root_files[p] = job
                if verbose:
                    print(f"[FOUND] {p} (job {job})", flush=True)

    if root_files:
        if verbose:
            print(f"[INFO] Found {len(root_files)} ROOT file(s) in top-level.", flush=True)
        return root_files

    if verbose:
        print("[INFO] No top-level ROOT files found. Recursing into subdirectories...", flush=True)

    scanned = 0
    for p in input_folder.rglob("*.root"):
        scanned += 1
        if verbose and scanned % 2000 == 0:
            print(f"[INFO] ...scanned {scanned} *.root paths so far", flush=True)

        if not p.is_file():
            continue
        m = ROOT_JOB_RE.match(p.name)
        if m:
            job = m.group("job")
            root_files[p] = job
            if verbose:
                print(f"[FOUND] {p} (job {job})", flush=True)

    if verbose:
        print(f"[INFO] Done searching. Total ROOT files found: {len(root_files)}", flush=True)

    return root_files


def read_member_text_from_tar_gz(tar_path: Path, member_name: str) -> Optional[str]:
    if not tar_path.exists():
        return None
    try:
        with tarfile.open(tar_path, mode="r:gz") as tf:
            names = tf.getnames()

            member = None
            if member_name in names:
                member = tf.getmember(member_name)
            else:
                for n in names:
                    if n.endswith("/" + member_name) or n.endswith(member_name):
                        member = tf.getmember(n)
                        break

            if member is None:
                return None

            f = tf.extractfile(member)
            if f is None:
                return None

            return f.read().decode("utf-8", errors="replace")
    except (tarfile.TarError, OSError):
        return None


def extract_error_snippets(log_text: str, context_lines: int = 10) -> List[str]:
    lines = log_text.splitlines()
    hit_indices: List[int] = []

    for i, line in enumerate(lines):
        for pat in ERROR_PATTERNS:
            if pat.search(line):
                hit_indices.append(i)
                break

    if not hit_indices:
        return []

    snippets: List[str] = []
    used = set()
    for idx in hit_indices:
        if idx in used:
            continue
        used.add(idx)
        start = max(0, idx - context_lines)
        end = min(len(lines), idx + context_lines + 1)
        snippets.append("\n".join(lines[start:end]).rstrip())

    return snippets


def check_one_root(
    root_path_str: str,
    job_str: str,
    global_log_folder_str: Optional[str],
    context_lines: int,
) -> Tuple[str, str, bool, str, List[str]]:
    """
    Returns:
      (root_path, job, is_good, status_message, error_snippets)
    """
    root_path = Path(root_path_str)
    job = job_str

    if global_log_folder_str:
        log_folder = Path(global_log_folder_str)
    else:
        log_folder = root_path.parent / "log"

    tar_path = log_folder / f"cmsRun_{job}.log.tar.gz"
    stdout_member = f"cmsRun-stdout-{job}.log"

    log_text = read_member_text_from_tar_gz(tar_path, stdout_member)
    if log_text is None:
        msg_parts = []
        if not log_folder.exists():
            msg_parts.append(f"log folder missing: {log_folder}")
        elif not tar_path.exists():
            msg_parts.append(f"archive missing: {tar_path.name}")
        else:
            msg_parts.append(f"missing member: {stdout_member}")
        msg = "; ".join(msg_parts) if msg_parts else "missing or unreadable log"
        return (str(root_path), job, False, msg, [])

    snippets = extract_error_snippets(log_text, context_lines=context_lines)
    if snippets:
        return (str(root_path), job, False, "found error(s)", snippets)

    return (str(root_path), job, True, "ok", [])


def job_sort_key(job: str) -> int:
    try:
        return int(job)
    except ValueError:
        return 10**18


def format_error_report(root_path: str, job: str, status: str, snippets: List[str]) -> str:
    """Build a readable block for the errors output file."""
    lines: List[str] = []
    lines.append("=" * 80)
    lines.append(f"JOB: {job}")
    lines.append(f"ROOT: {root_path}")
    lines.append(f"STATUS: {status}")
    lines.append("-" * 80)
    if snippets:
        for i, snip in enumerate(snippets, 1):
            lines.append(f"[SNIPPET {i}]")
            lines.append(snip.rstrip())
            lines.append("-" * 80)
    else:
        lines.append("(no snippets extracted; see STATUS for reason)")
    lines.append("")  # trailing newline between blocks
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Check cmsRun logs to decide which ROOT files are good (parallel, streaming prints)."
    )
    ap.add_argument("input_folder", help="Folder containing ROOT files or subdirectories")
    ap.add_argument(
        "--log-folder",
        default=None,
        help="If provided, use this log folder for ALL jobs (overrides per-file <root_parent>/log).",
    )
    ap.add_argument(
        "--output-good",
        default="good_root_files.txt",
        help="Output text file listing GOOD ROOT file paths (default: good_root_files.txt)",
    )
    ap.add_argument(
        "--output-bad",
        default="bad_root_files.txt",
        help="Output text file listing BAD ROOT file paths (default: bad_root_files.txt)",
    )
    ap.add_argument(
        "--output-errors",
        default="bad_root_files_errors.txt",
        help="Output text file containing error reports/snippets for BAD jobs (default: bad_root_files_errors.txt)",
    )
    ap.add_argument(
        "--workers",
        type=int,
        default=max(1, (os.cpu_count() or 1)),
        help="Number of parallel worker processes (default: CPU count).",
    )
    ap.add_argument(
        "--context-lines",
        type=int,
        default=10,
        help="Context lines to print around an error match (default: 10).",
    )
    ap.add_argument(
        "--quiet-find",
        action="store_true",
        help="Do not print per-file discovery while finding ROOT files.",
    )
    args = ap.parse_args()

    input_folder = Path(args.input_folder).expanduser().resolve()
    if not input_folder.is_dir():
        print(f"ERROR: INPUT_FOLDER is not a directory: {input_folder}", file=sys.stderr)
        return 2

    out_good = Path(args.output_good).expanduser().resolve()
    out_bad = Path(args.output_bad).expanduser().resolve()
    out_err = Path(args.output_errors).expanduser().resolve()

    if out_good.exists() or out_bad.exists() or out_err.exists():
        if out_good.exists():
            print(f"[INFO] Output GOOD file already exists: {out_good}")
        if out_bad.exists():
            print(f"[INFO] Output BAD file already exists: {out_bad}")
        if out_err.exists():
            print(f"[INFO] Output ERRORS file already exists: {out_err}")
        print("[INFO] Exiting without doing any work.")
        return 0

    root_files = find_root_files(input_folder, verbose=not args.quiet_find)
    if not root_files:
        print(f"No ROOT files matching '*__job_XX.root' found in: {input_folder}", file=sys.stderr)
        return 1

    items = sorted(root_files.items(), key=lambda kv: job_sort_key(kv[1]))
    workers = max(1, args.workers)

    print_lock = threading.Lock()
    good_files: List[str] = []
    bad_files: List[str] = []
    bad_error_reports: List[Tuple[str, str, str, List[str]]] = []  # (root_path, job, status, snippets)

    def safe_print(*a, **k):
        with print_lock:
            print(*a, **k, flush=True)

    safe_print(f"[INFO] Starting log checks with {workers} worker(s)...")

    with ProcessPoolExecutor(max_workers=workers) as ex:
        futures = [
            ex.submit(check_one_root, str(root_path), job, args.log_folder, args.context_lines)
            for (root_path, job) in items
        ]

        for fut in as_completed(futures):
            root_path, job, is_good, status, snippets = fut.result()

            if is_good:
                good_files.append(root_path)
                safe_print(f"[GOOD] job {job}: {root_path}")
            else:
                bad_files.append(root_path)
                bad_error_reports.append((root_path, job, status, snippets))

                if snippets:
                    safe_print(f"[BAD ] job {job}: {Path(root_path).name} -> {status}:")
                    for k, snip in enumerate(snippets, 1):
                        safe_print(f"--- error snippet {k} (job {job}) ---")
                        safe_print(snip)
                        safe_print("--- end snippet ---\n")
                else:
                    safe_print(f"[BAD ] job {job}: {Path(root_path).name} -> {status}")

    # Sort outputs by job id (best effort)
    job_by_path = {str(p): j for p, j in root_files.items()}
    good_sorted = sorted(good_files, key=lambda p: job_sort_key(job_by_path.get(p, "999999999")))
    bad_sorted = sorted(bad_files, key=lambda p: job_sort_key(job_by_path.get(p, "999999999")))
    bad_reports_sorted = sorted(
        bad_error_reports, key=lambda t: job_sort_key(t[1])
    )  # sort by job

    # Write output files
    try:
        with out_good.open("w", encoding="utf-8") as f:
            for p in good_sorted:
                f.write(p + "\n")
        with out_bad.open("w", encoding="utf-8") as f:
            for p in bad_sorted:
                f.write(p + "\n")

        # Errors file
        with out_err.open("w", encoding="utf-8") as f:
            for root_path, job, status, snippets in bad_reports_sorted:
                f.write(format_error_report(root_path, job, status, snippets))
    except OSError as e:
        print(f"ERROR: Could not write output file(s): {e}", file=sys.stderr)
        return 3

    print("\n=== Summary ===")
    print(f"Input folder: {input_folder}")
    print(f"Root files found: {len(root_files)}")
    print(f"Workers used: {workers}")
    print(f"Good files: {len(good_sorted)} -> {out_good}")
    print(f"Bad files:  {len(bad_sorted)} -> {out_bad}")
    print(f"Errors file: {out_err}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

