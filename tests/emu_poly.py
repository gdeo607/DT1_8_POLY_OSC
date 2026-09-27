#!/usr/bin/env python3
"""Digi Poly's own code (mods/digipoly/poly.c, poly_glue.s), run in unicorn without booting the firmware.

    <python with digiemu's patched unicorn> tests/emu_poly.py --stock <official .syx> --elekloader <checkout> \
        --mods <core.elemod> <digipoly.elemod> [<others>]

Links the mods as elekloader does and calls our functions directly on a made-up kit, pattern and engine
state, with the firmware routines they call stubbed out (an "rts", plus a bump allocator for the message
pool) and every call recorded. Seconds, not minutes: the emulator run (tests/digiemu_poly.py) then only has
to show the same things happening inside the real firmware.

Checks: which tracks lend their voice (per kit, so per pattern), the SETTINGS row's checkbox and its
toggle, chord trigs cloned onto stolen voices, locked / muted / busy tracks never stolen, live notes,
the chord preview of the unit's own keys, knob values and levels mirrored onto stolen voices.
"""
import argparse, os, struct, subprocess, sys, tempfile

ap = argparse.ArgumentParser()
ap.add_argument("--stock", required=True)
ap.add_argument("--elekloader", required=True)
ap.add_argument("--mods", nargs="+", required=True)
a = ap.parse_args()
sys.path.insert(0, a.elekloader)
from elekloader import syx, devices, elemod, link
from unicorn import Uc, UC_ARCH_M68K, UC_MODE_BIG_ENDIAN, UC_HOOK_CODE
from unicorn.m68k_const import *

st = syx.Syx.load(a.stock)
dev, rel = devices.identify(st.sha256)
L = link.link([elemod.load_any(p) for p in a.mods], st.section(dev.main_section))
MAP, img = L.map, L.image
ddr0, run_end = L.layout["ddr"]
bss0, bss1 = L.layout["bss"]
run = img[L.layout["run_load"] - 0x40000400: L.layout["run_load"] - 0x40000400 + run_end - ddr0]

uc = Uc(UC_ARCH_M68K, UC_MODE_BIG_ENDIAN)
uc.ctl_set_cpu_model(UC_CPU_M68K_CFV4E)
for base, size in ((0x40000000, 0x01000000), (0x41900000, 0x00100000), (0x421f0000, 0x00010000),
                   (0x43900000, 0x00100000), (0x47b00000, 0x00100000), (0x80000000, 0x00100000)):
    uc.mem_map(base, size)
uc.mem_write(0x40000400, img[:0x3fc000])
uc.mem_write(ddr0, run)
uc.mem_write(bss0, bytes(bss1 - bss0))

STACK, SENT = 0x47bf0000, 0x47b00100
FP = STACK + 0x1000                                          # the render's frame (its mute mask at -80)
KIT, KIT2, POOL, ARGS = 0x40900000, 0x40901000, 0x40902000, 0x40903000
PAT = 0x409bac18
UI_KIT, ENG_KIT, MUTES, OWNER = 0x4199dc44, 0x800019ac, 0x4199e47c, 0x4399db54
LOADED, PARAMS, LEVELS = 0x800014f0 + 0x131 * 4, 0x800014f2, 0x80002760
uc.mem_write(SENT, b"\x4e\x71\x4e\x71")

# ---- stubs for the firmware routines our code calls ----
RTS = b"\x4e\x75"
for addr in (0x400c9812, 0x400c19a6, 0x400c178a, 0x400c257c, 0x400c2960,   # invalidate, draw
             0x400d53dc, 0x400d575e, 0x40076b3c, 0x400ee0a0, 0x400ee036):  # live notes, message pool
    uc.mem_write(addr, RTS)
uc.mem_write(0x421f7a3c, struct.pack(">I", 0x40950000))                    # the checkbox bitmaps


