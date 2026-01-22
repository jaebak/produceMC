#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import posixpath
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

ROOT_JOB_RE = re.compile(r"^(?P<prefix>.+)__job_(?P<job>\d+)\.root$")
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

RootInfo = Tuple[str, str]  # (job, prefix)


# -------------------------
# XRootD URL + CLI helpers
# -------------------------
def is_xrootd_url(s: str) -> bool:
    return s.startswith("root://")


def require_cmd(name: str) -> None:
    if shutil.which(name) is None:
        raise RuntimeError(f"Required command '{name}' not found in PATH.")


def parse_xrootd_url(url: str) -> Tuple[str, str, str]:
    u = urlparse(url)
    if u.scheme != "root":
        raise ValueError(f"Not an XRootD URL: {url}")
    host = u.netloc
    path = u.path or "/"
    abs_path = "/" + path.lstrip("/")
    query = u.query or ""
    return host, abs_path, query


def make_xrootd_url(host: str, abs_path: str, query: str = "") -> str:
    p = "/" + abs_path.lstrip("/")
    base = f"root://{host}//{p.lstrip('/')}"
    return f"{base}?{query}" if query else base


def xrootd_dirname(url: str) -> str:
    host, p, q = parse_xrootd_url(url)
    d = posixpath.dirname(p) or "/"
    return make_xrootd_url(host, d, q)


def xrootd_join(url: str, *parts: str) -> str:
    host, p, q = parse_xrootd_url(url)
    joined = p
    for part in parts:
        joined = posixpath.join(joined, part)
    joined = "/" + joined.lstrip("/")
    return make_xrootd_url(host, joined, q)


def xrootd_basename(url: str) -> str:
    return posixpath.basename(urlparse(url).path)


def run_cmd(cmd: List[str], *, timeout_s: Optional[int], text: bool = True) -> subprocess.CompletedProcess:
    """
    Runs a command with a hard timeout.
    On timeout returns a CompletedProcess-like object with rc=124 and stderr containing [TIMEOUT].
    """
    try:
        return subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=text,
            check=False,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired as e:
        stdout = e.stdout if isinstance(e.stdout, str) else (e.stdout.decode("utf-8", "replace") if e.stdout else "")
        stderr = e.stderr if isinstance(e.stderr, str) else (e.stderr.decode("utf-8", "replace") if e.stderr else "")
        if stderr:
            stderr = f"{stderr}\n"
        stderr = f"{stderr}[TIMEOUT] command exceeded {timeout_s}s"
        return subprocess.CompletedProcess(cmd, 124, stdout=stdout, stderr=stderr)


def retry_loop(retries: int, retry_sleep: float):
    """
    Generator yielding attempt index. Sleeps between attempts.
    retries=0 means one attempt total.
    """
    for attempt in range(retries + 1):
        yield attempt
        if attempt < retries and retry_sleep > 0:
            time.sleep(retry_sleep)


def job_sort_key(job: str) -> int:
    try:
        return int(job)
    except Exception:
        return 10**18


# -------------------------
# xrdfs / xrdcp wrappers with retries
# -------------------------
def xrdfs_ls(dir_url: str, recursive: bool, cmd_timeout: int, retries: int, retry_sleep: float) -> List[str]:
    """
    Uses: xrdfs <host> ls [-R] <path>
    Returns full root:// URLs.
    Retries on failure/timeouts.
    """
    require_cmd("xrdfs")
    host, path, query = parse_xrootd_url(dir_url)

    cmd = ["xrdfs", host, "ls"]
    if recursive:
        cmd.append("-R")
    cmd.append(path)

    last_err = None
    for _ in retry_loop(retries, retry_sleep):
        proc = run_cmd(cmd, timeout_s=cmd_timeout, text=True)
        if proc.returncode == 0:
            out: List[str] = []
            for line in proc.stdout.splitlines():
                line = line.strip()
                if not line:
                    continue
                abs_path = "/" + line.lstrip("/")
                out.append(make_xrootd_url(host, abs_path, query))
            # de-dup preserve order
            seen = set()
            uniq: List[str] = []
            for u in out:
                if u in seen:
                    continue
                seen.add(u)
                uniq.append(u)
            return uniq

        last_err = proc.stderr.strip() or f"xrdfs ls rc={proc.returncode}"

    raise RuntimeError(f"xrdfs ls failed after {retries+1} attempt(s) for {dir_url}\nSTDERR:\n{last_err}")


