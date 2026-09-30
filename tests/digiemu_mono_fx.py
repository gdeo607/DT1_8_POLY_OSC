#!/usr/bin/env python3
"""Digi Mono tracks through the Digitakt's own FLTR, AMP and LFO pages, in the real firmware (digiemu).

    <digiemu's python> tests/digiemu_mono_fx.py --digiemu <digiemu checkout> --fw <firmware folder name>
        [--wavs <dir>]

The build must have core 2.1 and digimono (set up in digiemu with python -m emu.portable --add BUILD.syx).
Every case is its own headless run: pattern A16, track 1 -> a Digi Mono machine, trigs on steps 1, 5, 9
and 13, the page settings of the case, then PLAY for about 8 s. It records the output and
voice 0's block before the filter stage (0x80001a18), and compares each case with the baseline run. "The output" is what the firmware sends to the audio codec
(digiemu's recording of the SSI stream: the main outputs):

  filter   FLTR E (FREQ) all the way down: the output's spectral centroid falls
           FLTR F (RESO) up, FREQ half-way: a resonant peak stands out of the saw's harmonics
  amp      AMP B (HOLD) and C (DEC) down: every note dies within a fraction of a step
           AMP H (VOL) down by 40: the master level drops
           AMP G (PAN) full left: the right channel goes quiet
  LFO      LFO1 -> FREQ (slot 26), full depth: the master's brightness moves with the LFO
           LFO1 -> a Digi Mono knob (PULSE: PW, slot 22), full depth: the pulse width of the voice's
           own block (before the filter) moves with the LFO: LFOs reach the synth's parameters
Knob turns go through the panel (FLTR = key 21, AMP = 22; knobs A..H = encoders 1..8). The LFO cases set
the LFO's DEST, DEP and SPD in the kit and in the engine's parameter copy, as a knob or MIDI CC would.
"""
import argparse, json, math, os, struct, subprocess, sys, time, types, wave

HERE = os.path.dirname(os.path.abspath(__file__))
ap = argparse.ArgumentParser()
ap.add_argument("--digiemu", required=True)
ap.add_argument("--fw", required=True)
ap.add_argument("--wavs", default="")
ap.add_argument("--cases", default="", help="comma-separated subset of the cases (default: all)")
ap.add_argument("--one", default="", help=argparse.SUPPRESS)       # internal: run one case, print JSON
ap.add_argument("--out", default="", help=argparse.SUPPRESS)
a = ap.parse_args()

MACHINES = {"SAW": 2, "PULS": 3}
# Every case starts from the same page settings: filter open (FLTR E = FREQ all the way up), no resonance
# (F = RESO down), the amp held for the note (AMP B = HOLD all the way up). Then the case's own turns.
SETUP = [(21, 4, +80), (21, 5, -80), (22, 1, +80)]
CASES = {
    "base":      ("SAW",  [], {}),
    "fltr_low":  ("SAW",  [(21, 4, -70)], {}),                       # FREQ down
    "fltr_reso": ("SAW",  [(21, 4, -45), (21, 5, +80)], {}),         # FREQ half-way, RESO up
    "amp_short": ("SAW",  [(22, 1, -80), (22, 2, -80)], {}),         # HOLD and DEC down
    "amp_vol":   ("SAW",  [(22, 7, -40)], {}),                       # VOL down
    "amp_pan":   ("SAW",  [(22, 6, -80)], {}),                       # PAN full left
    "dry_vol":   ("SAW",  [(22, 4, -80), (22, 5, -80), (22, 7, -40)], {}),   # sends off, VOL down
    "fltr_mid":  ("SAW",  [(21, 4, -40)], {}),                       # FREQ half-way (the LFO case's base)
    "lfo_freq":  ("SAW",  [(21, 4, -40)], {1: 100, 4: 26, 8: 127}),  # LFO1 SPD, DEST = slot 26 (FREQ), DEP
    "puls_base": ("PULS", [], {}),
    "lfo_pw":    ("PULS", [], {1: 90, 4: 22, 8: 127}),               # LFO1 -> F (PW, slot 22)
}