def asm(src):
    d = tempfile.mkdtemp()
    open(d + "/s.s", "w").write(src)
    subprocess.run(["m68k-linux-gnu-as", "-mcpu=54455", "-o", d + "/s.o", d + "/s.s"], check=True)
    subprocess.run(["m68k-linux-gnu-objcopy", "-O", "binary", d + "/s.o", d + "/s.bin"], check=True)
    return open(d + "/s.bin", "rb").read()


# message pool: hand out 0x4c bytes at a time from POOL (0x400ee036 -> d0), and a 0x4c-byte copy
uc.mem_write(0x400ee036, asm("""
    move.l 0x%x, %%d0
    move.l %%d0, %%a0
    add.l #0x4c, %%a0
    move.l %%a0, 0x%x
    rts
""" % (POOL, POOL)))
uc.mem_write(0x400ee0a0, asm("""
    move.l 4(%sp), %a0
    move.l 8(%sp), %a1
    moveq #19, %d0
1:  move.l (%a1)+, (%a0)+
    subq.l #1, %d0
    bne.b 1b
    rts
"""))

calls = []


def record(name, nargs, deref=0):
    def h(u, addr, size, d):
        sp = u.reg_read(UC_M68K_REG_A7)
        args = struct.unpack(">%di" % nargs, u.mem_read(sp + 4, 4 * nargs))
        if deref:                                           # the argument is a struct on the caller's stack
            args = struct.unpack(">%di" % deref, u.mem_read(args[0] & 0xffffffff, 4 * deref))
        calls.append((name,) + args)
    return h


def rec_text(u, addr, size, d):
    sp = u.reg_read(UC_M68K_REG_A7)
    a = struct.unpack(">7I", u.mem_read(sp + 4, 28))
    b = bytes(u.mem_read(a[5], 16))
    fmt = b[:b.find(b"\0")].decode("latin1")
    calls.append(("text", a[2], a[3], fmt, a[6] - (1 << 32) if a[6] & 0x80000000 else a[6]))


uc.hook_add(UC_HOOK_CODE, rec_text, begin=0x400c257c, end=0x400c257c)

for name, addr, n, dr in (("live_on", 0x400d53dc, 3, 0), ("live_off", 0x400d575e, 2, 0),
                          ("live_build", 0x40076b3c, 1, 4), ("blit", 0x400c2960, 4, 0),
                          ("fill", 0x400c19a6, 6, 0), ("frame", 0x400c178a, 6, 0)):
    uc.hook_add(UC_HOOK_CODE, record(name, n, dr), begin=addr, end=addr)


def call(fn, *args):
    sp = STACK - 4 * (len(args) + 1)
    uc.mem_write(sp, struct.pack(">%dI" % (len(args) + 1), SENT, *[x & 0xffffffff for x in args]))
    uc.reg_write(UC_M68K_REG_A7, sp)
    uc.reg_write(UC_M68K_REG_A6, FP)                        # the router reads the render frame at fp-80
    uc.emu_start(MAP[fn], SENT, count=5_000_000)
    return uc.reg_read(UC_M68K_REG_D0)


def w32(addr, *vals):
    uc.mem_write(addr, struct.pack(">%dI" % len(vals), *[v & 0xffffffff for v in vals]))


def r32(addr, n=1):
    v = struct.unpack(">%dI" % n, uc.mem_read(addr, 4 * n))
    return [x - (1 << 32) if x & 0x80000000 else x for x in v]


def sound(kit, t):
    return kit + 0x20 + t * 0xa2


def xb(n):                                       # the persistent map (src/kitstore.h)
    return 0x20 + n // 6 * 0xa2 + (0, 1, 2, 3, 0x14, 0x15)[n % 6]


def spare_slots_clean(kit):                      # slots 46..52 are not saved: only the mods' markers may be there
    return all(struct.unpack(">H", uc.mem_read(kit + 0x20 + t * 0xa2 + 0x14 + 2 * s, 2))[0] in (0, 0x4b53)
               for t in range(8) for s in range(46, 53))


