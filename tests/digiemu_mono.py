#!/usr/bin/env python3
"""Digi Mono in the real firmware: boot a build in digiemu (headless), put a Digi Mono machine on track 1,
play it from the sequencer, and check what the render hands on is the engine's output, bit for bit.

    <digiemu's python> tests/digiemu_mono.py --digiemu <digiemu checkout> --fw <firmware folder name>
        --machine SAW [--knobs B:+20,E:-5] [--png <dir>] [--wav <file>]
        --stock <official .syx> --elekloader <checkout> --mods <core.elemod> <digimono.elemod>

The build must be set up in digiemu first (python -m emu.portable --add BUILD.syx --yes); it needs core 2.1
and digimono. Needs digiemu's patched Unicorn (its .venv, with numpy) and gcc (tests/mono_lib.py).

Steps: pattern A16 (empty in the factory project); FUNC+SRC, the machine, YES; the SRC page (screenshot:
the machine's knob names), knob turns; RECORD, trigs on steps 1, 5, 9 and 13 of track 1, RECORD; PLAY for
~2 s, STOP. Checks:
  1. the machine list has the five machines and the track took the one asked for (screenshots);
  2. the SRC page's knobs B..H have the machine's defaults, and a turned knob moves over 0..127;
  3. voice 0 was started once per trig;
  4. every block voice 0 hands to the filter stage (0x80001a18, read right after digimono_rblock) equals
     the engine's own block, replayed on this PC from the same starts, notes and parameter words (Q31 =
     sample << 16), from the engine state the voice had before its first start; a block of a voice not
     playing (its amp envelope silent for 32 blocks, no start) is silence and leaves the engine as it was: the render hook, the note and
     TUNE path, the knob mapping and the start detection;
  5. the master output carries it: the fundamental of the master mix is the note's.
"""
import argparse, collections, math, os, struct, sys, time, types, wave, zlib

HERE = os.path.dirname(os.path.abspath(__file__))
ap = argparse.ArgumentParser()
ap.add_argument("--digiemu", required=True)
ap.add_argument("--fw", required=True)
ap.add_argument("--machine", default="SAW", choices=["SIN", "NOIS", "SAW", "PULS", "ENS", "VO"])
ap.add_argument("--knobs", default="", help="knob turns, e.g. B:+20,E:-5 (notches)")
ap.add_argument("--png", default="")
ap.add_argument("--wav", default="")
ap.add_argument("--menu-before", type=int, default=0,
                help="added machines listed before Digi Mono's in FUNC+SRC (e.g. 1 with digisophie's SOPHIE)")
ap.add_argument("--stock", required=True, help="official OS 1.53 .syx (for the link map)")
ap.add_argument("--elekloader", required=True)
ap.add_argument("--mods", nargs="+", required=True, help="the build's .elemod files, core first")
a = ap.parse_args()

sys.path.insert(0, a.elekloader)
from elekloader import syx as _syx, devices as _dev, elemod as _em, link as _link
_st = _syx.Syx.load(a.stock)
_d, _r = _dev.identify(_st.sha256)
_L = _link.link([_em.load_any(p) for p in a.mods], _st.section(_d.main_section))
MAP = _L.map
RUN0, RUN1 = _L.layout["ddr"]                      # the mods' code and data in RAM
VOICES = MAP["digimono:voices"]                    # struct digimono_voice voices[8]; voice 0's engine state first
TRACK_MACH = MAP["core_track_machine"]             # core 2.1: the machine each voice plays (ours render as ONESHOT)

sys.path.insert(0, HERE)
import numpy as np
import mono_lib as H

MODEL = H.NAMES.index(a.machine)
KNOBS = "BCEFGHD"                                   # Digi Mono's knobs (digimono.c knob_slot, knob_p)
SLOTS = [18, 19, 21, 22, 23, 24, 20]
DEFAULTS = [[0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0], [0, 40, 0, 0, 0, 0, 0], [0, 40, 0, 64, 0, 40, 0],
            [63, 63, 63, 0, 0, 127, 0], [43, 113, 64, 0, 40, 100, 0]]
KNOB_P = [[-1] * 7, [0, 1, 2, -1, -1, -1, -1], [0, 1, 2, 4, 5, 6, -1], [0, 1, 2, 4, 5, 6, 3],
          [0, 1, 2, 3, 5, 6, 4], [0, 1, 2, 4, 5, 6, 3]]
MACH_FIRST = 20                                     # digimono's machine ids: 20..25
TURNS = []
for s in filter(None, a.knobs.split(",")):
    k, n = s.split(":")
    TURNS.append(("ABCDEFGH".index(k.upper()), int(n)))

