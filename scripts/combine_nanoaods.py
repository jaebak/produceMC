#!/usr/bin/env python3
import argparse, os
from pathlib import Path
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

if __name__ == "__main__":
  argument_parser = argparse.ArgumentParser(description="Combine NanoAOD files from multiple jobs")
  argument_parser.add_argument("-i", "--input_folder", required=True,
                              help="Input folder (can contain subfolders like 0000/, 0001/, ...)")
  argument_parser.add_argument("-c", "--combine_number_jobs", type=int, default=250,
                              help="Number of files (jobs) to combine per output (default: 250)")
  argument_parser.add_argument("-f", "--filter_files", default="",
                              help="Only include files whose name contains this substring (default: no filter)")
  argument_parser.add_argument("-x", "--execute", action="store_true", help="Run commands")
  arguments = argument_parser.parse_args()

  input_folder_path = Path(arguments.input_folder)

  candidate_file_paths = [
    file_path for file_path in input_folder_path.rglob("*.root")
    if ("__job-" in file_path.name or "__job_" in file_path.name)
    and (not arguments.filter_files or arguments.filter_files in file_path.name)
  ]

  candidate_file_paths.sort(key=lambda file_path: extract_job_number(file_path.name))

  files_per_output = max(1, arguments.combine_number_jobs)

  for chunk_start_index in range(0, len(candidate_file_paths), files_per_output):
    file_chunk_paths = candidate_file_paths[chunk_start_index:chunk_start_index + files_per_output]

    first_job_number = extract_job_number(file_chunk_paths[0].name)
    last_job_number  = extract_job_number(file_chunk_paths[-1].name)
    file_name_prefix = extract_file_prefix(file_chunk_paths[0].name)

    output_file_name = (
      f"{file_name_prefix}__jobs-{first_job_number}-{last_job_number}-njobs-{len(file_chunk_paths)}.root"
    )

    haddnano_command = (
      f"python3 scripts/haddnano.py {output_file_name} "
      + " ".join(map(str, file_chunk_paths))
    )

    print(haddnano_command)
    if arguments.execute:
      subprocess.run(haddnano_command, shell=True, check=True)

  if not arguments.execute:
    print("[Info] Add -x argument to run commands")
