#!/usr/bin/env python3
# singularity shell -B /cvmfs -B /etc/grid-security -B /ospool/cms-user/jaebak /cvmfs/singularity.opensciencegrid.org/cmssw/cms:rhel7
# source /cvmfs/cms.cern.ch/cmsset_default.sh
# cd CMSSW_10_6_29/src
# cmsenv
# cd -

# Uses haddnano.py
import argparse
import os

if __name__ == '__main__':
    
  parser = argparse.ArgumentParser(description='Combines NanoAOD files from multiple jobs')
  parser.add_argument('-c','--combine_number_jobs', required=True, help='Number of jobs to combine')
  parser.add_argument('-i','--input_folder', required=True, help='Input folder')
  parser.add_argument('-f','--filter_files', default='NanoAODv9', help='Filter files')
  parser.add_argument('-x', '--execute', action="store_true", help='Run commands')
  args = parser.parse_args()

  # Find all files
  files = os.listdir(args.input_folder)
  files = [f for f in files if args.filter_files in f]
  # Sort files by job number
  files.sort(key=lambda x: int(x.split('__job-')[1].split('.')[0]))

  # Group files by job number
  job_files = {}
  for f in files:
    job_number = int(f.split('__job-')[1].split('.')[0])
    # Group number is range of job numbers determined by combine_number_jobs
    group_number = job_number // int(args.combine_number_jobs)
    if group_number not in job_files: job_files[group_number] = []
    job_files[group_number].append(f)

  # Combine files using script called haddnano.py
  for group_number, files in job_files.items():
    files = [os.path.join(args.input_folder, f) for f in files]
    output_file = f"{files[0].split('__job-')[0]}__jobs-{files[0].split('__job-')[1].split('.')[0]}-{files[-1].split('__job-')[1].split('.')[0]}-njobs-{len(files)}.root"
    command = f'python scripts/haddnano.py {output_file} {" ".join(files)}'
    print(command)
    if args.execute: os.system(command)
    
  if not args.execute: print("[Info] Add -x argument to run commands")
