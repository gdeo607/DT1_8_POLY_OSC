#!/usr/bin/env python3
# v3n voice-start hook, end to end on the real audio-ISR code 0x40077cee..0x40077d7a (flag test, optional block,
# merge point). Stock image vs v3n image, same random registers / frame / engine memory, 0x4199e130 zero and non-zero:
# every register, the frame and all engine memory must be identical; TRIGCNT must grow by exactly the stock mask
# d3 at the merge point 0x40077d72 (both paths).  Usage: python3 emu_trig_v3n.py <stock sec3> <v3n sec3>
import struct, random, sys
from unicorn import *
from unicorn.m68k_const import *
STOCK = open(sys.argv[1], 'rb').read(); NEW = open(sys.argv[2], 'rb').read()
B = 0x40000400; START, MERGE, END = 0x40077cee, 0x40077d72, 0x40077d7a
TRIGCNT = 0x400ae280 + 16 + 2048
REGS = [UC_M68K_REG_D0 + i for i in range(8)] + [UC_M68K_REG_A0 + i for i in range(8)]
AREAS = [(0x80001800, 0x800), (0x4399d000, 0x1000), (0x4199e000, 0x1000), (0x7f000000, 0x4000)]
CMP = AREAS[:3] + [(0x7f002000, 0x2000)]   # stack: only at/above SP (below SP = scratch of the hook's jsr/saves)
def dev(img):
    mu = Uc(UC_ARCH_M68K, UC_MODE_BIG_ENDIAN); mu.ctl_set_cpu_model(UC_CPU_M68K_CFV4E)
    mu.mem_map(0x40000000, 0x280000); mu.mem_write(B, img)
    for a in (0x80000000, 0x43990000, 0x41990000): mu.mem_map(a, 0x10000)
    mu.mem_map(0x7f000000, 0x4000)
    return mu
def run(img, mem, regs, stop_at_merge=False):
    mu = dev(img)
    for a, d in mem.items(): mu.mem_write(a, d)
    for r, v in regs.items(): mu.reg_write(r, v)
    d3m = None
    if stop_at_merge:
        mu.emu_start(START, MERGE, count=100000); d3m = mu.reg_read(UC_M68K_REG_D3)
        mu.emu_start(MERGE, END, count=100000)
    else:
        mu.emu_start(START, END, count=100000)
    assert mu.reg_read(UC_M68K_REG_PC) == END
    return mu, d3m
paths = {0: 0, 1: 0}
for k in range(600):
    random.seed(k)
    mem = {a: bytes(random.getrandbits(8) for _ in range(n)) for a, n in AREAS}
    m = bytearray(mem[0x4199e000]); m[0x130:0x134] = struct.pack('>I', random.choice([0, 0, 1, random.getrandbits(32)]))
    mem[0x4199e000] = bytes(m)
    # per-voice list read by the optional block (0x8000198c..): mostly 0/1 so both branches inside it run
    m = bytearray(mem[0x80001800]); m[0x16c:0x16c + 32] = b''.join(struct.pack('>I', random.choice([0, 1, 1, 2])) for _ in range(8))
    mem[0x80001800] = bytes(m)
    regs = {r: random.getrandbits(32) for r in REGS}
    regs[UC_M68K_REG_A7] = 0x7f002000; regs[UC_M68K_REG_A6] = 0x7f003000     # sp, fp (frame read at -96..-72)
    regs[UC_M68K_REG_D3] = random.choice([0, 1, 0x80, 0xff, 0x5a, random.getrandbits(8)])
    cnt0 = bytes(random.getrandbits(8) for _ in range(8))
    s, d3m = run(STOCK, mem, regs, stop_at_merge=True)
    mu = dev(NEW)
    for a, d in mem.items(): mu.mem_write(a, d)
    mu.mem_write(TRIGCNT, cnt0)
    for r, v in regs.items(): mu.reg_write(r, v)
    mu.emu_start(START, END, count=100000); assert mu.reg_read(UC_M68K_REG_PC) == END
    for r in REGS: assert mu.reg_read(r) == s.reg_read(r), ("reg", k, r)
    for a, n_ in CMP: assert mu.mem_read(a, n_) == s.mem_read(a, n_), ("mem", k, hex(a))
    exp = bytes((cnt0[t] + ((d3m >> t) & 1)) & 0xff for t in range(8))
    assert bytes(mu.mem_read(TRIGCNT, 8)) == exp, ("counts", k, hex(d3m))
    paths[1 if struct.unpack('>I', mem[0x4199e000][0x130:0x134])[0] else 0] += 1
print("v3n trig hook: 600 ISR runs identical to stock (flag clear %d, set %d), counts = stock start mask" % (paths[0], paths[1]))
