#!/usr/bin/env python3
"""Boot an elekloader build in digiemu (headless) and walk through the features, with hooks counting how
often our code runs and PNG snapshots of the screen at each step.

    python3 tests/digiemu_scenario.py --digiemu <checkout, after --add of the build> --fw <firmware folder name>
        --stock <official .syx> --elekloader <checkout> --mods <core> <dt8poly> <digiutils> [<others>] --png <dir>

Needs digiemu's patched Unicorn (its .venv). Run with that interpreter. The build must have been set up
in digiemu first (python -m emu.portable --add BUILD.syx --yes). Steps: idle 3 s (FAST AUDIO, if present,
switches on after 2 s); three-dots: waveform, YES fullscreen, YES back, three-dots: spectrum, three-dots:
X-Y, three-dots: closes; FUNC+SRC machine list, DOWN to POLY, YES; checks track 1's machine byte.
"""
import argparse, collections, os, struct, sys, time, types, zlib

ap = argparse.ArgumentParser()
ap.add_argument("--digiemu", required=True)
ap.add_argument("--fw", required=True)
ap.add_argument("--stock", required=True)
ap.add_argument("--elekloader", required=True)
ap.add_argument("--mods", nargs="+", required=True)
ap.add_argument("--png", required=True)
a = ap.parse_args()

# ---- addresses of our code in this build, from elekloader's own linker ----
sys.path.insert(0, a.elekloader)
from elekloader import syx as _syx, devices as _dev, elemod as _em, link as _link
_st = _syx.Syx.load(a.stock)
_d, _r = _dev.identify(_st.sha256)
LINKED = _link.link([_em.load_any(p) for p in a.mods], _st.section(_d.main_section))
MAP = LINKED.map

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
from unicorn.m68k_const import UC_M68K_REG_A7
import math
INJECT = float(os.environ.get("INJECT", "0"))
ENC_A = int(os.environ.get("ENC_A", "1"))          # digiemu encoder code of knob A    # Hz: replace the render output with a sine (no samples here)
AMP = 1 << int(os.environ.get("AMPBITS", "22"))
import emu.gui as G

SNAP = [os.path.join(dp, f) for dp, _, fs in os.walk(FW + "/snapshots") for f in fs if f == "gui.snap"][0]
WATCH = ["digiutils_draw", "digiutils_tick", "digiutils_key", "digiutils_tap", "digiutils_tapc", "digiutils_trig", "digiutils_spec",
         "digiutils_scap", "digiutils_tune", "digiutils_tdraw", "digiutils_songfix", "digiutils_adopt", "digiutils_hold", "digiutils_patchk", "digiutils_popkey", "digiutils_made", "digiutils_made2", "dt8poly_lookup", "dt8poly_engine",
         "dt8poly_getter", "dt8poly_rawget", "dt8poly_icon", "dt8poly_rotate", "dt8poly_lock", "dt8poly_cable"]
WATCH = [w for w in WATCH if w in MAP]
counts = collections.Counter()
FA_OUT = 0x80003360 + (0x40071c20 - 0x400716c0)       # FAST AUDIO's SRAM copy of the output writer
os.makedirs(a.png, exist_ok=True)
log = []


def png(path, fb):
    rows = b"".join(b"\0" + bytes(0 if fb[y * 128 + x] else 255 for x in range(128) for _ in (0, 1, 2))
                    for y in range(64))
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    big = []                                            # 4x scale for viewing
    for y in range(64):
        line = b"".join(bytes([0 if fb[y * 128 + x] else 255] * 3) * 4 for x in range(128))
        big += [b"\0" + line] * 4
    data = zlib.compress(b"".join(big))
    open(path, "wb").write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 512, 256, 8, 2, 0, 0, 0))
                           + chunk(b"IDAT", data) + chunk(b"IEND", b""))


# the script: (step number, action)
PLAN = []
t = 600
def at(dt, *act):
    global t
    t += dt
    PLAN.append((t, act))
def tap(code, hold=20, gap=40):
    at(1, "press", code); at(hold, "release", code); at(gap, "wait")
def machine_poly():                          # FUNC+SRC, down to POLY (5th row), YES
    at(1, "press", 1); at(20, "press", 20); at(20, "release", 20); at(5, "release", 1); at(60, "wait")
    for _ in range(4):
        tap(15, 20, 60)
    at(80, "snap", "poly_row_%d" % len([x for x in PLAN if x[1][0] == "snap"]))
    tap(12, 20, 80); tap(13, 20, 60)
PLAN_NAME = os.environ.get("PLAN", "tour")
HOLD_OPENS = "digiutils_popkey" in MAP             # 1.7+: tap "..." = Song popup, hold = the page


