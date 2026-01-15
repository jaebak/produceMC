#!/usr/bin/env python3
import argparse
import os
import subprocess


def extract_job_number(file_name: str) -> int:
    for job_separator in ("__job-", "__job_"):
        if job_separator in file_name:
            return int(file_name.split(job_separator, 1)[1].split(".", 1)[0])
    raise ValueError(f"Cannot extract job number from: {file_name}")


def extract_file_prefix(file_name: str) -> str:
    for job_separator in ("__job-", "__job_"):
        if job_separator in file_name:
            return file_name.split(job_separator, 1)[0]
    raise ValueError(f"Cannot extract file prefix from: {file_name}")


def is_job_root_name(file_name: str) -> bool:
    return file_name.endswith(".root") and ("__job-" in file_name or "__job_" in file_name)


def collect_from_folder(input_folder: str):
    out = []
    for root_dir, _, files in os.walk(input_folder):
        for fn in files:
            if is_job_root_name(fn):
                out.append(os.path.join(root_dir, fn))
    return out


def read_file_list(list_path: str):
    """
    Reads a text file containing one ABSOLUTE Linux path per line.
    Ignores blank lines and lines starting with '#'.
    No tilde expansion, no resolving.
    """
    out = []
    with open(list_path, "r", encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            if not s.startswith("/"):
                raise SystemExit(f"[ERROR] Non-absolute path in list file (must start with '/'): {s}")
            out.append(s)
    return out


def apply_filters(paths, filter_substring: str):
    """
    IMPORTANT: does NOT check if paths exist.
    Filters only by basename pattern + optional substring.
    """
    filtered = []
    for p in paths:
        base = os.path.basename(p)
        if not is_job_root_name(base):
            continue
        if filter_substring and filter_substring not in base:
            continue
        filtered.append(p)
    return filtered


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Combine NanoAOD files from multiple jobs")

    # Exactly one source: folder OR list
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("-i", "--input_folder", help="Search this folder recursively for job ROOT files")
    src.add_argument("--good-list", dest="good_list", help="Text file with one absolute ROOT path per line")

    ap.add_argument(
        "-c", "--combine_number_jobs", type=int, default=250,
        help="Number of files (jobs) to combine per output (default: 250)",
    )
    ap.add_argument(
        "-f", "--filter_files", default="",
        help="Only include files whose *name* contains this substring (default: no filter)",
    )
    ap.add_argument("-x", "--execute", action="store_true", help="Run commands")

    args = ap.parse_args()

    # 1) Collect from ONE source
    if args.input_folder:
        if not os.path.isdir(args.input_folder):
            raise SystemExit(f"[ERROR] Not a directory: {args.input_folder}")
        print(f"[INFO] Collecting ROOT files by searching folder: {args.input_folder}")
        candidate_file_paths = collect_from_folder(args.input_folder)
    else:
        if not os.path.isfile(args.good_list):
            raise SystemExit(f"[ERROR] Good list not found: {args.good_list}")
        print(f"[INFO] Collecting ROOT files from list: {args.good_list}")
        candidate_file_paths = read_file_list(args.good_list)

    print("[INFO] Starting filtering...", flush=True)

    # 2) Filter after collection (no existence checks)
    candidate_file_paths = apply_filters(candidate_file_paths, args.filter_files)

    if not candidate_file_paths:
        print("[INFO] No candidate ROOT files found after collection + filtering.")
        raise SystemExit(0)

    # 3) Sort for stable chunking/output names
    candidate_file_paths.sort(key=lambda p: extract_job_number(os.path.basename(p)))

    files_per_output = max(1, args.combine_number_jobs)

    for chunk_start_index in range(0, len(candidate_file_paths), files_per_output):
        file_chunk_paths = candidate_file_paths[chunk_start_index:chunk_start_index + files_per_output]

        first_job_number = extract_job_number(os.path.basename(file_chunk_paths[0]))
        last_job_number = extract_job_number(os.path.basename(file_chunk_paths[-1]))
        file_name_prefix = extract_file_prefix(os.path.basename(file_chunk_paths[0]))

        output_file_name = (
            f"{file_name_prefix}__jobs-{first_job_number}-{last_job_number}-njobs-{len(file_chunk_paths)}.root"
        )

        haddnano_command = (
            f"python3 scripts/haddnano.py {output_file_name} "
            + " ".join(file_chunk_paths)
        )

        print(haddnano_command)
        if args.execute:
            subprocess.run(haddnano_command, shell=True, check=True)

    if not args.execute:
        print("[Info] Add -x argument to run commands")

