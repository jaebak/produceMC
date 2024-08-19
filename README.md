Files for producing MC with cmssw. Uses condor and singularity.  

Note: Use `produce_*.seed.sh` files
- `produce_mc_RunIISummer20UL18.sh` does not randomize seed for DYJets.
- `produce_mc_RunIISummer20UL18.seed.sh` will randomize seed for DYJets.
- All `produce_*SUS*.sh` seem to be not reproducable.

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
singularity shell -B /cvmfs -B /etc/grid-security -B /ospool/cms-user/jaebak /cvmfs/singularity.opensciencegrid.org/cmssw/cms:rhel7


mkdir test
cd test
cp ../voms_proxy.txt .
cp ../config/DYJetsToLL_M-50_TuneCP5_13TeV-amcatnloFXFX-pythia8__RunIISummer20UL18__fragment.py .
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
