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

if [ ! -f "config/${Fragment_filename}" ]; then
  echo "config/${Fragment_filename} does not exist"
  exit
fi

if [ ! -f "voms_proxy.txt" ]; then
  echo "voms_proxy.txt does not exist"
  echo "voms-proxy-init --voms cms --out $(pwd)/voms_proxy.txt -valid 172:0"
  exit
fi

export X509_USER_PROXY=$(pwd)/voms_proxy.txt

cat <<EndOfTestFile > "$TAG"_cmd.sh
#!/bin/bash

echo "----GEN----"
# https://cms-pdmv.cern.ch/mcm/public/restapi/requests/get_test/EGM-RunIISummer20UL17wmLHEGEN-00001
echo "Setting up CMSSW"
export SCRAM_ARCH=slc7_amd64_gcc700
source /cvmfs/cms.cern.ch/cmsset_default.sh
if [ -r CMSSW_10_6_19_patch3/src ] ; then
  echo release CMSSW_10_6_19_patch3 already exists
else
  scram p CMSSW CMSSW_10_6_19_patch3
fi
cd CMSSW_10_6_19_patch3/src
eval \`scram runtime -sh\`
# Setup custom fragment for CMSSW
mkdir -p Configuration/GenProduction/python
cp ../../config/${Fragment_filename} Configuration/GenProduction/python
scram b
cd ../..

echo "Make cmssw configuration file"
Output_filename=$AOD_NAME"__job-"${JOBNUM}"__LHE".root
cmsDriver.py Configuration/GenProduction/python/$Fragment_filename --python_filename "$TAG"__LHE__cfg.py --eventcontent RAWSIM,LHE --customise Configuration/DataProcessing/Utils.addMonitoring --datatier GEN,LHE --fileout file:\$Output_filename --conditions 106X_mc2017_realistic_v6 --beamspot Realistic25ns13TeVEarly2017Collision --customise_commands "process.source.numberEventsInLuminosityBlock = cms.untracked.uint32(100) \n process.source.firstRun = cms.untracked.uint32(${JOBNUM})" --step LHE,GEN --geometry DB:Extended --era Run2_2017 --no_exec --mc -n $NEVENTS

echo "Run cmssw with configuration file"
cmsRun "$TAG"__LHE__cfg.py

echo "----SIM----"
# https://cms-pdmv.cern.ch/mcm/public/restapi/requests/get_test/EGM-RunIISummer20UL17SIM-00002
echo "Setting up CMSSW"
export SCRAM_ARCH=slc7_amd64_gcc700
source /cvmfs/cms.cern.ch/cmsset_default.sh
if [ -r CMSSW_10_6_17_patch1/src ] ; then
  echo release CMSSW_10_6_17_patch1 already exists
else
  scram p CMSSW CMSSW_10_6_17_patch1
fi
cd CMSSW_10_6_17_patch1/src
eval \`scram runtime -sh\`
# Setup custom fragment for CMSSW
scram b
cd ../..

echo "Make cmssw configuration file"
Input_filename=$AOD_NAME"__job-"${JOBNUM}"__LHE".root
Output_filename=$AOD_NAME"__job-"${JOBNUM}"__SIM".root
cmsDriver.py --python_filename "$TAG"__SIM__cfg.py --eventcontent RAWSIM --customise Configuration/DataProcessing/Utils.addMonitoring --datatier GEN-SIM --fileout file:\$Output_filename --conditions 106X_mc2017_realistic_v6 --beamspot Realistic25ns13TeVEarly2017Collision --step SIM --geometry DB:Extended --filein file:\$Input_filename --era Run2_2017 --runUnscheduled --no_exec --mc -n -1

echo "Run cmssw with configuration file"
cmsRun "$TAG"__SIM__cfg.py

echo "----DIGIPREMIX----"
# https://cms-pdmv.cern.ch/mcm/public/restapi/requests/get_test/EGM-RunIISummer20UL17DIGIPremix-00002
echo "Setting up CMSSW"
export SCRAM_ARCH=slc7_amd64_gcc700
source /cvmfs/cms.cern.ch/cmsset_default.sh
if [ -r CMSSW_10_6_17_patch1/src ] ; then
  echo release CMSSW_10_6_17_patch1 already exists
else
  scram p CMSSW CMSSW_10_6_17_patch1
fi
cd CMSSW_10_6_17_patch1/src
eval \`scram runtime -sh\`
# Setup custom fragment for CMSSW
scram b
cd ../..

echo "Make cmssw configuration file"
Input_filename=$AOD_NAME"__job-"${JOBNUM}"__SIM".root
Output_filename=$AOD_NAME"__job-"${JOBNUM}"__DIGIPREMIX".root
cmsDriver.py --python_filename "$TAG"__DIGIPREMIX__cfg.py --eventcontent PREMIXRAW --customise Configuration/DataProcessing/Utils.addMonitoring --datatier GEN-SIM-DIGI --fileout file:\$Output_filename --pileup_input "dbs:/Neutrino_E-10_gun/RunIISummer20ULPrePremix-UL17_106X_mc2017_realistic_v6-v3/PREMIX" --conditions 106X_mc2017_realistic_v6 --step DIGI,DATAMIX,L1,DIGI2RAW --procModifiers premix_stage2 --geometry DB:Extended --filein file:\$Input_filename --datamix PreMix --era Run2_2017 --runUnscheduled --no_exec --mc -n -1

echo "Run cmssw with configuration file"
cmsRun "$TAG"__DIGIPREMIX__cfg.py

echo "----HLT----"
# https://cms-pdmv.cern.ch/mcm/public/restapi/requests/get_test/EGM-RunIISummer20UL17HLT-00002
echo "Setting up CMSSW"
export SCRAM_ARCH=slc7_amd64_gcc630
source /cvmfs/cms.cern.ch/cmsset_default.sh
if [ -r CMSSW_9_4_14_UL_patch1/src ] ; then
  echo release CMSSW_9_4_14_UL_patch1 already exists
else
  scram p CMSSW CMSSW_9_4_14_UL_patch1
fi
cd CMSSW_9_4_14_UL_patch1/src
eval \`scram runtime -sh\`
# Setup custom fragment for CMSSW
scram b
cd ../..

echo "Make cmssw configuration file"
Input_filename=$AOD_NAME"__job-"${JOBNUM}"__DIGIPREMIX".root
Output_filename=$AOD_NAME"__job-"${JOBNUM}"__HLT".root
cmsDriver.py --python_filename "$TAG"__HLT__cfg.py --eventcontent RAWSIM --customise Configuration/DataProcessing/Utils.addMonitoring --datatier GEN-SIM-RAW --fileout file:\$Output_filename --conditions 94X_mc2017_realistic_v15 --customise_commands 'process.source.bypassVersionCheck = cms.untracked.bool(True)' --step HLT:2e34v40 --geometry DB:Extended --filein file:\$Input_filename --era Run2_2017 --no_exec --mc -n -1

echo "Run cmssw with configuration file"
cmsRun "$TAG"__HLT__cfg.py

echo "----RECO----"
# https://cms-pdmv.cern.ch/mcm/public/restapi/requests/get_test/EGM-RunIISummer20UL17RECO-00002
echo "Setting up CMSSW"
export SCRAM_ARCH=slc7_amd64_gcc700
source /cvmfs/cms.cern.ch/cmsset_default.sh
if [ -r CMSSW_10_6_17_patch1/src ] ; then
  echo release CMSSW_10_6_17_patch1 already exists
else
  scram p CMSSW CMSSW_10_6_17_patch1
fi
cd CMSSW_10_6_17_patch1/src
eval \`scram runtime -sh\`
# Setup custom fragment for CMSSW
scram b
cd ../..

echo "Make cmssw configuration file"
Input_filename=$AOD_NAME"__job-"${JOBNUM}"__HLT".root
Output_filename=$AOD_NAME"__job-"${JOBNUM}.root
cmsDriver.py --python_filename "$TAG"__AOD__cfg.py --eventcontent AODSIM --customise Configuration/DataProcessing/Utils.addMonitoring --datatier AODSIM --fileout file:\$Output_filename --conditions 106X_mc2017_realistic_v6 --step RAW2DIGI,L1Reco,RECO,RECOSIM --geometry DB:Extended --filein file:\$Input_filename --era Run2_2017 --runUnscheduled --no_exec --mc -n -1

echo "Run cmssw with configuration file"
cmsRun "$TAG"__AOD__cfg.py

echo "----MiniAODv2----"
# https://cms-pdmv.cern.ch/mcm/public/restapi/requests/get_test/EGM-RunIISummer20UL17MiniAODv2-00002
echo "Setting up CMSSW"
export SCRAM_ARCH=slc7_amd64_gcc700
source /cvmfs/cms.cern.ch/cmsset_default.sh
if [ -r CMSSW_10_6_20/src ] ; then
  echo release CMSSW_10_6_20 already exists
else
  scram p CMSSW CMSSW_10_6_20
fi
cd CMSSW_10_6_20/src
eval \`scram runtime -sh\`
scram b
cd ../..

echo "Make cmssw configuration file"
Input_filename=$AOD_NAME"__job-"${JOBNUM}.root
Output_filename=$MINIAOD_NAME"__job-"${JOBNUM}.root
cmsDriver.py  --python_filename "$TAG"__MiniAODv2__cfg.py --eventcontent MINIAODSIM --customise Configuration/DataProcessing/Utils.addMonitoring --datatier MINIAODSIM --fileout file:\$Output_filename --conditions 106X_mc2017_realistic_v9 --step PAT --procModifiers run2_miniAOD_UL --geometry DB:Extended --filein file:\$Input_filename --era Run2_2017 --runUnscheduled --no_exec --mc -n -1

echo "Run cmssw with configuration file"
cmsRun "$TAG"__MiniAODv2__cfg.py

echo "----NanoAODv9----"
# https://cms-pdmv.cern.ch/mcm/public/restapi/requests/get_test/EGM-RunIISummer20UL17NanoAODv9-00002
echo "Setting up CMSSW"
export SCRAM_ARCH=slc7_amd64_gcc700
source /cvmfs/cms.cern.ch/cmsset_default.sh
if [ -r CMSSW_10_6_26/src ] ; then
  echo release CMSSW_10_6_26 already exists
else
  scram p CMSSW CMSSW_10_6_26
fi
cd CMSSW_10_6_26/src
eval \`scram runtime -sh\`
scram b
cd ../..

echo "Make cmssw configuration file"
Input_filename=$MINIAOD_NAME"__job-"${JOBNUM}.root
Output_filename=$NANOAOD_NAME"__job-"${JOBNUM}.root
cmsDriver.py --python_filename "$TAG"__NanoAODv9__cfg.py --eventcontent NANOAODSIM --customise Configuration/DataProcessing/Utils.addMonitoring --datatier NANOAODSIM --fileout file:\$Output_filename --conditions 106X_mc2017_realistic_v9 --step NANO --filein file:\$Input_filename --era Run2_2017,run2_nanoAOD_106Xv2 --no_exec --mc -n -1

echo "Run cmssw with configuration file"
cmsRun "$TAG"__NanoAODv9__cfg.py

echo "Clean up files"

rm -f ${TAG}__LHE__cfg.py
rm -rf CMSSW_10_6_19_patch3
rm -f ${AOD_NAME}__job-${JOBNUM}__LHE.root
rm -f ${AOD_NAME}__job-${JOBNUM}__LHE_inLHE.root

rm -f ${TAG}__SIM__cfg.py
rm -rf CMSSW_10_6_17_patch1
rm -f ${AOD_NAME}__job-${JOBNUM}__SIM.root
rm -f "$TAG"__DIGIPREMIX__cfg.py
rm -f ${AOD_NAME}__job-${JOBNUM}__DIGIPREMIX.root

rm -rf CMSSW_9_4_14_UL_patch1
rm -f ${AOD_NAME}__job-${JOBNUM}__HLT.root
rm -f ${TAG}__HLT__cfg.py

rm -f ${TAG}__AOD__cfg.py
rm -f ${AOD_NAME}__job-${JOBNUM}.root

rm -rf CMSSW_10_6_20/
rm -f ${TAG}__MiniAODv2__cfg.py

rm -rf CMSSW_10_6_26/
rm -f ${TAG}__NanoAODv9__cfg.py

# End of "$TAG"_cmd.sh file
EndOfTestFile

echo "Made "$TAG"_cmd.sh"
chmod +x "$TAG"_cmd.sh

#export SINGULARITY_CACHEDIR="/tmp/$(whoami)/singularity"
#singularity run -B /cvmfs -B /etc/grid-security docker://cmssw/slc6:latest $(echo $(pwd)/"$TAG"_cmd.sh)

./${TAG}_cmd.sh

rm ${TAG}_cmd.sh
