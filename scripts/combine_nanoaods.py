#!/usr/bin/env python3
import argparse
import os

def extract_job_number(filename: str) -> int:
  # expects something like ...__job-123.root
  return int(filename.split('__job-')[1].split('.')[0])

if __name__ == '__main__':

  parser = argparse.ArgumentParser(description='Combines NanoAOD files from multiple jobs')
  parser.add_argument(
    '-c','--combine_number_jobs',
    type=int,
    default=250,
    help='Number of files (jobs) to combine per output (default: 250)'
  )
  parser.add_argument('-i','--input_folder', required=True, help='Input folder')
  parser.add_argument('-f','--filter_files', default='NanoAODv9', help='Filter files')
  parser.add_argument('-x', '--execute', action="store_true", help='Run commands')
  args = parser.parse_args()

  # Find all files
  all_files = os.listdir(args.input_folder)
  files = [f for f in all_files if args.filter_files in f and '__job-' in f]

  # Sort files by job number
  files.sort(key=extract_job_number)

  # Combine in fixed-size chunks
  chunk_size = max(1, args.combine_number_jobs)

  for start in range(0, len(files), chunk_size):
    chunk = files[start:start + chunk_size]
    chunk_paths = [os.path.join(args.input_folder, f) for f in chunk]

    first_job = extract_job_number(chunk[0])
    last_job  = extract_job_number(chunk[-1])

    # Base prefix from the first file (everything before "__job-")
    prefix = chunk[0].split('__job-')[0]

    output_file = f"{prefix}__jobs-{first_job}-{last_job}-njobs-{len(chunk)}.root"
    command = f'python3 scripts/haddnano.py {output_file} {" ".join(chunk_paths)}'
    print(command)
    if args.execute:
      os.system(command)

  if not args.execute:
    print("[Info] Add -x argument to run commands")
