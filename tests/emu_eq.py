#!/usr/bin/env python3
"""Digi EQ's code (mods/digieq/eq.c, eq_dsp.s) against its model (tests/eq_model.py).

    <python with digiemu's patched unicorn> tests/emu_eq.py --stock <official .syx> --elekloader <checkout> \
        --mods <core.elemod> <digieq.elemod>

Links the mods as elekloader does, runs the linked code in unicorn (ColdFire V4e; the EMAC needs the
patched unicorn that digiemu installs) and checks:
  1. knobs -> coefficients: random knob turns and knob pushes through the master page's handlers
     (digieq_menc, digieq_mkey, on a view showing the EQ page), every coefficient of the live set
     equal to the model's;
  2. audio: digieq_run on sine/noise blocks of the master mix (32-bit samples, 8 bits hotter than the
     24-bit words the model works in), output equal to EQ.block bit for bit, over many blocks and
     settings (bands switching on/off and between the seven types);
  3. all registers and the EMAC state (MACSR, ACC0, ACCEXT01) kept;
  4. the settings in the pattern's kit: written by a knob turn, read back when the kit changes, each kit
     keeping its own, and the GLOBAL FX/MIX > MASTER EQ row overriding them all.
"""
import argparse, math, os, random, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import eq_model as M

ap = argparse.ArgumentParser()
ap.add_argument("--stock", required=True)
ap.add_argument("--elekloader", required=True)
ap.add_argument("--mods", nargs="+", required=True)
a = ap.parse_args()
sys.path.insert(0, a.elekloader)
from elekloader import syx, devices, elemod, link
from unicorn import Uc, UC_ARCH_M68K, UC_MODE_BIG_ENDIAN
from unicorn.m68k_const import *

st = syx.Syx.load(a.stock)
dev, rel = devices.identify(st.sha256)
L = link.link([elemod.load_any(p) for p in a.mods], st.section(dev.main_section))
MAP = L.map
img = L.image
ddr0, run_end = L.layout["ddr"]
bss0, bss1 = L.layout["bss"]
run = img[L.layout["run_load"] - 0x40000400: L.layout["run_load"] - 0x40000400 + run_end - ddr0]

uc = Uc(UC_ARCH_M68K, UC_MODE_BIG_ENDIAN)
uc.ctl_set_cpu_model(UC_CPU_M68K_CFV4E)
uc.mem_map(0x40000000, 0x00400000)
uc.mem_write(0x40000400, img[:0x3fc000])
uc.mem_map(0x47b00000, 0x00100000)                   # the loader's RAM area (+ bss), and a stack
uc.mem_map(0x41900000, 0x00100000)                   # the UI's kit pointer and our fake kits
uc.mem_map(0x421f0000, 0x00010000)                   # the checkbox bitmaps
for _a in (0x400c9812, 0x400c2960):                  # invalidate, blit: not under test here
    uc.mem_write(_a, b"\x4e\x75")
uc.mem_write(ddr0, run)
uc.mem_write(bss0, bytes(bss1 - bss0))
STACK, SENT, BUF, EV = 0x47bf0000, 0x47b00100, 0x47b01000, 0x47b02000
uc.mem_write(SENT, b"\x4e\x71\x4e\x71")
REGS = [UC_M68K_REG_D0 + i for i in range(8)] + [UC_M68K_REG_A0 + i for i in range(7)]


def call(fn, *args):
    sp = STACK - 4 * (len(args) + 1)
    uc.mem_write(sp, struct.pack(">%dI" % (len(args) + 1), SENT, *[x & 0xffffffff for x in args]))
    uc.reg_write(UC_M68K_REG_A7, sp)
    uc.emu_start(MAP[fn], SENT, count=5_000_000)
    return uc.reg_read(UC_M68K_REG_D0)


def s32(v):
    return v - (1 << 32) if v & 0x80000000 else v


def rd32(addr, n=1):
    return [s32(x) for x in struct.unpack(">%dI" % n, uc.mem_read(addr, 4 * n))]


