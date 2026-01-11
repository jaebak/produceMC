from WMCore.Configuration import Configuration
config = Configuration()

import os
work_area = "crab_projects"
base = "SMS-TChiHH_2D_TuneCP5_13p6TeV-madgraphMLM-pythia8__Run3Summer23BPix__FullSim"

# Set task number
n = 1
while True:
    req = "{}{}".format(base, n)
    # CRAB creates crab_<requestName>
    path1 = os.path.join(work_area, "crab_{}".format(req))
    if not os.path.exists(path1):
        break
    n += 1

config.section_("Debug")
config.section_("General")
config.General.requestName = req
config.General.workArea = work_area
config.General.transferLogs = True
config.General.transferOutputs = True

config.section_("JobType")
config.JobType.pluginName  = "PrivateMC"
config.JobType.psetName    = "PSet.py"
config.JobType.scriptExe   = "crab_convert_wrapper.sh"
config.JobType.numCores = 2
config.JobType.maxMemoryMB = 5000
config.JobType.maxJobRuntimeMin = 2750
config.Debug.extraJDL = ["request_disk = 8000000"]
config.JobType.inputFiles  = ["voms_proxy.txt", "config/SMS-TChiHH_2D_TuneCP5_13p6TeV-madgraphMLM-pythia8__Run3Summer23BPix.FullSim.env", "config/SMS-TChiHH_2D_TuneCP5_13p6TeV-madgraphMLM-pythia8__Run3Summer23BPix__fragment.py", "produce_mc_Run3Summer23BPix.SUS.seed.rand.sh"]
config.JobType.outputFiles = ["SMS-TChiHH_2D_TuneCP5_13p6TeV-madgraphMLM-pythia8__Run3Summer23BPixNanoAODv12-130X_mcRun3_2023_realistic_postBPix_v6-v2__privateProduction__job.root"]

config.section_("Data")
config.Data.outputPrimaryDataset = base
config.Data.splitting   = "EventBased"
config.Data.unitsPerJob = 1

config.JobType.scriptArgs  = ["script=produce_mc_Run3Summer23BPix.SUS.seed.rand.sh", "events=3000", "names=SMS-TChiHH_2D_TuneCP5_13p6TeV-madgraphMLM-pythia8__Run3Summer23BPix.FullSim.env"]
config.Data.totalUnits  = 5000

config.Data.publication = False

config.section_("Site")
config.Site.storageSite = "T2_KR_KISTI"