def run_one(name):
    import numpy as np
    machine, turns, lfo = CASES[name]
    turns = SETUP + turns
    DE = os.path.abspath(a.digiemu)
    FW = os.path.join(DE, "portable", "firmware", a.fw)
    sys.path.insert(0, DE)
    syxname = [f for f in os.listdir(FW) if f.endswith(".syx")][0]
    os.environ.update({"DT2_SYX": os.path.join(FW, syxname), "DT2_SECTIONS": FW + "/sections",
                       "DT2_SNAPSHOTS": FW + "/snapshots", "DT2_PLUSDRIVE": FW + "/plusdrive.img",
                       "DT2_MAIN_IMG": FW + "/sections/section_3_MAIN_OS.bin",
                       "DT2_DEVICES": FW + "/devices" if os.path.isdir(FW + "/devices") else os.path.join(DE, "devices"),
                       "DIGIKIT_PIT3_PROBE": "1"})
    out = os.path.abspath(a.out)
    os.chdir(FW)
    tk = types.ModuleType("tkinter")
    tk.Frame = type("Frame", (), {}); tk.Tk = type("Tk", (), {})
    sys.modules["tkinter"] = tk
    for n in ("ttk", "messagebox", "filedialog", "font"):
        sys.modules["tkinter." + n] = types.ModuleType("tkinter." + n)
    from unicorn import UC_HOOK_CODE
    from unicorn.m68k_const import UC_M68K_REG_A7, UC_M68K_REG_PC
    import emu.gui as G
    snap = [os.path.join(dp, f) for dp, _, fs in os.walk(FW + "/snapshots") for f in fs if f == "gui.snap"][0]

    plan = []
    t = [300]
    def at(dt, *act):
        t[0] += dt
        plan.append((t[0], act))
    def tap(code, hold=20, gap=40):
        at(1, "press", code); at(hold, "release", code); at(gap, "wait")
    at(1, "press", 3); at(20, "press", 39); at(20, "release", 39); at(5, "release", 3); at(150, "wait")
    at(1, "press", 1); at(20, "press", 20); at(20, "release", 20); at(5, "release", 1); at(80, "wait")
    for _ in range(int(os.environ.get("FX_DOWNS", 4 + MACHINES[machine]))):
        tap(15, 20, 60)
    tap(12, 20, 80); tap(13, 20, 60)
    page = None
    for pg, knob, n in turns:
        if pg != page:
            tap(pg, 20, 120)
            page = pg
        for _ in range(abs(n)):
            at(3, "encoder", 1 + knob, 4 if n > 0 else -4)
        at(60, "wait")
    if lfo:
        at(0, "lfo")
    tap(9, 20, 60)
    for k in (24, 28, 32, 36):
        tap(k, 20, 40)
    tap(9, 20, 60)
    at(0, "rec", True)
    tap(10, 20, 20)
    at(3000, "wait")
    tap(11, 20, 40)
    at(0, "rec", False)
    steps = t[0] + 2
    st = {"n": 0, "rec": False}
    master, voice, slots, latev, allv = [], [], {}, [], []

    def after(u, ad, s, d):
        if st["rec"]:
            voice.append(struct.unpack(">32i", u.mem_read(0x80001a18, 128)))

    def late(u, ad, s, d):                     # voice 0's buffer just before the output mixer
        if st["rec"]:
            latev.append(struct.unpack(">32i", u.mem_read(0x80001a18, 128)))
            allv.append([sum(abs(x) for x in struct.unpack(">32i", u.mem_read(0x80001a18 + 128 * k, 128))) / 32
                         for k in range(8)])

    seq = []                                   # TRACE=1: the order of reads/writes of voice 0's buffer
    def memhook(u, acc, addr, size, val, d):
        if st["rec"] and len(seq) < 20000 and struct.unpack(">i", u.mem_read(0x8000edc4 + 16, 4))[0] != 0:
            seq.append((acc, u.reg_read(UC_M68K_REG_PC)))

    def mst(u, ad, s, d):
        if st["rec"]:
            master.append(struct.unpack(">64i", u.mem_read(0x8000ea70, 256)))

    orig = G.spin
    def spin(m, pc, *args, **kw):
        n = st["n"]
        uc = m.uc
        if n == 0:
            uc.hook_add(UC_HOOK_CODE, after, begin=0x40077fc8, end=0x40077fc8)
            uc.hook_add(UC_HOOK_CODE, mst, begin=0x400721e6, end=0x400721e6)
            uc.hook_add(UC_HOOK_CODE, late, begin=0x4007814a, end=0x4007814a)
            if os.environ.get("TRACE"):
                from unicorn import UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE
                uc.hook_add(UC_HOOK_MEM_READ | UC_HOOK_MEM_WRITE, memhook, begin=0x80001a18, end=0x80001a18 + 127)
        for when, act in plan:
            if when != n:
                continue
            if act[0] in ("press", "release"):
                E.inbox.append((act[0], act[1], 0))
            elif act[0] == "encoder":
                E.inbox.append(("encoder", act[1], act[2]))
            elif act[0] == "lfo":                 # the kit (saved, shown) and the engine's copy (voice 0)
                kit = struct.unpack(">I", uc.mem_read(0x4199dc44, 4))[0]
                for s, v in lfo.items():
                    uc.mem_write(kit + 0x20 + 0x14 + 2 * s, struct.pack(">H", v << 8))
                    uc.mem_write(0x80001502 + 2 * s, struct.pack(">H", v << 8))
            elif act[0] == "rec":
                st["rec"] = act[1]
                if act[1]:
                    E.audio_clear()                # the codec's output from here: what the outputs play
                else:
                    st["pcm"] = E.audio_take()
                if act[1]:
                    kit = struct.unpack(">I", uc.mem_read(0x4199dc44, 4))[0]
                    slots.update({s: struct.unpack(">H", uc.mem_read(kit + 0x20 + 0x14 + 2 * s, 2))[0] >> 8
                                  for s in list(range(1, 9)) + list(range(17, 46))})
                    slots["machine"] = uc.mem_read(kit + 0x20 + 0x7e, 1)[0]
                    slots["engine"] = {s: struct.unpack(">h", uc.mem_read(0x80001502 + 2 * s, 2))[0] >> 8
                                       for s in (22, 26, 27, 39, 40, 44, 45)}
                    slots["smoothed"] = {s: struct.unpack(">h", uc.mem_read(0x80002772 + 2 * s, 2))[0] >> 8
                                         for s in (22, 26, 27, 39, 40, 44, 45)}
        st["n"] += 1
        r = orig(m, pc, *args, **kw)
        if st["n"] >= steps:
            E.stop_flag.set()
        return r
    G.spin = spin
    E = G.Emulator(snap, syx=os.environ["DT2_SYX"], realtime=False, audio=True)
    E.run()
    pcm = np.frombuffer(st.get("pcm", b""), dtype="<i2").astype(np.int32).reshape(-1, 2) << 16
    np.save(out + "_master.npy", pcm)
    np.save(out + "_voice.npy", np.array(voice, dtype=np.int32).ravel())
    np.save(out + "_late.npy", np.array(latev, dtype=np.int32).ravel())
    np.save(out + "_allv.npy", np.array(allv, dtype=np.float64))
    if seq:
        json.dump(seq, open(out + "_seq.json", "w"))
        order, last = [], None
        for acc, pc in seq[200:1400]:
            k = ("W" if acc == 17 else "R", pc)
            if k != last:
                order.append("%s%x" % k)
            last = k
        print("ORDER " + " ".join(order[:80]))
    print("JSON" + json.dumps(slots))


