#!/usr/bin/env python3
"""Digi Matrix's own code (mods/digimatrix/matrix.c, matrix_glue.s), run in unicorn without booting.

    <python with digiemu's patched unicorn> tests/emu_matrix.py --stock <official .syx> \
        --elekloader <checkout> --mods <core.elemod> <digimatrix.elemod> [<others>]

Links the mods as elekloader does and calls our two engine passes and our UI handlers directly, on a
made-up kit and a made-up set of smoothed parameter words, with the firmware's drawing routines stubbed
out and recorded. Seconds, not minutes.

Checks: the routing and depth words in the kit (so per pattern), what the matrix adds to a destination
track's parameter word and its clamps, an LFO taken off its own track and put back, two rows sharing one
LFO, rows that are off or at zero depth doing nothing, and the page's keys, knobs and drawing.
"""
import argparse, struct, sys

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
KIT, KIT2, BMP, MENU = 0x40900000, 0x40901000, 0x40902000, 0x40903000
UI_KIT, ENG_KIT = 0x4199dc44, 0x800019ac
WORDS = 0x80002760                      # the smoothed parameter words: slot s of voice v at +18+106v+2s
LFO = 0x421f3e14                        # the LFO stage's values: LFO1 at +80v, LFO2 at +80v+0x28
uc.mem_write(SENT, b"\x4e\x71\x4e\x71")

RTS = b"\x4e\x75"
for addr in (0x400c9812, 0x400c19a6, 0x400c257c):        # invalidate, fillRect, text
    uc.mem_write(addr, RTS)

calls = []


def rec_fill(u, addr, size, d):
    sp = u.reg_read(UC_M68K_REG_A7)
    calls.append(("fill",) + struct.unpack(">6i", u.mem_read(sp + 4, 24)))


def rec_text(u, addr, size, d):
    sp = u.reg_read(UC_M68K_REG_A7)
    args = struct.unpack(">6I", u.mem_read(sp + 4, 24))
    extra = struct.unpack(">2i", u.mem_read(sp + 28, 8))
    b = bytes(u.mem_read(args[5], 32))
    fmt = b[:b.find(b"\0")].decode("latin1")
    calls.append(("text", args[2], args[3], fmt) + extra)


uc.hook_add(UC_HOOK_CODE, rec_fill, begin=0x400c19a6, end=0x400c19a6)
uc.hook_add(UC_HOOK_CODE, rec_text, begin=0x400c257c, end=0x400c257c)


def call(fn, *args):
    sp = STACK - 4 * (len(args) + 1)
    uc.mem_write(sp, struct.pack(">%dI" % (len(args) + 1), SENT, *[x & 0xffffffff for x in args]))
    uc.reg_write(UC_M68K_REG_A7, sp)
    uc.reg_write(UC_M68K_REG_A6, STACK)
    uc.emu_start(MAP[fn], SENT, count=5_000_000)
    return uc.reg_read(UC_M68K_REG_D0)


def w32(addr, *vals):
    uc.mem_write(addr, struct.pack(">%dI" % len(vals), *[v & 0xffffffff for v in vals]))


def r32(addr):
    v = struct.unpack(">I", uc.mem_read(addr, 4))[0]
    return v - (1 << 32) if v & 0x80000000 else v


def w16(addr, v):
    uc.mem_write(addr, struct.pack(">H", v & 0xffff))


def r16(addr, signed=False):
    v = struct.unpack(">H", uc.mem_read(addr, 2))[0]
    return v - 0x10000 if signed and v & 0x8000 else v


# ---- the model of what our code should do ----
def word(v, s):                          # the smoothed word of voice v, slot s
    return WORDS + 18 + 106 * v + 2 * s


def lfoaddr(v, n):
    return LFO + 80 * v + (0x28 if n else 0)


def route(strk=0, slfo=0, dtrk=0, on=0, dest=-1, own=1):
    return ((strk & 7) | ((slfo & 1) << 3) | ((dtrk & 7) << 4) | (0x80 if on else 0)
            | (((dest + 1) & 0x7f) << 8) | (0x8000 if own else 0))


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

