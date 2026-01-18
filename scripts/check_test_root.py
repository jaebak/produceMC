#!/usr/bin/env python3
# check_nanoaod_dir_jets.py
#
# Usage:
#   python3 check_nanoaod_dir_jets.py /path/to/target_dir
#
# Optional:
#   python3 check_nanoaod_dir_jets.py /path/to/target_dir --recursive
#   python3 check_nanoaod_dir_jets.py /path/to/target_dir --pattern "*.root"
#   python3 check_nanoaod_dir_jets.py /path/to/target_dir --scan-events 10 --jets-per-event 12

import argparse
import math
import sys
from pathlib import Path

import ROOT


def is_finite(x: float) -> bool:
    return not (math.isnan(x) or math.isinf(x))


def safe_float(x) -> float:
    try:
        return float(x)
    except Exception:
        return float("nan")


def normalize_preview(preview, ndigits=6):
    norm = []
    for x in preview:
        x = safe_float(x)
        if math.isnan(x):
            norm.append(("nan",))
        elif math.isinf(x):
            norm.append(("inf", 1 if x > 0 else -1))
        else:
            norm.append(round(x, ndigits))
    return tuple(norm)


def open_events_tree(fname: str):
    f = ROOT.TFile.Open(fname)
    if not f or f.IsZombie():
        raise RuntimeError(f"Could not open ROOT file (or file is zombie): {fname}")
    t = f.Get("Events")
    if not t:
        raise RuntimeError(f"'Events' tree not found in file: {fname}")
    return f, t


def branch_to_list(obj, n_hint: int = -1):
    """
    Convert a PyROOT branch object to a Python list.

    Handles:
      - std::vector / ROOT::VecOps::RVec  (has .size())
      - NanoAOD leaf-count arrays         (cppyy.LowLevelView; has len(), indexing, iteration)
    """
    # vector-like
    if hasattr(obj, "size"):
        n = int(obj.size())
        return [safe_float(obj[i]) for i in range(n)]

    # LowLevelView / python-sequence-like
    try:
        n = len(obj)
        return [safe_float(obj[i]) for i in range(n)]
    except Exception:
        pass

    # iterable fallback
    try:
        return [safe_float(x) for x in obj]
    except Exception:
        pass

    # last resort: use hint length (e.g. nJet)
    if n_hint >= 0:
        return [safe_float(obj[i]) for i in range(n_hint)]

    raise RuntimeError(f"Cannot convert branch object of type {type(obj)} to list.")


def summarize_jet_pt(events_tree, n_events_to_scan: int, n_jets_per_event: int):
    summary = {
        "n_entries": int(events_tree.GetEntries()),
        "per_event_vectors": [],
        "flat_preview": [],
        "per_event_lengths": (),
        "notes": [],
    }

    if not events_tree.GetBranch("Jet_pt"):
        raise RuntimeError("Branch 'Jet_pt' not found in Events.")

    # NanoAOD usually has nJet; use it as a consistency hint/check
    has_nJet = bool(events_tree.GetBranch("nJet"))

    n_scan = min(n_events_to_scan, summary["n_entries"])
    for i in range(n_scan):
        got = events_tree.GetEntry(i)
        if got <= 0:
            raise RuntimeError(f"GetEntry({i}) returned {got} (cannot read event).")

        jet_obj = getattr(events_tree, "Jet_pt", None)
        if jet_obj is None:
            raise RuntimeError(f"Events.Jet_pt is None at entry {i}.")

        n_hint = int(getattr(events_tree, "nJet")) if has_nJet else -1
        pts = branch_to_list(jet_obj, n_hint=n_hint)

        # Optional consistency note (verbose)
        if has_nJet and n_hint != len(pts):
            summary["notes"].append(
                f"WARNING: entry {i}: nJet={n_hint} but len(Jet_pt)={len(pts)} (PyROOT view sizing mismatch?)"
            )

        summary["per_event_vectors"].append(pts)
        summary["flat_preview"].extend(pts[:n_jets_per_event])

    summary["per_event_lengths"] = tuple(len(v) for v in summary["per_event_vectors"])
    return summary