if a.one:
    run_one(a.one)
    sys.exit(0)

import numpy as np
work = a.wavs or os.path.join("/tmp", "digimono_fx_%d" % os.getpid())
os.makedirs(work, exist_ok=True)
FS = 48000
R = {}
for name in [c for c in CASES if not a.cases or c in a.cases.split(",")]:
    t0 = time.time()
    base = os.path.join(work, name)
    p = subprocess.run([sys.executable, os.path.abspath(__file__), "--digiemu", a.digiemu, "--fw", a.fw,
                        "--one", name, "--out", base], capture_output=True, text=True)
    js = [l for l in p.stdout.splitlines() if l.startswith("JSON")]
    if p.returncode or not js:
        sys.exit("%s: the run failed\n%s" % (name, p.stderr[-2000:]))
    m = np.load(base + "_master.npy").astype(np.float64) / 2 ** 31
    v = np.load(base + "_voice.npy").astype(np.float64) / 2 ** 31
    R[name] = (json.loads(js[0][4:]), m[len(m) // 8:], v[len(v) // 8:])
    if a.wavs:
        with wave.open(base + ".wav", "wb") as w:
            w.setnchannels(2); w.setsampwidth(2); w.setframerate(FS)
            w.writeframes(np.clip(np.round(m * 32767 * 4), -32768, 32767).astype("<i2").tobytes())
    print("  ran %-10s %4.0f s  machine %d  %s" % (name, time.time() - t0, R[name][0]["machine"],
          {k: v_ for k, v_ in R[name][0].items() if k in ("1", "4", "8", "22", "26", "27", "39", "40", "44", "45")}))
    print("      engine copy %s  smoothed %s" % (R[name][0].get("engine"), R[name][0].get("smoothed")))

FAIL = []
def check(ok, what):
    print(("  ok    " if ok else "  FAIL  ") + what)
    if not ok:
        FAIL.append(what)


def db(x):
    return 20 * math.log10(np.sqrt(np.mean(x ** 2)) + 1e-12)


def centroid(x):
    s = np.abs(np.fft.rfft(x * np.hanning(len(x)))) ** 2
    f = np.fft.rfftfreq(len(x), 1 / FS)
    return float((s * f).sum() / (s.sum() + 1e-30))


def frames(x, n=2400):
    return [x[i:i + n] for i in range(0, len(x) - n, n)]


L = {k: r[1][:, 0] for k, r in R.items()}
print("filter")
c0, c1 = centroid(L["base"]), centroid(L["fltr_low"])
check(c1 < c0 / 4, "FLTR FREQ down: the master's centroid %.0f Hz -> %.0f Hz" % (c0, c1))
s = np.abs(np.fft.rfft(L["fltr_reso"] * np.hanning(len(L["fltr_reso"]))))
f = np.fft.rfftfreq(len(L["fltr_reso"]), 1 / FS)
h = np.array([s[np.argmin(abs(f - k * 261.63))] for k in range(1, 40)])   # the saw's harmonics
hb = np.array([np.abs(np.fft.rfft(L["fltr_mid"] * np.hanning(len(L["fltr_mid"]))))[np.argmin(abs(f - k * 261.63))]
               for k in range(1, 40)])
rel = 20 * np.log10(h / h[0] + 1e-12) - 20 * np.log10(hb / hb[0] + 1e-12)
k = int(np.argmax(rel[1:])) + 2
check(rel[k - 1] > 6, "FLTR RESO up: harmonic %d (%.0f Hz) stands %.1f dB above its level in the baseline"
      % (k, k * 261.63, rel[k - 1]))

print("amp")
def sounding(x):                               # the share of 10 ms frames within 30 dB of the loudest
    e = np.array([np.sqrt(np.mean(y ** 2)) for y in frames(x, 480)])
    return float(np.mean(e > e.max() * 10 ** (-30 / 20)))
sb, ss = sounding(L["base"]), sounding(L["amp_short"])
check(ss < sb * 0.5, "AMP HOLD and DEC down: notes sound %.0f %% of the time instead of %.0f %%" % (100 * ss, 100 * sb))
dv = db(L["amp_vol"]) - db(L["base"])
check(dv < -6, "AMP VOL down 40: the master %.1f dB" % dv)
pl, pr = R["amp_pan"][1][:, 0], R["amp_pan"][1][:, 1]
check(db(pr) < db(pl) - 20, "AMP PAN full left: right %.1f dB, left %.1f dB" % (db(pr), db(pl)))

print("LFO")
def spread(x):
    c = [centroid(y) for y in frames(x) if np.sqrt(np.mean(y ** 2)) > 1e-4]
    return float(np.std(c) / (np.mean(c) + 1e-9))
s0, s1 = spread(L["fltr_mid"]), spread(L["lfo_freq"])
check(s1 > 3 * s0 + 0.05, "LFO1 -> FREQ: the brightness moves (centroid spread %.2f, baseline %.2f)" % (s1, s0))
def duties(v):
    out = []
    for y in frames(v, 1840):                  # 10 cycles of C4 a frame
        if np.max(np.abs(y)) > 1e-3:
            out.append(float(np.mean(y > np.mean(y))))
    return np.array(out)
d0, d1 = duties(R["puls_base"][2]), duties(R["lfo_pw"][2])
check(np.ptp(d1) > 0.3 and np.ptp(d0) < 0.05, "LFO1 -> PULSE PW: the voice's duty cycle swings %.2f..%.2f (without: %.2f..%.2f)"
      % (d1.min(), d1.max(), d0.min(), d0.max()))
print()
if FAIL:
    print("%d FAILED" % len(FAIL))
    sys.exit(1)
print("ALL FLTR / AMP / LFO CHECKS PASSED")