def open_page(gap=120):
    if HOLD_OPENS:
        at(1, "press", 5); at(220, "wait"); at(1, "release", 5); at(gap, "wait")
    else:
        tap(5, 20, gap)
if PLAN_NAME == "song":                     # Digi utilities 1.7: Song mode as stock, the page on HOLD "..."
    def hold5():
        at(1, "press", 5); at(220, "wait"); at(1, "release", 5); at(80, "wait")
    at(0, "snap", "s00_main")
    tap(5, 20, 100); at(0, "snap", "s01_tap_popup")            # stock SONG MODE popup
    tap(13, 20, 80); at(0, "snap", "s02_popup_closed")
    hold5(); at(0, "snap", "s03_hold_page")                     # the page (waveform)
    tap(5, 20, 80); tap(5, 20, 80); tap(5, 20, 150); at(0, "snap", "s04_eq")
    at(1, "encoder", ENC_A + 1, -8); at(1, "encoder", ENC_A + 5, 6); at(100, "snap", "s05_eq_mid1")
    tap(12, 20, 60); at(1, "encoder", ENC_A, 5); at(100, "snap", "s06_eq_page2")
    at(1, "press", 3); at(20, "press", 26); at(20, "release", 26); at(5, "release", 3); at(120, "snap", "s07_after_ptn")
    tap(5, 20, 80); at(0, "snap", "s08_closed")
    tap(5, 20, 100); tap(12, 20, 100); at(0, "snap", "s09_song_on")   # popup, YES = switch song mode on
    tap(13, 20, 80); at(0, "snap", "s10_main_song_on")
    hold5(); at(0, "snap", "s11_hold_page_song_on")
    tap(13, 20, 80); at(0, "snap", "s12_closed_song_on")
    tap(5, 20, 100); tap(17, 20, 150); at(0, "snap", "s13_popup_edit")  # popup, RIGHT = EDIT: the stock Song edit
    tap(13, 20, 100); at(0, "snap", "s14_after_no")
    at(1, "press", 5); at(8, "release", 5); at(6, "press", 5); at(8, "release", 5); at(150, "snap", "s15_double_tap")
    tap(13, 20, 100); tap(13, 20, 100); at(0, "snap", "s16_back")
    at(0, "check", None)
    PLAN_DONE = True
elif PLAN_NAME == "eq":                      # Digi utilities 1.8: the master EQ page (FUNC+LFO), one page
    def fl():
        at(1, "press", 1); at(20, "press", 23); at(20, "release", 23); at(5, "release", 1); at(120, "wait")
    def push(k):                              # knob push A..H = codes 40..47; the panel driver ignores that
        at(1, "press", 40 + k); at(20, "release", 40 + k); at(160, "wait")   # knob's turns for ~40 ms after a push
    at(0, "level", "flat_closed")
    fl(); at(0, "snap", "m1_compressor")
    fl(); at(0, "snap", "m2_eq"); at(0, "level", "eq_page_flat")
    def turn(k, n):                           # n notches of knob k (0..7 = A..H), one event a notch
        for _ in range(abs(n)):
            at(4, "encoder", ENC_A + k, 4 if n > 0 else -4)
        at(60, "wait")
    turn(0, 12); at(0, "mlast"); at(90, "level", "b1_lowshelf_+6dB"); at(0, "snap", "m3_low6")
    turn(4, 20); at(90, "level", "b1_higher_f")
    turn(1, -16); turn(5, -12); at(90, "level", "b2_bell_-8dB"); at(0, "snap", "m4_bell")
    push(1); turn(1, 8); at(90, "level", "b2_q_up"); at(0, "snap", "m5_q_mode")
    push(1)                                   # B back to level
    push(7); turn(7, 1); at(90, "level", "b4_type_lp"); at(0, "snap", "m6_type_lp")
    turn(3, -4); at(90, "level", "b4_lp_level_-2dB")
    push(7); turn(7, -40); at(90, "level", "b4_lp_freq_down"); at(0, "snap", "m7_lp_freq")
    push(6); turn(6, -2); at(90, "level", "b3_hp"); at(0, "snap", "m8_hp")
    at(0, "settings")
    at(1, "encoder", 9, -8); at(150, "wait")  # the LEVEL knob still works (track level)
    fl(); at(0, "snap", "m9_internal_mixer")
    fl(); at(0, "snap", "m10_external_mixer")
    fl(); at(0, "snap", "m11_compressor_again"); at(0, "level", "eq_still_on_other_page")
    tap(13, 20, 120); at(0, "snap", "m12_closed")
    open_page(120); at(0, "snap", "u1_waveform")        # the "..." page: waveform -> spectrum -> X-Y -> close
    tap(5, 20, 150); at(0, "snap", "u2_spectrum")
    tap(5, 20, 120); at(0, "snap", "u3_xy")
    tap(5, 20, 120); at(0, "snap", "u4_closed")
    at(0, "check", None)
    PLAN_DONE = True
