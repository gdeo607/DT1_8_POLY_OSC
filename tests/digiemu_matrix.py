#!/usr/bin/env python3
"""Digi Matrix inside the real firmware (digiemu, headless): the parts tests/emu_matrix.py cannot reach.

    python3 tests/digiemu_matrix.py --digiemu <checkout, after --add of the build> --fw <firmware folder>
        --stock <official .syx> --elekloader <checkout> --mods <core> <digimatrix> [<others>] --png <dir>

tests/emu_matrix.py checks the code itself (both engine passes, the clamps, the keys, the knobs, the
drawing) in seconds. This one boots the firmware and checks what only it can show:
  1. SETTINGS has a MOD MATRIX row and YES opens the page, drawn over the screen;
  2. its keys and knobs write the pattern's own kit (slots 46 and 47 of each track's sound);
  3. the engine really applies a routing: a track's LFO moves another track's parameter word, and stops
     moving it when the slot is switched off.
Prints a report and PASS/FAIL.
"""
import argparse, os, struct, sys, time, types, zlib

ap = argparse.ArgumentParser()
ap.add_argument("--digiemu", required=True)
ap.add_argument("--fw", required=True)
ap.add_argument("--stock", required=True)
ap.add_argument("--elekloader", required=True)
ap.add_argument("--mods", nargs="+", required=True)
ap.add_argument("--png", required=True)
a = ap.parse_args()

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
import emu.gui as G

SNAP = [os.path.join(dp, f) for dp, _, fs in os.walk(FW + "/snapshots") for f in fs if f == "gui.snap"][0]
os.makedirs(a.png, exist_ok=True)
UI_KIT, ENG_KIT = 0x4199dc44, 0x800019ac
WORDS = 0x80002760                               # the smoothed words: slot s of voice v at +18+106v+2s
LFOSTATE = 0x421f3e14                            # the LFO stage's value: LFO1 at +80v, LFO2 at +80v+0x28
DEST_SLOT = 45                                   # AMP page knob H
SRC_TRACK, DST_TRACK = 0, 1


def xb(n):                                       # the persistent map (src/kitstore.h)
    return 0x20 + n // 6 * 0xa2 + (0, 1, 2, 3, 0x14, 0x15)[n % 6]


def png(path, fb):
    def chunk(t_, d):
        return struct.pack(">I", len(d)) + t_ + d + struct.pack(">I", zlib.crc32(t_ + d) & 0xffffffff)
    big = []
    for y in range(64):
        line = b"".join(bytes([0 if fb[y * 128 + x] else 255] * 3) * 4 for x in range(128))
        big += [b"\0" + line] * 4
    open(path, "wb").write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 512, 256, 8, 2, 0, 0, 0))
                           + chunk(b"IDAT", zlib.compress(b"".join(big))) + chunk(b"IEND", b""))


def route(strk, slfo, dtrk, on, dest, own):
    return ((strk & 7) | ((slfo & 1) << 3) | ((dtrk & 7) << 4) | (0x80 if on else 0)
            | (((dest + 1) & 0x7f) << 8) | (0x8000 if own else 0))


PLAN, t = [], 600
def at(dt, *act):
    global t
    t += dt
    PLAN.append((t, act))
def tap(code, hold=25, gap=260):
    at(1, "press", code); at(hold, "release", code); at(gap, "wait")
def turn(enc, n):
    for _ in range(abs(n)):
        at(30, "encoder", enc, 4 if n > 0 else -4)
    at(200, "wait")

# --- 1/2. the SETTINGS row, the page, and what its keys and knobs write ---
tap(23, 20, 150)                                 # LFO page of track 1: give its LFO1 some speed
turn(1, 6)
tap(6, 20, 150)                                  # SETTINGS
for _ in range(20):                              # down to the last rows
    tap(15, 10, 45)
at(80, "snap", "m1_settings_row")
at(0, "grab", "row")
tap(12, 20, 150)                                 # YES: the page
at(80, "snap", "m2_page_empty")
at(0, "open", "after YES")
tap(12, 20, 120)                                 # YES: slot 1 on
at(0, "kit", "slot 1 on")
turn(3, 1)                                       # knob C: destination track 1 -> 2
turn(4, 4)                                       # knob D: destination parameter, a few steps on
turn(5, 4)                                       # knob E: depth, a few steps up
at(80, "snap", "m3_page_row1")
at(0, "kit", "row 1 edited")
tap(15, 20, 80); tap(12, 20, 120)                # DOWN, YES: slot 2 on as well
at(60, "snap", "m4_two_rows")
at(0, "kit", "two rows on")
tap(12, 20, 120)                                 # YES again: slot 2 off
tap(13, 20, 150)                                 # NO: leave the page
at(0, "open", "after NO")
tap(13, 20, 100)                                 # out of SETTINGS

# --- 3. the engine: the routing moves the other track's parameter word ---
at(0, "poke", 1)                                 # the engine kit: T1 LFO1 -> T2 AMP.VOL, +64, OWN on
at(0, "phase", "on")
at(1, "press", 24)                               # trig key of track 1: its LFO runs
at(400, "release", 24)
at(200, "phase", None)
at(0, "poke", 0)                                 # the slot off
at(0, "phase", "off")
at(1, "press", 24)
at(400, "release", 24)
at(200, "phase", None)
STEPS = t + 20

