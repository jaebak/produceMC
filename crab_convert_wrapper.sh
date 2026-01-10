#!/bin/bash
set -euo pipefail

echo "=== Args received (argc=$#) ==="
i=1
for a in "$@"; do
  echo "arg[$i] = <$a>"
  i=$((i+1))
done
echo "==============================="

# First arg is the jobID (bare number)
JOBID=$1
shift || true

SCRIPT=""
EVENTS=""
NAMES=""

# Parse remaining key=value arguments
for a in "$@"; do
  case "$a" in
    script=*) SCRIPT="${a#*=}" ;;
    events=*) EVENTS="${a#*=}" ;;
    names=*)  NAMES="${a#*=}" ;;
    *) echo "WARNING: unknown arg '$a' (expected script=, events=, names=)" ;;
  esac
done

# Validate
[[ -n "$SCRIPT" ]] || { echo "ERROR: missing script=..."; exit 2; }
[[ -n "$EVENTS" ]] || { echo "ERROR: missing events=..."; exit 2; }
[[ -n "$NAMES"  ]] || { echo "ERROR: missing names=..."; exit 2; }

# Ensure files exist
[[ -f "$SCRIPT" ]] || { echo "ERROR: $SCRIPT not found"; ls -lah; exit 3; }
[[ -f "$NAMES"  ]] || { echo "ERROR: $NAMES not found";  ls -lah; exit 3; }

echo "Running: ./$SCRIPT $JOBID $EVENTS $NAMES"
bash "./$SCRIPT" "$JOBID" "$EVENTS" "$NAMES"

echo "Changing filename"
for f in *__job-[0-9]*.root; do
  [ -e "$f" ] || continue
  mv -- "$f" "${f%-[0-9]*.root}.root"
done

echo "=== Producing FrameworkJobReport.xml (required by CRAB wrapper) ==="
source /cvmfs/cms.cern.ch/cmsset_default.sh
# If CRAB shipped CMSSW (typical), CMSSW_BASE is set:
if [[ -n "${CMSSW_BASE:-}" && -d "${CMSSW_BASE}/src" ]]; then
  cd "${CMSSW_BASE}/src"
  eval "$(scramv1 runtime -sh)"
  cd -
fi
# Run a tiny cmsRun using your dummy PSet.py and write the job report
cmsRun -j FrameworkJobReport.xml PSet.py
# sanity check
test -s FrameworkJobReport.xml || { echo "FrameworkJobReport.xml missing/empty"; exit 90; }
