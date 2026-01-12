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
OUTROOT=""
for f in *__job-[0-9]*.root; do
  [ -e "$f" ] || continue
  OUTROOT="${f%-[0-9]*.root}.root"
  mv -- "$f" "$OUTROOT"
  break
done

[[ -n "$OUTROOT" && -f "$OUTROOT" ]] || { echo "ERROR: no output root file found"; exit 20; }

echo "=== Checking Events tree entries in $OUTROOT ==="
NEV="$(root -l -b -q -e "TFile f(\"$OUTROOT\"); auto t=(TTree*)f.Get(\"Events\"); if(!t){std::cout<<0; gSystem->Exit(0);} std::cout<<t->GetEntries(); gSystem->Exit(0);" \
  2>/dev/null | tail -n 1 | tr -d '[:space:]')"
[[ "$NEV" =~ ^[0-9]+$ ]] || NEV=0
echo "Events = $NEV"

STATUS=0
if [[ "$NEV" -eq 0 ]]; then
  echo "ERROR: Events tree has 0 entries"
  STATUS=21
fi

echo "=== Producing FrameworkJobReport.xml (required by CRAB wrapper) ==="
cmsRun -j FrameworkJobReport.xml PSet.py || true
test -s FrameworkJobReport.xml || { echo "FrameworkJobReport.xml missing/empty"; exit 90; }

exit "$STATUS"