VIEW, KINDS, KEV = 0x47b04000, 0x47b04400, 0x47b04800      # a master view (kinds 11, 0, 12, 13), a key event
uc.mem_write(VIEW, bytes(256))
uc.mem_write(KINDS, struct.pack(">4i", 11, 0, 12, 13))
uc.mem_write(VIEW + 124, struct.pack(">III", KINDS, KINDS + 16, KINDS + 16))
PER = 16                                                     # the page's knob events carry 16 a notch
alt = [0] * 8


def page(idx):
    uc.mem_write(VIEW + 144, struct.pack(">i", idx))


def knob(model, enc, delta):
    """Turn a knob on the unit (digieq_menc) and in the model; returns the handler's result."""
    if delta and random.random() < 0.3:                  # the same steps as two partial turns
        uc.mem_write(EV + 12, struct.pack(">ii", enc, PER * delta - PER // 2))
        call("digieq_menc", VIEW, EV)
        uc.mem_write(EV + 12, struct.pack(">ii", enc, PER // 2))
    else:
        uc.mem_write(EV + 12, struct.pack(">ii", enc, PER * delta))
    r = call("digieq_menc", VIEW, EV)
    b = (enc - 1) & 3
    if enc <= 4:
        if alt[enc - 1]:
            model.p[b][2] = max(0, min(15, model.p[b][2] + delta))
        else:
            model.p[b][1] = max(0, min(48, model.p[b][1] + delta))
    else:
        if alt[enc - 1]:
            model.p[b][3] = max(0, min(6, model.p[b][3] + delta))
        else:
            model.p[b][0] = max(0, min(127, model.p[b][0] + delta))
    return r & 0xff


def push(k):
    """Press knob k (0..7 = A..H): it switches between its two settings."""
    uc.mem_write(KEV, struct.pack(">IIIIII", 0, 0, 0, 40 + k, 1, 0))
    r = call("digieq_mkey", VIEW, KEV)
    alt[k] ^= 1
    return r & 0xff


def check_set(model):
    live = rd32(MAP["digieq_live"])[0] & 0xffffffff
    v = rd32(live, 30)
    act = model.active()
    ok = v[0] == (1 if any(act) else 0) and v[1] == 0
    ok &= [bool(x) for x in v[2:6]] == [bool(x) for x in act]
    for b in range(4):
        ok &= tuple(v[6 + 6 * b: 12 + 6 * b]) == M.coef(*model.p[b])
    return ok


fails = 0
random.seed(1)
# ---- 1. knobs -> coefficients ----
model = M.EQ()
page(1)                                                       # the view shows the EQ page
n_sets = 0
for i in range(600):
    if random.random() < 0.1:
        if push(random.randint(0, 7)) != 1:
            print("FAIL knob push not taken on the EQ page"); fails += 1
            break
    enc = random.randint(1, 8)
    d = random.choice([-7, -3, -1, 1, 1, 2, 5, 30, -30])
    if knob(model, enc, d) != 1:
        print("FAIL knob not taken on the EQ page"); fails += 1
        break
    if rd32(MAP["digieq_live"])[0]:
        n_sets += 1
        if not check_set(model):
            print("FAIL coefficients differ after knob %d %+d (params %s)" % (enc, d, model.p))
            fails += 1
            break
print("knobs -> coefficients: %d settings checked (types seen: %s)" % (
    n_sets, sorted(set(M.TYPES[b[3]] for b in model.p))))

# ---- 2. audio: bit-exact vs the model; 3. registers and EMAC state kept ----
STUB, SAVE = 0x47b00200, 0x47b03000


def build_stub():
    """Sets MACSR 0xa0 and ACC0 0x12345678, calls digieq_run(BUF), then leaves d0-d7/a0-a6 on the
    stack (60 bytes at STACK-60) and MACSR, ACC0 at SAVE, SAVE+4. Assembled with m68k binutils."""
    import subprocess, tempfile
    src = """
    move.l #0xa0,%%macsr
    move.l %%d0,-(%%sp)
    move.l #0x12345678,%%d0
    move.l %%d0,%%acc0
    move.l (%%sp)+,%%d0
    move.l #0x%x,-(%%sp)
    jsr 0x%x
    addq.l #4,%%sp
    lea -60(%%sp),%%sp
    movem.l %%d0-%%d7/%%a0-%%a6,(%%sp)
    move.l %%macsr,%%d0
    move.l %%d0,0x%x
    move.l %%acc0,%%d0
    move.l %%d0,0x%x
    nop
""" % (BUF, MAP["digieq_run"], SAVE, SAVE + 4)
    d = tempfile.mkdtemp()
    open(d + "/s.s", "w").write(src)
    subprocess.run(["m68k-linux-gnu-as", "-mcpu=54455", "-o", d + "/s.o", d + "/s.s"], check=True)
    subprocess.run(["m68k-linux-gnu-objcopy", "-O", "binary", d + "/s.o", d + "/s.bin"], check=True)
    c = open(d + "/s.bin", "rb").read()
    uc.mem_write(STUB, c)
    return STUB + len(c) - 2


STUB_END = build_stub()


def run_block(buf):
    uc.mem_write(BUF, struct.pack(">64i", *buf))
    regs = {r: random.getrandbits(32) for r in REGS}
    for r, v in regs.items():
        uc.reg_write(r, v)
    uc.reg_write(UC_M68K_REG_A7, STACK)
    uc.emu_start(STUB, STUB_END, count=5_000_000)
    saved = struct.unpack(">15I", uc.mem_read(STACK - 60, 60))
    macsr, acc0 = struct.unpack(">II", uc.mem_read(SAVE, 8))
    kept = list(saved) == [regs[r] for r in REGS]
    kept &= (macsr & 0xf0) == 0xa0 and acc0 == 0x12345678 and uc.reg_read(UC_M68K_REG_A7) == STACK - 60
    return rd32(BUF, 64), kept


blocks = 0
uc.mem_write(bss0, bytes(bss1 - bss0))       # fresh audio state
uc.mem_write(ddr0, run)                      # fresh settings (initialised data)
alt[:] = [0] * 8
model = M.EQ()
f_list = [55.0, 180.0, 440.0, 1250.0, 5000.0, 13000.0]
ph = 0
types_heard = set()
for step in range(240):
    if step % 5 == 0:
        for _ in range(random.randint(1, 4)):
            if random.random() < 0.25:
                push(random.randint(0, 7))
            knob(model, random.randint(1, 8), random.choice([-9, -3, -1, 1, 2, 5, 12]))
        types_heard |= set(M.TYPES[b[3]] for b, a_ in zip(model.p, model.active()) if a_)
    for blk in range(4):
        f = f_list[step % len(f_list)]
        buf = []
        for i in range(32):
            l = int(3_000_000 * math.sin(2 * math.pi * f * ph / 48000.0)) + random.randint(-40000, 40000)
            r = int(2_000_000 * math.sin(2 * math.pi * f * 1.5 * ph / 48000.0)) + random.randint(-40000, 40000)
            ph += 1
            buf += [max(-(1 << 23) + 1, min((1 << 23) - 1, l)), max(-(1 << 23) + 1, min((1 << 23) - 1, r))]
        got, kept = run_block([x << 8 for x in buf])         # the master mix's own scale
        want = [y << 8 for y in model.block(buf)]
        blocks += 1
        if got != want:
            i = next(j for j in range(64) if got[j] != want[j])
            print("FAIL block %d sample %d: unit %d model %d (params %s)" % (blocks, i, got[i], want[i], model.p))
            fails += 1
            break
        if not kept:
            print("FAIL registers or MACSR not kept"); fails += 1
            break
    if fails:
        break
print("audio: %d blocks bit-exact vs the model (band types heard: %s)" % (blocks, sorted(types_heard)))

# ---- 4. the settings in the pattern's kit, and the global override ----
UI_KIT, KIT1, KIT2, MENU = 0x4199dc44, 0x41980000, 0x41981000, 0x41982000
BMP, CHECKBOXES = 0x41983000, 0x421f7a3c


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

def eqwords(kit):                                # in the shape of the old two words a band
    rd = lambda n: uc.mem_read(kit + xb(n), 1)[0]
    out = []
    for b in range(4):
        w = (rd(6 * b + 4) << 8) | rd(6 * b + 5)
        out.append((w & ~0x4000, (rd(6 * b + 3) & 0x7f) | (((w >> 14) & 1) << 7 if b == 0 else 0)))
    return out


def setkit(kit):
    uc.mem_write(UI_KIT, struct.pack(">I", kit))
    call("digieq_tick", 0)


def params():                                    # what the live settings say, through the drawn values
    live = rd32(MAP["digieq_live"])[0] & 0xffffffff
    return tuple(rd32(live, 30)[6:])


def check(name, got, want):
    global fails
    if got != want:
        print("FAIL %s: got %r want %r" % (name, got, want)); fails += 1
    else:
        print("  ok  %s" % name)


uc.mem_write(KIT1, bytes(0x600)); uc.mem_write(KIT2, bytes(0x600))
uc.mem_write(bss0, bytes(bss1 - bss0)); uc.mem_write(ddr0, run)
alt[:] = [0] * 8
model = M.EQ()
setkit(KIT1)
check("a kit with no EQ starts flat", rd32(MAP["digieq_live"])[0] != 0 and params() != (), True)
knob(model, 1, 6)                                # band 1 level up: written into kit 1
w = eqwords(KIT1)
check("a knob turn is written into the kit", (w[0][0] & 0x8000) != 0 and (w[0][0] >> 7) & 0x3f, 24 + 6)
after1 = params()
setkit(KIT2)                                     # another pattern: its own (empty) settings
check("another pattern starts from its own", params() != after1, True)
setkit(KIT1)
check("back to the first pattern's settings", params(), after1)

uc.mem_write(CHECKBOXES, struct.pack(">I", 0x41984000))
uc.mem_write(MENU, struct.pack(">I", MENU + 0x100))
call("digieq_gselect", MENU)                     # GLOBAL FX/MIX > MASTER EQ on
check("the row turns global on", rd32(MAP["digieq_global"])[0], 1)
check("the kit carries the global bit", (eqwords(KIT1)[0][1] >> 7) & 1, 1)
setkit(KIT2)
check("the other pattern is overridden", params(), after1)
check("and is given these settings", eqwords(KIT2)[0][0], eqwords(KIT1)[0][0])
check("nothing in the sound slots the +Drive does not keep", spare_slots_clean(KIT1) and spare_slots_clean(KIT2), True)
call("digieq_gselect", MENU)                     # off again
check("the row turns global off", rd32(MAP["digieq_global"])[0], 0)

# a project load refills the same kit in place (every sound loaded again): its own settings come back
setkit(KIT1)
before = params()
for t in range(8):
    sound_load(KIT1, t)
uc.mem_write(KIT1 + xb(4), bytes([0x80 | (15 >> 1)])); uc.mem_write(KIT1 + xb(5), bytes([((15 & 1) << 7) | 25]))
call("digieq_tick", 0)
check("a kit loaded in place is picked up", eqwords(KIT1)[0][0] >> 7 & 0x3f, 15)
after = params()
check("and heard", after != before, True)
call("digieq_tick", 0)
check("and only once", params(), after)
sound_load(KIT1, 0)                                   # a sound onto track 1: band 1 must not change
call("digieq_tick", 0)
check("a sound load keeps band 1", (eqwords(KIT1)[0][0] >> 7 & 0x3f, params()), (15, after))
for t in range(8):                                    # a loaded kit with no EQ in it: flat
    sound_load(KIT1, t)
call("digieq_tick", 0)
check("a loaded kit with no EQ goes flat", params() != after, True)
check("only markers in the RAM-only slots", spare_slots_clean(KIT1), True)

print("PASS" if not fails else "FAIL")
sys.exit(1 if fails else 0)
