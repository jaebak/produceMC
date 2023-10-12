# https://cms-pdmv.cern.ch/mcm/public/restapi/requests/get_fragment/HIG-RunIISummer20UL16wmLHEGENAPV-00390
import FWCore.ParameterSet.Config as cms

# link to datacards: 
# https://github.com/cms-sw/genproductions/blob/10c5dcbdb388cffcd973e80f08244fd0057b422a/bin/Powheg/production/2017/13TeV/Higgs/ttH_inclusive_hdamp_NNPDF31_13TeV_M125/ttH_inclusive_hdamp_NNPDF31_13TeV_M125.input

externalLHEProducer = cms.EDProducer("ExternalLHEProducer",
    args = cms.vstring('/cvmfs/cms.cern.ch/phys_generator/gridpacks/2017/13TeV/powheg/V2/ttH_inclusive_hdamp_NNPDF31_13TeV_M125/v1/ttH_inclusive_hdamp_NNPDF31_13TeV_M125.tgz'),
    nEvents = cms.untracked.uint32(5000),
    numberOfParameters = cms.uint32(1),
    outputFile = cms.string('cmsgrid_final.lhe'),
    scriptName = cms.FileInPath('GeneratorInterface/LHEInterface/data/run_generic_tarball_cvmfs.sh')
)

#Link to GS fragment

from Configuration.Generator.Pythia8CommonSettings_cfi import *
from Configuration.Generator.MCTunes2017.PythiaCP5Settings_cfi import *
from Configuration.Generator.PSweightsPythia.PythiaPSweightsSettings_cfi import *
from Configuration.Generator.Pythia8PowhegEmissionVetoSettings_cfi import *

generator = cms.EDFilter("Pythia8HadronizerFilter",
                         maxEventsToPrint = cms.untracked.int32(1),
                         pythiaPylistVerbosity = cms.untracked.int32(1),
                         filterEfficiency = cms.untracked.double(1.0),
                         pythiaHepMCVerbosity = cms.untracked.bool(False),
                         comEnergy = cms.double(13000.),
                         PythiaParameters = cms.PSet(
        pythia8CommonSettingsBlock,
        pythia8CP5SettingsBlock,
        pythia8PSweightsSettingsBlock,
        pythia8PowhegEmissionVetoSettingsBlock,
        processParameters = cms.vstring(
            'POWHEG:nFinal = 3',   ## Number of final state particles
                                   ## (BEFORE THE DECAYS) in the LHE
                                   ## other than emitted extra parton
            '25:m0 = 125.0',
            '25:onMode = off',
            '25:onIfMatch = 23 22', ## H-> Z Gamma
            '23:onMode = off',
            '23:onIfAny = 11 13 15'
          ),
        parameterSets = cms.vstring('pythia8CommonSettings',
                                    'pythia8CP5Settings',
                                    'pythia8PSweightsSettings',
                                    'pythia8PowhegEmissionVetoSettings',
                                    'processParameters'
                                    )
        )
                         )

ProductionFilterSequence = cms.Sequence(generator)

