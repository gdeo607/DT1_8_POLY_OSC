#!/usr/bin/env python3
# Page "spectrum" on the patched section (real image, real vline; operator new stubbed):
#  shared shell : emu_scope.py's key, TAP (mid/side + transparency), X-Y draw and race tests run on this build
#  SCAP         : capture through the real TAP = model (clamp((L+R)>>9)), stops at exactly 1024, SREQ/SRDY handshake
#  analysis     : COLH/PK bit-exact vs spec_model (both bands) for tones, saw, noise, chord, silence, clipping
#  draw         : bars, falling peaks and 100 Hz/1 kHz/10 kHz ticks pixel-exact, normal and fullscreen
#  allocation   : one 6 KB buffer, capture requested
# Usage: python3 emu_spectrum.py <section_3 (page spectrum)> <bin/scope_spectrum.sym> <bin/spectrum.elf>
#        ALLVIEWS=1 python3 emu_spectrum.py <section_3 (page all)> <bin/scope_all.sym> <bin/spectrum.elf>
import sys, os, struct, random, math
SEC, SYM, ELF = sys.argv[1:4]
sys.argv = [sys.argv[0], SEC, SYM]
import emu_scope as S                                  # shared page shell tests (module reads sys.argv)
from spec_model import *
from unicorn.m68k_const import *
T = {}
for ln in os.popen('m68k-linux-gnu-nm ' + ELF).read().split('\n'):
    p = ln.split()
    if len(p) == 3: T[p[2]] = int(p[0], 16)
SPEC, SCAP = T['SPEC'], T['SCAP']
SREQ = 0x400aeed0; SRDY, SCNT, SPTR, SWORK = SREQ + 4, SREQ + 8, SREQ + 12, SREQ + 16
COLH, PK = 0x400aeee8, 0x400aef68
TRING, TIDX, FULLA, PYMAX = 0x400aead0, 0x400aeab4, 0x400ae28c, 0x400aeaa8
BUF = 0x53008000; NEWOP = 0x400d4180
l, rd, s32 = S.l, S.rd, S.s32
NEWSTUB = bytes.fromhex("203c") + l(BUF) + bytes.fromhex("52b9") + l(0x53000ff0) + bytes.fromhex("4e75")

def dev():
    mu = S.dev(); mu.mem_write(NEWOP, NEWSTUB); mu.mem_write(0x53000ff0, l(0)); return mu

# ---------------- shared shell (same code paths as the scope page) ----------------
random.seed(1)
S.test_key({0: 2, 2: 1, 1: None} if os.environ.get('ALLVIEWS') else None)
blocks = [[(random.getrandbits(24) - (1 << 23), random.getrandbits(24) - (1 << 23)) for _ in range(32)] for _ in range(6)]
S.test_tap([[(a & 0xffffffff, b & 0xffffffff) for a, b in bl] for bl in blocks])
for s_ in range(12):
    random.seed(300 + s_)
    M = [random.randint(-32768, 32767) for _ in range(512)]; Sd = [random.randint(-3000, 3000) for _ in range(512)]
    S.test_draw(M, Sd, random.getrandbits(32), 1, 'xy%d' % s_, mach=[random.choice([0, 4]) for _ in range(8)],
                vnote=[random.choice([0xff, 60]) for _ in range(8)], full=s_ % 2)
print("shared shell (keys, TAP, X-Y, overlays) ok on the spectrum build")

# ---------------- SCAP through the real TAP ----------------
def cap_model(words):
    out = []
    for i in range(32):
        v = (s32(words[2 * i]) + s32(words[2 * i + 1])) >> 9
        out.append(max(-32767, min(32767, v)))
    return out
mu = dev(); mu.mem_write(S.OUTWRITE, S.W_STUB)
mu.mem_write(SPTR, l(BUF)); mu.mem_write(SREQ, l(1)); mu.mem_write(SRDY, l(0)); mu.mem_write(SCNT, l(0))
model = []; random.seed(4)
for blk in range(40):
    fr = [(random.choice([random.getrandbits(24) - (1 << 23), (1 << 23) - 1, -(1 << 23)]),
           random.choice([random.getrandbits(24) - (1 << 23), (1 << 23) - 1, -(1 << 23)])) for _ in range(32)]
    words = [w & 0xffffffff for f in fr for w in f]
    mu.mem_write(0x51000000, b''.join(l(w) for w in words))
    before = model[:]
    if len(model) < 1024: model += cap_model(words)[:1024 - len(model)]
    S.call(mu, S.TAP, [0x53000000, 0x53001000, 0x12345678])
    n = rd(mu, SCNT)
    assert n == len(model), (blk, n, len(model))
    assert (rd(mu, SREQ), rd(mu, SRDY)) == ((0, 1) if len(model) == 1024 else (1, 0)), blk
got = list(struct.unpack('>1024h', mu.mem_read(BUF, 2048)))
assert got == model, "capture mismatch"
print("SCAP: capture exact, stops at 1024, handshake ok")

# ---------------- analysis + draw ----------------
def bmp(mu):
    mu.mem_write(S.BMP, l(0) + l(128) + l(64) + l(2) + l(S.BMPDATA)); mu.mem_write(S.BMPDATA, bytes(random.getrandbits(8) for _ in range(1024)))
def draw_model(hs, pk, full):
    ymax = 63 if full else 52; base, H = (0, 63) if full else (8, 44)
    px = [[0] * 128 for _ in range(ymax + 1)]
    for c in range(128):
        hd = hs[c] * H // HMAX
        for y in range(base, base + hd + 1 if hd > 0 else base): px[y][c] = 1
        pd = pk[c] * H // HMAX
        if pd > hd: px[base + pd][c] = 1
    if not full:
        for m in MARKS: px[7][m] = 1
    return px