DE = os.path.abspath(a.digiemu)
FW = os.path.join(DE, "portable", "firmware", a.fw)
sys.path.insert(0, DE)
syxname = [f for f in os.listdir(FW) if f.endswith(".syx")][0]
os.environ.update({"DT2_SYX": os.path.join(FW, syxname), "DT2_SECTIONS": FW + "/sections",
                   "DT2_SNAPSHOTS": FW + "/snapshots", "DT2_PLUSDRIVE": FW + "/plusdrive.img",
                   "DT2_MAIN_IMG": FW + "/sections/section_3_MAIN_OS.bin",
                   "DT2_DEVICES": FW + "/devices" if os.path.isdir(FW + "/devices") else os.path.join(DE, "devices"),
                   "DIGIKIT_PIT3_PROBE": "1"})
PNG = os.path.abspath(a.png) if a.png else ""
WAV = os.path.abspath(a.wav) if a.wav else ""
if PNG:
    os.makedirs(PNG, exist_ok=True)
os.chdir(FW)
_tk = types.ModuleType("tkinter")
_tk.Frame = type("Frame", (), {}); _tk.Tk = type("Tk", (), {})
sys.modules["tkinter"] = _tk
for _n in ("ttk", "messagebox", "filedialog", "font"):
    sys.modules["tkinter." + _n] = types.ModuleType("tkinter." + _n)
from unicorn import UC_HOOK_CODE
from unicorn.m68k_const import UC_M68K_REG_A7
import emu.gui as G

SNAP = [os.path.join(dp, f) for dp, _, fs in os.walk(FW + "/snapshots") for f in fs if f == "gui.snap"][0]
AFTER = 0x40077fc8                                  # right after digimono_rblock returns (voice 0's block: 0x80001a18)
MASTER = 0x400721e6                                 # the master pair at 0x8000ea70 (digieq's site)
FAIL = []


def check(ok, what):
    print(("  ok    " if ok else "  FAIL  ") + what)
    if not ok:
        FAIL.append(what)


def png(path, fb):
    big = []
    for y in range(64):
        line = b"".join(bytes([0 if fb[y * 128 + x] else 255] * 3) * 4 for x in range(128))
        big += [b"\0" + line] * 4
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    open(path, "wb").write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 512, 256, 8, 2, 0, 0, 0))
                           + chunk(b"IDAT", zlib.compress(b"".join(big))) + chunk(b"IEND", b""))


PLAN = []
t = 300
def at(dt, *act):
    global t
    t += dt
    PLAN.append((t, act))
def tap(code, hold=20, gap=40):
    at(1, "press", code); at(hold, "release", code); at(gap, "wait")

at(1, "press", 3); at(20, "press", 39); at(20, "release", 39); at(5, "release", 3); at(150, "wait")   # PTN + 16
at(1, "press", 1); at(20, "press", 20); at(20, "release", 20); at(5, "release", 1); at(80, "wait")    # FUNC+SRC
for _ in range(4 + a.menu_before + MODEL):          # ONESHOT WERP REPITCH SLICE, others, then ours
    tap(15, 20, 60)
at(0, "snap", "1_machine_list")
tap(12, 20, 80); tap(13, 20, 60)                    # YES, NO
tap(20, 20, 120)                                    # the SRC page
at(0, "snap", "2_src_page"); at(0, "knobs", "defaults")
for k, n in TURNS:
    for _ in range(abs(n)):
        at(3, "encoder", 1 + k, 4 if n > 0 else -4)
    at(60, "wait")
at(0, "knobs", "turned")
tap(9, 20, 60)                                      # RECORD
for k in (24, 28, 32, 36):                          # steps 1, 5, 9, 13 of track 1
    tap(k, 20, 40)
tap(9, 20, 60)                                      # RECORD off
at(0, "rec", True)
tap(10, 20, 20)                                     # PLAY
at(2600, "snap", "3_playing")
tap(11, 20, 40)                                     # STOP
at(0, "rec", False)
STEPS = t + 2

st = {"n": 0, "rec": False, "state": None, "init": None, "ins": 0}
cost = []                                            # instructions in the mods' code, per render block
blocks = []                                          # (start bit, note word, 8 SRC words, 32 samples)
master = []
knobs = {}


def after(u, ad, s, d):
    if not st["rec"]:
        return
    sb = struct.unpack(">I", u.mem_read(0x80001228, 4))[0] & 1
    if sb and st["init"] is None:
        st["init"] = st["state"]                    # the engine's state before this block: the last one's after
    st["state"] = bytes(u.mem_read(VOICES, H.VOICE_SIZE))
    blocks.append((sb,
                   struct.unpack(">i", u.mem_read(0x80001f28, 4))[0],
                   struct.unpack(">8h", u.mem_read(0x80002772 + 34, 16)),
                   struct.unpack(">32i", u.mem_read(0x80001a18, 128)),
                   u.mem_read(TRACK_MACH, 1)[0],
                   struct.unpack(">2i", u.mem_read(0x4199df54, 8))))   # voice 0's amp phase and level


