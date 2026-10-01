#!/usr/bin/env python3
"""Drive a build in digiemu like a person: give tracks SRC machines, look at their SRC pages, turn
knobs, play. For checking digichain: run the chained build and a build with one mod as it is, and
compare what they show and play (tests/chain_compare.py does both).

    python tests/digiemu_chain.py --digiemu DIGIEMU --fw FOLDER --tracks 1:5,2:4 --out DIR
        [--turn B:+3,F:+2] [--play 1] [--play2 1,2]

--tracks  track:index in the machine list (FUNC+SRC; 0 ONESHOT .. 3 SLICE, then the mods' machines by
          number), each set in turn and its SRC page shown
--turn    knob turns (notches) on each page after it is shown, each followed by a screenshot (the
          value pop-up); track:knob:notches for one track only
--play    the tracks to trig (steps 1, 5, 9, 13) for the first recording: DIR/play.wav
--play2   the tracks for a second recording, after the first: DIR/play2.wav

DIR gets t<track>_page.png, t<track>_<knob>.png, machines.txt (each track's machine number and knobs A-H) and the
recordings (the codec's output, 16-bit stereo, as the outputs play it).
"""
import argparse, os, struct, sys, types, wave, zlib

ap = argparse.ArgumentParser()
ap.add_argument("--digiemu", required=True)
ap.add_argument("--fw", required=True)
ap.add_argument("--tracks", required=True)
ap.add_argument("--turn", default="")
ap.add_argument("--play", default="")
ap.add_argument("--play2", default="")
ap.add_argument("--blocks", default="", help="tracks whose voice block to record while playing, right after the"
                " render step at 0x40077fba (SOPHIE's and NEIGHBOR's): DIR/blocks.json")
ap.add_argument("--set", default="", help="track:slot:value words written into the tracks' sounds before playing,"
                " as a loaded kit would have them (e.g. 2:21:256: NEIGHBOR's SLOT = 1)")
ap.add_argument("--settle", type=int, default=0, help="steps to wait on each SRC page before its screenshot")
ap.add_argument("--blocks-at", default="0x40077fc0", help="where --blocks reads the voice blocks (default: right"
                " after the render step at 0x40077fba; 0x40078142: before the mixer, every track stage done)")
ap.add_argument("--out", required=True)
a = ap.parse_args()

TRACKS = [tuple(int(x) for x in s.split(":")) for s in a.tracks.split(",")]
TURNS = []                                          # (track or 0 for every track, knob, notches)
for s in filter(None, a.turn.split(",")):
    f = s.split(":")
    TURNS.append((int(f[0]), f[1].upper(), int(f[2])) if len(f) == 3 else (0, f[0].upper(), int(f[1])))
OUT = os.path.abspath(a.out)
os.makedirs(OUT, exist_ok=True)

DE = os.path.abspath(a.digiemu)
FW = os.path.join(DE, "portable", "firmware", a.fw)
sys.path.insert(0, DE)
syxname = [f for f in os.listdir(FW) if f.endswith(".syx")][0]
os.environ.update({"DT2_SYX": os.path.join(FW, syxname), "DT2_SECTIONS": FW + "/sections",
                   "DT2_SNAPSHOTS": FW + "/snapshots", "DT2_PLUSDRIVE": FW + "/plusdrive.img",
                   "DT2_MAIN_IMG": FW + "/sections/section_3_MAIN_OS.bin",
                   "DT2_DEVICES": FW + "/devices" if os.path.isdir(FW + "/devices") else os.path.join(DE, "devices"),
                   "DIGIKIT_PIT3_PROBE": "1"})
os.chdir(FW)
_tk = types.ModuleType("tkinter")
_tk.Frame = type("Frame", (), {}); _tk.Tk = type("Tk", (), {})
sys.modules["tkinter"] = _tk
for _n in ("ttk", "messagebox", "filedialog", "font"):
    sys.modules["tkinter." + _n] = types.ModuleType("tkinter." + _n)
import emu.gui as G
from unicorn import UC_HOOK_CODE
import json
AFTER_INJECT = int(a.blocks_at, 0)                  # 0x40077fc0: the instruction after the site at 0x40077fba
BLOCK_TRACKS = [int(x) for x in filter(None, a.blocks.split(","))]
BLOCKS = {t_: [] for t_ in BLOCK_TRACKS}

