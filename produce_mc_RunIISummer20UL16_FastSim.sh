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

mkdir config
mv $Fragment_filename config

if [ ! -f "config/$Fragment_filename" ]; then
  echo "config/$Fragment_filename does not exist"
  exit
fi

if [ ! -f "voms_proxy.txt" ]; then
  echo "voms_proxy.txt does not exist"
  echo "voms-proxy-init --voms cms --out $(pwd)/voms_proxy.txt -valid 172:0"
  exit
fi

export X509_USER_PROXY=$(pwd)/voms_proxy.txt

BASE_DIR=$(pwd)
#OUTPUT_DIR=${BASE_DIR}/output/${TAG}
Fragment_path=${BASE_DIR}/config/$Fragment_filename

#SLEEP_TIME=$(expr $1 / 8 \* 1800) # Do 4 jobs at a time. Wait 30 min for xz to pass step
#echo "Will wait for ${SLEEP_TIME}" 
#sleep ${SLEEP_TIME}

mkdir job_scripts

cat <<EndOfTestFile > job_scripts/cmd_"$TAG".sh
#!/bin/bash

#mkdir ${OUTPUT_DIR}
#cd ${OUTPUT_DIR}

echo "----GEN-SIM-DIGI-RAW----"
# https://cms-pdmv-prod.web.cern.ch/mcm/requests?prepid=SUS-RunIISpring21UL16FSGSPremixLLPBugFix-00023&page=0&shown=127
echo "Setting up CMSSW"
export SCRAM_ARCH=slc7_amd64_gcc700
source /cvmfs/cms.cern.ch/cmsset_default.sh
if [ -r CMSSW_10_6_30/src ] ; then
  echo release CMSSW_10_6_30 already exists
else
  scram p CMSSW CMSSW_10_6_30