def xrdfs_exists(url: str, cmd_timeout: int, retries: int, retry_sleep: float) -> Tuple[bool, Optional[str]]:
    """
    Uses: xrdfs <host> stat <path>
    Retries on timeout/nonzero rc.
    Returns (exists_ok, reason_if_false)
    """
    require_cmd("xrdfs")
    host, path, _query = parse_xrootd_url(url)
    cmd = ["xrdfs", host, "stat", path]

    last_reason = None
    for _ in retry_loop(retries, retry_sleep):
        proc = run_cmd(cmd, timeout_s=cmd_timeout, text=True)
        if proc.returncode == 0:
            return True, None
        if proc.returncode == 124 and "TIMEOUT" in (proc.stderr or ""):
            last_reason = f"timeout stat after {cmd_timeout}s"
        else:
            last_reason = proc.stderr.strip() or f"xrdfs stat rc={proc.returncode}"

    return False, last_reason


def _xrdcp_fetch_once(url: str, local_path: Path, cmd_timeout: int) -> Tuple[bool, Optional[str]]:
    """
    One attempt.
    Prefer xrdcp; fall back to xrdfs cat if xrdcp is missing.
    Returns (ok, reason_if_failed)
    """
    if shutil.which("xrdcp") is not None:
        proc = run_cmd(["xrdcp", "-f", url, str(local_path)], timeout_s=cmd_timeout, text=True)
        if proc.returncode == 0:
            return True, None
        if proc.returncode == 124 and "TIMEOUT" in (proc.stderr or ""):
            return False, f"timeout fetching after {cmd_timeout}s"
        return False, (proc.stderr.strip() or f"xrdcp rc={proc.returncode}")

    # fallback: xrdfs cat (binary)
    require_cmd("xrdfs")
    host, path, _query = parse_xrootd_url(url)
    try:
        proc = subprocess.run(
            ["xrdfs", host, "cat", path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=cmd_timeout,
        )
    except subprocess.TimeoutExpired:
        return False, f"timeout cat after {cmd_timeout}s"

    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", "replace").strip()
        return False, (err or f"xrdfs cat rc={proc.returncode}")

    try:
        local_path.write_bytes(proc.stdout)
        return True, None
    except OSError as e:
        return False, f"write temp file failed: {e}"


def xrdcp_fetch(url: str, local_path: Path, cmd_timeout: int, retries: int, retry_sleep: float) -> Tuple[bool, Optional[str]]:
    """
    Fetch with retries.
    """
    last_reason = None
    for _ in retry_loop(retries, retry_sleep):
        ok, reason = _xrdcp_fetch_once(url, local_path, cmd_timeout)
        if ok:
            return True, None
        last_reason = reason
    return False, last_reason


# -------------------------
# Input normalization (server required for /paths)
# -------------------------
def to_root_url(user_input: str, server: Optional[str]) -> str:
    """
    Accepts:
      - root://host:port//path    -> returned as-is
      - /store/... (or any /...)  -> converted to root://<server>//<path>   (server is required)
    """
    if is_xrootd_url(user_input):
        return user_input

    if not user_input.startswith("/"):
        raise ValueError(f"Path must start with '/' or be a root:// URL: {user_input}")

    if not server:
        raise ValueError("For non-root:// paths you must provide --server host:port")

    return make_xrootd_url(server, user_input, "")


# -------------------------
# ROOT discovery
# -------------------------
def find_root_files(
    input_folder_url: str,
    verbose: bool,
    cmd_timeout: int,
    retries: int,
    retry_sleep: float,
) -> Dict[str, RootInfo]:
    root_files: Dict[str, RootInfo] = {}

    if verbose:
        print(f"[INFO] Searching for ROOT files on XRootD in: {input_folder_url}", flush=True)
        print("[INFO] First: scanning top-level...", flush=True)

    entries = xrdfs_ls(input_folder_url, recursive=False, cmd_timeout=cmd_timeout, retries=retries, retry_sleep=retry_sleep)
    for u in entries:
        name = xrootd_basename(u)
        m = ROOT_JOB_RE.match(name)
        if m:
            job = m.group("job")
            prefix = m.group("prefix")
            root_files[u] = (job, prefix)
            if verbose:
                print(f"[FOUND] {u} (job {job})", flush=True)

    if root_files:
        if verbose:
            print(f"[INFO] Found {len(root_files)} ROOT file(s) in top-level.", flush=True)
        return root_files

    if verbose:
        print("[INFO] No top-level ROOT files found. Recursing into subdirectories...", flush=True)

    scanned = 0
    entries = xrdfs_ls(input_folder_url, recursive=True, cmd_timeout=cmd_timeout, retries=retries, retry_sleep=retry_sleep)
    for u in entries:
        scanned += 1
        if verbose and scanned % 5000 == 0:
            print(f"[INFO] ...scanned {scanned} paths so far", flush=True)

        if not urlparse(u).path.endswith(".root"):
            continue

        name = xrootd_basename(u)
        m = ROOT_JOB_RE.match(name)
        if m:
            job = m.group("job")
            prefix = m.group("prefix")
            root_files[u] = (job, prefix)
            if verbose:
                print(f"[FOUND] {u} (job {job})", flush=True)

    if verbose:
        print(f"[INFO] Done searching. Total ROOT files found: {len(root_files)}", flush=True)
    return root_files


# -------------------------
# Log reading / checking
# -------------------------
def read_member_text_from_tar_gz(
    tar_url: str,
    member_name: str,
    cmd_timeout: int,
    retries: int,
    retry_sleep: float,
) -> Tuple[Optional[str], Optional[str]]:
    """
    Returns (text, error_reason).
    Downloads remote tar.gz to temp and extracts member text.
    """
    with tempfile.TemporaryDirectory(prefix="xrdlog_") as td:
        tmp = Path(td) / "log.tar.gz"
        ok, why = xrdcp_fetch(tar_url, tmp, cmd_timeout=cmd_timeout, retries=retries, retry_sleep=retry_sleep)
        if not ok or not tmp.exists():
            return None, (why or "fetch failed")

        try:
            with tarfile.open(tmp, mode="r:gz") as tf:
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
                    return None, f"missing member: {member_name}"

                f = tf.extractfile(member)
                if f is None:
                    return None, f"cannot extract member: {member_name}"

                return f.read().decode("utf-8", errors="replace"), None
        except (tarfile.TarError, OSError) as e:
            return None, f"tar read failed: {e}"


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
    root_url: str,
    job_str: str,
    global_log_folder_url: Optional[str],
    context_lines: int,
    cmd_timeout: int,
    retries: int,
    retry_sleep: float,
) -> Tuple[str, str, bool, str, List[str]]:
    job = job_str

    if global_log_folder_url:
        log_folder = global_log_folder_url
    else:
        log_folder = xrootd_join(xrootd_dirname(root_url), "log")

    tar_name = f"cmsRun_{job}.log.tar.gz"
    stdout_member = f"cmsRun-stdout-{job}.log"
    tar_url = xrootd_join(log_folder, tar_name)

    log_text, why = read_member_text_from_tar_gz(
        tar_url, stdout_member, cmd_timeout=cmd_timeout, retries=retries, retry_sleep=retry_sleep
    )
    if log_text is None:
        exists_log, why_log = xrdfs_exists(log_folder, cmd_timeout=cmd_timeout, retries=retries, retry_sleep=retry_sleep)
        if not exists_log:
            return (root_url, job, False, f"log folder missing/unreachable ({why_log})", [])

        exists_tar, why_tar = xrdfs_exists(tar_url, cmd_timeout=cmd_timeout, retries=retries, retry_sleep=retry_sleep)
        if not exists_tar:
            return (root_url, job, False, f"archive missing/unreachable ({why_tar})", [])

        return (root_url, job, False, why or "missing or unreadable log", [])

    snippets = extract_error_snippets(log_text, context_lines=context_lines)
    if snippets:
        return (root_url, job, False, "found error(s)", snippets)

    return (root_url, job, True, "ok", [])


