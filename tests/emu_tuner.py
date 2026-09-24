#!/usr/bin/env python3
# v3o tuner on the SHIPPED section (real image; only operator new is stubbed to a fixed buffer):
#  TUNE : TNOTE/TCENT bit-exact vs tuner_model.tune() for 360 tones (A0..C7, sine/saw/square, detuned) + silence,
#         noise, quiet, noisy, decaying, chord; every-4th-call gating; registers preserved; allocation once.
#  TTAP : via the real scope TAP, the 3 kHz ring = model (sum of 4 mids >> 2), ISR-transparent.
#  TDRAW: the text call gets (bmp, font 0x40200b0c, x 1, y 1, -1, "%s%d %c%d", name, octave, sign, |cents|) or "--";
#         only x 0..31 / rows 0..6 change; the real text routine draws inside that box.
# Usage: python3 emu_tuner_v3o.py <section_3_v3o.bin> <scope_v3o.sym> <tuner.elf>
import struct, random, sys, os, math
from unicorn import *
from unicorn.m68k_const import *
from tuner_model import tune as model_tune, RN
import tuner_eval
IMG = open(sys.argv[1], 'rb').read(); B = 0x40000400
SYMS = {p[2]: int(p[0], 16) for p in (ln.split() for ln in open(sys.argv[2])) if len(p) == 3}
T = {}
for ln in os.popen('m68k-linux-gnu-nm ' + sys.argv[3]).read().split('\n'):
    p = ln.split()
    if len(p) == 3: T[p[2]] = int(p[0], 16)
TUNE, TDRAW, TTAP = T['TUNE'], T['TDRAW'], T['TTAP']
SCOPE = 0x400abe9c; TAP = SCOPE + SYMS['TAP']
RING, IDXA = 0x400ae290, 0x400ae280
TIDX, TNOTE, TCENT, TCNT, TBUF, TRING = 0x400aeab4, 0x400aeab8, 0x400aeabc, 0x400aeac0, 0x400aeac4, 0x400aead0
TEXT, NEWOP, OUTWRITE = 0x400c257c, 0x400d4180, 0x40071c20
HEAP = 0x53008000; STK = 0x7f000000; BMP, BD = 0x52000000, 0x52000100
def l(x): return struct.pack('>I', x & 0xffffffff)
def s32(x): return x - (1 << 32) if x & 0x80000000 else x
ALL = [UC_M68K_REG_D0 + i for i in range(8)] + [UC_M68K_REG_A0 + i for i in range(7)]
SAVED = [UC_M68K_REG_D0 + i for i in range(2, 8)] + [UC_M68K_REG_A0 + i for i in range(2, 7)]
assert IMG[TUNE - B:TUNE - B + 4] == open(sys.argv[3].replace('.elf', '.bin'), 'rb').read()[TUNE - 0x400ac8f0:][:4]
NEWSTUB = bytes.fromhex("203c") + l(HEAP) + bytes.fromhex("52b9") + l(0x53000ff0) + bytes.fromhex("4e75")  # d0=HEAP; count++
def dev():
    mu = Uc(UC_ARCH_M68K, UC_MODE_BIG_ENDIAN); mu.ctl_set_cpu_model(UC_CPU_M68K_CFV4E)
    mu.mem_map(0x40000000, 0x280000)
    img = bytearray(IMG); img[NEWOP - B:NEWOP - B + len(NEWSTUB)] = NEWSTUB
    mu.mem_write(B, bytes(img))
    for a in (0x52000000, 0x53000000, 0x51000000): mu.mem_map(a, 0x10000)
    mu.mem_map(STK, 0x8000)
    return mu
def call(mu, fn, args):
    ret = 0x40000500; sp = STK + 0x6000
    mu.mem_write(sp, l(ret) + b''.join(l(a) for a in args)); mu.reg_write(UC_M68K_REG_A7, sp)
    regs = {r: random.getrandbits(32) for r in ALL}
    for r, v in regs.items(): mu.reg_write(r, v)
    mu.emu_start(fn, ret, count=60_000_000)
    assert mu.reg_read(UC_M68K_REG_PC) == ret and mu.reg_read(UC_M68K_REG_A7) == sp + 4
    for r in SAVED: assert regs[r] == mu.reg_read(r), ("reg leak", hex(fn), r)
    return regs
