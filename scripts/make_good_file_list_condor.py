#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import re
import sys
import threading
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# ROOT files: FILENAME__job-XXX.root
ROOT_JOB_RE = re.compile(r"^(?P<prefix>.+)__job-(?P<job>\d+)\.root$")

ERROR_PATTERNS = [
    re.compile(r"\bFatal Exception\b", re.IGNORECASE),
    re.compile(r"\bBegin Fatal Exception\b", re.IGNORECASE),
    re.compile(r"\b----- Begin Fatal Exception\b", re.IGNORECASE),
    re.compile(r"\bAn exception of category\b", re.IGNORECASE),
    re.compile(r"\bSegmentation fault\b", re.IGNORECASE),
    re.compile(r"\bSIGSEGV\b", re.IGNORECASE),
    re.compile(r"\bstack trace\b", re.IGNORECASE),
    re.compile(r"\bTraceback \(most recent call last\)\b", re.IGNORECASE),
]


def find_root_files(ntuples_dir: Path, verbose: bool = True) -> Dict[Path, str]:
    """Top-level scan first; if none found, recurse. Returns {path: job_str}."""
    root_files: Dict[Path, str] = {}

    if verbose:
        print(f"[INFO] Searching for ROOT files in: {ntuples_dir}", flush=True)
        print("[INFO] First: scanning top-level...", flush=True)

    for p in ntuples_dir.iterdir():
        if not p.is_file():
            continue
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
    for p in ntuples_dir.rglob("*.root"):
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


def read_text_file(path: Path) -> Optional[str]:
    if not path.exists():
        return None
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
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


def job_sort_key(job: str) -> int:
    try:
        return int(job)
    except ValueError:
        return 10**18


def format_error_report(root_path: str, job: str, status: str, snippets: List[str]) -> str:
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
    lines.append("")
    return "\n".join(lines)


def compute_zzz(job_str: str, offset: int, minus_one: bool) -> Tuple[Optional[int], str]:
    """
    Compute ZZZ from XXX (parsed from FILENAME__job-XXX.root).

      If minus_one=True (default):  ZZZ = XXX - offset - 1
      If minus_one=False:           ZZZ = XXX - offset

    IMPORTANT: ZZZ in log filenames is NOT zero-padded.
      e.g. log_produce_mc_<condor_id>.0.err  (NOT .0000.err)

    Returns (zzz_int_or_None, zzz_str).
    """
    try:
        xxx = int(job_str)
    except ValueError:
        return None, job_str

    zzz = xxx - offset - (1 if minus_one else 0)
    return zzz, str(zzz)


def check_one_root(
    root_path_str: str,
    job_str: str,
    logs_dir_str: str,
    condor_id: str,
    offset: int,
    minus_one: bool,
    context_lines: int,
) -> Tuple[str, str, bool, str, List[str]]:
    """
    ROOT: ntuples/.../FILENAME__job-XXX.root
    LOGS: <logs-dir>/log_produce_mc_<condor_id>.<ZZZ>.{out,err}
          where ZZZ is computed by compute_zzz(...)

    Returns: (root_path, job, is_good, status_message, error_snippets)
    """
    root_path = Path(root_path_str)
    logs_dir = Path(logs_dir_str)

    zzz_int, zzz_str = compute_zzz(job_str, offset=offset, minus_one=minus_one)
    if zzz_int is None:
        return (str(root_path), job_str, False, "job id is not an integer", [])
    if zzz_int < 0:
        # Normally filtered out earlier, but keep safe.
        return (
            str(root_path),
            job_str,
            False,
            f"computed ZZZ is negative (XXX={job_str}, offset={offset}, minus_one={minus_one} => ZZZ={zzz_str})",
            [],
        )

    base = f"log_produce_mc_{condor_id}.{zzz_str}"
    out_path = logs_dir / f"{base}.out"
    err_path = logs_dir / f"{base}.err"

    out_text = read_text_file(out_path)
    err_text = read_text_file(err_path)

    missing = []
    if out_text is None:
        missing.append(out_path.name)
    if err_text is None:
        missing.append(err_path.name)

    if missing:
        if not logs_dir.exists():
            return (str(root_path), job_str, False, f"logs dir missing: {logs_dir}", [])
        return (str(root_path), job_str, False, "missing log(s): " + ", ".join(missing), [])

    snippets: List[str] = []

    out_snips = extract_error_snippets(out_text or "", context_lines=context_lines)
    if out_snips:
        snippets.extend([f"[{out_path.name}]\n{snip}" for snip in out_snips])

    err_snips = extract_error_snippets(err_text or "", context_lines=context_lines)
    if err_snips:
        snippets.extend([f"[{err_path.name}]\n{snip}" for snip in err_snips])

    if snippets:
        return (str(root_path), job_str, False, "found error(s)", snippets)

    return (str(root_path), job_str, True, "ok", [])