def setrow(kit, i, r, depth=None):               # bytes 6i..6i+2: routing high, routing low, depth + 128
    uc.mem_write(kit + xb(6 * i), bytes([r >> 8]))
    uc.mem_write(kit + xb(6 * i + 1), bytes([r & 0xff]))
    if depth is not None:
        uc.mem_write(kit + xb(6 * i + 2), bytes([depth + 128]))


def getrow(kit, i):
    rd = lambda n: uc.mem_read(kit + xb(n), 1)[0]
    return (rd(6 * i) << 8) | rd(6 * i + 1), rd(6 * i + 2)


def expect(val, depth):
    x = ((val if val < (1 << 31) else val - (1 << 32)) >> 15) * (depth * 508) >> 16
    return x


fails = []


def check(name, got, want):
    if got != want:
        fails.append("%s: got %r, want %r" % (name, got, want))
        print("  FAIL %-46s got %r want %r" % (name, got, want))
    else:
        print("  ok   %s" % name)


def blank():
    uc.mem_write(KIT, bytes(0x600))
    uc.mem_write(KIT2, bytes(0x600))
    uc.mem_write(WORDS, bytes(0x400))
    uc.mem_write(LFO, bytes(0x300))
    w32(UI_KIT, KIT)
    w32(ENG_KIT, KIT)
    del calls[:]


# ================= the engine passes =================
print("\n-- a routing slot adds its LFO to another track's parameter --")
blank()
setrow(KIT, 0, route(strk=1, slfo=0, dtrk=3, on=1, dest=26, own=1), depth=32)   # T2 LFO1 -> T4 FLT.FREQ
w16(word(3, 26), 16000)
w32(lfoaddr(1, 0), 0x40000000)                                                  # half scale
call("digimatrix_pre", WORDS)
call("digimatrix_post", WORDS)
check("destination word moved by value * depth", r16(word(3, 26)),
      16000 + expect(0x40000000, 32))
check("the source LFO's own DEST word is untouched", r16(word(1, 4)), 0)
check("no other voice's word moved", [r16(word(v, 26)) for v in (0, 1, 2, 4)], [0, 0, 0, 0])

print("\n-- a negative depth, and both clamps --")
blank()
setrow(KIT, 0, route(strk=0, slfo=1, dtrk=0, on=1, dest=45, own=1), depth=-64)   # T1 LFO2 -> T1 AMP.VOL
w16(word(0, 45), 100)
w32(lfoaddr(0, 1), 0x7fffffff)
call("digimatrix_pre", WORDS)
call("digimatrix_post", WORDS)
check("clamped at 0", r16(word(0, 45)), 0)
setrow(KIT, 0, route(strk=0, slfo=1, dtrk=0, on=1, dest=45, own=1), depth=64)
w16(word(0, 45), 30000)
call("digimatrix_pre", WORDS)
call("digimatrix_post", WORDS)
check("clamped at 32512", r16(word(0, 45)), 32512)

print("\n-- LFO2 is read from its own half of the voice's state --")
blank()
setrow(KIT, 0, route(strk=2, slfo=1, dtrk=5, on=1, dest=38, own=1), depth=16)
w32(lfoaddr(2, 0), 0x7fffffff)                                                  # LFO1: must be ignored
w32(lfoaddr(2, 1), -0x20000000 & 0xffffffff)
call("digimatrix_pre", WORDS)
w16(word(5, 38), 5000)
call("digimatrix_post", WORDS)
check("LFO2 of track 3", r16(word(5, 38)), 5000 + expect(-0x20000000 & 0xffffffff, 16))

print("\n-- off, no destination, zero depth: nothing happens --")
for name, r, dep in (("slot off", route(strk=0, dtrk=1, on=0, dest=26), 32),
                     ("no destination", route(strk=0, dtrk=1, on=1, dest=-1), 32),
                     ("zero depth", route(strk=0, dtrk=1, on=1, dest=26), 0)):
    blank()
    setrow(KIT, 0, r, depth=dep)
    w16(word(1, 26), 12345)
    w32(lfoaddr(0, 0), 0x7fffffff)
    call("digimatrix_pre", WORDS)
    call("digimatrix_post", WORDS)
    check(name, r16(word(1, 26)), 12345)

