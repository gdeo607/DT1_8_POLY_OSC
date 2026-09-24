#!/usr/bin/env python3
# Unicorn (ColdFire V4e) tests for the v3d/v3f additions (KEY = v3f semantics):
#  CC  : cc.s entry-patched over 0x400e0b84 (MIDI task CC buffer append). Must be invisible to the caller
#        (same registers, same CC-out bytes as the original) and call 0x400d6a58(t, cc, val, 0, 0) for each
#        POLY track t (ascending) whose receive channel == channel, for 3-byte 0xBn with cc < 120.
#  (the scope KEY tests live in emu_scope.py)  old: scope.s KEY (SongEditView vtable slot 2): id 5 -> close on press edge, consumed; id 6 -> original
#        SongEditView handler (tail call); everything else -> MainScreenView (singleton 0x421f9b50) handler
#        with (mainscreen, event), its result returned; no main screen -> consumed, nothing called.
# Usage: python3 emu_cc.py <patched section_3.bin> <cc.bin>
import struct, random, sys, os
from unicorn import *
from unicorn.m68k_const import *

IMG = open(sys.argv[1], 'rb').read()
CCB = open(sys.argv[2], 'rb').read()
B = 0x40000400
CCHK, CCENTRY, TRACKCC = 0x400b9110, 0x400e0b84, 0x400d6a58
SCOPE, OLDKEY = 0x400abe9c, 0x400ac8f0
def sym(o):
    r = {}
    for ln in os.popen('m68k-linux-gnu-nm ' + o).read().split('\n'):
        p = ln.split()
        if len(p) == 3 and p[1] == 't': r[p[2]] = int(p[0], 16)
    return r
Q = 0x50000000; RX = 0x4197b700; OUTLEN, OUTBUF = 0x421b5a21, 0x421b5a22
LOG = 0x51000000; STK = 0x7f000000
def l(x): return struct.pack('>I', x & 0xffffffff)
ALL = [UC_M68K_REG_D0 + i for i in range(8)] + [UC_M68K_REG_A0 + i for i in range(7)]

# logging stub: append 5 stack args to LOG ring (ptr at LOG), clobber d0/d1/a0/a1
LOGSTUB = (bytes.fromhex("2079") + l(LOG) +                 # movea.l LOG,a0
           bytes.fromhex("20ef0004") + bytes.fromhex("20ef0008") + bytes.fromhex("20ef000c") +
           bytes.fromhex("20ef0010") + bytes.fromhex("20ef0014") +   # move.l n(sp),(a0)+
           bytes.fromhex("23c8") + l(LOG) +
           bytes.fromhex("203c") + l(0x77) + bytes.fromhex("223c") + l(0xdead0001) +
           bytes.fromhex("207c") + l(0xdead0002) + bytes.fromhex("227c") + l(0xdead0003) + bytes.fromhex("4e75"))

def dev(patch_cc=True, patch_key=True):
    mu = Uc(UC_ARCH_M68K, UC_MODE_BIG_ENDIAN); mu.ctl_set_cpu_model(UC_CPU_M68K_CFV4E)
    mu.mem_map(0x40000000, 0x280000)
    img = bytearray(IMG)
    def put(a, bs): img[a - B:a - B + len(bs)] = bs
    jmp = bytes.fromhex("4ef9") + l(CCHK)
    cur = bytes(img[CCENTRY - B:CCENTRY - B + 6])
    if cur == jmp:
        assert bytes(img[CCHK - B:CCHK - B + len(CCB)]) == CCB
        if not patch_cc: put(CCENTRY, bytes.fromhex("73b9421b5a21"))
    else:
        assert cur.hex() == "73b9421b5a21"
        if patch_cc: put(CCHK, CCB); put(CCENTRY, jmp)
    put(TRACKCC, LOGSTUB); put(OLDKEY, LOGSTUB)
    mu.mem_write(B, bytes(img))
    mu.mem_map(0x41970000, 0x40000); mu.mem_map(0x421b0000, 0x10000)
    mu.mem_map(Q, 0x10000); mu.mem_map(0x421f0000, 0x10000); mu.mem_map(0x51000000, 0x10000); mu.mem_map(0x52000000, 0x10000); mu.mem_map(STK, 0x2000)
    return mu

