#!/usr/bin/env python3
"""Build the DT1_8_POLY_OSC firmware image from YOUR copy of the official OS 1.53 file.

    python3 tools/build.py --official <official OS 1.53 .syx> --tool <path to container tool> [--page scope|spectrum] [--out out/]

--page chooses the utility on the three-dots key (POLY is always included, Song mode is always removed).

Steps (each one verified, the build stops on any mismatch):
  1. SHA-256 of the official .syx must be the known OS 1.53 file.
  2. Unpack it with the open-source .syx container tool (by mischa85 on GitHub, MIT license).
  3. SHA-256 of the unpacked MAIN OS section (section 3) must match.
  4. tools/patch_section3.py applies every patch (each site checks the original bytes first).
  5. SHA-256 of the patched section must equal the released build.
  6. Repack with only section 3 replaced and the version tag set, then re-check the container checksums
     and that the other sections are byte-identical to the official file.
"""
import argparse, hashlib, os, subprocess, sys, tempfile, filecmp

# page -> (release, version tag shown on the unit, patched section SHA-256, .syx SHA-256 with the tool version used)
PAGES = {
    "scope":    ("v3p",          "1.5b", "3b1258bc7556ebb42898120fa2c0f759da6a2e5fb759db96ab9d33a837ddab53",
                 "f8cd0d721c265a07077078a5aae95908c265ce3fadd0c83cbbb377916b51b8b3"),
    "spectrum": ("v3q-spectrum", "1.5c", "154c6fe55633a1f5dcde36ed1c21fadb96bd08ff6e5238dd93ef29fb3604a34e",
                 "3aeb2bb8c4a79c7a807d4ee62336ba8e045078d6ae3d122d64e53a0c8851564a"),
}
OFFICIAL_SYX = "9bdd44bb6102fb25c143cfab97bc92b7a89c463f795d3112dce89771e29bcc92"
OFFICIAL_S3  = "4b47a9507758ca5669ca02ab2c0374d2c04c98aece445408295cc1dcb265c5df"

HERE = os.path.dirname(os.path.abspath(__file__))

def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()

def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        sys.exit("command failed: %s\n%s%s" % (" ".join(cmd), r.stdout, r.stderr))
    return r.stdout

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--official", required=True, help="official OS 1.53 .syx (downloaded by you)")
    ap.add_argument("--tool", required=True, help="path to the container tool binary")
    ap.add_argument("--page", default="scope", choices=sorted(PAGES), help="three-dots utility (default: scope)")
    ap.add_argument("--out", default="out", help="output folder (default: out/)")
    a = ap.parse_args()
    RELEASE, VERSION_TAG, PATCHED_S3, PATCHED_SYX = PAGES[a.page]

    if sha(a.official) != OFFICIAL_SYX:
        sys.exit("%s is not the expected official OS 1.53 file (SHA-256 %s)" % (a.official, sha(a.official)))
    print("official OS 1.53 file ok")
    os.makedirs(a.out, exist_ok=True)
    with tempfile.TemporaryDirectory() as t:
        off = os.path.join(t, "official")
        run([a.tool, "-i", a.official, "-o", off])
        s3 = os.path.join(off, "section_3_MAIN_OS.bin")
        if sha(s3) != OFFICIAL_S3:
            sys.exit("unpacked MAIN OS section does not match (tool version?)")
        print("MAIN OS section ok")
        patched = os.path.join(a.out, "section_3_MAIN_OS_%s.bin" % RELEASE)
        run([sys.executable, os.path.join(HERE, "patch_section3.py"), s3, patched, a.page])
        if sha(patched) != PATCHED_S3:
            sys.exit("patched section differs from the release build (%s)" % sha(patched))
        print("patched section = release %s" % RELEASE)
        syx = os.path.join(a.out, "DT1_8_POLY_OSC_%s_%s.syx" % (RELEASE, VERSION_TAG))
        run([a.tool, "-i", a.official, "-c", "3", patched, "-V", VERSION_TAG, "-o", syx])
        rep = run([a.tool, "-i", syx])
        if "checksums : ok" not in rep or VERSION_TAG not in rep:
            sys.exit("rebuilt image failed its own checks:\n" + rep)
        chk = os.path.join(t, "check")
        run([a.tool, "-i", syx, "-o", chk])
        for name in sorted(os.listdir(off)):
            same = filecmp.cmp(os.path.join(off, name), os.path.join(chk, name), shallow=False)
            if name.startswith("section_3"):
                if not filecmp.cmp(os.path.join(chk, name), patched, shallow=False):
                    sys.exit("section 3 did not round-trip")
            elif not same:
                sys.exit("%s changed - only section 3 may differ" % name)
        print("container checksums ok; only section 3 differs from official")
    h = sha(syx)
    print("wrote %s\nSHA-256 %s%s" % (syx, h, "  (= release build)" if h == PATCHED_SYX else
          "  (differs from the release .syx: different tool version / compression - section 3 is identical, which is what counts)"))

if __name__ == "__main__":
    main()