def run_spec(capture, r3, i3, pk0, full, ready=True):
    mu = dev(); bmp(mu)
    mu.mem_write(SPTR, l(BUF)); mu.mem_write(SWORK, l(BUF + 2048)); mu.mem_write(BUF, b''.join(struct.pack('>h', v) for v in capture))
    mu.mem_write(TRING, b''.join(struct.pack('>h', v) for v in r3)); mu.mem_write(TIDX, l(i3))
    mu.mem_write(PK, bytes(pk0)); mu.mem_write(COLH, bytes(random.getrandbits(6) for _ in range(128)))
    mu.mem_write(SRDY, l(1 if ready else 0)); mu.mem_write(SREQ, l(0)); mu.mem_write(SCNT, l(1024))
    mu.mem_write(FULLA, l(full)); mu.mem_write(PYMAX, l(63 if full else 52))
    S.call(mu, SPEC, [S.BMP])
    return mu
def rings3(fn, blocks=400):
    r3 = [0] * 512; i3 = 0; acc = []
    for blk in range(blocks):
        for k in range(8):
            s = 0
            for f in range(4):
                L, R = fn(blk * 32 + k * 4 + f); s += int(L) + int(R)
            acc.append(max(-32768, min(32767, (s >> 8) >> 3)))
            if len(acc) == 4: r3[i3 % 512] = sum(acc) >> 2; i3 += 1; acc = []
    return r3, i3
def capture(fn, n0):
    return [max(-32767, min(32767, (int(fn(n0 + n)[0]) + int(fn(n0 + n)[1])) >> 9)) for n in range(1024)]
random.seed(7)
sigs = {'sine440': lambda n: (4e6 * math.sin(2 * math.pi * 440 * n / 48000),) * 2,
        'sine55': lambda n: (5e6 * math.sin(2 * math.pi * 55 * n / 48000),) * 2,
        'saw110': lambda n: (3e6 * (2 * ((110 * n / 48000) % 1) - 1),) * 2,
        'hi 9k': lambda n: (2e6 * math.sin(2 * math.pi * 9000 * n / 48000), 0),
        'noise': lambda n: (random.gauss(0, 1e6), random.gauss(0, 1e6)),
        'clip': lambda n: ((1 << 23) - 1 if (n // 30) % 2 else -(1 << 23),) * 2,
        'silence': lambda n: (0, 0)}
nimg = 0
for k, (name, fn) in enumerate(sigs.items()):
    r3, i3 = rings3(fn); cap = capture(fn, 400 * 32 - 1024)
    hs = heights(fft_mag([r3[(i3 - 512 + j) % 512] for j in range(512)], 512), fft_mag(cap, 1024))
    for full in (0, 1):
        pk0 = [random.randrange(64) for _ in range(128)]
        mu = run_spec(cap, r3, i3 + random.choice([0, 512 * 1000]), pk0, full)
        assert list(mu.mem_read(COLH, 128)) == hs, (name, 'heights')
        pk = update_peaks(pk0, hs)
        assert list(mu.mem_read(PK, 128)) == pk, (name, 'peaks')
        assert (rd(mu, SREQ), rd(mu, SRDY), rd(mu, SCNT)) == (1, 0, 0), name
        px = S.bitmap_read(mu); exp = draw_model(hs, pk, full)
        for y in range(len(exp)):
            assert px[y] == exp[y], (name, full, y, [x for x in range(128) if px[y][x] != exp[y][x]])
        if os.environ.get('PNG'):
            from PIL import Image
            im = Image.new('L', (128, 64)); im.putdata([255 if px[63 - y][x] else 0 for y in range(64) for x in range(128)])
            im.resize((512, 256), Image.NEAREST).save(os.path.join(os.environ['PNG'], 'spec_%s_%d.png' % (name.replace(' ', ''), full)))
print("analysis: COLH/PK bit-exact vs model (both bands), pixels exact, normal + fullscreen")
# not ready -> no analysis, just draw the stored bars
hs = [random.randrange(64) for _ in range(128)]; pk = [random.randrange(64) for _ in range(128)]
mu = dev(); bmp(mu); mu.mem_write(SPTR, l(BUF)); mu.mem_write(COLH, bytes(hs)); mu.mem_write(PK, bytes(pk)); mu.mem_write(SRDY, l(0))
mu.mem_write(SREQ, l(1)); mu.mem_write(FULLA, l(0)); mu.mem_write(PYMAX, l(52))
S.call(mu, SPEC, [S.BMP]); px = S.bitmap_read(mu); exp = draw_model(hs, pk, 0)
assert all(px[y] == exp[y] for y in range(53)) and list(mu.mem_read(PK, 128)) == pk and rd(mu, SREQ) == 1
# allocation
mu = dev(); bmp(mu); mu.mem_write(SPTR, l(0)); mu.mem_write(FULLA, l(0)); mu.mem_write(PYMAX, l(52))
S.call(mu, SPEC, [S.BMP]); S.call(mu, SPEC, [S.BMP])
assert rd(mu, 0x53000ff0) == 1 and rd(mu, SPTR) == BUF and rd(mu, SWORK) == BUF + 2048 and rd(mu, SREQ) == 1 and rd(mu, SCNT) == 0
print("idle draw + one-time allocation ok")
print("spectrum page: all emulator tests passed")