def main() -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Check produce_mc logs (log_produce_mc_<condor_id>.<ZZZ>.{out,err}) to decide which ROOT files are good.\n"
            "ROOT files: ntuples-dir/**/FILENAME__job-XXX.root.\n"
            "Default mapping: ZZZ = XXX - offset - 1 (use --no-minus-one to use ZZZ = XXX - offset).\n"
            "If offset>0: ROOT files below the offset are ignored (not checked).\n"
            "ZZZ in log filenames is NOT zero-padded (e.g. .0.err)."
        )
    )
    ap.add_argument("ntuples_dir", help="Directory containing ROOT ntuples (searched top-level first, then recursively).")
    ap.add_argument("condor_id", help="condor_id used in log_produce_mc_<condor_id>.<ZZZ>.(out|err)")

    ap.add_argument(
        "--logs-dir",
        default="logs",
        help="Directory containing logs. If a relative path, it is interpreted relative to ntuples-dir (default: logs).",
    )
    ap.add_argument(
        "--offset",
        type=int,
        default=0,
        help="Offset used in mapping (default: 0). See --no-minus-one for exact formula.",
    )
    ap.add_argument(
        "--no-minus-one",
        action="store_true",
        help="Use ZZZ = XXX - offset (instead of default ZZZ = XXX - offset - 1).",
    )
    ap.add_argument(
        "--n-jobs",
        type=int,
        default=None,
        help=(
            "If set, ignore ROOT files whose computed ZZZ is >= n_jobs "
            "(i.e., only consider ZZZ in [0, n_jobs-1])."
        ),
    )

    ap.add_argument("--output-good", default="good_root_files.txt")
    ap.add_argument("--output-bad", default="bad_root_files.txt")
    ap.add_argument("--output-errors", default="bad_root_files_errors.txt")
    ap.add_argument(
        "--force",
        action="store_true",
        help="Overwrite output files if they already exist (default: exit if any output exists).",
    )

    ap.add_argument(
        "--workers",
        type=int,
        default=max(1, (os.cpu_count() or 1)),
        help="Number of parallel worker processes (default: CPU count).",
    )
    ap.add_argument("--context-lines", type=int, default=10)
    ap.add_argument("--quiet-find", action="store_true")
    args = ap.parse_args()

    ntuples_dir = Path(args.ntuples_dir).expanduser().resolve()
    if not ntuples_dir.is_dir():
        print(f"ERROR: ntuples-dir is not a directory: {ntuples_dir}", file=sys.stderr)
        return 2

    # Make logs-dir follow ntuples-dir:
    # - If --logs-dir is absolute, use it as-is.
    # - If relative (including default "logs"), interpret it relative to ntuples_dir.
    logs_dir = Path(args.logs_dir).expanduser()
    if not logs_dir.is_absolute():
        logs_dir = ntuples_dir / logs_dir
    logs_dir = logs_dir.resolve()

    condor_id = str(args.condor_id)

    if args.n_jobs is not None and args.n_jobs < 0:
        print("ERROR: --n-jobs must be >= 0", file=sys.stderr)
        return 2

    minus_one = not args.no_minus_one

    out_good = Path(args.output_good).expanduser().resolve()
    out_bad = Path(args.output_bad).expanduser().resolve()
    out_err = Path(args.output_errors).expanduser().resolve()

    if (out_good.exists() or out_bad.exists() or out_err.exists()) and not args.force:
        if out_good.exists():
            print(f"[INFO] Output GOOD file already exists: {out_good}")
        if out_bad.exists():
            print(f"[INFO] Output BAD file already exists: {out_bad}")
        if out_err.exists():
            print(f"[INFO] Output ERRORS file already exists: {out_err}")
        print("[INFO] Exiting without doing any work. Use --force to overwrite.")
        return 0

    root_files = find_root_files(ntuples_dir, verbose=not args.quiet_find)
    if not root_files:
        print(f"No ROOT files matching '*__job-XXX.root' found in: {ntuples_dir}", file=sys.stderr)
        return 1

    # Filtering
    skipped_by_offset: List[Path] = []
    skipped_by_njobs: List[Path] = []
    skipped_by_negative_zzz: List[Path] = []

    # "below offset" rule:
    # - with minus_one=True (default): skip XXX <= offset  (so first checked is XXX=offset+1 -> ZZZ=0)
    # - with minus_one=False:          skip XXX <  offset  (so first checked is XXX=offset   -> ZZZ=0)
    def is_below_offset(xxx: int) -> bool:
        if args.offset <= 0:
            return False
        return (xxx <= args.offset) if minus_one else (xxx < args.offset)

    filtered: Dict[Path, str] = {}
    for p, job in root_files.items():
        # Apply "below offset" skip based on XXX if integer
        try:
            xxx = int(job)
            if is_below_offset(xxx):
                skipped_by_offset.append(p)
                continue
        except ValueError:
            # keep non-integer jobs; they will be marked bad later
            pass

        zzz_int, _zzz_str = compute_zzz(job, offset=args.offset, minus_one=minus_one)
        if zzz_int is None:
            filtered[p] = job
            continue

        if zzz_int < 0:
            skipped_by_negative_zzz.append(p)
            continue

        if args.n_jobs is not None and zzz_int >= args.n_jobs:
            skipped_by_njobs.append(p)
            continue

        filtered[p] = job

    root_files = filtered

    if not root_files:
        print("[INFO] After applying filters, there are no ROOT files left to check.")
        if skipped_by_offset:
            print(f"[INFO] Skipped by offset rule: {len(skipped_by_offset)}")
        if skipped_by_negative_zzz:
            print(f"[INFO] Skipped due to negative ZZZ: {len(skipped_by_negative_zzz)}")
        if skipped_by_njobs:
            print(f"[INFO] Skipped by n_jobs cap: {len(skipped_by_njobs)}")
        return 0

    items = sorted(root_files.items(), key=lambda kv: job_sort_key(kv[1]))
    workers = max(1, args.workers)

    print_lock = threading.Lock()
    good_files: List[str] = []
    bad_files: List[str] = []
    bad_error_reports: List[Tuple[str, str, str, List[str]]] = []

    def safe_print(*a, **k):
        with print_lock:
            print(*a, **k, flush=True)

    formula = "ZZZ = XXX - offset - 1" if minus_one else "ZZZ = XXX - offset"
    safe_print(f"[INFO] Using ntuples-dir: {ntuples_dir}")
    safe_print(f"[INFO] Using logs-dir:   {logs_dir}")
    safe_print(f"[INFO] Using condor_id:  {condor_id}")
    safe_print(f"[INFO] Mapping:         {formula}  (offset={args.offset})")
    if skipped_by_offset:
        safe_print(f"[INFO] Skipped by offset rule: {len(skipped_by_offset)}")
    if skipped_by_negative_zzz:
        safe_print(f"[INFO] Skipped due to negative ZZZ: {len(skipped_by_negative_zzz)}")
    if args.n_jobs is not None:
        safe_print(f"[INFO] n_jobs cap:      {args.n_jobs} (skipped {len(skipped_by_njobs)})")
    safe_print(f"[INFO] Starting log checks with {workers} worker(s)...")

    with ProcessPoolExecutor(max_workers=workers) as ex:
        futures = [
            ex.submit(
                check_one_root,
                str(root_path),
                job,
                str(logs_dir),
                condor_id,
                args.offset,
                minus_one,
                args.context_lines,
            )
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
    bad_reports_sorted = sorted(bad_error_reports, key=lambda t: job_sort_key(t[1]))

    # Write outputs (normal 'w' overwrites; --force only controls refusal earlier)
    try:
        with out_good.open("w", encoding="utf-8") as f:
            for p in good_sorted:
                f.write(p + "\n")
        with out_bad.open("w", encoding="utf-8") as f:
            for p in bad_sorted:
                f.write(p + "\n")
        with out_err.open("w", encoding="utf-8") as f:
            for root_path, job, status, snippets in bad_reports_sorted:
                f.write(format_error_report(root_path, job, status, snippets))
    except OSError as e:
        print(f"ERROR: Could not write output file(s): {e}", file=sys.stderr)
        return 3

    print("\n=== Summary ===")
    print(f"Ntuples dir: {ntuples_dir}")
    print(f"Logs dir:    {logs_dir}")
    print(f"Condor ID:   {condor_id}")
    print(f"Mapping:     {formula}  (offset={args.offset})")
    if skipped_by_offset:
        print(f"Skipped by offset rule: {len(skipped_by_offset)}")
    if skipped_by_negative_zzz:
        print(f"Skipped due to negative ZZZ: {len(skipped_by_negative_zzz)}")
    if args.n_jobs is not None:
        print(f"n_jobs cap:  {args.n_jobs} (skipped {len(skipped_by_njobs)})")
    print(f"Root files checked: {len(root_files)}")
    print(f"Workers used: {workers}")
    print(f"Good files: {len(good_sorted)} -> {out_good}")
    print(f"Bad files:  {len(bad_sorted)} -> {out_bad}")
    print(f"Errors file: {out_err}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