def sound_load(kit, t):                          # what the firmware's loader does to one sound
    uc.mem_write(kit + 0x20 + t * 0xa2, bytes(4))
    uc.mem_write(kit + 0x20 + t * 0xa2 + 0x14, bytes(0x6a))

def lockw(kit, t, v=None):                       # bit 7 of byte 6t + 3: track t kept out of the pool
    b = uc.mem_read(kit + xb(6 * t + 3), 1)[0]
    if v is not None:
        b = (b | 0x80) if v else (b & 0x7f)
        uc.mem_write(kit + xb(6 * t + 3), bytes([b]))
    return b >> 7


def setup_kit(kit, machines=(4, 0, 0, 0, 0, 0, 0, 0), level=100):
    uc.mem_write(kit, bytes(0x600))
    for t in range(8):
        uc.mem_write(sound(kit, t) + 0x7e, bytes([machines[t]]))
        uc.mem_write(kit + 0x10 + 2 * t, bytes([level]))   # the level word's high byte
    w32(UI_KIT, kit)
    w32(ENG_KIT, kit)


def msg(voice, note, mid=1, chord=None, flags=0x81, on=1, sound_ptr=0, nxt=0):
    """a note message of the engine's shape at the pool's next free block"""
    m = r32(POOL)[0]
    w32(POOL, m + 0x4c)
    uc.mem_write(m, bytes(0x4c))
    w32(m + 4, on)
    w32(m + 8, voice)
    w32(m + 12, mid)
    w32(m + 24, note)
    w32(m + 36, flags)
    w32(m + 40, sound_ptr)
    w32(m + 72, nxt)
    if chord:
        uc.mem_write(m + 28, bytes([0xc4] + list(chord)))
    return m


def reset(free_pool=True):
    del calls[:]
    if free_pool:
        w32(POOL, POOL + 0x100)
    uc.mem_write(0x4399db54, bytes(32))                      # no voice owned
    uc.mem_write(MUTES, b"\0\0")
    uc.mem_write(FP - 80, bytes(4))                          # the render's own mute mask
    uc.mem_write(LOADED, bytes(32))
    setup_kit(KIT)


def chain(m):                                                # the message list from m, by +72
    out = []
    while m:
        out.append(m)
        m = r32(m + 72)[0]
    return out


fails = []


def check(cond, what):
    if not cond:
        fails.append(what)
    return cond


# ---- 1. which tracks lend their voice: per kit, so per pattern ----
uc.mem_write(PAT, bytes(0x38f * 16))
setup_kit(KIT)
setup_kit(KIT2)
w32(UI_KIT, KIT)
call("digipoly_select", ARGS)                                # cursor is on track 1
check(lockw(KIT, 0) != 0, "YES did not take track 1 out of the pool")
check(lockw(KIT2, 0) == 0, "the other pattern's kit changed too")
call("digipoly_select", ARGS)
check(lockw(KIT, 0) == 0, "YES did not put track 1 back in the pool")
uc.mem_write(ARGS, struct.pack(">I", 0x40910000))            # the row's payload: a menu object
w32(0x40910000, 0)
for _ in range(3):
    call("digipoly_change", ARGS, 0, 4)
call("digipoly_select", ARGS)
check(lockw(KIT, 3) != 0, "RIGHT x3 then YES did not take track 4 out of the pool")
check(spare_slots_clean(KIT), "the pool was written into a sound slot the +Drive does not keep")
call("digipoly_rectick", 0)                                  # the tick marks the kit
lockw(KIT, 5, 1)
call("digipoly_rectick", 0)
sound_load(KIT, 5)                                           # a sound loaded onto track 6
check(lockw(KIT, 5) == 0, "the test's sound load did not clear the flag")
call("digipoly_rectick", 0)
check(lockw(KIT, 5) == 1 and lockw(KIT, 3) == 1, "a sound load onto track 6 lost its pool flag")
for t in range(8):                                           # the whole kit loaded: its bytes win
    sound_load(KIT, t)