def rd(mu, a): return struct.unpack('>I', mu.mem_read(a, 4))[0]

def load_rings(mu, r12, i12, r3, i3):
    mu.mem_write(RING, b''.join(struct.pack('>hh', r12[k], 0) for k in range(RN)))
    mu.mem_write(IDXA, l(i12)); mu.mem_write(TRING, b''.join(struct.pack('>h', v) for v in r3)); mu.mem_write(TIDX, l(i3))
def run_tune(r12, i12, r3, i3, cnt=3):
    mu = dev(); load_rings(mu, r12, i12, r3, i3)
    mu.mem_write(TCNT, l(cnt)); mu.mem_write(TBUF, l(0)); mu.mem_write(TNOTE, l(0x1234)); mu.mem_write(0x53000ff0, l(0))
    call(mu, TUNE, [])
    return mu, s32(rd(mu, TNOTE)), s32(rd(mu, TCENT))

# ---- TUNE vs model
n_ok = n_none = 0
cases = []
for f in [27.5, 32.7, 41.2, 55, 61.7, 65.4, 73.4, 82.4, 110, 146.8, 220, 261.6, 329.6, 440, 523.3, 880, 1046.5, 1318.5, 1760, 2093]:
    for det in (-37, -12, 0, 8, 23, 44):
        ff = f * 2 ** (det / 1200)
        for wave in ('sine', 'saw', 'square'):
            amp = random.choice([3e6, 8e5, 7e6])
            if wave == 'sine': fn = (lambda ff, amp: lambda n: int(amp * math.sin(2 * math.pi * ff * n / 48000)))(ff, amp)
            elif wave == 'saw': fn = (lambda ff, amp: lambda n: int(amp * (2 * ((ff * n / 48000) % 1) - 1)))(ff, amp)
            else: fn = (lambda ff, amp: lambda n: int(amp * (1 if (ff * n / 48000) % 1 < 0.5 else -1)))(ff, amp)
            cases.append(('%s %.1f' % (wave, ff), fn))
random.seed(5)
cases += [('silence', lambda n: 0), ('noise', lambda n: int(random.gauss(0, 2e6))),
          ('quiet', lambda n: int(2.6e4 * math.sin(2 * math.pi * 440 * n / 48000))),
          ('440+noise', lambda n: int(3e6 * math.sin(2 * math.pi * 440 * n / 48000) + random.gauss(0, 5e5))),
          ('decay saw 110', lambda n: int(4e6 * math.exp(-n / 20000) * (2 * ((110 * n / 48000) % 1) - 1))),
          ('chord', lambda n: int(1.5e6 * sum(math.sin(2 * math.pi * f * n / 48000) for f in (261.6, 329.6, 392))))]
for name, fn in cases:
    r12, i12, r3, i3 = tuner_eval.rings(fn)
    i12 += random.choice([0, 0x10000000, 0xfffff000]) // RN * RN        # large / wrapping indices, same content
    i3 += random.choice([0, 0x20000000]) // RN * RN
    exp = model_tune(r12, i12 & 0xffffffff, r3, i3 & 0xffffffff)
    mu, note, cent = run_tune(r12, i12 & 0xffffffff, r3, i3 & 0xffffffff)
    if exp is None: assert note == -1, (name, note, cent); n_none += 1
    else: assert (note, cent) == exp, (name, (note, cent), exp); n_ok += 1
    assert rd(mu, 0x53000ff0) == 1 and rd(mu, TBUF) == HEAP
print("TUNE bit-exact vs model: %d pitched, %d none" % (n_ok, n_none))
# gating: only every 4th call estimates; buffer allocated once
r12, i12, r3, i3 = tuner_eval.rings(lambda n: int(3e6 * math.sin(2 * math.pi * 440 * n / 48000)))
mu = dev(); load_rings(mu, r12, i12, r3, i3); mu.mem_write(TCNT, l(0)); mu.mem_write(TBUF, l(0)); mu.mem_write(TNOTE, l(0x777))
mu.mem_write(0x53000ff0, l(0))
for k in range(1, 9):
    call(mu, TUNE, [])
    assert rd(mu, TCNT) == k
    assert (rd(mu, TNOTE) == 69) == (k >= 4), (k, rd(mu, TNOTE))