else:
    PLAN_DONE = False
if not PLAN_DONE:
  at(0, "snap", "0_main")
  open_page(120); at(0, "snap", "1_waveform")
  tap(12, 20, 60); at(0, "snap", "2_fullscreen")
  tap(12, 20, 30); at(0, "snap", "2b_normal")
  tap(5, 20, 250); at(0, "snap", "3_spectrum")
  tap(5, 20, 120); at(0, "snap", "4_xy")
  if "digiutils_eqdraw" in MAP:
      tap(5, 20, 120); at(0, "snap", "4b_eq")                  # Digi utilities 1.6: X-Y -> EQ -> close
  tap(5, 20, 60); at(0, "snap", "5_closed")
  machine_poly()                                # track 1 -> POLY
  at(1, "press", 2); at(10, "press", 25); at(20, "release", 25); at(5, "release", 2); at(60, "wait")   # TRK+2
  machine_poly()                                # track 2 -> POLY
  at(1, "press", 2); at(10, "press", 24); at(20, "release", 24); at(5, "release", 2); at(60, "wait")   # TRK+1
  tap(9, 20, 60)                                # RECORD: grid recording
  for k in (24, 28, 32, 36):                    # trigs on steps 1, 5, 9, 13 of track 1
      tap(k, 20, 40)
  tap(9, 20, 60)                                # RECORD off
  at(0, "mark")
  tap(10, 20, 100)                              # PLAY
  open_page(300); at(0, "snap", "6_playing_waveform")
  tap(5, 20, 300); at(0, "snap", "7_playing_spectrum")
  tap(5, 20, 200); at(0, "snap", "8_playing_xy")
  at(0, "check", None)
  tap(11, 20, 40)                               # STOP
STEPS = t + 2
state = {"n": 0, "ph": 0}