lockw(KIT, 2, 1)
call("digipoly_rectick", 0)
check([lockw(KIT, t) for t in range(8)] == [0, 0, 1, 0, 0, 0, 0, 0], "a kit load did not bring its own pool")
lockw(KIT, 2, 0); lockw(KIT, 3, 1)                            # back to what the checks below expect
call("digipoly_rectick", 0)
check(spare_slots_clean(KIT), "something other than the marker in the RAM-only slots")
del calls[:]
call("digipoly_draw", 0, 0, 0x40920000, 10, 20)              # the row's own drawing
box = [c for c in calls if c[0] == "blit"]
check(len(box) == 1 and box[0][2] == 0x40950000,
      "the checkbox is not the empty one for a track out of the pool (%s)" % (box,))
# FILLRECT(bmp, x0, y0, x1, y1, colour) -> c[1]..c[6]; a cell of track t is at x = 10 + 34 + 5t - 1
inv = [c for c in calls if c[0] == "fill" and c[6] == -1 and c[3] == 19]
shown = sorted(set((c[2] + 1 - 10 - 34) // 5 for c in inv))
check(shown == [0, 1, 2, 4, 5, 6, 7], "the tracks shown as lending their voice are %s" % (shown,))
for _ in range(3):
    call("digipoly_change", ARGS, 0, -4)
del calls[:]
call("digipoly_draw", 0, 0, 0x40920000, 10, 20)
box = [c for c in calls if c[0] == "blit"]
check(len(box) == 1 and box[0][2] == 0x40950000 + 0x1c,
      "the checkbox is not the ticked one for a track in the pool (%s)" % (box,))
print("SETTINGS > POLY: per-kit flags, checkbox and the %d tracks shown in the pool" % len(shown))

# ---- the POLY track's TRIG page keeps its level in view ----
setup_kit(KIT, level=64)
view = 0x40930000
w32(view + 124, 0x40931000, 0x40931004, 0x40931004)
w32(0x40931000, 15)                                          # the page kind a POLY track borrows
w32(view + 144, 0)
w32(0x4197b6b4, 0)                                           # the active track
del calls[:]
# the stock audio TRIG page's fader, measured off the screen: frame x 4..10 y 7..23, the filled part
# x 6..8 from y 9, 13 rows at 127, and the scale marks at x 0..1 and 13..14 every four rows
TICKS = [m for y in (7, 11, 15, 19, 23) for m in ((0, y, 1, y, 1), (13, y, 14, y, 1))]


def fader():
    del calls[:]
    call("digipoly_levdraw", view, 0x40920000)
    fr = [c[2:] for c in calls if c[0] == "frame"]
    fills = [c[2:] for c in calls if c[0] == "fill"]
    return fr, fills


setup_kit(KIT, level=100)
fr, fills = fader()
check(fr == [(4, 7, 10, 23, 1)], "the level fader's frame is not the stock one (%s)" % (fr,))
check(fills[0] == (0, 0, 15, 24, 0), "the fader does not clear its own cell only (%s)" % (fills[0],))
check(fills[1] == (6, 9, 8, 18, 1), "level 100 does not fill 10 rows (%s)" % (fills[1],))
check([f for f in fills[2:]] == TICKS, "the fader's scale marks are wrong (%s)" % (fills[2:],))
setup_kit(KIT, level=127)
fr, fills = fader()
check(fills[1] == (6, 9, 8, 21, 1), "a full level does not fill 13 rows (%s)" % (fills[1],))
setup_kit(KIT, level=0)
fr, fills = fader()
check(len(fills) == 1 + len(TICKS), "level 0 still draws a filled part (%s)" % (fills,))
setup_kit(KIT, machines=(0, 4, 0, 0, 0, 0, 0, 0), level=0)   # a POLY track 2: its own level word
uc.mem_write(KIT + 0x12, bytes([127])); lockw(KIT, 1, 1); lockw(KIT, 2, 1)
w32(0x4197b6b4, 1)
fr, fills = fader()
w32(0x4197b6b4, 0)
check(fills[1:2] == [(6, 9, 8, 21, 1)], "track 2's fader does not read track 2's level word (%s)" % (fills[:2],))
setup_kit(KIT, level=100)
del calls[:]
call("digipoly_levdraw", view, 0x40920000)                   # the level changed: the value is shown
txt = [c for c in calls if c[0] == "text"]
check(bool(txt) and txt[-1][4] == 100, "the fader does not show the value after a change (%s)" % (txt,))
for _ in range(30):
    del calls[:]
    call("digipoly_levdraw", view, 0x40920000)
txt = [c for c in calls if c[0] == "text"]
check(bool(txt) and txt[-1][3] == "LEV", "the fader does not go back to LEV (%s)" % (txt,))
w32(0x40931000, 1)                                           # an ordinary track's page: nothing of ours
del calls[:]
call("digipoly_levdraw", view, 0x40920000)
check(not calls, "the level fader was drawn over an ordinary track's TRIG page")
print("TRIG page: the level fader matches the stock one (frame %s, 10 rows at 100, 13 at 127)" % (fr,))

# ---- the LEVEL knob on the POLY TRIG page ----
w32(0x40931000, 15)
ENC = 0x40932000
kinds_seen = []
uc.mem_write(0x40032a78, RTS)


def stock_enc(u, addr, size, d):
    sp = u.reg_read(UC_M68K_REG_A7)
    v = struct.unpack(">I", u.mem_read(sp + 4, 4))[0]
    kv = struct.unpack(">I", u.mem_read(v + 124, 4))[0]
    kinds_seen.append(struct.unpack(">i", u.mem_read(kv, 4))[0])


uc.hook_add(UC_HOOK_CODE, stock_enc, begin=0x40032a78, end=0x40032a78)
for knob, want in ((9, 1), (1, 15)):
    del kinds_seen[:]
    w32(ENC + 12, knob)
    w32(ENC + 16, 16)
    call("digipoly_trigenc", view, ENC)
    check(kinds_seen == [want], "knob %d reached the stock handler with page kind %s, wanted %d"
          % (knob, kinds_seen, want))
    check(r32(0x40931000)[0] == 15, "the page kind was left at %d" % r32(0x40931000)[0])
setup_kit(KIT2, machines=(0,) * 8)                           # an ordinary track: straight through
w32(UI_KIT, KIT2)
del kinds_seen[:]
w32(ENC + 12, 9)
call("digipoly_trigenc", view, ENC)
check(kinds_seen == [15], "an ordinary track's LEVEL knob was meddled with (%s)" % (kinds_seen,))
w32(UI_KIT, KIT)
print("TRIG page: the LEVEL knob reaches the audio page's knob map, other knobs are left alone")

# ---- recording a chord onto a POLY track ----
RECPAT, STEPNOW = 0x40940000, 0x4020c29c


def notes(step):
    return [uc.mem_read(RECPAT + 0x280 + 0x40 * i + step, 1)[0] for i in range(4)]


def rec(track, note, step=None):
    if step is not None:
        w32(STEPNOW, step)
    call("digipoly_recnote", RECPAT, track, note)


setup_kit(KIT)
uc.mem_write(RECPAT, b"\xff" * 0x400)
w32(STEPNOW, 5)
call("digipoly_rectick", 0)
for n in (67, 60, 64, 71):                                   # a chord, arriving in any order
    rec(0, n)
check(notes(5) == [60, 0x40 + 4, 0x40 + 7, 0x40 + 11],
      "a four-note chord was not recorded as NOT1..NOT4 (%s)" % (notes(5),))
rec(0, 74)
check(notes(5) == [60, 0x40 + 4, 0x40 + 7, 0x40 + 11], "a fifth note changed the chord (%s)" % (notes(5),))
rec(0, 60)
check(notes(5) == [60, 0x40 + 4, 0x40 + 7, 0x40 + 11], "a repeated note changed the chord (%s)" % (notes(5),))
for _ in range(8):                                           # a chord of three, then a frame or two
    call("digipoly_rectick", 0)
uc.mem_write(RECPAT, b"\xff" * 0x400)
for n in (50, 57, 53):
    rec(0, n)
for _ in range(2):                                           # the record step is -1 between notes, so
    call("digipoly_rectick", 0)                              # frames must not break a chord up
uc.mem_write(RECPAT, b"\xff" * 0x400)
rec(0, 62)
check(notes(5) == [50, 0x40 + 3, 0x40 + 7, 0x40 + 12],
      "the chord was not held across a frame (%s)" % (notes(5),))
for _ in range(8):                                           # long enough, and the next note is its own
    call("digipoly_rectick", 0)
uc.mem_write(RECPAT, b"\xff" * 0x400)
rec(0, 72)
check(notes(5) == [72, 0x40, 0x40, 0x40], "a later note did not start a new chord (%s)" % (notes(5),))
rec(0, 48, step=6)                                           # the next step starts afresh
check(notes(6) == [48, 0x40, 0x40, 0x40], "a new step kept the old chord (%s)" % (notes(6),))
w32(STEPNOW, 7)
for _ in range(8):
    call("digipoly_rectick", 0)                              # long enough since the last note
rec(0, 55)
check(notes(7) == [55, 0x40, 0x40, 0x40], "the chord did not restart after the step moved (%s)" % (notes(7),))
uc.mem_write(RECPAT, b"\xff" * 0x400)
rec(1, 60, step=8)                                           # track 2 is not POLY here
check(notes(8) == [255, 255, 255, 255], "a note was recorded on an ordinary track (%s)" % (notes(8),))
rec(0, 60, step=-1)                                          # not recording
check(notes(0) == [255, 255, 255, 255], "a note was recorded while the sequencer was not (%s)" % (notes(0),))
print("recording: a chord of up to four notes goes into the step's NOT1..NOT4")

# ---- 2. chord trigs: clones on stolen voices ----
reset()
m = msg(0, 60, chord=[0x44, 0x47, 0x4b], sound_ptr=sound(KIT, 0))
call("digipoly_route_c", m, 0, FP)
got = [(r32(x + 8)[0], r32(x + 24)[0], r32(x + 40)[0]) for x in chain(m)]
check(sorted(g[1] for g in got) == [60, 64, 67, 71], "chord notes %s" % (got,))
check(len(set(g[0] for g in got)) == 4 and got[0][0] == 0, "chord voices %s" % (got,))
check(all(g[2] == sound(KIT, 0) for g in got), "a chord note does not play the POLY track's sound")
print("chord trig: %s" % (got,))

# ---- 3. tracks out of the pool, muted tracks and busy voices are never stolen ----
reset()
lockw(KIT, 1, 1); lockw(KIT, 2, 1)                           # tracks 2 and 3 out of the pool
uc.mem_write(MUTES, struct.pack(">H", 1 << 3))               # track 4 muted
w32(OWNER + 4 * 4, 2)                                        # voice 5 holds a live note
m = msg(0, 60, chord=[0x44, 0x47, 0x4b], sound_ptr=sound(KIT, 0))
w32(m + 72, msg(6, 40))                                      # track 7 trigs in the same block
call("digipoly_route_c", m, 0, FP)
voices = [r32(x + 8)[0] for x in chain(m) if r32(x + 12)[0] == 1 and r32(x + 40)[0] == sound(KIT, 0)]
check(sorted(voices) == [0, 5, 7], "stole a voice it should not have: %s" % (voices,))
print("locked / muted / busy voices kept: chord played on %s" % (voices,))

# ---- 4. live notes: a voice each, released by the note-off ----
reset()
held = []
for note in (60, 64, 67):
    m = msg(0, note, mid=2, flags=0x81, sound_ptr=0)
    call("digipoly_route_c", m, 0, FP)
    v = r32(m + 8)[0]
    held.append(v)
    w32(OWNER + 4 * v, 2)
check(len(set(held)) == 3 and 0 in held, "live chord voices %s" % (held,))
vst = list(uc.mem_read(MAP["dt8poly_vstate"], 8))
check(sorted(x for x in vst if x != 0xff) == [60, 64, 67], "held notes %s" % (vst,))
for note, v in zip((60, 64, 67), held):
    m = msg(0, note, mid=2, on=2, flags=0)
    call("digipoly_route_c", m, 0, FP)
    check(r32(m + 8)[0] == v, "the note-off of %d went to voice %d, not %d" % (note, r32(m + 8)[0], v))
print("live notes: voices %s, note-offs routed back" % (held,))

# ---- 5. the unit's own keys preview the chord ----
reset()
uc.mem_write(PAT + 0x385, bytes([0x44, 0x47, 0x40]))         # the track's NOT2, NOT3; NOT4 off
call("digipoly_prevon", 0, 60, 100, 0x40, 0, -1, -1)
stock = [c for c in calls if c[0] == "live_on"]
extra = [c[1:] for c in calls if c[0] == "live_build"]
check(len(stock) == 1 and stock[0][1:] == (0, 60, 100), "the key's own note did not go to the firmware")
check([e[1] for e in extra] == [64, 67], "the chord preview played %s" % ([e[1] for e in extra],))
check(all(e[0] == 0 and e[3] == 1 for e in extra), "a preview note is not a note-on of that track")
del calls[:]
call("digipoly_prevoff", 0, 60, 0x40)
offs = [c[1:] for c in calls if c[0] == "live_build"]
check([o[1] for o in offs] == [64, 67] and all(o[3] == 2 for o in offs),
      "the chord preview's notes were not released (%s)" % (offs,))
del calls[:]
setup_kit(KIT, machines=(0,) * 8)                            # not a POLY track: one note, as stock
call("digipoly_prevon", 0, 60, 100, 0x40, 0, -1, -1)
check(not [c for c in calls if c[0] == "live_build"], "a plain track's key played a chord")
print("chord preview: the key's note through the firmware, the rest straight to the engine")

# ---- 6. knob values and levels follow the stolen voices ----
reset()
w32(LOADED + 4 * 3, sound(KIT, 0))                           # voice 4 plays the POLY track's sound
w32(LOADED + 4 * 5, sound(KIT, 5))                           # voice 6 plays its own
call("digipoly_setparam", 0x1234, 0, 0x19)                   # a knob of track 1
def pw(v, slot):
    return struct.unpack(">h", uc.mem_read(PARAMS + 2 * (8 + 53 * v + slot), 2))[0]
check(pw(0, 0x19) == 0x1234 and pw(3, 0x19) == 0x1234, "the knob did not reach the stolen voice")
check(pw(5, 0x19) == 0, "the knob reached a voice that plays its own sound")
uc.mem_write(LEVELS, struct.pack(">8h", 100, 200, 300, 400, 500, 600, 700, 800))
call("digipoly_levels", LEVELS)
lv = struct.unpack(">8h", uc.mem_read(LEVELS, 16))
check(lv[3] == 100 and lv[5] == 600, "the stolen voice does not play at the POLY track's level (%s)" % (lv,))
print("stolen voices: knob %s and level %s of the POLY track" % (hex(pw(3, 0x19)), lv[3]))

print("PASS" if not fails else "FAIL:\n  " + "\n  ".join(fails))
sys.exit(1 if fails else 0)
