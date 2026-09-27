#!/usr/bin/env python3
"""Digi EQ inside the real firmware (digiemu, headless): the parts tests/emu_eq.py cannot reach.

    python3 tests/digiemu_eq.py --digiemu <checkout, after --add of the build> --fw <firmware folder>
        --stock <official .syx> --elekloader <checkout> --mods <core> <digieq> [<others>] --png <dir>

tests/emu_eq.py checks the code itself (knobs -> coefficients, the audio bit-exact against the model, the
settings in the kit, the global override) in seconds. This one boots the firmware and checks what only it
can show:
  1. the EQ page is still a master page (FUNC+LFO) and its knobs reach it;
  2. the EQ is applied to the MASTER MIX, so it reaches the USB stream as well as the analog outputs: a
     test tone is put into the master pair before the EQ runs and measured again in the 12-channel bus
     the USB stream is built from, and the level matches what the model says the settings should do;
  3. the settings are written into the pattern's kit;
  4. SETTINGS > GLOBAL FX/MIX has a MASTER EQ row and YES on it turns the override on.
Prints a report and PASS/FAIL.
"""
import argparse, math, os, struct, sys, time, types, zlib

ap = argparse.ArgumentParser()
ap.add_argument("--digiemu", required=True)
ap.add_argument("--fw", required=True)
ap.add_argument("--stock", required=True)
ap.add_argument("--elekloader", required=True)
ap.add_argument("--mods", nargs="+", required=True)
ap.add_argument("--png", required=True)
a = ap.parse_args()

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import eq_model as EM

sys.path.insert(0, a.elekloader)
from elekloader import syx as _syx, devices as _dev, elemod as _em, link as _link
_st = _syx.Syx.load(a.stock)
_d, _r = _dev.identify(_st.sha256)
MAP = _link.link([_em.load_any(p) for p in a.mods], _st.section(_d.main_section)).map

FW = os.path.join(a.digiemu, "portable", "firmware", a.fw)
sys.path.insert(0, a.digiemu)
syxname = [f for f in os.listdir(FW) if f.endswith(".syx")][0]
os.environ.update({
    "DT2_SYX": os.path.join(FW, syxname), "DT2_SECTIONS": FW + "/sections", "DT2_SNAPSHOTS": FW + "/snapshots",
    "DT2_PLUSDRIVE": FW + "/plusdrive.img", "DT2_MAIN_IMG": FW + "/sections/section_3_MAIN_OS.bin",
    "DT2_DEVICES": FW + "/devices" if os.path.isdir(FW + "/devices") else os.path.join(a.digiemu, "devices"),
    "DIGIKIT_PIT3_PROBE": "1"})
os.chdir(FW)
_tk = types.ModuleType("tkinter")
_tk.Frame = type("Frame", (), {}); _tk.Tk = type("Tk", (), {})
sys.modules["tkinter"] = _tk
for _n in ("ttk", "messagebox", "filedialog", "font"):
    sys.modules["tkinter." + _n] = types.ModuleType("tkinter." + _n)
from unicorn import UC_HOOK_CODE
import emu.gui as G

SNAP = [os.path.join(dp, f) for dp, _, fs in os.walk(FW + "/snapshots") for f in fs if f == "gui.snap"][0]
os.makedirs(a.png, exist_ok=True)
UI_KIT = 0x4199dc44
MASTER = 0x8000ea70                    # the master pair: 32 frames of {L, R}, 32-bit
BUS = 0x80002160                       # the 12-channel bus the USB stream is built from, 48 bytes a frame
BUSFILL = 0x4007227c                   # where the master is copied into it
FA_BASE, FA_LO = 0x80003360, 0x400716c0   # FAST AUDIO (digihealth) runs a copy of the render from SRAM
TONE_HZ = 55.0
AMP = 1 << 29


def xb(n):                                       # the persistent map (src/kitstore.h)
    return 0x20 + n // 6 * 0xa2 + (0, 1, 2, 3, 0x14, 0x15)[n % 6]