def format_error_report(root_url: str, job: str, status: str, snippets: List[str]) -> str:
    lines: List[str] = []
    lines.append("=" * 80)
    lines.append(f"JOB: {job}")
    lines.append(f"ROOT: {root_url}")
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


def _expand_output_path(
    template: Optional[str],
    *,
    prefix: str,
    default_name: str,
    run_folder: Path,
    multiple_prefixes: bool,
) -> Path:
    if template is None:
        return (run_folder / default_name).expanduser().resolve()

    tmpl = os.path.expanduser(template)
    if "{prefix}" in tmpl:
        return Path(tmpl.format(prefix=prefix)).expanduser().resolve()

    p = Path(tmpl).expanduser()

    if tmpl.endswith("/") or tmpl.endswith(os.sep) or (p.exists() and p.is_dir()):
        return (p / default_name).expanduser().resolve()

    if not multiple_prefixes:
        return p.resolve()

    return (p.parent / f"{prefix}__{p.name}").expanduser().resolve()


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Check cmsRun logs to decide which ROOT files are good (XRootD only; uses xrdfs/xrdcp; timeouts + retries)."
    )
    ap.add_argument(
        "input_folder",
        help="root://host:port//path OR absolute path like /store/user/... (requires --server).",
    )
    ap.add_argument(
        "--server",
        default=None,
        help="XRootD server host:port used to convert /paths into root:// URLs (required if input/log are /paths).",
    )
    ap.add_argument(
        "--log-folder",
        default=None,
        help="Optional log folder (root://... OR /store/... ; /paths require --server). Overrides per-file <root_parent>/log.",
    )

    ap.add_argument("--output-good", default=None)
    ap.add_argument("--output-bad", default=None)
    ap.add_argument("--output-errors", default=None)

    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 1)))
    ap.add_argument("--context-lines", type=int, default=10)
    ap.add_argument("--quiet-find", action="store_true")

    ap.add_argument("--cmd-timeout", type=int, default=180, help="Timeout (seconds) for xrdfs/xrdcp (default: 180).")
    ap.add_argument("--retries", type=int, default=2, help="Retries for xrdfs/xrdcp failures (default: 2).")
    ap.add_argument("--retry-sleep", type=float, default=2.0, help="Seconds to sleep between retries (default: 2.0).")
    ap.add_argument(
        "--status-every",
        type=int,
        default=30,
        help="Print progress every N seconds even if no jobs finish (default: 30; set 0 to disable).",
    )

    args = ap.parse_args()

    try:
        require_cmd("xrdfs")
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    # Normalize paths to root:// URLs
    try:
        input_url = to_root_url(args.input_folder, args.server)
        log_folder_url = to_root_url(args.log_folder, args.server) if args.log_folder else None
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    run_folder = Path.cwd().resolve()

    # Sanity: input exists
    ok_in, why_in = xrdfs_exists(
        input_url, cmd_timeout=args.cmd_timeout, retries=args.retries, retry_sleep=args.retry_sleep
    )
    if not ok_in:
        print(f"ERROR: input_folder not accessible: {input_url} ({why_in})", file=sys.stderr)
        return 2

    root_files = find_root_files(
        input_url,
        verbose=not args.quiet_find,
        cmd_timeout=args.cmd_timeout,
        retries=args.retries,
        retry_sleep=args.retry_sleep,
    )
    if not root_files:
        print(f"No ROOT files matching '*__job_XX.root' found in: {input_url}", file=sys.stderr)
        return 1

    prefixes = sorted({info[1] for info in root_files.values()})
    multiple_prefixes = len(prefixes) > 1

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

    # no overwrite
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

    items = sorted(root_files.items(), key=lambda kv: job_sort_key(kv[1][0]))
    total = len(items)
    workers = max(1, args.workers)

    print_lock = threading.Lock()
    state_lock = threading.Lock()
    stop_evt = threading.Event()

    completed = 0
    good_n = 0
    bad_n = 0
    last_done_ts = time.time()

    good_by_prefix: Dict[str, List[str]] = {p: [] for p in prefixes}
    bad_by_prefix: Dict[str, List[str]] = {p: [] for p in prefixes}
    bad_reports_by_prefix: Dict[str, List[Tuple[str, str, str, List[str]]]] = {p: [] for p in prefixes}

    job_by_path = {p: info[0] for p, info in root_files.items()}
    prefix_by_path = {p: info[1] for p, info in root_files.items()}

    def safe_print(*a, **k):
        with print_lock:
            print(*a, **k, flush=True)

    def watchdog():
        while not stop_evt.wait(args.status_every):
            with state_lock:
                c = completed
                g = good_n
                b = bad_n
                idle = int(time.time() - last_done_ts)
            safe_print(f"[INFO] Progress: {c}/{total} done (good={g}, bad={b}), last completion {idle}s ago...")

    if args.status_every > 0:
        threading.Thread(target=watchdog, daemon=True).start()

    safe_print(
        f"[INFO] Starting log checks with {workers} worker(s)... "
        f"(cmd timeout {args.cmd_timeout}s, retries {args.retries}, sleep {args.retry_sleep}s)"
    )

    with ProcessPoolExecutor(max_workers=workers) as ex:
        futures = [
            ex.submit(
                check_one_root,
                root_url,
                job,
                log_folder_url,
                args.context_lines,
                args.cmd_timeout,
                args.retries,
                args.retry_sleep,
            )
            for (root_url, (job, _prefix)) in items
        ]

        for fut in as_completed(futures):
            root_url, job, is_good, status, snippets = fut.result()

            with state_lock:
                completed += 1
                last_done_ts = time.time()
                if is_good:
                    good_n += 1
                else:
                    bad_n += 1

            prefix = prefix_by_path.get(root_url, "UNKNOWN")
            name = xrootd_basename(root_url)

            if is_good:
                good_by_prefix.setdefault(prefix, []).append(root_url)
                safe_print(f"[GOOD] job {job}: {root_url}")
            else:
                bad_by_prefix.setdefault(prefix, []).append(root_url)
                bad_reports_by_prefix.setdefault(prefix, []).append((root_url, job, status, snippets))
                if snippets:
                    safe_print(f"[BAD ] job {job}: {name} -> {status}:")
                    for k, snip in enumerate(snippets, 1):
                        safe_print(f"--- error snippet {k} (job {job}) ---")
                        safe_print(snip)
                        safe_print("--- end snippet ---\n")
                else:
                    safe_print(f"[BAD ] job {job}: {name} -> {status}")

    stop_evt.set()

    # write outputs per prefix
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
                for root_url, job, status, snippets in bad_reports_sorted:
                    f.write(format_error_report(root_url, job, status, snippets))
    except OSError as e:
        print(f"ERROR: Could not write output file(s): {e}", file=sys.stderr)
        return 3

    print("\n=== Summary ===")
    print(f"Run folder (cwd): {run_folder}")
    print(f"Input folder (normalized): {input_url}")
    print(f"Root files found: {len(root_files)}")
    print(f"Workers used: {workers}")
    print(f"Command timeout: {args.cmd_timeout}s")
    print(f"Retries: {args.retries} (sleep {args.retry_sleep}s)")
    print(f"Prefixes: {len(prefixes)}")
    for prefix in prefixes:
        out_good, out_bad, out_err = out_paths[prefix]
        ng = len(good_by_prefix.get(prefix, []))
        nb = len(bad_by_prefix.get(prefix, []))
        print(f"- {prefix}: good {ng} -> {out_good.name}; bad {nb} -> {out_bad.name}; errors -> {out_err.name}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

