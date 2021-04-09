#!/usr/bin/env python
import subprocess
import multiprocessing
import json
import sys
import os
import ROOT


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

def exist_premix_file((index, premix_file)):
  result = ROOT.TFile.Open('root://cmsxrootd-kit.gridka.de//'+premix_file)
  print(index, premix_file, result!=None)
  return premix_file, result!=None

if __name__ == '__main__':
  ROOT.gErrorIgnoreLevel = ROOT.kFatal # To suppress error when opening file

  ## Should work
  #exist_premix_file((1, '/store/mc/RunIISummer16FSPremix/Neutrino_E-10_gun/GEN-SIM-DIGI-RAW/PUMoriond17_80X_mcRun2_asymptotic_2016_TrancheIV_v4-v1/120001/E0E67F58-D09D-E611-9F7F-0CC47A4D7698.root'))
  ## Should fail
  #exist_premix_file((1, '/store/mc/RunIISummer16FSPremix/Neutrino_E-10_gun/GEN-SIM-DIGI-RAW/PUMoriond17_80X_mcRun2_asymptotic_2016_TrancheIV_v4-v1/120000/C8DDC158-509D-E611-B44F-0025905A6092.root'))

  
  #result_filename = "saved_results.json.kit.de"
  #input_filename = 'SUS-RunIISummer16FSPremix-00164_1_cfg_premixfiles'
  #premix_files = []
  #index = 0
  #with open(input_filename) as input_file:
  #  for line in input_file:
  #    index += 1
  #    premix_files.append((index, line.replace("'",'').replace(",",'').strip()))
  #
  #pool = multiprocessing.Pool()
  ##result = pool.map(exist_premix_file, premix_files[:3])
  #result = pool.map(exist_premix_file, premix_files)

  ##print(result)
  ## Save results
  #with open(result_filename, 'w') as result_file:
  #  json.dump(result, result_file)


  #result_filename = "saved_results.json.fnal"
  result_filename = "saved_results.json.kit.de"
  # Load results
  # result_json =  [(/store/mc/..., True/False)]
  with open(result_filename) as result_file:
    result_json = json.load(result_file)
  #print(result_json)

  # Convert to dict
  result_dict = {}
  nvalid = 0
  for item in result_json:
    if (item[1] == True):
      #print(item[0], item[1])
      nvalid += 1
    result_dict[item[0]] = item[1]

  # Line for cmssw configuration script
  valid_premix_fragment_name = 'valid_premix_fragment'
  line = 'process.mixData.input.fileNames = cms.untracked.vstring(['
  for item in result_json:
    if (item[1] == False): continue
    line += "'"+item[0] +"',"
  line += '])'
  with open(valid_premix_fragment_name, 'w') as valid_premix_fragment:
    valid_premix_fragment.write(line+'\n')
    print("Wrote to "+valid_premix_fragment_name)

  print("Valid premix files: "+str(nvalid)+"/"+str(len(result_dict)))

  if len(sys.argv) == 2:
    print(result_dict[sys.argv[1]])
