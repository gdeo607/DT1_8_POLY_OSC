#!/usr/bin/env python3
# Page "all" (waveform -> spectrum -> X-Y -> close) on the patched section:
#  DRAW dispatch: MODE 0 = waveform and MODE 1 = X-Y pixel-exact (emu_scope models, with overlays);
#                 MODE 2 = spectrum: exactly the pixels of the real SPEC run alone on the same state, plus the
#                 activity boxes on top (tuner box excluded, tested in emu_tuner.py); normal and fullscreen.
#  TRIG at 0x400ab072 is reached from the ISR hook (behaviour: emu_trig.py).
#  Keys / TAP / capture / FFT: ALLVIEWS=1 emu_spectrum.py (same code, three-step key cycle).
# Usage: python3 emu_allviews.py <section_3 (page all)> <bin/scope_all.sym> <bin/spectrum.elf>
import sys, os, struct, random
SEC, SYM, ELF = sys.argv[1:4]
sys.argv = [sys.argv[0], SEC, SYM]
import emu_scope as S
from unicorn.m68k_const import *
T = {}
for ln in os.popen('m68k-linux-gnu-nm ' + ELF).read().split('\n'):
    p = ln.split()
    if len(p) == 3: T[p[2]] = int(p[0], 16)
SPEC = T['SPEC']
l, rd = S.l, S.rd
TRIG_ALL = 0x400ab072
IMG = open(SEC, 'rb').read(); B = 0x40000400
assert IMG[0x40077d72 - B:0x40077d7a - B] == bytes.fromhex("4eb9") + l(TRIG_ALL) + bytes.fromhex("4e71")
SREQ = 0x400aeed0; SPTR = SREQ + 12; SWORK = SREQ + 16; COLH, PK = 0x400aeee8, 0x400aef68
BUF = 0x53008000
# modes 0 and 1: the scope models (pixel-exact incl. boxes; tuner box excluded)
random.seed(11)
for s_ in range(24):
    M = [random.randint(-32768, 32767) if random.random() < 0.5 else random.randint(-300, 300) for _ in range(512)]
    Sd = [random.randint(-4000, 4000) for _ in range(512)]
    S.test_draw(M, Sd, random.getrandbits(32), s_ % 2, 'all%d' % s_, mach=[random.choice([0, 1, 4]) for _ in range(8)],
                vnote=[random.choice([0xff, 60]) for _ in range(8)], full=(s_ // 2) % 2, lastv=(S.THIS if s_ % 5 else 0x53009999))
print("modes 0 (waveform) and 1 (X-Y): pixel-exact")
# mode 2: DRAW == SPEC alone + boxes
def state(mu, colh, pk, full, mach, vnote, cnt):
    S.ms_setup(mu, True)
    mu.mem_write(SPTR, l(BUF)); mu.mem_write(SWORK, l(BUF + 2048)); mu.mem_write(SREQ, l(1)); mu.mem_write(SREQ + 4, l(0))
    mu.mem_write(COLH, bytes(colh)); mu.mem_write(PK, bytes(pk))
    mu.mem_write(S.MODEA, l(2)); mu.mem_write(S.FULLA, l(full)); mu.mem_write(S.LASTV, l(S.THIS))
    mu.mem_write(0x400aeaa8, l(63 if full else 52))
    for t in range(8): mu.mem_write(S.Q + 0x9e + t * 0xa2, bytes([mach[t]]))
    mu.mem_write(S.QP, l(S.Q)); mu.mem_write(S.VSTATE, bytes(vnote))
    mu.mem_write(S.TRIGCNT, bytes(cnt))
    S.bitmap_setup(mu)
for s_ in range(16):
    random.seed(900 + s_)
    colh = [random.randrange(64) for _ in range(128)]; pk = [random.randrange(64) for _ in range(128)]
    full = s_ % 2; mach = [random.choice([0, 4]) for _ in range(8)]; vnote = [random.choice([0xff, 48]) for _ in range(8)]
    cnt = [random.randrange(256) for _ in range(8)] + [random.randrange(256) for _ in range(8)] + [random.choice([0, 3]) for _ in range(8)]
    a = S.dev(); state(a, colh, pk, full, mach, vnote, cnt)
    calls = []
    a.hook_add(S.UC_HOOK_CODE, lambda uc, addr, size, _: calls.append(struct.unpack('>I', uc.mem_read(uc.reg_read(UC_M68K_REG_A7) + 4, 4))[0]), begin=SPEC, end=SPEC)
    S.call(a, S.DRAW, [S.THIS, S.BMP])
    assert calls == [S.BMP], calls
    b = S.dev(); state(b, colh, pk, full, mach, vnote, cnt)
    if not full:                                                     # DRAW draws the main screen first
        S.call(b, 0x53006000, [S.THIS, S.BMP])
    S.call(b, SPEC, [S.BMP])
    pa, pb = S.bitmap_read(a), S.bitmap_read(b)
    if not full:
        S.model_dots(pb, mach, vnote, True, [list(cnt[0:8]), list(cnt[8:16]), list(cnt[16:24])])
    for y in range(64):
        for x in range(128):
            if not full and y <= 6 and x < 32: continue              # tuner box
            assert pa[y][x] == pb[y][x], ("mode 2 pixel", s_, full, x, y)
print("mode 2 (spectrum): DRAW = SPEC + boxes, normal and fullscreen")
print("all-views page: all emulator tests passed")