print("\n-- OWN off takes the LFO off its own track for the stock stage, and gives it back --")
blank()
setrow(KIT, 0, route(strk=1, slfo=0, dtrk=3, on=1, dest=26, own=0), depth=32)
w16(word(1, 4), 26)                                                             # LFO1 of T2: DEST = 26
call("digimatrix_pre", WORDS)
check("DEST taken away before the stock stage", r16(word(1, 4), signed=True), -1)
call("digimatrix_post", WORDS)
check("DEST put back after it", r16(word(1, 4)), 26)

print("\n-- two rows off one LFO, one of them OWN off --")
blank()
setrow(KIT, 0, route(strk=1, slfo=0, dtrk=3, on=1, dest=26, own=0), depth=32)
setrow(KIT, 1, route(strk=1, slfo=0, dtrk=4, on=1, dest=27, own=0), depth=-16)
w16(word(1, 4), 26)
w16(word(3, 26), 8000)
w16(word(4, 27), 8000)
w32(lfoaddr(1, 0), 0x40000000)
call("digimatrix_pre", WORDS)
check("taken away once", r16(word(1, 4), signed=True), -1)
call("digimatrix_post", WORDS)
check("put back, not -1", r16(word(1, 4)), 26)
check("row 1 applied", r16(word(3, 26)), 8000 + expect(0x40000000, 32))
check("row 2 applied", r16(word(4, 27)), 8000 + expect(0x40000000, -16))

print("\n-- the matrix comes from the kit, so every pattern has its own --")
blank()
setrow(KIT, 0, route(strk=0, dtrk=1, on=1, dest=26, own=1), depth=32)
setrow(KIT2, 0, route(strk=0, dtrk=1, on=1, dest=26, own=1), depth=-32)
w32(lfoaddr(0, 0), 0x40000000)
w16(word(1, 26), 9000)
call("digimatrix_pre", WORDS)
call("digimatrix_post", WORDS)
one = r16(word(1, 26))
w32(ENG_KIT, KIT2)
w16(word(1, 26), 9000)
call("digimatrix_pre", WORDS)
call("digimatrix_post", WORDS)
check("the other kit's depth", (one, r16(word(1, 26))),
      (9000 + expect(0x40000000, 32), 9000 + expect(0x40000000, -32)))

print("\n-- no kit: nothing is touched --")
blank()
w32(ENG_KIT, 0)
w16(word(1, 26), 4321)
call("digimatrix_pre", WORDS)
call("digimatrix_post", WORDS)
check("no kit", r16(word(1, 26)), 4321)

# ================= the page =================
KEY, ENC = 0x40904000, 0x40904100


def key(id, down=1):
    w32(KEY + 12, id)
    w32(KEY + 16, 1 if down else 0)
    return call("digimatrix_key", 0, KEY)


def enc(id, delta):
    w32(ENC + 12, id)
    w32(ENC + 16, delta)
    return call("digimatrix_enc", 0, ENC)


print("\n-- the page opens from the SETTINGS row and closes on NO --")
blank()
w32(MENU, MENU + 0x100)
check("shut, keys pass through", key(12), 0)
call("digimatrix_select", MENU)
check("open", r32(MAP["digimatrix_open"]), 1)
check("keys are taken", key(14), 1)
check("PLAY still goes through", key(10), 0)
key(13)
check("NO closes it", r32(MAP["digimatrix_open"]), 0)

print("\n-- YES fills an empty slot in, and turns it off again --")
blank()
call("digimatrix_select", MENU)
key(12)
r, d = getrow(KIT, 0)
check("row 1 on, T1 LFO1 -> T1, first destination", (r & 0x80 != 0, r & 7, (r >> 3) & 1,
                                                    (r >> 4) & 7, ((r >> 8) & 0x7f) - 1), (True, 0, 0, 0, 1))
check("its depth starts at 0", d - 128, 0)
key(12)
check("YES again turns it off, the rest kept", (getrow(KIT, 0)[0] & 0x80, getrow(KIT, 0)[0] >> 8), (0, r >> 8))

print("\n-- UP/DOWN and LEVEL walk the slots; the knobs edit the one under the cursor --")
blank()
call("digimatrix_select", MENU)
key(15); key(15)                                            # DOWN, DOWN -> slot 3
key(12)                                                     # turn it on
check("slot 3 is the one that came on", [getrow(KIT, i)[0] & 0x80 != 0 for i in range(8)],
      [False, False, True, False, False, False, False, False])
