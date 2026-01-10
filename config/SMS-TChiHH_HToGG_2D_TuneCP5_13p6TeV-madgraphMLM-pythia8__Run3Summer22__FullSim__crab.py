from WMCore.Configuration import Configuration
config = Configuration()

import os
work_area = "crab_projects"
base = "SMS-TChiHH_HToGG_2D_TuneCP5_13p6TeV-madgraphMLM-pythia8__Run3Summer22__FullSim"

# Set task number
n = 1
while True:
    req = "{}{}".format(base, n)
    # CRAB creates crab_<requestName>
    path1 = os.path.join(work_area, "crab_{}".format(req))
    if not os.path.exists(path1):
        break
    n += 1

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
config.JobType.inputFiles  = ["voms_proxy.txt", "config/SMS-TChiHH_HToGG_2D_TuneCP5_13p6TeV-madgraphMLM-pythia8__Run3Summer22.FullSim.env", "config/SMS-TChiHH_HToGG_2D_TuneCP5_13p6TeV-madgraphMLM-pythia8__Run3Summer22__fragment.py", "produce_mc_Run3Summer22.SUS.seed.rand.sh"]
config.JobType.outputFiles = ["SMS-TChiHH_HToGG_2D_TuneCP5_13p6TeV-madgraphMLM-pythia8__Run3Summer22NanoAODv12-130X_mcRun3_2022_realistic_v5-v2__privateProduction__job.root"]

# Pass args to run.sh
config.JobType.scriptArgs  = ["script=produce_mc_Run3Summer22.SUS.seed.rand.sh", "events=3000", "names=SMS-TChiHH_HToGG_2D_TuneCP5_13p6TeV-madgraphMLM-pythia8__Run3Summer22.FullSim.env"]

config.section_("Data")
config.Data.outputPrimaryDataset = base
config.Data.splitting   = "EventBased"
config.Data.unitsPerJob = 1
config.Data.totalUnits  = 5000
config.Data.publication = False

config.section_("Site")
config.Site.storageSite = "T2_KR_KISTI"
