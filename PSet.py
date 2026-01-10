import FWCore.ParameterSet.Config as cms
process = cms.Process("DUMMY")
process.maxEvents = cms.untracked.PSet(input=cms.untracked.int32(1))
process.source = cms.Source("EmptySource")
process.options = cms.untracked.PSet(
    numberOfThreads = cms.untracked.uint32(2),
)
