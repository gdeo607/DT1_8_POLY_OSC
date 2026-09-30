#!/usr/bin/env python3
"""Build the elekloader mods (mods/digipoly, mods/digiutils, mods/digimatrix, mods/digieq, mods/digimono; mods/dt8poly on
request) from this repo's sources.

    python3 tools/build_elemods.py --stock <official OS 1.53 .syx> --elekloader <path to elekloader checkout> [--out out/elk]
        [--mods digipoly digiutils digimatrix digieq dt8poly]

digipoly (Digi Poly) is the POLY machine with chords and voice stealing; digimatrix (Digi Matrix) is the
LFO modulation matrix; digieq (Digi EQ) is the master EQ; digimono (Digi Mono) adds synth machines (it needs
core 2.1, and does not combine with digipoly 1.0f); dt8poly is the earlier POLY mod
(internal MIDI cable, voice rotation), superseded by digipoly and kept for tests/elk_equiv.py.

Each mod folder holds its mod.json and the files only it needs; the shared sources come from src/ and
the generated tables from bin/. They are copied into one staging folder per mod (out/elk/<id>/), which is
handed to elekloader's SDK (python -m elekloader.sdk.build). The sources are assembled with ELK defined:
the same code, linked by the SDK into the mod's RAM image instead of placed at fixed addresses.
Needs m68k binutils (m68k-linux-gnu-as, -ld). Writes out/elk/<id>/out/<id>-<version>.elemod.
"""
import argparse, json, os, shutil, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SHARED = {  # file -> folder it comes from
    "cable.s": "src", "cc.s": "src", "lock.s": "src", "scope.s": "src", "tuner.s": "src",
    "spectrum.s": "src", "songoff.s": "src", "kitstore.h": "src", "spec_tables.inc": "bin", "spec_sin.bin": "bin",
}
MODS = ["digipoly", "digiutils", "digimatrix", "digieq", "digimono"]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stock", required=True, help="official OS 1.53 .syx")
    ap.add_argument("--elekloader", required=True, help="elekloader checkout (its folder, with elekloader/)")
    ap.add_argument("--out", default=os.path.join(ROOT, "out", "elk"))
    ap.add_argument("--mods", nargs="+", default=MODS, help="mod folders to build (default: %(default)s)")
    a = ap.parse_args()
    env = dict(os.environ, PYTHONPATH=os.path.abspath(a.elekloader) + os.pathsep + os.environ.get("PYTHONPATH", ""))
    built = []
    for mid in a.mods:
        src_dir = os.path.join(ROOT, "mods", mid)
        stage = os.path.join(a.out, mid)
        shutil.rmtree(stage, ignore_errors=True)
        shutil.copytree(src_dir, stage)
        for name, folder in SHARED.items():
            shutil.copy(os.path.join(ROOT, folder, name), stage)
        r = subprocess.run([sys.executable, "-m", "elekloader.sdk.build", stage, "--stock", a.stock],
                           env=env, capture_output=True, text=True)
        print(r.stdout.strip())
        if r.returncode or "BUILT" not in r.stdout:
            sys.exit("%s: build failed\n%s" % (mid, r.stderr))
        with open(os.path.join(src_dir, "mod.json")) as fh:
            m = json.load(fh)
        built.append(os.path.join(stage, "out", "%s-%s.elemod" % (mid, m["version"])))
    print("\n".join(["built:"] + built))


if __name__ == "__main__":
    main()
