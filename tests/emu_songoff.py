#!/usr/bin/env python3
# Unicorn test for songoff.s (v3g): runs the REAL project-settings song-mode getter 0x4001d8a8 and setter
# 0x4001d842 with and without the patch, stored values / requested modes -5..6 and huge values.
# Expected: getter returns stock clamp (0..2) except 1 -> 0; setter stores stock clamp except 1 -> 0,
# still notifies exactly as stock; callee-saved registers preserved.
# Usage: python3 emu_songoff.py <section_3.bin> <songoff.bin>
import struct, random, sys
from unicorn import *
from unicorn.m68k_const import *
IMG = open(sys.argv[1], 'rb').read(); FIXB = open(sys.argv[2], 'rb').read()
B = 0x40000400; GET, SET, FIX = 0x4001d8a8, 0x4001d842, 0x400b91c4
def l(x): return struct.pack('>I', x & 0xffffffff)
ALL = [UC_M68K_REG_D0 + i for i in range(8)] + [UC_M68K_REG_A0 + i for i in range(7)]
OBJ, VT, DATA, LOG = 0x50000000, 0x50000100, 0x50000200, 0x50000400
# vtable slot 10 (+0x28): return DATA ; slot 4 (+0x10): notify -> log (obj, event vtable)
S_DATA = bytes.fromhex("203c") + l(DATA) + bytes.fromhex("4e75")
S_NOTE = (bytes.fromhex("206f0008") + bytes.fromhex("23d0") + l(LOG) +      # move.l (8(sp)) -> LOG : event vtable
          bytes.fromhex("23ef0004") + l(LOG + 4) + bytes.fromhex("4e75"))    # obj
def dev(patched):
    img = bytearray(IMG)
    def put(a, bs): img[a - B:a - B + len(bs)] = bs
    g = bytes(img[0x4001d8cc - B:0x4001d8cc - B + 14]); s = bytes(img[0x4001d878 - B:0x4001d878 - B + 8])
    pg = bytes.fromhex("22280028") + bytes.fromhex("4eb9") + l(FIX) + bytes.fromhex("20016004")
    ps = bytes.fromhex("4eb9") + l(FIX) + bytes.fromhex("4e71")
    og, os_ = bytes.fromhex("20286d0a7202b2806c0670026002")[:14], bytes.fromhex("7402b4816c027202")
    og = bytes.fromhex("202800286d0a7202b2806c067002")   # original 14 bytes at 0x4001d8cc
    if patched:
        if g != pg: assert g == og; put(0x4001d8cc, pg)
        if s != ps: assert s == os_; put(0x4001d878, ps)
        put(FIX, FIXB) if bytes(img[FIX - B:FIX - B + len(FIXB)]) != FIXB else None
    else:
        put(0x4001d8cc, og); put(0x4001d878, os_)
    mu = Uc(UC_ARCH_M68K, UC_MODE_BIG_ENDIAN); mu.ctl_set_cpu_model(UC_CPU_M68K_CFV4E)
    mu.mem_map(0x40000000, 0x280000); mu.mem_write(B, bytes(img))
    mu.mem_map(0x50000000, 0x10000); mu.mem_map(0x7f000000, 0x2000)
    mu.mem_write(OBJ, l(VT)); mu.mem_write(VT + 0x28, l(0x50001000)); mu.mem_write(VT + 0x10, l(0x50001100))
    mu.mem_write(0x50001000, S_DATA); mu.mem_write(0x50001100, S_NOTE)
    return mu
def call(mu, fn, args, seed):
    ret = 0x40000500; sp = 0x7f001000
    mu.mem_write(sp, l(ret) + b''.join(l(a) for a in args)); mu.reg_write(UC_M68K_REG_A7, sp)
    random.seed(seed); regs = {r: random.getrandbits(32) for r in ALL}
    for r, v in regs.items(): mu.reg_write(r, v)
    mu.emu_start(fn, ret, count=10000)
    assert mu.reg_read(UC_M68K_REG_PC) == ret and mu.reg_read(UC_M68K_REG_A7) == sp + 4
    out = {r: mu.reg_read(r) for r in ALL}
    for r in ALL[2:8] + ALL[10:15]: assert regs[r] == out[r], ("reg", fn, r)
    return out
def s32(x): return x - (1 << 32) if x & 0x80000000 else x
vals = list(range(-5, 7)) + [0x7fffffff, -0x80000000, 1000]
for v in vals:
    res = []
    for patched in (False, True):
        mu = dev(patched)
        mu.mem_write(DATA + 0x28, l(v))
        g = s32(call(mu, GET, [OBJ], v)[UC_M68K_REG_D0])
        mu.mem_write(LOG, l(0) + l(0))
        call(mu, SET, [OBJ, v], v + 1)
        stored = s32(struct.unpack('>I', mu.mem_read(DATA + 0x28, 4))[0]); note = struct.unpack('>II', mu.mem_read(LOG, 8))
        res.append((g, stored, note))
    (g0, s0, n0), (g1, s1, n1) = res
    assert g0 == max(0, min(2, v)) and s0 == max(0, min(2, v)), (v, g0, s0)
    assert g1 == (0 if g0 == 1 else g0) and s1 == (0 if s0 == 1 else s0), (v, g1, s1)
    assert n1 == n0 and n0[0] == 0x40180694 and n0[1] == OBJ, (v, n0, n1)
print("song-mode block: getter/setter pass for", len(vals), "values (1 -> 0, 0/2 and clamping unchanged, notify unchanged)")
