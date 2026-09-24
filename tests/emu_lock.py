#!/usr/bin/env python3
# Unicorn (ColdFire V4e) test of lock.s (POLY v3e: per-voice TUNE + LFO). Runs the REAL engine param load
# 0x40077282 (+ real memcpy, machine copy, 0x400749cc expansion) with and without the tail patch, on
# random kit blocks, and checks the patched result = original result with slots 1..0x11 of the voice's
# own block written into both per-voice copies exactly when: voice 0..7, loaded block is another kit
# track's block (Q-based or engine-base), own track machine == 4. Otherwise byte-identical to the original.
# Usage: python3 emu_lock.py <section_3.bin> <lock.bin> [hook address hex, default 400ac4d4 (v3e); v3f: 400ac4ec]
import struct, random, sys
from unicorn import *
from unicorn.m68k_const import *
IMG = open(sys.argv[1], 'rb').read(); HOOK = open(sys.argv[2], 'rb').read()
B = 0x40000400; LOAD = 0x40077282; TAIL = 0x400772e0; POST = int(sys.argv[3], 16) if len(sys.argv) > 3 else 0x400ac4d4
Q = 0x50000000; E = 0x50010000; POOL = 0x50020000; STK = 0x7f000000
def l(x): return struct.pack('>I', x & 0xffffffff)
ALL = [UC_M68K_REG_D0 + i for i in range(8)] + [UC_M68K_REG_A0 + i for i in range(7)]

def dev(patched):
    mu = Uc(UC_ARCH_M68K, UC_MODE_BIG_ENDIAN); mu.ctl_set_cpu_model(UC_CPU_M68K_CFV4E)
    mu.mem_map(0x40000000, 0x280000)
    img = bytearray(IMG)
    def put(a, bs): img[a - B:a - B + len(bs)] = bs
    jmp = bytes.fromhex("4ef9") + l(POST)
    cur = bytes(img[TAIL - B:TAIL - B + 6])
    if cur == jmp:
        assert bytes(img[POST - B:POST - B + len(HOOK)]) == HOOK
        if not patched: put(TAIL, bytes.fromhex("4ef9400749cc"))
    else:
        assert cur.hex() == "4ef9400749cc"
        if patched: put(POST, HOOK); put(TAIL, jmp)
    mu.mem_write(B, bytes(img))
    mu.mem_map(0x41990000, 0x10000); mu.mem_map(0x80000000, 0x10000)
    mu.mem_map(Q, 0x30000); mu.mem_map(STK, 0x2000)
    return mu

def run(mu, ptr, voice, seed):
    ret = 0x40000500; sp = STK + 0x1000
    mu.mem_write(sp, l(ret) + l(ptr) + l(voice)); mu.reg_write(UC_M68K_REG_A7, sp)
    random.seed(seed); regs = {r: random.getrandbits(32) for r in ALL}
    for r, v in regs.items(): mu.reg_write(r, v)
    mu.emu_start(LOAD, ret, count=100000)
    assert mu.reg_read(UC_M68K_REG_PC) == ret and mu.reg_read(UC_M68K_REG_A7) == sp + 4
    return regs, {r: mu.reg_read(r) for r in ALL}

def state(mu): return bytes(mu.mem_read(0x80000000, 0x10000))

def case(seed, qset=True, eset=True):
    random.seed(seed)
    blocks = {base: bytes(random.getrandbits(8) for _ in range(0x20 + 8 * 0xa2 + 64)) for base in (Q, E)}
    pool = bytes(random.getrandbits(8) for _ in range(0x400))
    mach = [random.choice([0, 1, 4, 4]) for _ in range(8)]
    sram = bytes(random.getrandbits(8) for _ in range(0x4000))
    base = random.choice([Q, E, POOL])
    src_t = random.randrange(8); voice = random.choice([random.randrange(8), random.randrange(8), 8, 15])
    ptr = base + 0x20 + src_t * 0xa2 if base != POOL else POOL + 0x20 + random.randrange(4) * 0xa2
    if random.random() < 0.15 and voice < 8 and base != POOL: ptr = base + 0x20 + voice * 0xa2   # own block
    out = []
    for patched in (True, False):
        mu = dev(patched)
        for bb, blk in blocks.items():
            bl = bytearray(blk)
            for t in range(8): bl[0x20 + t * 0xa2 + 0x7e] = mach[t]
            mu.mem_write(bb, bytes(bl))
        mu.mem_write(POOL, pool)
        mu.mem_write(0x4199dc44, l(Q if qset else 0)); mu.mem_write(0x80000000, sram)
        mu.mem_write(0x800019ac, l(E if eset else 0))
        r, o = run(mu, ptr, voice, seed)
        out.append((mu, r, o))
    (mp, rp, op), (mo, ro, oo) = out
    for reg in ALL[2:8] + ALL[10:15]: assert op[reg] == oo[reg], ("callee-saved reg changed", seed, reg)
    sp_, so = bytearray(state(mp)), bytearray(state(mo))
    exp = bytearray(so)
    patch = False
    if voice < 8:
        for bb in ([Q] if qset else []) + ([E] if eset else []):
            lo = bb + 0x20
            if lo <= ptr < lo + 8 * 0xa2:
                own = lo + voice * 0xa2
                if ptr != own and mp.mem_read(own + 0x7e, 1)[0] == 4:
                    ob = mp.mem_read(own, 0xa2)
                    for s in range(1, 0x12):
                        w = ob[0x14 + 2 * s:0x16 + 2 * s]
                        o16 = 0x1502 + voice * 0x6a + 2 * s; o32 = 0x2b50 + voice * 0xd4 + 4 * s
                        exp[o16:o16 + 2] = w; exp[o32:o32 + 4] = bytes(w) + b'\0\0'
                    patch = True
                break
    assert sp_ == exp, ("engine state mismatch", seed, hex(ptr), voice, patch)
    return patch

if __name__ == '__main__':
    n = sum(case(s, qset=(s % 7 != 0), eset=(s % 11 != 0)) for s in range(400))
    print("per-voice tune/LFO: 400 cases pass (%d patched, %d untouched)" % (n, 400 - n))