fi
cd CMSSW_10_6_30/src
eval \`scram runtime -sh\`
# Setup custom fragment for CMSSW
mkdir -p Configuration/GenProduction/python
cp $Fragment_path Configuration/GenProduction/python
scram b
cd ../..

echo "Make cmssw configuration file"
Output_filename=$AOD_NAME"__job-"${JOBNUM}.root
cmsDriver.py Configuration/GenProduction/python/$Fragment_filename --python_filename AOD_"$TAG"_cfg.py --eventcontent AODSIM --customise Configuration/DataProcessing/Utils.addMonitoring --datatier AODSIM --fileout file:\$Output_filename --pileup_input "dbs:/Neutrino_E-10_gun/RunIIFall17FSPrePremix-PUFSUL16CP5_106X_mcRun2_asymptotic_v16-v1/PREMIX" --conditions 106X_mcRun2_asymptotic_v17 --beamspot Realistic25ns13TeV2016Collision --customise_commands "process.source.numberEventsInLuminosityBlock = cms.untracked.uint32(200)" \\n process.source.numberEventsInLuminosityBlock="cms.untracked.uint32(223) \n process.source.firstRun = cms.untracked.uint32(${JOBNUM})" --step GEN,SIM,RECOBEFMIX,DIGI,DATAMIX,L1,DIGI2RAW,L1Reco,RECO --procModifiers premix_stage2,fastSimFixLongLivedBug --datamix PreMix --era Run2_2016 --fast --no_exec --mc -n $NEVENTS

echo "Run cmssw with configuration file"
cmsRun AOD_"$TAG"_cfg.py

echo "Clean up files"
rm NuclearInteractionOutputFile.txt
rm AOD_"$TAG"_cfg.py
rm -rf CMSSW_10_6_30

echo "----MiniAODv2----"
# https://cms-pdmv-prod.web.cern.ch/mcm/requests?prepid=SUS-RunIISummer20UL16MiniAODv2-00137&page=0&shown=127
echo "Setting up CMSSW"
export SCRAM_ARCH=slc7_amd64_gcc700
source /cvmfs/cms.cern.ch/cmsset_default.sh
if [ -r CMSSW_10_6_29/src ] ; then
  echo release CMSSW_10_6_29 already exists
else
  scram p CMSSW CMSSW_10_6_29
fi
cd CMSSW_10_6_29/src
eval \`scram runtime -sh\`
scram b
cd ../..

echo "Make cmssw configuration file"
Input_filename=$AOD_NAME"__job-"${JOBNUM}.root
Output_filename=$MINIAOD_NAME"__job-"${JOBNUM}.root
cmsDriver.py  --python_filename MiniAODv2_"$TAG"_cfg.py --eventcontent MINIAODSIM --customise Configuration/DataProcessing/Utils.addMonitoring --datatier MINIAODSIM --fileout file:\$Output_filename --conditions 106X_mcRun2_asymptotic_v17 --step PAT --procModifiers run2_miniAOD_UL --geometry DB:Extended --filein file:\$Input_filename --era Run2_2016 --fast --runUnscheduled --no_exec --mc -n -1

echo "Run cmssw with configuration file"
cmsRun MiniAODv2_"$TAG"_cfg.py

echo "Clean up files"
rm MiniAODv2_"$TAG"_cfg.py
rm "$AOD_NAME"__job-"${JOBNUM}".root
#rm -rf CMSSW_10_6_29

echo "----NanoAODv7----"
# https://cms-pdmv-prod.web.cern.ch/mcm/requests?prepid=SUS-RunIISpring21UL16FSGSPremixLLPBugFix-00023&page=0&shown=127
echo "Setting up CMSSW"
export SCRAM_ARCH=slc7_amd64_gcc700
source /cvmfs/cms.cern.ch/cmsset_default.sh
if [ -r CMSSW_10_6_29/src ] ; then
  echo release CMSSW_10_6_29 already exists
else
  scram p CMSSW CMSSW_10_6_29
fi
cd CMSSW_10_6_29/src
eval \`scram runtime -sh\`
scram b
cd ../..

echo "Make cmssw configuration file"
Input_filename=$MINIAOD_NAME"__job-"${JOBNUM}.root
Output_filename=$NANOAOD_NAME"__job-"${JOBNUM}.root
cmsDriver.py --python_filename NanoAODv9_"$TAG"_cfg.py --eventcontent NANOAODSIM --customise Configuration/DataProcessing/Utils.addMonitoring --datatier NANOAODSIM --fileout file:\$Output_filename --conditions 106X_mcRun2_asymptotic_v17 --step NANO --filein file:\$Input_filename --era Run2_2016,run2_nanoAOD_106Xv2 --fast --no_exec --mc -n -1

echo "Run cmssw with configuration file"
cmsRun NanoAODv9_"$TAG"_cfg.py

echo "Clean up files"
rm NanoAODv9_"$TAG"_cfg.py
rm -rf CMSSW_10_6_29

# End of cmd_"$TAG".sh file
EndOfTestFile

echo "Made cmd_"$TAG".sh"
chmod +x job_scripts/cmd_"$TAG".sh

#export SINGULARITY_CACHEDIR="/tmp/$(whoami)/singularity"
#singularity run -B /cvmfs -B /etc/grid-security docker://cmssw/slc6:latest $(echo $(pwd)/cmd_"$TAG".sh)
#singularity run -B /cvmfs -B /etc/grid-security -B /data -B /net/cms11/data/jbkim/analysis.cms11 -B /net/cms18/cms18r0/jbkim/produceMC /cvmfs/singularity.opensciencegrid.org/cmssw/cms:rhel6-m20201113 $(echo $(pwd)/job_scripts/cmd_"$TAG".sh)
#singularity run -B /cvmfs -B /etc/grid-security -B /data -B /net/cms11/data/jbkim/analysis.cms11 -B /net/cms18/cms18r0/jbkim/produceMC /cvmfs/unpacked.cern.ch/registry.hub.docker.com/cmssw/el7:x86_64 $(echo $(pwd)/job_scripts/cmd_"$TAG".sh)
./job_scripts/cmd_"$TAG".sh