def mst(u, ad, s, d):
    if st["rec"]:
        master.append(struct.unpack(">64i", u.mem_read(0x8000ea70, 256)))
        cost.append(st["ins"])
    st["ins"] = 0


def count(u, ad, s, d):
    st["ins"] += 1


_spin = G.spin
def spin(m, pc, *args, **kw):
    n = st["n"]
    if n == 0:
        m.uc.hook_add(UC_HOOK_CODE, after, begin=AFTER, end=AFTER)
        m.uc.hook_add(UC_HOOK_CODE, mst, begin=MASTER, end=MASTER)
        m.uc.hook_add(UC_HOOK_CODE, count, begin=RUN0, end=RUN1)
    for when, act in PLAN:
        if when != n:
            continue
        if act[0] in ("press", "release"):
            E.inbox.append((act[0], act[1], 0))
        elif act[0] == "encoder":
            E.inbox.append(("encoder", act[1], act[2]))
        elif act[0] == "snap" and PNG:
            png(os.path.join(PNG, act[1] + ".png"), E.fb)
        elif act[0] == "knobs":
            kit = struct.unpack(">I", m.uc.mem_read(0x4199dc44, 4))[0]
            snd = kit + 0x20
            knobs[act[1]] = (m.uc.mem_read(snd + 0x7e, 1)[0],
                             [struct.unpack(">H", m.uc.mem_read(snd + 0x14 + 2 * s, 2))[0] >> 8 for s in SLOTS])
        elif act[0] == "rec":
            st["rec"] = act[1]
    st["n"] += 1
    r = _spin(m, pc, *args, **kw)
    if st["n"] >= STEPS:
        E.stop_flag.set()
    return r
G.spin = spin

print("digiemu: %s, machine MONO %s, knobs %s" % (a.fw, a.machine, a.knobs or "untouched"))
t0 = time.time()
E = G.Emulator(SNAP, syx=os.environ["DT2_SYX"], realtime=False, audio=True)
E.run()
print("  ran %.0f s: %d blocks of voice 0, %d of the master" % (time.time() - t0, len(blocks), len(master)))

print("the track and its SRC page")
mach, dk = knobs.get("defaults", (None, None))
check(mach == MACH_FIRST + MODEL, "track 1's machine is %s (%s)" % (MACH_FIRST + MODEL, mach))
check(dk == DEFAULTS[MODEL], "knobs B C E F G H hold the machine's defaults %s (%s)" % (DEFAULTS[MODEL], dk))
if TURNS:
    # digiemu's encoder events do not map one to one onto the firmware's steps (it accelerates), so the check
    # is the direction and the range: a turned knob moves the right way, past its stock range where it had
    # one (B was PLAY, 0..3; G was LOOP, 0..4), and stays within 0..127.
    _, tk = knobs["turned"]
    ok = True
    for k, n in TURNS:
        L = "ABCDEFGH"[k]
        if L not in KNOBS:
            continue
        i = KNOBS.index(L)
        d0, d1 = DEFAULTS[MODEL][i], tk[i]
        ok &= 0 <= d1 <= 127 and ((d1 > d0) if n > 0 else (d1 < d0) if d0 > 0 else d1 == 0)
        if n > 5 and L in "BG":
            ok &= d1 > 4
    check(ok, "the turns %s moved the knobs over 0..127: B C E F G H %s -> %s" % (a.knobs, DEFAULTS[MODEL], tk))