assert rd(mu, 0x53000ff0) == 1
print("TUNE gating + single allocation ok")

# ---- TTAP through the real TAP
W_STUB = (bytes.fromhex("206f0004") + bytes.fromhex("43f9") + l(0x51000000) + bytes.fromhex("7240") +
          bytes.fromhex("20d9") + bytes.fromhex("5381") + bytes.fromhex("66fa") + bytes.fromhex("203c") + l(0x1234) + bytes.fromhex("4e75"))
mu = dev(); mu.mem_write(OUTWRITE, W_STUB); mu.mem_write(IDXA, l(0)); mu.mem_write(TIDX, l(0))
random.seed(9); mids = []; r3 = [0] * RN; i3 = 0
for blk in range(200):
    frames = [(random.getrandbits(24) - (1 << 23), random.getrandbits(24) - (1 << 23)) for _ in range(32)]
    words = [w & 0xffffffff for f in frames for w in f]
    mu.mem_write(0x51000000, b''.join(l(w) for w in words))
    call(mu, TAP, [0x53000000, 0x53001000, 0x12345678])
    for k in range(8):
        s = sum(s32(words[k * 8 + j]) for j in range(8)); m = max(-32768, min(32767, (s >> 8) >> 3)); mids.append(m)
    for g in (mids[-8:-4], mids[-4:]):
        r3[i3 % RN] = sum(g) >> 2; i3 += 1
got = list(struct.unpack('>%dh' % RN, mu.mem_read(TRING, RN * 2)))
assert got == r3 and rd(mu, TIDX) == i3, "TTAP ring mismatch"
print("TTAP 3 kHz ring exact over 200 blocks (wraps)")

# ---- TDRAW
NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
def cstr(mu, a):
    b = b''
    while True:
        c = mu.mem_read(a, 1)
        if c == b'\0': return b.decode()
        b += c; a += 1
def bitmap(mu):
    raw = mu.mem_read(BD, 1024); px = [[0] * 128 for _ in range(64)]
    for X in range(128):
        for wi in range(2):
            wv = struct.unpack('>I', raw[(X * 2 + wi) * 4:(X * 2 + wi) * 4 + 4])[0]
            for b in range(32):
                if wv & (0x80000000 >> b): px[wi * 32 + b][X] = 1
    return px
for note, cent in [(-1, 0), (69, 0), (69, 12), (70, -3), (12, 49), (127, -50), (33, 7), (96, -40), (61, 1)]:
    mu = dev(); mu.mem_write(TNOTE, l(note)); mu.mem_write(TCENT, l(cent))
    mu.mem_write(BMP, l(0) + l(128) + l(64) + l(2) + l(BD)); mu.mem_write(BD, bytes(random.getrandbits(8) for _ in range(1024)))
    before = bitmap(mu); seen = []
    def hk(uc, addr, size, _):
        sp = uc.reg_read(UC_M68K_REG_A7); a = struct.unpack('>11I', uc.mem_read(sp + 4, 44)); seen.append(a)
    mu.hook_add(UC_HOOK_CODE, hk, begin=TEXT, end=TEXT)
    call(mu, TDRAW, [BMP])
    assert len(seen) == 1
    a = seen[0]; assert a[0] == BMP and a[1] == 0x40200b0c and a[2:5] == (1, 1, 0xffffffff), a
    fmt = cstr(mu, a[5])
    if note < 0: assert fmt == "--"
    else:
        assert fmt == "%s%d %c%d"
        txt = "%s%d %s%d" % (cstr(mu, a[6]), s32(a[7]), chr(a[8]), a[9])
        want = "%s%d %s%d" % (NAMES[note % 12], note // 12 - 1, '+' if cent >= 0 else '-', abs(cent))
        assert txt == want, (txt, want)
    px = bitmap(mu)
    for y in range(64):
        for x in range(128):
            if x < 32 and y < 7: continue
            assert px[y][x] == before[y][x], ("TDRAW outside its box", x, y)
    assert any(px[y][x] for y in range(1, 6) for x in range(1, 31)) and not any(px[0][x] or px[6][x] for x in range(32))
print("TDRAW text/args/box ok")
print("tuner v3o: all emulator tests passed")