def run(mu, fn, args, seed):
    mu.mem_write(LOG, l(LOG + 0x100))
    ret = 0x40000500; sp = STK + 0x1000
    mu.mem_write(sp, l(ret) + b''.join(l(a) for a in args))
    mu.reg_write(UC_M68K_REG_A7, sp)
    random.seed(seed); regs = {r: random.getrandbits(32) for r in ALL}
    for r, v in regs.items(): mu.reg_write(r, v)
    mu.emu_start(fn, ret, count=100000)
    assert mu.reg_read(UC_M68K_REG_PC) == ret and mu.reg_read(UC_M68K_REG_A7) == sp + 4
    lp = struct.unpack('>I', mu.mem_read(LOG, 4))[0]
    logs = [struct.unpack('>5I', mu.mem_read(a, 20)) for a in range(LOG + 0x100, lp, 20)]
    return regs, {r: mu.reg_read(r) for r in ALL}, logs

def setup(mu, rx, mach, qptr=Q):
    for t in range(16): mu.mem_write(RX + 4 * t, l(rx[t]))
    for t in range(8): mu.mem_write(Q + 0x9e + t * 0xa2, bytes([mach[t]]))
    mu.mem_write(0x4199dc44, l(qptr)); mu.mem_write(OUTLEN, b'\0')

def test_cc(seq, rx, mach, qptr=Q, seed=0):
    a = dev(True); b = dev(False)
    for m in (a, b): setup(m, rx, mach, qptr)
    for k, bs in enumerate(seq):
        for m in (a, b): m.mem_write(0x52000000, bytes(bs) + b'\0' * 4)
        r1, o1, lg = run(a, CCENTRY, [len(bs), 0x52000000], seed * 1000 + k)
        r2, o2, lg2 = run(b, CCENTRY, [len(bs), 0x52000000], seed * 1000 + k)
        assert lg2 == []
        assert o1 == o2, ("CC hook not transparent", bytes(bs).hex())
        n1 = a.mem_read(OUTLEN, 1)[0]; n2 = b.mem_read(OUTLEN, 1)[0]
        assert n1 == n2 and a.mem_read(OUTBUF, n1) == b.mem_read(OUTBUF, n2)
        exp = []
        if len(bs) == 3 and (bs[0] & 0xf0) == 0xb0 and bs[1] < 120 and qptr:
            exp = [(t, bs[1], bs[2], 0, 0) for t in range(8) if rx[t] == (bs[0] & 15) and mach[t] == 4]
        assert [tuple(x) for x in lg] == exp, ("CC calls", bytes(bs).hex(), lg, exp)
        for m in (a, b): m.mem_write(OUTLEN, b'\0')

if __name__ == '__main__':
    rx = [0, 1, 2, 3, 4, 4, 4, 4] + [4] * 8
    mach = [0, 0, 4, 0, 4, 4, 4, 4]
    seq = [[0xb4, 74, 64], [0xb4, 7, 127], [0xb4, 119, 1], [0xb4, 120, 0], [0xb4, 123, 0], [0xb2, 74, 3],
           [0xb3, 74, 3], [0x94, 60, 100], [0xc4, 5], [0xb4, 74], [0xb4, 74, 64, 0], [0xf8]]
    test_cc(seq, rx, mach)
    test_cc([[0xb4, 74, 64]], rx, mach, qptr=0)
    for s in range(30):
        random.seed(500 + s)
        rxr = [random.choice([0, 1, 2, 0xffffffff]) for _ in range(16)]
        mr = [random.choice([0, 1, 4, 4]) for _ in range(8)]
        sq = [[0xb0 | random.randint(0, 3), random.choice([0, 1, 7, 74, 94, 98, 99, 6, 38, 119, 120, 127]), random.randint(0, 127)]
              if random.random() < 0.8 else [random.choice([0x90, 0x80, 0xc0, 0xe0]) | random.randint(0, 3), 60, 1]
              for _ in range(40)]
        test_cc(sq, rxr, mr, seed=s + 1)
    print("CC cable hook: all emulator tests passed")
