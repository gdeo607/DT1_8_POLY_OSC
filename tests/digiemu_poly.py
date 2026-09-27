#!/usr/bin/env python3
"""Digi Poly inside the real firmware (digiemu, headless): the parts tests/emu_poly.py cannot reach.

    python3 tests/digiemu_poly.py --digiemu <checkout, after --add of the build> --fw <firmware folder name>
        --stock <official .syx> --elekloader <checkout> --mods <core> <digipoly> [<others>] --png <dir>

tests/emu_poly.py checks the code itself (voice choice, the settings row, the chord's messages, the knob
and level mirroring) in seconds. This one boots the firmware and checks what only it can show:
  1. a track set to POLY gets the MIDI tracks' TRIG page, with the track's level beside it;
  2. pressing that track's key plays the whole chord;
  3. its trigs play the chord while the sequencer runs, and the POLY track's LEVEL and knobs reach every
     voice of the chord, including a voice stolen for the first time after the knob was turned;
  4. SETTINGS > POLY writes the pattern's own kit, and another pattern keeps its own voice allocation;
  5. the LEVEL knob on the POLY track's TRIG page moves the track level;
  6. a live note recorded onto a POLY track goes into the step's NOT1..NOT4, not a bare trig. The
     emulator has no MIDI input, so the note comes from the unit's own key and the sequencer's record
     step (0x4020c29c, which the firmware only sets while it is recording) is forced for that one note -
     which is exactly the condition the record path runs under.
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
from unicorn import UC_HOOK_CODE
from unicorn.m68k_const import UC_M68K_REG_A2, UC_M68K_REG_D2, UC_M68K_REG_A7
import emu.gui as G

SNAP = [os.path.join(dp, f) for dp, _, fs in os.walk(FW + "/snapshots") for f in fs if f == "gui.snap"][0]
os.makedirs(a.png, exist_ok=True)
UI_KIT, ENG_KIT = 0x4199dc44, 0x800019ac
LOADED, PARAMS, LEVELS = 0x800014f0 + 0x131 * 4, 0x800014f2, 0x80002760
PAT = 0x409bac18
VOICE_START = 0x40077a76                       # the render starts voice d2 for message a2


def xb(n):                                       # the persistent map (src/kitstore.h)
    return 0x20 + n // 6 * 0xa2 + (0, 1, 2, 3, 0x14, 0x15)[n % 6]


def png(path, fb):
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    big = []
    for y in range(64):
        line = b"".join(bytes([0 if fb[y * 128 + x] else 255] * 3) * 4 for x in range(128))
        big += [b"\0" + line] * 4
    open(path, "wb").write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 512, 256, 8, 2, 0, 0, 0))
                           + chunk(b"IDAT", zlib.compress(b"".join(big))) + chunk(b"IEND", b""))


PLAN, t = [], 600
def at(dt, *act):
    global t
    t += dt
    PLAN.append((t, act))
def tap(code, hold=20, gap=40):
    at(1, "press", code); at(hold, "release", code); at(gap, "wait")
def turn(enc, n):                               # n notches, one event each
    for _ in range(abs(n)):
        at(4, "encoder", enc, 4 if n > 0 else -4)
    at(40, "wait")

# 1. track 1 -> POLY, its TRIG page
at(1, "press", 1); at(20, "press", 20); at(20, "release", 20); at(5, "release", 1); at(60, "wait")
for _ in range(4):
    tap(15, 20, 60)
tap(12, 20, 80); tap(13, 20, 60)
at(0, "machines")
at(0, "chord", (0x44, 0x47, 0x4b))              # the track's NOT2-NOT4: a major 7th chord
tap(19, 20, 150); at(0, "snap", "q1_trig_poly")
# 2. the track's key plays the chord
at(0, "phase", "key"); at(1, "press", 24); at(60, "release", 24); at(120, "wait"); at(0, "phase", None)
# 3. trigs, then PLAY; knobs while it runs
tap(9, 20, 60); tap(24, 20, 40); tap(32, 20, 40); tap(9, 20, 60)
at(0, "phase", "play"); tap(10, 20, 400)
tap(21, 20, 60)                                 # FLTR page of the POLY track
at(0, "follow", "before")
turn(5, 12)                                     # knob E: filter frequency
turn(9, -12)                                    # the LEVEL knob
at(0, "follow", "after the knobs")
at(300, "follow", "after more chords")          # a voice stolen for the first time since the knobs
tap(11, 20, 80); at(0, "phase", None)
# 4. SETTINGS > POLY, and another pattern's own allocation
tap(6, 20, 150)
for _ in range(20):          # to the bottom of the list, then one up: MOD MATRIX sits under POLY
    tap(15, 10, 45)
tap(14, 20, 120)
at(60, "snap", "q2_settings")
tap(17, 20, 200); tap(12, 20, 200)              # RIGHT to track 2, YES: out of the pool
at(60, "snap", "q3_settings_track2_out")
tap(13, 20, 80); tap(13, 20, 80)
at(0, "locks", "pattern 1")
at(1, "press", 3); at(20, "press", 25); at(20, "release", 25); at(5, "release", 3); at(400, "locks", "pattern 2")
at(1, "press", 3); at(20, "press", 24); at(20, "release", 24); at(5, "release", 3); at(400, "locks", "pattern 1 again")
# 5. the TRIG page's LEVEL knob
tap(19, 20, 200)                                # the POLY track's TRIG page
at(0, "level", "before")
turn(9, -14)
at(200, "level", "after 14 down")
at(0, "snap", "q4_trig_level")
# 6. recording a live note onto the POLY track
tap(20, 20, 150)                                # off the TRIG page
at(0, "clearnotes", None)
at(0, "force", 5)                               # the sequencer's record step, as while recording
at(1, "press", 24); at(80, "release", 24); at(300, "wait")
at(0, "force", 0)
at(0, "notes", "after a recorded note")
STEPS = t + 2

state = {"n": 0, "phase": None}
starts = {}
log, fails = [], []

_spin = G.spin
def spin(m, pc, *args, **kw):
    uc = m.uc
    if state["n"] == 0:
        def vstart(u, ad, s_, d):
            ph = state["phase"]
            if not ph:
                return
            msg = u.reg_read(UC_M68K_REG_A2)
            v = u.reg_read(UC_M68K_REG_D2)
            note, mid, snd = (struct.unpack(">i", u.mem_read(msg + 24, 4))[0],
                              struct.unpack(">i", u.mem_read(msg + 12, 4))[0],
                              struct.unpack(">I", u.mem_read(msg + 40, 4))[0])
            kit = struct.unpack(">I", u.mem_read(ENG_KIT, 4))[0]
            st = (snd - kit - 0x20) // 0xa2 if snd else v
            starts.setdefault(ph, []).append((state["n"], v, note, mid, st))
        uc.hook_add(UC_HOOK_CODE, vstart, begin=VOICE_START, end=VOICE_START)
        if "digipoly_recnote" in MAP:
            def recn(u, ad, s_, d):
                sp = u.reg_read(0x100 + 15) if False else u.reg_read(UC_M68K_REG_A7)
                a = struct.unpack(">3I", u.mem_read(sp + 4, 12))
                st = struct.unpack(">i", u.mem_read(0x4020c29c, 4))[0]
                state.setdefault("rec", []).append((a[1], a[2], st))
            uc.hook_add(UC_HOOK_CODE, recn, begin=MAP["digipoly_recnote"], end=MAP["digipoly_recnote"])

            def liveon(u, ad, s_, d):
                sp = u.reg_read(UC_M68K_REG_A7)
                a = struct.unpack(">3I", u.mem_read(sp + 4, 12))
                if state.get("force"):
                    u.mem_write(0x4020c29c, struct.pack(">i", state["force"]))
                st = struct.unpack(">i", u.mem_read(0x4020c29c, 4))[0]
                state.setdefault("live", []).append((a[0], a[1], st))
            uc.hook_add(UC_HOOK_CODE, liveon, begin=0x400d53dc, end=0x400d53dc)
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
        elif k == "phase":
            state["phase"] = act[1]
        elif k == "chord":
            uc.mem_write(PAT + 0x385, bytes(act[1]))
        elif k == "machines":
            m_ = [uc.mem_read(kit + 0x9e + i * 0xa2, 1)[0] for i in range(8)]
            log.append("machines: %s" % m_)
            if m_[0] != 4:
                fails.append("track 1 is not POLY")
        elif k == "level":
            state.setdefault("lev", []).append((act[1], list(uc.mem_read(kit + 0x10, 8))[0]))
            log.append("%-16s track 1 level %d" % (act[1], list(uc.mem_read(kit + 0x10, 8))[0]))
        elif k == "force":
            state["force"] = act[1]
        elif k == "clearnotes":
            for i in range(4):
                uc.mem_write(PAT + 0x280 + 0x40 * i, b"\xff" * 64)
        elif k == "notes":
            d = [list(uc.mem_read(PAT + 0x280 + 0x40 * i, 64)) for i in range(4)]
            rows = [(st, [d[i][st] for i in range(4)]) for st in range(64)
                    if d[0][st] != 0xff]
            state["notes"] = rows
            log.append("%-16s steps with a note: %s" % (act[1], rows[:6]))
        elif k == "locks":
            lk = [uc.mem_read(kit + xb(6 * i + 3), 1)[0] >> 7 for i in range(8)]
            log.append("%-16s kit %s  out of the POLY pool: %s" % (act[1], hex(kit), lk))
            state.setdefault("locks", []).append((act[1], kit, lk))
        elif k == "follow":
            loaded = struct.unpack(">8I", uc.mem_read(LOADED, 32))
            prm = struct.unpack(">%dh" % (8 + 53 * 8), uc.mem_read(PARAMS, 2 * (8 + 53 * 8)))
            blk = [prm[8 + 53 * w: 8 + 53 * (w + 1)] for w in range(8)]
            lv = struct.unpack(">8h", uc.mem_read(LEVELS, 16))
            own = kit + 0x20
            stolen = [w for w in range(1, 8) if loaded[w] == own]
            badlv = [w for w in stolen if lv[w] != lv[0]]
            log.append("%-22s chord voices %s; levels %s" % (act[1], stolen, lv))
            state.setdefault("follow", []).append((act[1], stolen, badlv, lv, blk))
    state["n"] += 1
    r = _spin(m, pc, *args, **kw)
    if state["n"] >= STEPS:
        E.stop_flag.set()
    return r
G.spin = spin

E = G.Emulator(SNAP, syx=os.environ["DT2_SYX"], realtime=False, audio=True)
t0 = time.time()
E.run()
print("error:", E.error, "steps:", state["n"], "%.0fs" % (time.time() - t0))
print("\n".join(log))

# ---- checks ----
key = starts.get("key", [])
kv = [e[1] for e in key]
print("the track's key started: %s" % (key,))
if len(key) != 4 or len(set(kv)) != 4 or 0 not in kv or any(e[4] != 0 for e in key):
    fails.append("the track's key did not play the chord on four voices with its own sound: %s" % (key,))
elif sorted(e[2] for e in key) != sorted([60, 64, 67, 71]):
    fails.append("the key's chord notes are %s" % (sorted(e[2] for e in key),))

g = {}
for n, v, note, mid, st in starts.get("play", []):
    g.setdefault(n, []).append((v, note, mid, st))
chords = 0
for n in sorted(g):
    ev = g[n]
    poly = [e for e in ev if e[3] == 0]
    if len(poly) < 2:
        continue
    chords += 1
    if chords <= 3:
        print("  step %5d: voices %s notes %s" % (n, [e[0] for e in poly], sorted(e[1] for e in poly)))
    if len(set(e[0] for e in poly)) != len(poly):
        fails.append("a voice was used twice in one chord")
if chords < 2:
    fails.append("only %d chords played while the sequencer ran" % chords)

lev = state.get("lev", [])
print("TRIG page level: %s" % (lev,))
if len(lev) != 2 or lev[1][1] >= lev[0][1]:
    fails.append("the LEVEL knob did not lower the track level on the POLY TRIG page: %s" % (lev,))
print("liveNoteOn calls (track, note, step): %s" % (state.get("live", [])[:8],))
print("digipoly_recnote calls (track, note, step): %s" % (state.get("rec", [])[:6],))
rows = state.get("notes", [])
if not rows:
    fails.append("no note was recorded onto the POLY track")
elif not any(r[1][0] <= 127 and r[1][1] == 0x40 for r in rows):
    fails.append("the recorded step does not hold a note and an empty chord: %s" % (rows[:4],))

fl = state.get("follow", [])
if len(fl) == 3:
    # the words the knob itself moved on the POLY track's own voice (the rest of the block is the
    # engine's running state for that voice, which differs from voice to voice by nature)
    moved = [sl for sl in range(53) if fl[1][4][0][sl] != fl[0][4][0][sl]]
    print("knob E moved slots %s on the POLY voice" % [hex(x) for x in moved])
    if not moved:
        fails.append("knob E changed nothing on the POLY track")
    for name, stolen, badlv, lv, blk in fl[1:]:
        if not stolen:
            fails.append("%s: no voice was playing the POLY track's sound" % name)
        # every chord voice must carry the knob's value. Right after the turn the voices that are
        # sounding are still ramping towards it (the engine smooths a playing voice), so the strict
        # comparison waits for the settled snapshot, by which time voices have also been stolen anew.
        if name.startswith("after more"):
            ref = [0] + stolen
            bad = [(w, hex(sl), blk[w][sl]) for w in ref for sl in moved if blk[w][sl] != blk[0][sl]]
            if bad:
                fails.append("%s: the knob did not reach every chord voice %s" % (name, bad[:6]))
        elif not [w for w in stolen if all(blk[w][sl] == blk[stolen[0]][sl] for sl in moved)]:
            fails.append("%s: the knob reached no chord voice" % name)
        if badlv:
            fails.append("%s: voices %s are not at the POLY track's level (%s)" % (name, badlv, lv))
    if fl[1][3][0] == fl[0][3][0]:
        fails.append("the LEVEL knob changed nothing on the POLY track")
else:
    fails.append("the knob checks did not run")

lk = state.get("locks", [])
if len(lk) == 3:
    if lk[0][2][1] == 0:
        fails.append("SETTINGS did not take track 2 out of this pattern's pool")
    if lk[1][1] == lk[0][1]:
        fails.append("the second pattern uses the same kit, so this says nothing about per-pattern locks")
    elif lk[1][2][1] != 0:
        fails.append("the second pattern inherited the first pattern's voice allocation")
    if lk[2][2] != lk[0][2]:
        fails.append("the first pattern lost its voice allocation (%s -> %s)" % (lk[0][2], lk[2][2]))
else:
    fails.append("the lock checks did not run")

print("PASS" if not fails else "FAIL:\n  " + "\n  ".join(fails))
sys.exit(1 if fails else 0)