def png(path, fb):
    def ch(t_, d):
        return struct.pack(">I", len(d)) + t_ + d + struct.pack(">I", zlib.crc32(t_ + d) & 0xffffffff)
    big = []
    for y in range(64):
        line = b"".join(bytes([0 if fb[y * 128 + x] else 255] * 3) * 4 for x in range(128))
        big += [b"\0" + line] * 4
    open(path, "wb").write(b"\x89PNG\r\n\x1a\n" + ch(b"IHDR", struct.pack(">IIBBBBB", 512, 256, 8, 2, 0, 0, 0))
                           + ch(b"IDAT", zlib.compress(b"".join(big))) + ch(b"IEND", b""))


PLAN, t = [], 600
def at(dt, *act):
    global t
    t += dt
    PLAN.append((t, act))
def tap(code, hold=25, gap=220):
    at(1, "press", code); at(hold, "release", code); at(gap, "wait")
def turn(enc, n):
    for _ in range(abs(n)):
        at(8, "encoder", enc, 4 if n > 0 else -4)
    at(200, "wait")

# 1. the EQ page (FUNC+LFO twice: Compressor, then Master EQ)
for _ in range(2):
    at(1, "press", 1); at(20, "press", 23); at(20, "release", 23); at(5, "release", 1); at(200, "wait")
at(80, "snap", "e1_eq_page")
at(0, "settle", None)
at(400, "measure", "flat")
# 2. band 1 up (knob A), at 55 Hz where its low shelf works
turn(1, 12)
at(0, "settle", None)
at(400, "snap", "e2_band1_up")
at(0, "kit", "after knob A")
at(0, "measure", "band 1 +6 dB")
# 3. band 1 down the other way
turn(1, -24)
at(0, "settle", None)
at(400, "measure", "band 1 -6 dB")
at(80, "snap", "e3_band1_down")
# 4. SETTINGS > GLOBAL FX/MIX > MASTER EQ
tap(6)
for _ in range(22):
    tap(15, 10, 45)
for _ in range(5):
    tap(14, 10, 45)
at(60, "snap", "e4_settings_row")
tap(12)
at(80, "snap", "e5_globalfx")
for _ in range(6):
    tap(15, 10, 45)
at(60, "snap", "e6_master_eq_row")
tap(12)
at(80, "snap", "e7_master_eq_on")
at(0, "global", "after YES")
STEPS = t + 20

state = {"n": 0, "ph": 0, "acc": 0.0, "cnt": 0, "blocks": 0}
log, fails, levels, kits, globals_ = [], [], [], [], []


def sound(kit, b):
    return kit + 0x20 + b * 0xa2