_spin = G.spin
def spin(m, pc, *args, **kw):
    uc = m.uc
    n = state["n"]
    if n == 0:
        for w in WATCH:
            uc.hook_add(UC_HOOK_CODE, (lambda name: lambda u, ad, s, d: counts.__setitem__(name, counts[name] + 1))(w),
                        begin=MAP[w], end=MAP[w])
        if INJECT:                                 # a test tone in place of the (sample-less) render output
            # Into the master mix, before Digi EQ runs on it (the master is 8 bits hotter than the words
            # the outputs take, so the tone goes in at AMP << 8 and comes out measured against AMP).
            _mst = MAP.get("digieq_master")
            def inject(u, ad, s, d):
                buf = 0x8000ea70 if _mst else struct.unpack(">I", u.mem_read(u.reg_read(UC_M68K_REG_A7) + 4, 4))[0]
                sc = 256 if _mst else 1
                out = bytearray()
                for i in range(32):
                    v = int(AMP * sc * math.sin(2 * math.pi * INJECT * state["ph"] / 48000.0))
                    state["ph"] += 1
                    out += struct.pack(">ii", v, v)
                u.mem_write(buf, bytes(out))
            _at = _mst or MAP.get("digiutils_tap", MAP["digiutils_tapc"])
            uc.hook_add(UC_HOOK_CODE, inject, begin=_at, end=_at)
        def measure(u, ad, s_, d):
            buf = struct.unpack(">I", u.mem_read(u.reg_read(UC_M68K_REG_A7) + 4, 4))[0]
            v = struct.unpack(">64i", u.mem_read(buf, 256))
            state["sq"] = state.get("sq", 0.0) * 0.98 + 0.02 * sum(x * x for x in v[0::2]) / 32.0
        uc.hook_add(UC_HOOK_CODE, measure, begin=MAP["digiutils_tapc"], end=MAP["digiutils_tapc"])
        if "digieq_run" in MAP:
            lo = MAP["digieq_run"]
            def cnt(u, ad, s_, d):
                state["eqi"] = state.get("eqi", 0) + 1
            def ent(u, ad, s_, d):
                state["eqc"] = state.get("eqc", 0) + 1
            uc.hook_add(UC_HOOK_CODE, cnt, begin=lo, end=lo + 0x220)
            uc.hook_add(UC_HOOK_CODE, ent, begin=lo, end=lo)
        if "digiutils_enc" in MAP:
            def encid(u, ad, s_, d):
                ev = struct.unpack(">I", u.mem_read(u.reg_read(UC_M68K_REG_A7) + 8, 4))[0]
                state["enc"] = struct.unpack(">ii", u.mem_read(ev + 12, 8))
            uc.hook_add(UC_HOOK_CODE, encid, begin=MAP["digiutils_enc"], end=MAP["digiutils_enc"])
        uc.hook_add(UC_HOOK_CODE, lambda u, ad, s, d: counts.__setitem__("fastaudio_out", counts["fastaudio_out"] + 1),
                    begin=FA_OUT, end=FA_OUT)
        uc.hook_add(UC_HOOK_CODE, lambda u, ad, s, d: counts.__setitem__("stock_out", counts["stock_out"] + 1),
                    begin=0x40071c20, end=0x40071c20)
    for when, act in PLAN:
        if when == n:
            if act[0] in ("press", "release"):
                E.inbox.append((act[0], act[1], 0))
            elif act[0] == "encoder":
                E.inbox.append(("encoder", act[1], act[2]))
            elif act[0] == "settings":
                st_ = [list(uc.mem_read(MAP["digieq:" + n_], 4)) for n_ in ("fi", "gi", "qi", "ty")]
                log.append("EQ settings: freq %s level %s Q %s type %s  knobs switched %s  last %s" % (tuple(st_) + (
                    list(uc.mem_read(MAP["digieq:alt"], 8)), uc.mem_read(MAP["digieq:last"], 1)[0])))
                state["eqset"] = st_
            elif act[0] == "mlast":
                log.append("master EQ page: last knob event (knob, turn) = %s" % (struct.unpack(">2i", uc.mem_read(MAP["digieq_mlast"], 8)),))
            elif act[0] == "encid":
                log.append("encoder code %d -> firmware id, delta %s" % (act[1], state.pop("enc", None)))
            elif act[0] == "level":
                sq = state.get("sq", 0.0)
                got = 10 * math.log10(max(sq, 1e-9) / (AMP * AMP / 2.0))
                exp = ""
                if "digieq:fi" in MAP and INJECT:
                    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
                    import eq_model as EM
                    fi_ = list(uc.mem_read(MAP["digieq:fi"], 4)); gi_ = list(uc.mem_read(MAP["digieq:gi"], 4))
                    qi_ = list(uc.mem_read(MAP["digieq:qi"], 4)); ty_ = list(uc.mem_read(MAP["digieq:ty"], 4))
                    h = 1.0
                    for b in range(4):
                        if EM.active(fi_[b], gi_[b], qi_[b], ty_[b]):
                            g_, k_, m_ = EM.design(fi_[b], gi_[b], qi_[b], ty_[b])
                            h *= abs(EM.svf_response(g_, k_, m_, INJECT))
                    e = 20 * math.log10(max(h, 1e-6))
                    exp = "  expected %6.2f dB  (freq %s level %s Q %s type %s)" % (
                        e, fi_, gi_, qi_, [EM.TYPES[t] for t in ty_])
                    state.setdefault("errs", []).append(abs(got - e))
                if state.get("eqc"):
                    exp += "  [EQ: %d instructions a block]" % (state["eqi"] // state["eqc"])
                    state["eqi"] = state["eqc"] = 0
                log.append("%-24s output level %6.2f dB%s" % (act[1], got, exp))
            elif act[0] == "snap":
                png(os.path.join(a.png, act[1] + ".png"), E.fb)
                log.append("%-16s step %4d  %s" % (act[1], n, dict(sorted(counts.items()))))
            elif act[0] == "mark":
                trig0 = bytes(uc.mem_read(MAP["digiutils_data"] + 16 + 2048, 8))
                state["mark"] = (dict(counts), trig0)
            elif act[0] == "check":
                trig1 = bytes(uc.mem_read(MAP["digiutils_data"] + 16 + 2048, 8))
                c0, trig0 = state.get("mark", ({}, trig1))
                log.append("while playing: voice starts per voice %s; POLY rotation hook ran %d times"
                           % ([(trig1[i] - trig0[i]) & 0xff for i in range(8)],
                              counts["dt8poly_rotate"] - c0.get("dt8poly_rotate", 0)))
                kit = struct.unpack(">I", uc.mem_read(0x800019ac, 4))[0]
                q = struct.unpack(">I", uc.mem_read(0x4199dc44, 4))[0]
                mach = [uc.mem_read(q + 0x20 + tr * 0xa2 + 0x7e, 1)[0] for tr in range(8)] if q else None
                log.append("machine bytes per track (sequencer kit): %s" % mach)
                if "digiutils_adopt" in MAP:
                    log.append("pages adopted: %d; vtable copy at %s" % (counts["digiutils_adopt"],
                               hex(struct.unpack(">I", uc.mem_read(MAP["digiutils_vtprim"], 4))[0])))
                ram = bytes(uc.mem_read(LINKED.layout["ddr"][0], 64))
                load = LINKED.layout["run_load"] - 0x40000400
                log.append("RAM image copied at boot: %s" % (ram == LINKED.image[load:load + 64]))
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
if state.get("errs"):
    print("worst |measured - expected| = %.2f dB over %d settings" % (max(state["errs"]), len(state["errs"])))
