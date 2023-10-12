Files for producing MC with cmssw. Uses condor and singularity.  

# Testing production: Reference ``2021.10.23.HToAll/cmssw_generation.org``
```bash
voms-proxy-init --voms cms --out $(pwd)/voms_proxy.txt -valid 172:0
export X509_USER_PROXY=$(pwd)/voms_proxy.txt
export SINGULARITY_CACHEDIR="/tmp/$(whoami)/singularity"

# Running an example
# At UCSD for rhel6
singularity shell -B /cvmfs -B /etc/grid-security /cvmfs/singularity.opensciencegrid.org/cmssw/cms:rhel6-m20201113
# At UCSB for cc7 (Ref: https://cms-sw.github.io/singularity.html)
singularity shell -B /cvmfs -B /etc/grid-security /cvmfs/unpacked.cern.ch/registry.hub.docker.com/cmssw/cc7:x86_64
# At CERN for rhel6
singularity shell -B /cvmfs -B /etc/grid-security -B /afs/cern.ch/work/j/jaebak/analysis /cvmfs/singularity.opensciencegrid.org/cmssw/cms:rhel6-m20201113

./produce_mc_RunIISummer20UL18.sh 0 100 ./mc_datasets_config/DYJetsToLL_M-50_TuneCP5_13TeV-amcatnloFXFX-pythia8__RunIISummer20UL18.env 2>&1 | tee produce.log
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