def print_verbose_report(fname: str, summary: dict, n_events_to_scan: int, n_jets_per_event: int):
    print("=" * 100)
    print(f"[FILE] {fname}")
    print(f"  - Events entries: {summary['n_entries']}")
    print(f"  - Scan config: first {min(n_events_to_scan, summary['n_entries'])} events, "
          f"preview first {n_jets_per_event} jets/event")

    if summary["notes"]:
        print("  - Notes:")
        for n in summary["notes"]:
            print(f"      * {n}")

    if summary["n_entries"] == 0:
        print("  - WARNING: Events tree has 0 entries (empty file).")
        print("  - Jet_pt flat preview: []")
        return

    print("  - Per-event Jet_pt details:")
    for i, pts in enumerate(summary["per_event_vectors"]):
        print(f"    [Event {i}] Jet_pt vector length = {len(pts)}")
        if len(pts) == 0:
            print("      Jet_pt (full)    = []")
            print("      Jet_pt (preview) = []")
            continue

        full_str = ", ".join(f"{p:.6g}" if is_finite(p) else str(p) for p in pts)
        print(f"      Jet_pt (full)    = [{full_str}]")

        sl = pts[:n_jets_per_event]
        prev_str = ", ".join(f"{p:.6g}" if is_finite(p) else str(p) for p in sl)
        print(f"      Jet_pt (preview) = [{prev_str}]")

    print("  - Flat preview (first events * first jets/event):")
    if summary["flat_preview"]:
        flat_str = ", ".join(f"{p:.6g}" if is_finite(p) else str(p) for p in summary["flat_preview"])
        print(f"      [{flat_str}]")
    else:
        print("      []")


def list_root_files(target_dir: Path, pattern: str, recursive: bool):
    files = sorted(target_dir.rglob(pattern) if recursive else target_dir.glob(pattern))
    return [p for p in files if p.is_file()]


def main():
    parser = argparse.ArgumentParser(
        description="Verbose NanoAOD checker: scan ALL ROOT files in a target directory and compare Events.Jet_pt samples."
    )
    parser.add_argument("target_dir", help="Target directory containing NanoAOD ROOT files (required).")
    parser.add_argument("--pattern", default="*.root", help="Glob pattern (default: *.root).")
    parser.add_argument("--recursive", action="store_true", help="Recursively search under target_dir.")
    parser.add_argument("--scan-events", type=int, default=5, help="First N events to scan (default: 5).")
    parser.add_argument("--jets-per-event", type=int, default=8, help="Preview jets/event (default: 8).")
    parser.add_argument("--round-digits", type=int, default=6, help="Rounding digits for float compare (default: 6).")
    args = parser.parse_args()

    ROOT.gROOT.SetBatch(True)

    target_dir = Path(args.target_dir).expanduser().resolve()
    if not target_dir.exists() or not target_dir.is_dir():
        print(f"[ERROR] Target directory does not exist or is not a directory: {target_dir}")
        sys.exit(2)

    files = list_root_files(target_dir, args.pattern, args.recursive)

    print("\n[INFO] Starting NanoAOD directory comparison check")
    print(f"[INFO] Target dir : {target_dir}")
    print(f"[INFO] Pattern    : {args.pattern}")
    print(f"[INFO] Recursive  : {args.recursive}")
    print(f"[INFO] Scan config: first {args.scan_events} events, first {args.jets_per_event} jets/event\n")

    if len(files) == 0:
        print(f"[ERROR] No files matched pattern '{args.pattern}' in {target_dir} (recursive={args.recursive}).")
        sys.exit(2)

    print(f"[INFO] Found {len(files)} file(s):")
    for p in files:
        print(f"  - {p}")
    print()

    if len(files) < 2:
        print("[ERROR] Need at least TWO ROOT files in the target directory to compare.")
        sys.exit(2)

    opened_files = []  # keep TFile references alive
    reports = []

    for p in files:
        fname = str(p)
        try:
            f, t = open_events_tree(fname)
            opened_files.append(f)

            summary = summarize_jet_pt(t, args.scan_events, args.jets_per_event)
            print_verbose_report(fname, summary, args.scan_events, args.jets_per_event)

            signature = (
                summary["n_entries"],
                normalize_preview(summary["flat_preview"], ndigits=args.round_digits),
                summary["per_event_lengths"],
            )
            reports.append((fname, signature))
        except Exception as e:
            print("=" * 100)
            print(f"[FILE] {fname}")
            print(f"[ERROR] {e}")
            print("[ERROR] Cannot proceed with comparison due to read/format problem.")
            sys.exit(2)

    print("\n" + "=" * 100)
    print("[INFO] Comparison phase")

    sig_to_files = {}
    for fname, sig in reports:
        sig_to_files.setdefault(sig, []).append(fname)

    if len(sig_to_files) == 1:
        print("[ERROR] All files appear IDENTICAL under these checks:")
        print("        - same Events entry count")
        print(f"        - same sampled Jet_pt preview (first {args.scan_events} events, {args.jets_per_event} jets/event)")
        print("        - same per-event Jet_pt vector lengths in scanned events")
        for f in next(iter(sig_to_files.values())):
            print(f"          - {f}")
        sys.exit(1)

    print("[SUCCESS] The files are DIFFERENT under these checks.")
    print(f"[INFO] Found {len(sig_to_files)} distinct signature group(s).")
    for idx, fnames in enumerate(sig_to_files.values(), start=1):
        print(f"  - Group {idx}: {len(fnames)} file(s)")
        for f in fnames:
            print(f"      * {f}")
    sys.exit(0)


if __name__ == "__main__":
    main()

