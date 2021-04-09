#!/bin/bash
# Requires below files
# - voms_proxy.txt : From voms-proxy-init --voms cms --out $(pwd)/voms_proxy.txt -valid 172:0
# - ENV_FILE : Sets names for Fragment_filename, AOD_NAME, MINIAOD_NAME, NANOAOD_NAME, BASE_TAG
#     Fragment_filename="SMS-TChiHH_mChi-500_mLSP-1__RunIISummer16__fragment.py"
#     AOD_NAME="SMS-TChiHH_mChi-500_mLSP-1_TuneCUETP8M1_13TeV-madgraphMLM-pythia8__RunIISummer16AOD__PUSummer16v3Fast_80X_mcRun2_asymptotic__privateProduction"
#     MINIAOD_NAME="SMS-TChiHH_mChi-500_mLSP-1_TuneCUETP8M1_13TeV-madgraphMLM-pythia8__RunIISummer16MiniAODv3__PUSummer16v3Fast_94X_mcRun2_asymptotic_v3-v1__privateProduction"
#     NANOAOD_NAME="SMS-TChiHH_mChi-500_mLSP-1_TuneCUETP8M1_13TeV-madgraphMLM-pythia8__RunIISummer16NanoAODv7__PUSummer16v3Fast_Nano02Apr2020_102X_mcRun2_asymptotic_v8-v1__privateProduction"
#     BASE_TAG="SMS-TChiHH_mChi-500_mLSP-1__RunIISummer16"
# - fragment.py: Fragment should match the name in ENV_FILE. Will be copied to CMSSW/src/Configuration/GenProduction/python/ 
# Requires a job number and number of events
if [ $# -ne 3 ]; then
  echo "[Usage] $0 JOB_NUMBER NUMBER_OF_EVENTS ENV_FILE"
  echo "  JOB_NUMBER is used for file names and run number to randomize between jobs"
  echo "  ENV_FILE is used to set names"
  exit
fi

if [ ! -f "$3" ]; then
  echo "ENV_FILE does not exist"
  echo "  ENV_FILE : Sets names for Fragment_filename, AOD_NAME, MINIAOD_NAME, NANOAOD_NAME, BASE_TAG"
  echo '  Example'
  echo '    Fragment_filename="SMS-TChiHH_mChi-500_mLSP-1__RunIISummer16__fragment.py"'
  echo '    AOD_NAME="SMS-TChiHH_mChi-500_mLSP-1_TuneCUETP8M1_13TeV-madgraphMLM-pythia8__RunIISummer16AOD__PUSummer16v3Fast_80X_mcRun2_asymptotic__privateProduction"'
  echo '    MINIAOD_NAME="SMS-TChiHH_mChi-500_mLSP-1_TuneCUETP8M1_13TeV-madgraphMLM-pythia8__RunIISummer16MiniAODv3__PUSummer16v3Fast_94X_mcRun2_asymptotic_v3-v1__privateProduction"'
  echo '    NANOAOD_NAME="SMS-TChiHH_mChi-500_mLSP-1_TuneCUETP8M1_13TeV-madgraphMLM-pythia8__RunIISummer16NanoAODv7__PUSummer16v3Fast_Nano02Apr2020_102X_mcRun2_asymptotic_v8-v1__privateProduction"'
  echo '    BASE_TAG="SMS-TChiHH_mChi-500_mLSP-1__RunIISummer16"'
  exit
fi

source $3
echo "Set below variables with $3"
echo Fragment_filename \= $Fragment_filename
echo AOD_NAME \= $AOD_NAME
echo MINIAOD_NAME \= $MINIAOD_NAME
echo NANOAOD_NAME \= $NANOAOD_NAME
echo BASE_TAG \= $BASE_TAG

# Set variables
JOBNUM=$(($1+1)) #$1 will start from 0. Need to add at least 1.
NEVENTS=$2
TAG="$BASE_TAG""__job-"${JOBNUM}
#Fragment_filename="SUS-RunIISummer16FSPremix-00164-fragment_custom.py"
#AOD_NAME="SMS-TChiHH_mChi-500_mLSP-1_TuneCUETP8M1_13TeV-madgraphMLM-pythia8__RunIISummer16AOD__PUSummer16v3Fast_80X_mcRun2_asymptotic__privateProduction__"$JOBNUM".root"
#MINIAOD_NAME="SMS-TChiHH_mChi-500_mLSP-1_TuneCUETP8M1_13TeV-madgraphMLM-pythia8__RunIISummer16MiniAODv3__PUSummer16v3Fast_94X_mcRun2_asymptotic_v3-v1__privateProduction__"$JOBNUM".root"
#NANOAOD_NAME="SMS-TChiHH_mChi-500_mLSP-1_TuneCUETP8M1_13TeV-madgraphMLM-pythia8__RunIISummer16NanoAODv7__PUSummer16v3Fast_Nano02Apr2020_102X_mcRun2_asymptotic_v8-v1__privateProduction__"$JOBNUM".root"

if [ ! -f "$Fragment_filename" ]; then
  echo "$Fragment_filename does not exist"
  exit
fi

if [ ! -f "voms_proxy.txt" ]; then
  echo "voms_proxy.txt does not exist"
  echo "voms-proxy-init --voms cms --out $(pwd)/voms_proxy.txt -valid 172:0"
  exit
fi

export X509_USER_PROXY=$(pwd)/voms_proxy.txt

cat <<EndOfTestFile > cmd_"$TAG".sh
#!/bin/bash

echo "----GEN-SIM-DIGI-RAW----"
# https://cms-pdmv.cern.ch/mcm/public/restapi/requests/get_test/SUS-RunIIFall17FSPremix-00140
echo "Setting up CMSSW"
export SCRAM_ARCH=slc6_amd64_gcc630
source /cvmfs/cms.cern.ch/cmsset_default.sh
if [ -r CMSSW_9_4_12/src ] ; then
  echo release CMSSW_9_4_12 already exists
else
  scram p CMSSW CMSSW_9_4_12
fi
cd CMSSW_9_4_12/src
eval \`scram runtime -sh\`
# Setup custom fragment for CMSSW
mkdir -p Configuration/GenProduction/python
cp ../../$Fragment_filename Configuration/GenProduction/python
scram b
cd ../..

echo "Make cmssw configuration file"
Output_filename=$AOD_NAME"__job-"${JOBNUM}.root
cmsDriver.py Configuration/GenProduction/python/$Fragment_filename --python_filename AOD_"$TAG"_cfg.py --eventcontent AODSIM --customise Configuration/DataProcessing/Utils.addMonitoring --datatier AODSIM --fileout file:\$Output_filename --pileup_input "dbs:/Neutrino_E-10_gun/RunIIFall17FSPrePremix-PUMoriond17_94X_mc2017_realistic_v15-v1/GEN-SIM-DIGI-RAW" --conditions 94X_mc2017_realistic_v15 --beamspot Realistic25ns13TeVEarly2017Collision --customise_commands "process.source.numberEventsInLuminosityBlock = cms.untracked.uint32(200) \n process.source.firstRun = cms.untracked.uint32(${JOBNUM})" --step GEN,SIM,RECOBEFMIX,DIGIPREMIX_S2,DATAMIX,L1,DIGI2RAW,L1Reco,RECO --datamix PreMix --era Run2_2017_FastSim --fast --no_exec --mc -n $NEVENTS

echo "Run cmssw with configuration file"
cmsRun AOD_"$TAG"_cfg.py

echo "Clean up files"
rm NuclearInteractionOutputFile.txt
rm AOD_"$TAG"_cfg.py
rm -rf CMSSW_9_4_12

echo "----MiniAODv3----"
# https://cms-pdmv.cern.ch/mcm/requests?prepid=SUS-RunIIFall17MiniAODv2-00421&page=0&shown=524415
echo "Setting up CMSSW"
export SCRAM_ARCH=slc6_amd64_gcc630
source /cvmfs/cms.cern.ch/cmsset_default.sh
if [ -r CMSSW_9_4_12/src ] ; then
  echo release CMSSW_9_4_12 already exists
else
  scram p CMSSW CMSSW_9_4_12
fi
cd CMSSW_9_4_12/src
eval \`scram runtime -sh\`
scram b
cd ../..

echo "Make cmssw configuration file"
Input_filename=$AOD_NAME"__job-"${JOBNUM}.root
Output_filename=$MINIAOD_NAME"__job-"${JOBNUM}.root
cmsDriver.py  --python_filename MiniAODv3_"$TAG"_cfg.py --eventcontent MINIAODSIM --customise Configuration/DataProcessing/Utils.addMonitoring --datatier MINIAODSIM --fileout file:\$Output_filename --conditions 94X_mc2017_realistic_v15 --step PAT --scenario pp --filein file:\$Input_filename --era Run2_2017_FastSim,run2_miniAOD_94XFall17 --runUnscheduled --fast --no_exec --mc -n -1

echo "Run cmssw with configuration file"
cmsRun MiniAODv3_"$TAG"_cfg.py

echo "Clean up files"
rm MiniAODv3_"$TAG"_cfg.py
rm "$AOD_NAME"__job-"${JOBNUM}".root
rm -rf CMSSW_9_4_12

echo "----NanoAODv7----"
# https://cms-pdmv.cern.ch/mcm/requests?prepid=SUS-RunIIFall17NanoAODv7-00406&page=0&shown=524415
echo "Setting up CMSSW"
export SCRAM_ARCH=slc6_amd64_gcc700
source /cvmfs/cms.cern.ch/cmsset_default.sh
if [ -r CMSSW_10_2_22/src ] ; then
  echo release CMSSW_10_2_22 already exists
else
  scram p CMSSW CMSSW_10_2_22
fi
cd CMSSW_10_2_22/src
eval \`scram runtime -sh\`
scram b
cd ../..

echo "Make cmssw configuration file"
Input_filename=$MINIAOD_NAME"__job-"${JOBNUM}.root
Output_filename=$NANOAOD_NAME"__job-"${JOBNUM}.root
cmsDriver.py --python_filename NanoAODv7_"$TAG"_cfg.py --eventcontent NANOAODSIM --customise Configuration/DataProcessing/Utils.addMonitoring --datatier NANOAODSIM --fileout file:\$Output_filename --conditions 102X_mc2017_realistic_v8 --step NANO --filein file:\$Input_filename --era Run2_2017,run2_nanoAOD_94XMiniAODv2 --fast --no_exec --mc -n -1

echo "Run cmssw with configuration file"
cmsRun NanoAODv7_"$TAG"_cfg.py

echo "Clean up files"
rm NanoAODv7_"$TAG"_cfg.py
rm -rf CMSSW_10_2_22

# End of cmd_"$TAG".sh file
EndOfTestFile

echo "Made cmd_"$TAG".sh"
chmod +x cmd_"$TAG".sh

#export SINGULARITY_CACHEDIR="/tmp/$(whoami)/singularity"
#singularity run -B /cvmfs -B /etc/grid-security docker://cmssw/slc6:latest $(echo $(pwd)/cmd_"$TAG".sh)

./cmd_"$TAG".sh

rm cmd_"$TAG".sh
