#!/usr/bin/env python3
"""Parse OASIS-1 FreeSurfer segstats tables into one subject x region cohort table.

Inputs : <root>/disc1/<SUBJ>/stats/aseg.stats, lh.aparc.stats, rh.aparc.stats
Output : CSV with hippocampal + subcortical volumes (mm^3), ICV, and
         cortical GrayVol / ThickAvg / SurfArea for every Desikan region.

Old FreeSurfer (2006-2007) table layouts:
  aseg.stats   data rows : SeqOffset Seg #Vox RelVox Label Mean Std Min Max Median
               ICV from header line 'Measure IntraCranialVol, ICV, ... , <val>, mm^3'
  aparc.stats  ColHeaders StructName NumVert SurfArea GrayVol ThickAvg ThickStd ...
Voxel size is 1 mm isotropic, so RelVox is the volume in mm^3.
"""
import csv
import os
import re
import sys

ICV_RE = re.compile(r"Measure\s+IntraCranialVol,\s+ICV,\s+Intracranial Volume,\s*([0-9.eE+-]+)")
# subcortical structures worth keeping for an atrophy panel (aseg label names)
ASEG_KEEP = [
    "Left-Hippocampus", "Right-Hippocampus",
    "Left-Amygdala", "Right-Amygdala",
    "Left-Lateral-Ventricle", "Right-Lateral-Ventricle",
    "Left-Thalamus-Proper", "Right-Thalamus-Proper",
    "Left-Caudate", "Right-Caudate",
    "Left-Putamen", "Right-Putamen",
    "Left-Pallidum", "Right-Pallidum",
    "Left-Accumbens-area", "Right-Accumbens-area",
    "Brain-Stem",
    "Left-Cerebellum-Cortex", "Right-Cerebellum-Cortex",
    "Left-VentralDC", "Right-VentralDC",
]


def parse_aseg(path):
    """Return (icv, {label: volume_mm3})."""
    icv = None
    vol = {}
    with open(path, errors="replace") as fh:
        for line in fh:
            if line.startswith("#"):
                if icv is None:
                    m = ICV_RE.search(line)
                    if m:
                        icv = float(m.group(1))
                continue
            f = line.split()
            if len(f) < 5 or not f[0].isdigit():
                continue
            label, relvox = f[4], float(f[3])
            vol[label] = relvox
    return icv, vol


def parse_aparc(path, hemi):
    """Return {StructName: (SurfArea, GrayVol, ThickAvg)} using the ColHeaders line."""
    cols = None
    out = {}
    with open(path, errors="replace") as fh:
        for line in fh:
            if line.startswith("#"):
                if "ColHeaders" in line:
                    cols = line.split("ColHeaders", 1)[1].split()
                continue
            f = line.split()
            if len(f) < 6:
                continue
            if cols is None:  # fall back to the documented order
                cols = ["StructName", "NumVert", "SurfArea", "GrayVol",
                        "ThickAvg", "ThickStd", "MeanCurv", "GausCurv",
                        "FoldInd", "CurvInd"]
            d = dict(zip(cols, f))
            name = d["StructName"]
            if name.lower() in ("unknown", "cortex", "empty"):
                continue
            try:
                out[name] = (float(d["SurfArea"]), float(d["GrayVol"]),
                             float(d["ThickAvg"]))
            except KeyError:
                continue
    return out


def main(root, outcsv):
    subjects = sorted(
        d for d in os.listdir(root)
        if d.startswith("OAS") and os.path.isdir(os.path.join(root, d, "stats"))
    )
    if not subjects:
        sys.exit("no OAS* subject dirs with stats/ under %s" % root)

    rows, aseg_names, parc_names = [], [], []
    for s in subjects:
        sd = os.path.join(root, s, "stats")
        aseg_path = os.path.join(sd, "aseg.stats")
        if not os.path.exists(aseg_path):
            sys.stderr.write("skip %s: no aseg.stats\n" % s)
            continue
        icv, aseg = parse_aseg(aseg_path)
        row = {"Subject": s, "ICV_mm3": icv}
        for lab in ASEG_KEEP:
            key = lab.replace(" ", "_").replace("-", "_")
            row[key] = aseg.get(lab)
            row["pctICV_" + key] = (100.0 * aseg[lab] / icv
                                    if aseg.get(lab) is not None and icv else None)
            if key not in aseg_names:
                aseg_names.append(key)
        for hemi, fn in (("lh", "lh.aparc.stats"), ("rh", "rh.aparc.stats")):
            p = os.path.join(sd, fn)
            if not os.path.exists(p):
                continue
            for name, (area, gvol, thk) in parse_aparc(p, hemi).items():
                row["%s_%s_GrayVol" % (hemi, name)] = gvol
                row["%s_%s_ThickAvg" % (hemi, name)] = thk
                row["%s_%s_SurfArea" % (hemi, name)] = area
                if name not in parc_names:
                    parc_names.append(name)
        rows.append(row)

    ordered = (["Subject", "ICV_mm3"] + aseg_names + ["pctICV_" + a for a in aseg_names]
               + sum([["lh_%s_GrayVol" % n, "rh_%s_GrayVol" % n,
                       "lh_%s_ThickAvg" % n, "rh_%s_ThickAvg" % n] for n in parc_names], []))
    ordered = [c for c in ordered if any(c in r for r in rows)]
    with open(outcsv, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=ordered, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print("subjects parsed : %d" % len(rows))
    print("aseg structures : %d" % len(aseg_names))
    print("aparc regions   : %d x 2 hemis" % len(parc_names))
    print("columns         : %d" % len(ordered))
    print("wrote           : %s" % outcsv)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