enc(1, 4); enc(1, 4)                                        # knob A: source track, T3 -> T5
enc(2, 4)                                                   # knob B: LFO2
enc(3, -4)                                                  # knob C: destination track, T3 -> T2
enc(4, 4); enc(4, 4)                                        # knob D: destination parameter
enc(5, 4); enc(5, 4); enc(5, 4)                             # knob E: depth
enc(6, -4)                                                  # knob F: OWN off
r, d = getrow(KIT, 2)
check("source track", r & 7, 4)
check("source LFO", (r >> 3) & 1, 1)
check("destination track", (r >> 4) & 7, 1)
check("destination parameter", ((r >> 8) & 0x7f) - 1, 3)
check("depth", d - 128, 6)
check("OWN off", r & 0x8000, 0)
enc(9, 4)
enc(1, 4)
check("LEVEL moved the cursor, so slot 3 did not change", getrow(KIT, 2)[0] & 7, 4)

print("\n-- knobs do nothing to a slot that is off --")
blank()
call("digimatrix_select", MENU)
enc(1, 4); enc(5, 4)
check("nothing written", getrow(KIT, 0), (0, 0))
check("nothing in the sound slots the +Drive does not keep", spare_slots_clean(KIT), True)

print("\n-- a sound loaded onto a track keeps the matrix; a kit load brings its own --")
uc.mem_write(UI_KIT, struct.pack(">I", KIT))
setrow(KIT, 4, route(strk=1, slfo=0, dtrk=3, on=1, dest=26, own=1), depth=20)
call("digimatrix_tick", 0x40904200)
sound_load(KIT, 4)
call("digimatrix_tick", 0x40904200)
check("slot 5 back after a sound load onto track 5", getrow(KIT, 4)[1], 148)
for t in range(8):
    sound_load(KIT, t)
call("digimatrix_tick", 0x40904200)
check("a kit load's own (empty) matrix stays", getrow(KIT, 4), (0, 0))
check("only markers in the RAM-only slots", spare_slots_clean(KIT), True)

print("\n-- the page draws a title, 8 rows and the cursor's bar --")
blank()
call("digimatrix_select", MENU)
key(12)
setrow(KIT, 1, route(strk=1, slfo=1, dtrk=4, on=1, dest=26, own=0), depth=-20)
del calls[:]
call("digimatrix_draw", BMP, 0)
fills = [c for c in calls if c[0] == "fill"]
texts = [c for c in calls if c[0] == "text"]
check("the screen is cleared first", fills[0][2:], (0, 0, 127, 63, 0))
check("one inverted bar, on the cursor's row", [f[2:] for f in fills[1:]], [(0, 48, 127, 54, -1)])
check("the title", [(t[1], t[3]) for t in texts[:3]], [(1, "MOD MATRIX"), (92, "DEP"), (112, "OWN")])
row2 = [t for t in texts if t[2] == 42]                      # row 2: y = 49 - 7
check("row 2 shows its source, destination, depth and OWN",
      [(t[1], t[3], t[4]) for t in row2],
      [(1, "%d", 2), (10, "T%d", 2), (23, "L%d", 2), (36, ">", row2[3][4]), (43, "T%d", 5),
       (56, "%s", row2[5][4]), (92, "-%d", 20), (116, "X", row2[7][4])])
name = bytes(uc.mem_read(row2[5][4] & 0xffffffff, 12))
check("the destination's name", name[:name.find(b"\0")].decode(), "FLT.FREQ")
row3 = [t for t in texts if t[2] == 35]
check("an empty slot shows dashes", [(t[1], t[3]) for t in row3], [(1, "%d"), (10, "- - -")])

print("\n-- the SETTINGS row counts the slots that are on --")
blank()
setrow(KIT, 0, route(strk=0, dtrk=0, on=1, dest=1), depth=8)
setrow(KIT, 5, route(strk=0, dtrk=0, on=1, dest=1), depth=8)
del calls[:]
call("digimatrix_rowdraw", 0, 0, BMP, 30, 10)
check("2 of 8", [(c[1], c[3], c[4]) for c in calls if c[0] == "text"], [(88, "%d/8", 2)])

print("\n%s  (%d failed)" % ("FAILED" if fails else "all good", len(fails)))
sys.exit(1 if fails else 0)
