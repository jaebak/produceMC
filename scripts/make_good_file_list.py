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

RootInfo = Tuple[str, str]  # (job, prefix)


def find_root_files(input_folder: Path, verbose: bool = True) -> Dict[Path, RootInfo]:
    """Top-level scan first; if none found, recurse. Prints progress while searching."""
    root_files: Dict[Path, RootInfo] = {}

    if verbose:
        print(f"[INFO] Searching for ROOT files in: {input_folder}", flush=True)
        print("[INFO] First: scanning top-level...", flush=True)

    for p in input_folder.iterdir():
        if p.is_file():
            m = ROOT_JOB_RE.match(p.name)
            if m:
                job = m.group("job")
                prefix = m.group("prefix")
                root_files[p] = (job, prefix)
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
            prefix = m.group("prefix")
            root_files[p] = (job, prefix)
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


def _expand_output_path(
    template: Optional[str],
    *,
    prefix: str,
    default_name: str,
    run_folder: Path,
    multiple_prefixes: bool,
) -> Path:
    """
    Build an output path.

    Default behavior (template is None):
      - write into the folder where the script is run (cwd): run_folder/default_name

    If template contains "{prefix}":
      - format it (e.g. "out/{prefix}_good.txt")

    If template looks like a directory (ends with "/" or exists as dir):
      - put default_name inside it

    If multiple_prefixes and template has no "{prefix}":
      - prefix the filename with "<prefix>__" to avoid collisions
    """
    if template is None:
        return (run_folder / default_name).expanduser().resolve()

    tmpl = os.path.expanduser(template)
    if "{prefix}" in tmpl:
        return Path(tmpl.format(prefix=prefix)).expanduser().resolve()

    p = Path(tmpl).expanduser()

    # treat as directory if it ends with a slash OR is an existing directory
    if tmpl.endswith("/") or tmpl.endswith(os.sep) or (p.exists() and p.is_dir()):
        return (p / default_name).expanduser().resolve()

    # single-prefix: respect explicit filename as-is
    if not multiple_prefixes:
        return p.resolve()

    # multi-prefix: avoid overwriting by inserting prefix
    return (p.parent / f"{prefix}__{p.name}").expanduser().resolve()


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
        default=None,
        help=(
            "Output path for GOOD list (optionally use {prefix}). "
            "Default: <cwd>/<prefix>__good_root_files.txt"
        ),
    )
    ap.add_argument(
        "--output-bad",
        default=None,
        help=(
            "Output path for BAD list (optionally use {prefix}). "
            "Default: <cwd>/<prefix>__bad_root_files.txt"
        ),
    )
    ap.add_argument(
        "--output-errors",
        default=None,
        help=(
            "Output path for BAD errors report (optionally use {prefix}). "
            "Default: <cwd>/<prefix>__bad_root_files_errors.txt"
        ),
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

    run_folder = Path.cwd().resolve()

    root_files = find_root_files(input_folder, verbose=not args.quiet_find)
    if not root_files:
        print(f"No ROOT files matching '*__job_XX.root' found in: {input_folder}", file=sys.stderr)
        return 1

    prefixes = sorted({info[1] for info in root_files.values()})
    multiple_prefixes = len(prefixes) > 1

    # Build per-prefix output paths (defaulting to run_folder)
    out_paths: Dict[str, Tuple[Path, Path, Path]] = {}
    for prefix in prefixes:
        out_good = _expand_output_path(
            args.output_good,
            prefix=prefix,
            default_name=f"{prefix}__good_root_files.txt",
            run_folder=run_folder,
            multiple_prefixes=multiple_prefixes,
        )
        out_bad = _expand_output_path(
            args.output_bad,
            prefix=prefix,
            default_name=f"{prefix}__bad_root_files.txt",
            run_folder=run_folder,
            multiple_prefixes=multiple_prefixes,
        )
        out_err = _expand_output_path(
            args.output_errors,
            prefix=prefix,
            default_name=f"{prefix}__bad_root_files_errors.txt",
            run_folder=run_folder,
            multiple_prefixes=multiple_prefixes,
        )
        out_paths[prefix] = (out_good, out_bad, out_err)

    # Do not overwrite any outputs
    existing: List[Tuple[str, Path]] = []
    for (og, ob, oe) in out_paths.values():
        if og.exists():
            existing.append(("GOOD", og))
        if ob.exists():
            existing.append(("BAD", ob))
        if oe.exists():
            existing.append(("ERRORS", oe))
    if existing:
        for kind, p in existing:
            print(f"[INFO] Output {kind} file already exists: {p}")
        print("[INFO] Exiting without doing any work.")
        return 0

    # Sort items by job id
    items = sorted(root_files.items(), key=lambda kv: job_sort_key(kv[1][0]))
    workers = max(1, args.workers)

    print_lock = threading.Lock()

    good_by_prefix: Dict[str, List[str]] = {p: [] for p in prefixes}
    bad_by_prefix: Dict[str, List[str]] = {p: [] for p in prefixes}
    bad_reports_by_prefix: Dict[str, List[Tuple[str, str, str, List[str]]]] = {p: [] for p in prefixes}

    job_by_path = {str(p): info[0] for p, info in root_files.items()}
    prefix_by_path = {str(p): info[1] for p, info in root_files.items()}

    def safe_print(*a, **k):
        with print_lock:
            print(*a, **k, flush=True)

    safe_print(f"[INFO] Starting log checks with {workers} worker(s)...")

    with ProcessPoolExecutor(max_workers=workers) as ex:
        futures = [
            ex.submit(check_one_root, str(root_path), job, args.log_folder, args.context_lines)
            for (root_path, (job, _prefix)) in items
        ]

        for fut in as_completed(futures):
            root_path, job, is_good, status, snippets = fut.result()
            prefix = prefix_by_path.get(root_path, "UNKNOWN")

            if is_good:
                good_by_prefix.setdefault(prefix, []).append(root_path)
                safe_print(f"[GOOD] job {job}: {root_path}")
            else:
                bad_by_prefix.setdefault(prefix, []).append(root_path)
                bad_reports_by_prefix.setdefault(prefix, []).append((root_path, job, status, snippets))

                if snippets:
                    safe_print(f"[BAD ] job {job}: {Path(root_path).name} -> {status}:")
                    for k, snip in enumerate(snippets, 1):
                        safe_print(f"--- error snippet {k} (job {job}) ---")
                        safe_print(snip)
                        safe_print("--- end snippet ---\n")
                else:
                    safe_print(f"[BAD ] job {job}: {Path(root_path).name} -> {status}")

    # Write output files (per prefix)
    try:
        for prefix in prefixes:
            out_good, out_bad, out_err = out_paths[prefix]

            good_sorted = sorted(
                good_by_prefix.get(prefix, []),
                key=lambda p: job_sort_key(job_by_path.get(p, "999999999")),
            )
            bad_sorted = sorted(
                bad_by_prefix.get(prefix, []),
                key=lambda p: job_sort_key(job_by_path.get(p, "999999999")),
            )
            bad_reports_sorted = sorted(
                bad_reports_by_prefix.get(prefix, []),
                key=lambda t: job_sort_key(t[1]),
            )

            out_good.parent.mkdir(parents=True, exist_ok=True)
            out_bad.parent.mkdir(parents=True, exist_ok=True)
            out_err.parent.mkdir(parents=True, exist_ok=True)

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
    print(f"Run folder (cwd): {run_folder}")
    print(f"Input folder: {input_folder}")
    print(f"Root files found: {len(root_files)}")
    print(f"Workers used: {workers}")
    print(f"Prefixes: {len(prefixes)}")
    for prefix in prefixes:
        out_good, out_bad, out_err = out_paths[prefix]
        ng = len(good_by_prefix.get(prefix, []))
        nb = len(bad_by_prefix.get(prefix, []))
        print(
            f"- {prefix}: good {ng} -> {out_good.name}; "
            f"bad {nb} -> {out_bad.name}; "
            f"errors -> {out_err.name}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