state = {"n": 0, "phase": None}
log, fails, samples, lfos, kits, opens, rows = [], [], {}, {}, [], [], []


def sound(kit, t_):
    return kit + 0x20 + t_ * 0xa2


_spin = G.spin
def spin(m, pc, *args, **kw):
    uc = m.uc
    if state["phase"]:
        v = struct.unpack(">h", uc.mem_read(WORDS + 18 + 106 * DST_TRACK + 2 * DEST_SLOT, 2))[0]
        lv = struct.unpack(">i", uc.mem_read(LFOSTATE + 80 * SRC_TRACK, 4))[0]
        samples.setdefault(state["phase"], []).append(v)
        lfos.setdefault(state["phase"], []).append(lv)
    for when, act in PLAN:
        if when != state["n"]:
            continue
        k = act[0]
        ui = struct.unpack(">I", uc.mem_read(UI_KIT, 4))[0]
        if k in ("press", "release"):
            E.inbox.append((k, act[1], 0))
        elif k == "encoder":
            E.inbox.append(("encoder", act[1], act[2]))
        elif k == "snap":
            png(os.path.join(a.png, act[1] + ".png"), E.fb)
        elif k == "phase":
            state["phase"] = act[1]
        elif k == "open":
            opens.append((act[1], struct.unpack(">I", uc.mem_read(MAP["digimatrix_open"], 4))[0]))
        elif k == "grab":
            rows.append(bytes(E.fb))
        elif k == "kit":
            b_ = lambda n: uc.mem_read(ui + xb(n), 1)[0]
            r = [(b_(6 * i) << 8) | b_(6 * i + 1) for i in range(8)]
            dp = [b_(6 * i + 2) for i in range(8)]
            kits.append((act[1], ui, r, dp))
            log.append("%-14s kit %s  routings %s  depths %s" % (act[1], hex(ui), [hex(x) for x in r], dp))
        elif k == "poke":
            eng = struct.unpack(">I", uc.mem_read(ENG_KIT, 4))[0]
            r = route(SRC_TRACK, 0, DST_TRACK, act[1], DEST_SLOT, 1) if act[1] else 0
            uc.mem_write(eng + xb(0), bytes([r >> 8])); uc.mem_write(eng + xb(1), bytes([r & 0xff]))
            uc.mem_write(eng + xb(2), bytes([64 + 128]))
            log.append("engine kit %s row 1 = %s" % (hex(eng), hex(r)))
    state["n"] += 1
    r_ = _spin(m, pc, *args, **kw)
    if state["n"] >= STEPS:
        E.stop_flag.set()
    return r_
G.spin = spin

E = G.Emulator(SNAP, syx=os.environ["DT2_SYX"], realtime=False, audio=True)
t0 = time.time()
E.run()
print("error:", E.error, "steps:", state["n"], "%.0fs" % (time.time() - t0))
print("\n".join(log))

# ---- checks ----
if E.error:
    fails.append("the firmware stopped: %s" % E.error)

print("digimatrix_open: %s" % (opens,))
if [v for _, v in opens] != [1, 0]:
    fails.append("the page did not open on YES and close on NO: %s" % (opens,))

if len(kits) == 3:
    (_, k1, r1, d1), (_, k2, r2, d2), (_, k3, r3, d3) = kits
    if not (r1[0] & 0x80):
        fails.append("YES did not switch slot 1 on: %s" % hex(r1[0]))
    if (r2[0] >> 4) & 7 != 1:
        fails.append("knob C did not move the destination track to 2: %s" % hex(r2[0]))
    if ((r2[0] >> 8) & 0x7f) - 1 <= 1:
        fails.append("knob D did not move the destination parameter on: %s" % hex(r2[0]))
    if d2[0] - 128 <= 0:
        fails.append("knob E did not raise the depth: %s" % (d2[0] - 128))
    if not (r3[1] & 0x80):
        fails.append("DOWN + YES did not switch slot 2 on: %s" % hex(r3[1]))
    if k1 != k2 or k2 != k3:
        fails.append("the kit pointer moved under the page")
else:
    fails.append("only %d kit reads" % len(kits))

on, off = samples.get("on", []), samples.get("off", [])
def spread(s):
    return (min(s), max(s), max(s) - min(s)) if s else (0, 0, 0)
print("track 2's AMP.VOL word: routed %s over %d samples, not routed %s over %d"
      % (spread(on), len(on), spread(off), len(off)))
print("track 1's LFO1 value:   routed %s, not routed %s" % (spread(lfos.get("on", [])), spread(lfos.get("off", []))))
if spread(lfos.get("on", []))[2] < 1000:
    fails.append("track 1's LFO1 never moved, so the test could not see a routing")
if spread(on)[2] < 500:
    fails.append("the routing did not move track 2's parameter word (spread %d)" % spread(on)[2])
if spread(off)[2] != 0:
    fails.append("the word still moved with the slot off (spread %d)" % spread(off)[2])

print("\n%s" % ("PASS" if not fails else "FAIL\n  " + "\n  ".join(fails)))
sys.exit(1 if fails else 0)
