Files for producing MC with cmssw. Uses condor and singularity.  

Note that different years should use different seeds or can use `produce_*.seed.rand.sh`
Note: Use `produce_*.seed.sh` files
- `produce_mc_RunIISummer20UL18.sh` does not randomize seed for DYJets.
- `produce_mc_RunIISummer20UL18.seed.sh` will randomize seed for DYJets.
- All `produce_*SUS*.sh` seem to be not reproducable.

# Getting valid premix file list

```bash
# Setup root on el9
source /cvmfs/cms.cern.ch/cmsset_default.sh
cmsrel CMSSW_15_0_17
cd CMSSW_15_0_17/src
cmsenv
cd -

voms-proxy-init -voms cms -valid 168:0

# Create valid_premix_fragment
./scripts/find_valid_premix.py
```

# Testing production: Reference ``2021.10.23.HToAll/cmssw_generation.org``
```bash
voms-proxy-init --voms cms --out $(pwd)/voms_proxy.txt -valid 172:0
export X509_USER_PROXY=$(pwd)/voms_proxy.txt
export SINGULARITY_CACHEDIR="/tmp/$(whoami)/singularity"

# Running an example
# At UCSD for rhel6
singularity shell -B /cvmfs -B /etc/grid-security /cvmfs/singularity.opensciencegrid.org/cmssw/cms:rhel6-m20201113
# At UCSB for cc7 (Ref: https://cms-sw.github.io/singularity.html)
singularity shell -B /cvmfs -B /etc/grid-security /cvmfs/unpacked.cern.ch/registry.hub.docker.com/cmssw/el7:x86_64
# At CERN for rhel6
singularity shell -B /cvmfs -B /etc/grid-security -B /afs/cern.ch/work/j/jaebak/analysis /cvmfs/singularity.opensciencegrid.org/cmssw/cms:rhel6-m20201113
# At CMSCONNECT for cc7
unset PERL5LIB; unset PYTHONPATH; 
singularity shell -B /cvmfs -B /etc/grid-security -B /ospool/cms-user/jaebak /cvmfs/singularity.opensciencegrid.org/cmssw/cms:rhel7
# At CMSCONNECT for alma8
unset PERL5LIB; unset PYTHONPATH; 
singularity shell -B /cvmfs -B /etc/grid-security -B /ospool/cms-user/jaebak /cvmfs/singularity.opensciencegrid.org/cmssw/cms:rhel8

mkdir test
cd test
cp ../voms_proxy.txt .
cp ../config/DYJetsToLL_M-50_TuneCP5_13TeV-amcatnloFXFX-pythia8__RunIISummer20UL18__fragment.py .
cp ../replace_premix.py .
cp ../valid_premix_fragment_2018 .
../produce_mc_RunIISummer20UL18.seed.sh 0 100 ../config/DYJetsToLL_M-50_TuneCP5_13TeV-amcatnloFXFX-pythia8__RunIISummer20UL18.env 2>&1 | tee produce.log
```

# Submitting condor
```bash
# Modify config/job.sub. Change number of events. Add number of jobs after queue.
# Example:
#   arguments = $(Process) 2500 DYJetsToLL_M-50_TuneCP5_13TeV-amcatnloFXFX-pythia8__RunIISummer20UL18.env
#   queue 320
# Submit job
condor_submit config/DYJetsToLL_M-50_TuneCP5_13TeV-amcatnloFXFX-pythia8__RunIISummer20UL18.sub
# Check jobs
condor_q
```

# Submitting with crab
```bash
# When using el7: Run-2 jobs
source /cvmfs/cms.cern.ch/cmsset_default.sh
cmssw-el7
cmsrel CMSSW_10_6_47
cd CMSSW_10_6_47/src
cmsenv
cd -

# When using el8: Run-3 jobs
source /cvmfs/cms.cern.ch/cmsset_default.sh
cmssw-el8
cmsrel CMSSW_14_0_21
cd CMSSW_14_0_21/src
cmsenv
cd -

# Check if you have write permission
crab checkwrite --site=T2_KR_KISTI

crab submit -c SMS-TChiHH_2D_TuneCP5_13TeV-madgraphMLM-pythia8__RunIISummer20UL18.FullSim.crab.py

# Type in task name at https://cmsweb.cern.ch/crabserver/ui/task/ 
crab status -d crab_projects/
```

# Procedures after production

## Find how many events are produced
```bash
screen 
source /cvmfs/cms.cern.ch/cmsset_default.sh
cmsrel CMSSW_15_0_17
cd CMSSW_15_0_17/src
cmsenv
cd -

# Find good files by scanning logs. Will scan sub directories.
./scripts/make_good_file_list.py /path/to/nanoaod_folder

# Combine files
./scripts/combine_nanoaods.py --good-list good_root_files.txt
./scripts/combine_nanoaods.py --good-list good_root_files.txt -x
## OR
#./scripts/combine_nanoaods.py -i ntuple_folder 
#./scripts/combine_nanoaods.py -i ntuple_folder -x

# Check number of events
cd path_to_root_files
root
TChain ch("Events")
ch.Add("*.root")
ch.Scan("Jet_pt")
ch.GetEntries()

# Stop production if enough events
cd /path/to/produceMc
crab kill task_folder

# If multiple tasks, use below line to change filename of combined files
mv task1_nutples* task1
mv task2_nutples* task2
# Print commands
for d in task*/; do t="${d%/}"; for f in "$d"*.root; do [ -e "$f" ] || continue; printf 'mv -n -- %q %q\n' "$f" "${f%.root}-$t.root"; done; done
# Run the printed commands
for d in task*/; do t="${d%/}"; for f in "$d"*.root; do [ -e "$f" ] || continue; printf 'mv -n -- %q %q\n' "$f" "${f%.root}-$t.root"; done; done | sh

# Copy files using rsync
rsync -avzPhe ssh FILES TARGET

# Deleting files on storage
eval `scram unsetenv -sh`
gfal-rm -rv 'davs://cms-t2-se01.sdfarm.kr:2880/store/user/jaebak/FOLDERNAME/'
```

# Combining files and copying
```bash
./scripts/combine_nanoaods.py -i ntuples
./scripts/combine_nanoaods.py -i ntuples -x
rsync -avzPhe ssh FILES TARGET
```
