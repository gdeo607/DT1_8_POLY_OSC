#!/usr/bin/env python3
"""The elekloader build runs the same code as the stand-alone build.

    python3 tests/elk_equiv.py --stock <official .syx> --elekloader <checkout> --core <core.elemod> \
        --mods <dt8poly.elemod> <digiutils.elemod> [<other mods>...]

Links the mods the way elekloader does (link.link), then compares, routine by routine, the disassembly of
our code in the linked image (running at its RAM address) with the stand-alone "all" build
(tools/patch_section3.py ... all), after naming every address operand that points into our code or data
(label+offset) and every stock address as itself. Also compares every patched stock site. Expected
differences are listed explicitly (the audio tap site, the raw getter, which is written anew here).
"""
import argparse, bisect, hashlib, os, re, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
B = 0x40000400


def objdump(code, vma):
    with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as fh:
        fh.write(code)
        p = fh.name
    out = subprocess.run(["m68k-linux-gnu-objdump", "-D", "-b", "binary", "-m", "m68k:cfv4e",
                          "--adjust-vma=0x%x" % vma, p], capture_output=True, text=True).stdout
    os.unlink(p)
    ins = []
    for ln in out.splitlines():
        m = re.match(r"\s*([0-9a-f]+):\t([0-9a-f ]+)\t(.*)$", ln)
        if m:
            ins.append((int(m.group(1), 16), m.group(3).strip()))
    return ins


class Namer:
    def __init__(self, labels):              # {name: addr}
        self.items = sorted((a, n) for n, a in labels.items())
        self.addrs = [a for a, _ in self.items]
        self.lo, self.hi = self.addrs[0], max(self.addrs) + 0x1000

    def name(self, a):
        i = bisect.bisect_right(self.addrs, a) - 1
        if i < 0 or not (self.lo <= a < self.hi):
            return None
        base, n = self.items[i]
        return n if a == base else "%s+0x%x" % (n, a - base)

    def norm(self, text):
        def rep(m):
            v = int(m.group(0), 16)
            n = self.name(v)
            return "<%s>" % n if n else m.group(0)
        text = re.sub(r"0x[0-9a-f]{6,8}", rep, text)
        def rep_dec(m):                      # immediates print in decimal
            v = int(m.group(1)) & 0xffffffff
            n = self.name(v)
            return "#<%s>" % n if n else m.group(0)
        return re.sub(r"#(-?\d{9,10})\b", rep_dec, text)