print("the render")
if cost:
    c = np.array(cost[len(cost) // 4:])
    print("  cost: %.0f instructions a block in the mods' code (core + digimono), max %d; the stock render is"
          " about 84,000 a block" % (c.mean(), c.max()))
starts = sum(b[0] for b in blocks)
secs = len(blocks) * 32 / 48000.0
check(0.6 * secs / 0.5 <= starts <= 1.4 * secs / 0.5 + 2,
      "voice 0 started %d times in %.1f s (a trig every 4 steps at 120 BPM: every 0.5 s)" % (starts, secs))
mine = [b for b in blocks if b[4] == MACH_FIRST + MODEL]
check(len(mine) > len(blocks) * 0.9, "voice 0 plays machine %d in %d of %d blocks" % (MACH_FIRST + MODEL, len(mine), len(blocks)))

# replay on this PC: the same engine, the same starts, notes and words, block by block
e = H.Engine(MODEL)
if st["init"]:                                       # the device's state (big-endian) into this PC's struct
    le = H.swap_state(st["init"])
    e.v.raw[:] = le
same = diff = 0
first_bad = None
started = False
skipped = 0
quiet = 32                                           # digimono.c: QUIET_BLOCKS of a silent amp envelope
for i, (sb, note, words, samples, mb, amp) in enumerate(blocks):
    if mb != MACH_FIRST + MODEL:
        continue
    if sb:
        e.trig()
        started = True
        quiet = 0
    else:
        if amp[0] != 0 or abs(amp[1]) > (1 << 19):
            quiet = 0
        elif quiet < 32:
            quiet += 1
        if quiet >= 32:                              # the voice sleeps: digimono renders nothing,
            if started:                              # the (empty) window stays silence
                skipped += 1
                if any(samples):
                    diff += 1
                    first_bad = first_bad or (i, "a silent block that is not", samples[:4])
            continue
    if not started:
        continue
    k = [max(0, min(127, words[s - 17] >> 8)) for s in SLOTS]
    p = [0] * 7
    for i, j in enumerate(KNOB_P[MODEL]):
        if j >= 0:
            p[j] = k[i]
    if MODEL == H.ENS:                               # PW on D: 0 = square .. 127 = thinnest
        p[4] = 64 + (p[4] >> 1)
    pitch = note + ((words[0] - 16384) << 8)
    x = e.render(32, inc=H.LIB.mono_pitch_inc(pitch >> 9), params=p)
    want = [int(round(v * 32768)) << 16 for v in x]
    if list(samples) == want:
        same += 1
    else:
        diff += 1
        if first_bad is None:
            first_bad = (i, samples[:4], want[:4])
check(diff == 0 and same > 100, "%d blocks after the first start equal the engine's own, bit for bit, and %d"
      " blocks of a voice not playing are silence%s" % (same, skipped, "" if not diff else
                                                       "; %d differ, first %s" % (diff, first_bad)))

mm = np.array(master, dtype=np.float64).reshape(-1, 2) / 2 ** 31
seg = mm[len(mm) // 4: len(mm) // 4 + 48000, 0]
if len(seg) == 48000 and np.max(np.abs(seg)) > 0:
    w = np.blackman(len(seg))
    s = np.abs(np.fft.rfft(seg * w)) ** 2
    f = np.fft.rfftfreq(len(seg), 1 / 48000)
    def near(hz, cents=15):
        b = (f > hz * 2 ** (-cents / 1200)) & (f < hz * 2 ** (cents / 1200))
        return 10 * math.log10(s[b].sum() / s.sum() + 1e-30)
    if MODEL == H.NOIS:                        # noise: sound, but no line at the note (the voice itself is
        c4 = near(261.63)                       # checked bit for bit above; the track's filter shapes the rest)
        check(c4 < -20, "the master mix carries noise, not a tone: %.1f dB near C4" % c4)
    elif MODEL == H.ENS:                       # oscillator 1 at the note and 2..4 at their PCH intervals
        _, kk = knobs.get("turned", knobs["defaults"])
        want = [0] + [max(-36, min(36, kk[i] - 63)) for i in range(3)]
        lv = [near(261.63 * 2 ** (x / 12), 25) for x in want]
        check(all(v > -30 for v in lv), "the master mix has C4 and the PCH intervals %s: %s dB"
              % (want[1:], ["%.1f" % v for v in lv]))
    else:
        # The pitch the engine plays is the firmware's (note + TUNE + the kit's LFOs), checked bit for bit
        # above; here: the trigs play C4, and the voice reaches the master.
        notes = sorted(set(b[1] >> 16 for b in blocks if b[0] and b[4] == MACH_FIRST + MODEL))
        rms = float(np.sqrt((seg ** 2).mean()))
        check(notes == [60] and rms > 1e-3, "the trigs play note %s (C4 = 60), and the master carries the voice"
              " (rms %.3f)" % (notes, rms))
else:
    check(False, "the master mix carries sound")
if WAV and len(mm):
    with wave.open(WAV, "wb") as wv:
        wv.setnchannels(2); wv.setsampwidth(2); wv.setframerate(48000)
        wv.writeframes(np.clip(np.round(mm / max(np.max(np.abs(mm)), 1e-9) * 0.9 * 32767), -32768, 32767)
                       .astype("<i2").tobytes())
    print("  wrote", WAV)
print()
if FAIL:
    print("%d FAILED" % len(FAIL))
    sys.exit(1)
print("ALL DIGIEMU CHECKS PASSED (MONO %s)" % a.machine)