_spin = G.spin
def spin(m, pc, *args, **kw):
    uc = m.uc
    if state["n"] == 0:
        def inject(u, ad, s_, d):                  # a tone into the master, before the EQ runs
            out = bytearray()
            for i in range(32):
                v = int(AMP * math.sin(2 * math.pi * TONE_HZ * state["ph"] / 48000.0))
                state["ph"] += 1
                out += struct.pack(">ii", v, v)
            u.mem_write(MASTER, bytes(out))
        uc.hook_add(UC_HOOK_CODE, inject, begin=MAP["digieq_master"], end=MAP["digieq_master"])

        def measure(u, ad, s_, d):                 # the bus the USB stream is built from
            v = [struct.unpack(">i", u.mem_read(BUS + 48 * i, 4))[0] for i in range(32)]
            state["acc"] += sum(x * x for x in v) / 32.0
            state["cnt"] += 1
            state["blocks"] += 1
        for _b in (BUSFILL, FA_BASE + BUSFILL - FA_LO):   # the original and FAST AUDIO's copy
            uc.hook_add(UC_HOOK_CODE, measure, begin=_b, end=_b)
        def ran(u, ad, s_, d):
            state["eq"] = state.get("eq", 0) + 1
        uc.hook_add(UC_HOOK_CODE, ran, begin=MAP["digieq_run"], end=MAP["digieq_run"])
        uc.ctl_flush_tb()
    for when, act in PLAN:
        if when != state["n"]:
            continue
        k = act[0]
        kit = struct.unpack(">I", uc.mem_read(UI_KIT, 4))[0]
        if k in ("press", "release"):
            E.inbox.append((k, act[1], 0))
        elif k == "encoder":
            E.inbox.append(("encoder", act[1], act[2]))
        elif k == "snap":
            png(os.path.join(a.png, act[1] + ".png"), E.fb)
        elif k == "settle":
            state["acc"], state["cnt"] = 0.0, 0
        elif k == "global":
            globals_.append((act[1], struct.unpack(">I", uc.mem_read(MAP["digieq_global"], 4))[0]))
        elif k == "kit":
            b_ = lambda n: uc.mem_read(kit + xb(n), 1)[0]
            ww = [(b_(6 * b + 4) << 8) | b_(6 * b + 5) for b in range(4)]   # in the old two words' shape
            w = [(ww[b] & ~0x4000, (b_(6 * b + 3) & 0x7f) | (((ww[b] >> 14) & 1) << 7 if b == 0 else 0))
                 for b in range(4)]
            kits.append((act[1], kit, w))
            log.append("%-14s kit %s  EQ words %s" % (act[1], hex(kit), [(hex(x), hex(y)) for x, y in w]))
        elif k == "measure":
            fi_ = list(uc.mem_read(MAP["digieq:fi"], 4)); gi_ = list(uc.mem_read(MAP["digieq:gi"], 4))
            qi_ = list(uc.mem_read(MAP["digieq:qi"], 4)); ty_ = list(uc.mem_read(MAP["digieq:ty"], 4))
            h = 1.0
            for b in range(4):
                if EM.active(fi_[b], gi_[b], qi_[b], ty_[b]):
                    g_, k_, m_ = EM.design(fi_[b], gi_[b], qi_[b], ty_[b])
                    h *= abs(EM.svf_response(g_, k_, m_, TONE_HZ))
            want = 20 * math.log10(max(h, 1e-6))
            mean = state["acc"] / state["cnt"] if state["cnt"] else 0.0
            got = 10 * math.log10(max(mean, 1e-9) / (AMP * AMP / 2.0))
            state["acc"], state["cnt"] = 0.0, 0
            levels.append((act[1], got, want))
            log.append("%-16s USB bus %6.2f dB   model %6.2f dB   (level %s type %s)"
                       % (act[1], got, want, gi_, ty_))
    state["n"] += 1
    r = _spin(m, pc, *args, **kw)
    if state["n"] >= STEPS:
        E.stop_flag.set()
    return r
G.spin = spin

E = G.Emulator(SNAP, syx=os.environ["DT2_SYX"], realtime=False, audio=True)
t0 = time.time()
E.run()
print("error:", E.error, "steps:", state["n"], "blocks measured:", state["blocks"],
      "EQ ran %d times" % state.get("eq", 0), "%.0fs" % (time.time() - t0))
if not state.get("eq"):
    fails.append("the EQ never ran on the master mix")
print("\n".join(log))

if E.error:
    fails.append("the firmware stopped: %s" % E.error)
if state["blocks"] < 100:
    fails.append("the 12-channel bus was never filled (%d blocks)" % state["blocks"])
if len(levels) != 3:
    fails.append("only %d level measurements" % len(levels))
else:
    for name, got, want in levels:
        if abs(got - want) > 0.7:
            fails.append("%s: the USB bus is %.2f dB, the model says %.2f dB" % (name, got, want))
    if levels[1][1] - levels[0][1] < 3.0:
        fails.append("turning band 1 up did not raise the USB bus level")
    if levels[1][1] - levels[2][1] < 6.0:
        fails.append("turning band 1 down did not lower it again")
if not kits or not (kits[0][2][0][0] & 0x8000):
    fails.append("the knob turn was not written into the pattern's kit: %s" % (kits,))
print("digieq_global: %s" % (globals_,))
if [v for _, v in globals_] != [1]:
    fails.append("GLOBAL FX/MIX > MASTER EQ did not turn on: %s" % (globals_,))

print("\n%s" % ("PASS" if not fails else "FAIL\n  " + "\n  ".join(fails)))
sys.exit(1 if fails else 0)