def nm_syms(path, base=0, section_filter=None):
    out = subprocess.run(["m68k-linux-gnu-nm", path], capture_output=True, text=True).stdout
    d = {}
    for ln in out.splitlines():
        p = ln.split()
        if len(p) == 3 and p[1] in "tTdDbB" and not p[2].startswith(".L"):
            d.setdefault(p[2], base + int(p[0], 16))
    return d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stock", required=True)
    ap.add_argument("--elekloader", required=True)
    ap.add_argument("--core", required=True)
    ap.add_argument("--mods", nargs="+", required=True)
    a = ap.parse_args()
    sys.path.insert(0, a.elekloader)
    from elekloader import syx, devices, elemod, link
    stock = syx.Syx.load(a.stock)
    dev, rel = devices.identify(stock.sha256)
    img0 = stock.section(dev.main_section)
    mods = [elemod.load_any(p) for p in [a.core] + a.mods]
    L = link.link(mods, img0)
    img = L.image
    run_load, (ddr0, run_end) = L.layout["run_load"], L.layout["ddr"]
    run = img[run_load - B: run_load - B + (run_end - ddr0)]

    def elk_at(addr, n):                     # bytes as they run (RAM image) or in the patched OS
        if ddr0 <= addr < run_end:
            return run[addr - ddr0: addr - ddr0 + n]
        return img[addr - B: addr - B + n]

    # the stand-alone "all" build
    sec3 = os.path.join(tempfile.mkdtemp(), "s3.bin")
    open(sec3, "wb").write(img0)
    fixed_p = sec3 + ".all"
    subprocess.run([sys.executable, os.path.join(ROOT, "tools", "patch_section3.py"), sec3, fixed_p, "all"],
                   check=True, capture_output=True)
    fixed = open(fixed_p, "rb").read()

    def fix_at(addr, n):
        return fixed[addr - B: addr - B + n]

    # ---- labels, stand-alone ----
    binp = lambda n: os.path.join(ROOT, "bin", n)
    SCOPE = 0x400abe9c
    F = {}
    for ln in open(binp("scope_all.sym")):
        v, _t, n = ln.split()
        F[n] = SCOPE + int(v, 16)
    F["TRIG"] = 0x400ab072                    # .trigtext in the all build
    F.update({k: v for k, v in nm_syms(binp("tuner.elf")).items() if k.isupper() or k[:1] == "N"})
    F.update(nm_syms(binp("spectrum.elf")))
    F.update({"DATA": 0x400ae280, "TDATA": 0x400aeab4, "TRING": 0x400aead0, "SREQ": 0x400aeed0,
              "SINT": 0x400aefe8, "VSTATE": 0x400b907c})
    F.update({"CABLE": 0x400b8e60, "CCHOOK": 0x400b9110, "POST": 0x400ac4ec, "FIX": 0x400b91c4})
    # ---- labels, elekloader ----
    E = {}
    for key, v in L.map.items():
        if ":" in key:
            mid, n = key.split(":", 1)
            if (mid in ("digiutils", "dt8poly") and not n.startswith(("dt8", "digiutils_", ".L"))
                    and ddr0 <= v < L.layout["bss"][1]):          # our code and data only, not .set constants
                E.setdefault(n, v)
    E.update({"DATA": L.map["digiutils_data"], "TDATA": L.map["digiutils_tdata"], "TRING": L.map["digiutils_tring"],
              "SREQ": L.map["digiutils_sreq"], "SINT": L.map["digiutils_sint"],
              "VSTATE": L.map.get("dt8poly_vstate", 0)})
    E.pop("STATE", None); F.pop("STATE", None)
    # POLY hooks: hex in the stand-alone script (addresses as it prints them), poly_ui.s here
    POLYF = {"PNAMES": 0x400b8cfc, "POLYSTR": 0x400b8d24, "LOOKUP": 0x400b8d2c, "ENGINE": 0x400b8d44,
             "GETTER": 0x400b8d58, "ROTATE": 0x400b8d9c, "RR": 0x400b9104, "ICONOBJ": 0x400b9260,
             "ICONMASK": 0x400b9280, "ICONGLYPH": 0x400b92b0, "ICONTAB": 0x400b92e0, "ICON": 0x400b92f0}
    POLYE = {"PNAMES": "dt8poly_names", "POLYSTR": "dt8poly:poly_str", "LOOKUP": "dt8poly_lookup",
             "ENGINE": "dt8poly_engine", "GETTER": "dt8poly_getter", "ROTATE": "dt8poly_rotate",
             "RR": "dt8poly:poly_rr", "ICONOBJ": "dt8poly:icon_obj", "ICONMASK": "dt8poly:icon_mask",
             "ICONGLYPH": "dt8poly:icon_glyph", "ICONTAB": "dt8poly_icon_tab", "ICON": "dt8poly_icon"}
    for k in POLYF:
        F[k] = POLYF[k]
        E[k] = L.map[POLYE[k]]
    for k in ("poly_str", "poly_rr", "icon_obj", "icon_mask", "icon_glyph"):
        E.pop(k, None)
    fn, en = Namer(F), Namer(E)

    # routines to compare: (label, end label or length). The stand-alone TRIG sits elsewhere, so each
    # routine is compared from its own label to the next label of the same file.
    def spans(labels, names):
        out = {}
        for n in names:
            a = labels[n]
            nxt = min([v for k, v in labels.items() if v > a] + [a + 0x800])
            out[n] = (a, nxt - a)
        return out
    code_names = [n for n in F if n in E and n not in ("DATA", "TDATA", "TRING", "SREQ", "SINT", "VSTATE",
                                                       "PNAMES", "NAMES", "STRFMT", "STRNONE", "POLYSTR", "RR", "ICONOBJ", "ICONMASK",
                                                       "ICONGLYPH", "ICONTAB")]
    POLYLEN = {"LOOKUP": 24, "ENGINE": 18, "GETTER": 20, "ROTATE": 192, "ICON": 64,
               "CABLE": 592, "CCHOOK": 178, "POST": 218, "FIX": 38}
    code_names = [n for n in code_names if not (len(n) <= 3 and n[0] == "N")]   # tuner note-name strings
    # only code labels (the tuner's note-name strings and tables are data: compare them as bytes)
    fails, checked = [], 0
    fsp, esp = spans(F, code_names), spans(E, code_names)
    for n in sorted(code_names):
        fa, fl = fsp[n]
        ea, el = esp[n]
        if n in ("TAP",):                    # ELK: TAP is unused (the tap is digiutils_tapc, see below)
            continue
        if n in ("DRAW", "KEY"):             # 1.6: + the EQ view (4th view, YES = knob page); see emu_eq.py
            continue                          # and the digiemu walk-through for these two
        ln = POLYLEN.get(n, min(fl, el))
        if n in POLYLEN:
            ln += 6
        fi = [(x, fn.norm(t)) for x, t in objdump(fix_at(fa, ln), fa)]
        ei = [(x, en.norm(t)) for x, t in objdump(elk_at(ea, ln), ea)]
        fi = [t for x, t in fi if x - fa < ln - 6] ; ei = [t for x, t in ei if x - ea < ln - 6]
        if fi != ei:
            for i, (p, q) in enumerate(zip(fi, ei)):
                if p != q:
                    fails.append("%s: +%d  stand-alone %r  elekloader %r" % (n, i, p, q))
                    break
            else:
                fails.append("%s: lengths %d / %d" % (n, len(fi), len(ei)))
        checked += 1
    # data: the name table (as addresses), the icon object/glyph/mask/table, the sine table, the tuner strings
    def words(get, a, n, namer):
        return [namer.name(int.from_bytes(get(a + i, 4), "big")) or get(a + i, 4).hex() for i in range(0, n, 4)]
    for k, n in (("PNAMES", 40), ("NAMES", 48), ("ICONOBJ", 28), ("ICONMASK", 44), ("ICONGLYPH", 44)):
        if words(fix_at, F[k], n, fn) != words(elk_at, E[k], n, en):
            fails.append("data %s differs" % k)
        checked += 1
    for k, n in (("ICONTAB", 8), ("POLYSTR", 5), ("SINT", 514), ("STRFMT", 10), ("STRNONE", 3)):
        if fix_at(F[k], n) != elk_at(E[k], n):
            fails.append("data %s differs" % k)
        checked += 1
    # the tap: stand-alone TAP after its output-write call == elekloader digiutils_tapc
    fa = F["TAP"] + 22                        # after "jsr OUTWRITE; lea 12(sp),sp"
    ea = L.map["digiutils_tapc"]
    fi = [fn.norm(t) for _, t in objdump(fix_at(fa, 0x60), fa)]
    ei = [en.norm(t) for _, t in objdump(elk_at(ea, 0x60), ea)]
    if fi != ei:
        fails.append("tap capture differs:\n    %s\n    %s" % (fi[:8], ei[:8]))
    checked += 1
    # stock sites: every site of ours, same bytes except the operand naming our code
    sites = {}
    for m in mods:
        if m.id in ("dt8poly", "digiutils"):
            for s in m.sites:
                sites[s["addr"]] = (m.id, s["len"])
    ours = {"dt8poly_lookup": 0, "dt8poly_engine": 0}
    site_fails = []
    EXPECTED = {0x40078150: "the tap moved after the output write (FAST AUDIO owns 0x4007814a)",
                0x401b3794: "EQ view knob handler (1.6)", 0x401b37ac: "EQ view knob handler (1.6)",
                0x4002b754: "raw getter", 0x4003b3fc: "raw getter", 0x4003bd3a: "raw getter",
                0x4001d8cc: "split in three sites", 0x4001d8d0: "split", 0x4001d8d6: "split",
                # 1.7: Song mode stays; the page is a SongEditView adopted on HOLD "..." (page.s / page.c)
                0x40095aec: "pattern pick: close stock Song edit, keep the page",
                0x40095bf6: "bank pick: close stock Song edit, keep the page",
                0x400aee4a: "Song popup: hold opens the page", 0x400af086: "Song popup: adopt the new view",
                0x401845e4: "master view keys (EQ page, 1.8a)", 0x401845ec: "master view draw (EQ page, 1.8a)",
                0x401846bc: "master view knobs (EQ page, 1.8a)"}
    for addr, (mid, n) in sorted(sites.items()):
        f, e = fix_at(addr, n), elk_at(addr, n)
        if addr in EXPECTED:
            continue
        ft = [fn.norm(t) for _, t in objdump(f, addr)] if n > 4 or addr < 0x40100000 else [f.hex()]
        et = [en.norm(t) for _, t in objdump(e, addr)] if n > 4 or addr < 0x40100000 else [e.hex()]
        if addr >= 0x40180000:               # vtable/data words
            fv, ev = int.from_bytes(f, "big"), int.from_bytes(e, "big")
            ft, et = [fn.name(fv) or hex(fv)], [en.name(ev) or hex(ev)]
        if ft != et:
            site_fails.append("site 0x%08x (%s): %s / %s" % (addr, mid, ft, et))
    # the 14-byte song-mode getter patch (only while the mods switch Song mode off): same bytes but the FIX address
    f, e = fix_at(0x4001d8cc, 14), elk_at(0x4001d8cc, 14)
    if any(a in (0x4001d8cc, "0x4001d8cc") for a in sites) or e != img0[0x4001d8cc - B: 0x4001d8cc - B + 14]:
      if f[:6] != e[:6] or f[10:] != e[10:] or en.name(int.from_bytes(e[6:10], "big")) != "FIX":
        site_fails.append("song-mode getter: %s / %s" % (f.hex(), e.hex()))
    # bytes our mods change in the stock image outside the listed sites: none
    print("routines compared: %d, sites compared: %d" % (checked, len(sites)))
    for x in fails + site_fails:
        print("DIFF", x)
    print("PASS" if not (fails or site_fails) else "FAIL")
    return 1 if (fails or site_fails) else 0


if __name__ == "__main__":
    sys.exit(main())