SNAP = [os.path.join(dp, f) for dp, _, fs in os.walk(FW + "/snapshots") for f in fs if f == "gui.snap"][0]
FUNC, TRK, PTN, RECORD, PLAY, STOP, YES, NO, DOWN, SRC = 1, 2, 3, 9, 10, 11, 12, 13, 15, 20
TRIG = 24                                           # trig 1; 24..39


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
def combo(a_, b_, gap=80):
    at(1, "press", a_); at(20, "press", b_); at(20, "release", b_); at(5, "release", a_); at(gap, "wait")

combo(PTN, TRIG + 15, 150)                          # pattern 16: empty
for track, index in TRACKS:
    combo(TRK, TRIG + track - 1)                    # the track
    combo(FUNC, SRC)                                # its machine list, the cursor on ONESHOT
    for _ in range(index):
        tap(DOWN, 20, 60)
    tap(YES, 20, 80); tap(NO, 20, 60)
    tap(SRC, 20, 120)                               # its SRC page
    at(a.settle, "snap", "t%d_page" % track)
    for tt, k, n in TURNS:
        if tt and tt != track:
            continue
        for _ in range(abs(n)):
            at(3, "encoder", 1 + "ABCDEFGH".index(k), 4 if n > 0 else -4)
        at(25, "snap", "t%d_%s" % (track, k))
        at(80 + a.settle, "wait")
at(0, "machines")


def record(tracks, name):
    tap(RECORD, 20, 60)
    for track in tracks:
        combo(TRK, TRIG + track - 1, 60)
        for k in (0, 4, 8, 12):
            tap(TRIG + k, 20, 40)
    tap(RECORD, 20, 60)
    at(0, "clear")
    tap(PLAY, 20, 20)
    at(2600, "take", name)
    tap(STOP, 20, 200)


if a.play:
    record([int(x) for x in a.play.split(",")], "play")
if a.play2:
    record([int(x) for x in a.play2.split(",")], "play2")
STEPS = t + 2
st = {"n": 0, "rec": None}


def after_inject(u, ad, sz, d):
    if st["rec"] is None:
        return
    sb = struct.unpack(">I", u.mem_read(0x80001228, 4))[0]
    for tr in BLOCK_TRACKS:
        v = tr - 1
        BLOCKS[tr].append([st["rec"], (sb >> v) & 1,
                           list(struct.unpack(">32i", u.mem_read(0x80001a18 + 128 * v, 128)))])


_spin = G.spin
def spin(m, pc, *args, **kw):
    n = st["n"]
    if n == 0 and BLOCK_TRACKS:
        m.uc.hook_add(UC_HOOK_CODE, after_inject, begin=AFTER_INJECT, end=AFTER_INJECT)
    for when, act in PLAN:
        if when != n:
            continue
        if act[0] in ("press", "release"):
            E.inbox.append((act[0], act[1], 0))
        elif act[0] == "encoder":
            E.inbox.append(("encoder", act[1], act[2]))
        elif act[0] == "snap":
            png(os.path.join(OUT, act[1] + ".png"), E.fb)
        elif act[0] == "machines":
            kit = struct.unpack(">I", m.uc.mem_read(0x4199dc44, 4))[0]
            for w in filter(None, a.set.split(",")):
                tr, sl, val = (int(x, 0) for x in w.split(":"))
                m.uc.mem_write(kit + 0x20 + 0xa2 * (tr - 1) + 0x14 + 2 * sl, struct.pack(">H", val))
            with open(os.path.join(OUT, "machines.txt"), "w") as fh:
                for track, _ in TRACKS:
                    snd = kit + 0x20 + 0xa2 * (track - 1)
                    knobs = [struct.unpack(">H", m.uc.mem_read(snd + 0x14 + 2 * k, 2))[0] >> 8 for k in range(17, 25)]
                    fh.write("%d %d %s\n" % (track, m.uc.mem_read(snd + 0x7e, 1)[0], " ".join(map(str, knobs))))
        elif act[0] == "clear":
            E.audio_clear()
            st["rec"] = 1 if st["rec"] is None else st["rec"] + 1
        elif act[0] == "take":
            pcm = E.audio_take()
            with wave.open(os.path.join(OUT, act[1] + ".wav"), "wb") as w:
                w.setnchannels(2); w.setsampwidth(2); w.setframerate(48000); w.writeframes(pcm)
            if BLOCK_TRACKS:
                with open(os.path.join(OUT, "blocks.json"), "w") as fh:
                    json.dump(BLOCKS, fh)
    st["n"] += 1
    r = _spin(m, pc, *args, **kw)
    if st["n"] >= STEPS:
        E.stop_flag.set()
    return r
G.spin = spin

E = G.Emulator(SNAP, syx=os.environ["DT2_SYX"], realtime=False, audio=True)
E.run()
print("done: %s" % OUT)
