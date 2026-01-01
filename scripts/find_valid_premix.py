#!/usr/bin/env python3
import subprocess
import multiprocessing
import json
import sys
import os
import ROOT
import argparse
import re
import time

#def exist_premix_file((index, premix_file)):
#  command = "xrdfs cmsxrootd.fnal.gov ls -l "+premix_file
#  #command = "xrdfs cms-xrd-global.cern.ch:1094 ls -l "+premix_file
#  #command = "xrdfs xrootd-cms.infn.it ls -l "+premix_file
#  #command = "xrdfs cmsxrootd-kit.gridka.de ls -l "+premix_file
#  process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
#  output, error = process.communicate()
#  if "ERROR" in error: result = False
#  else: result = True
#  print(index, command, result)
#  return premix_file, result

#def exist_premix_file((index, premix_file)):
#  ROOT.TFile.Open('root://cmsxrootd-kit.gridka.de//'+premix_file)
#  process = subprocess.Popen('root -q', shell=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
#  output, error = process.communicate('TFile *f =TFile::Open("root://cmsxrootd-kit.gridka.de//'+premix_file+'");')
#  print(output, error)
#  if "ERROR" in error: result = False
#  else: result = True
#  print(index, premix_file, result)
#  return premix_file, result

#def exist_premix_file((index, premix_file)):
#  result = ROOT.TFile.Open('root://cmsxrootd-kit.gridka.de//'+premix_file)
#  print(index, premix_file, result!=None)
#  return premix_file, result!=None

def exist_premix_file(index, premix_file):
  command = f'crab checkfile --lfn {premix_file}'
  for iRetry in range(5):
    try:
      result = subprocess.check_output(command, shell=True).decode()
      #print(result)
      is_file_on_disk = False
      unknown_log = ''
      if re.compile(r"LFN has 0 disk replica").search(result): is_file_on_disk = False
      elif re.compile(r"LFN has ([1-9]\d*) disk replica").search(result): is_file_on_disk = True
      elif re.compile(r"most likely file was deleted but non invalidated in DBS").search(result): is_file_on_disk = False 
      else: 
        print('Unknown case.')
        print(result)
        unknown_log = result
      print(index, premix_file, is_file_on_disk)
      break
    except subprocess.CalledProcessError as e:
      print(e.output)
      print(f'Trying again {iRetry+1}: {command}')
      time.sleep(3)
  return premix_file, is_file_on_disk, unknown_log

if __name__ == '__main__':
  parser = argparse.ArgumentParser(description='Finds valid premix files', formatter_class=argparse.RawTextHelpFormatter)
  
  parser.add_argument('-y', '--years', required=True, nargs="+", help='Enter years to search. Ex) -y 2017, 2018')
  parser.add_argument('-d', '--data_folder', default='premix_data', help='Folder to store data')
  parser.add_argument('-f', '--force_search', action="store_true", help='Search even if files have been searched for')
  
  args = parser.parse_args()

  premix_datasets = {
  # "2016APV": "/Neutrino_E-10_gun/RunIISummer20ULPrePremix-UL16_106X_mcRun2_asymptotic_v13-v1/PREMIX", # Same as 2016
  "2016": "/Neutrino_E-10_gun/RunIISummer20ULPrePremix-UL16_106X_mcRun2_asymptotic_v13-v1/PREMIX",
  "2017": "/Neutrino_E-10_gun/RunIISummer20ULPrePremix-UL17_106X_mc2017_realistic_v6-v3/PREMIX",
  "2018": "/Neutrino_E-10_gun/RunIISummer20ULPrePremix-UL18_106X_upgrade2018_realistic_v11_L1v1-v2/PREMIX",
  }

  # Make premix file list 
  if not os.path.exists(args.data_folder): os.makedirs(args.data_folder)
  for year in args.years:
    out_filename = f'{args.data_folder}/premix_file_list_{year}'
    if not os.path.isfile(out_filename):
      premix_dataset = premix_datasets[year]
      command = f'dasgoclient -query="file dataset={premix_dataset}"'
      result = subprocess.check_output(command, shell=True, universal_newlines=True).split()
      # Save result
      with open(out_filename,'w') as f_premix_file_list:
        for dataset in result:
          f_premix_file_list.write(f'{dataset}\n')

  # Load premix file list
  # premix_file_list_years[year] = [dataset_file]
  premix_file_list_years = {}
  for year in args.years:
    in_filename = f'{args.data_folder}/premix_file_list_{year}'
    with open(in_filename) as f_premix_file_list:
      premix_file_list_years[year] = f_premix_file_list.read().splitlines()

  # Make list of premix files that are on disk if it does not exist
  for year in args.years:
    out_filename = f'{args.data_folder}/exist_premix_file_list_{year}.json'
    if not os.path.isfile(out_filename) or args.force_search:
      print(f'Will scan {len(premix_file_list_years[year])} files for year {year}')
      pool = multiprocessing.Pool()
      #premix_file_list = premix_file_list_years[year][2014:2019]
      premix_file_list = premix_file_list_years[year]
      result = pool.starmap(exist_premix_file, enumerate(premix_file_list))
      #print(result)
      # Save result
      with open(out_filename, 'w') as f_exist_premix_file_list:
        json.dump(result, f_exist_premix_file_list)

  # Load results 
  # result_json_years[year] =  [(/store/mc/..., True/False, unknown_log)]
  result_json_years = {}
  for year in args.years:
    in_filename = f'{args.data_folder}/exist_premix_file_list_{year}.json'
    with open(in_filename) as f_exist_premix_file_list:
      result_json_years[year] = json.load(f_exist_premix_file_list)
    # Print number of valid files
    print(f'Valid premix file for year {year}: {sum(valid for _,valid,_ in result_json_years[year])} / {len(result_json_years[year])}')

  #print(result_json_years)

  # Make line for cmssw configuration script
  for year in args.years:
    valid_premix_fragment_name = f'valid_premix_fragment_{year}'
    line = 'process.mixData.input.fileNames = cms.untracked.vstring(['
    for item in result_json_years[year]:
      if (item[1] == False): continue
      line += "'"+item[0] +"',"
    line += '])'
    with open(valid_premix_fragment_name, 'w') as valid_premix_fragment:
      valid_premix_fragment.write(line+'\n')
      print("Wrote to "+valid_premix_fragment_name)
