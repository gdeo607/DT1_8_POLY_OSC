#!/usr/bin/env python3
# Unicorn (ColdFire V4e) test of the Build B "internal MIDI cable" hook (cable.s) patched over 0x400e0dda.
# Runs the REAL OS 1.53 image; only the message allocator (0x400ee036) and poster (0x400ee296) are
# replaced by stubs that behave like the originals (alloc clears 0/0x28/0x2c/0x44/0x48 of a junk-filled
# 0x4c block; post records the message) and clobber the ABI scratch registers.
# Usage: python3 emu_cable.py <section_3.bin> <cable.bin>
import struct, random, sys, os
from unicorn import *
from unicorn.m68k_const import *

IMG = open(sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser('~/w/os.bin'), 'rb').read()
HOOK = open(sys.argv[2] if len(sys.argv) > 2 else os.path.expanduser('~/w/cable.bin'), 'rb').read()
BASE = 0x40000400
HK = 0x400b8e60
ENTRY = 0x400e0dda
ALLOC, POST = 0x400ee036, 0x400ee296
Q = 0x50000000; PSEQ = 0x50100000
PAT_BASE = 0x409bac18
RX = 0x4197b700
OUTLEN, OUTBUF = 0x421b5620, 0x421b5621
POOL = 0x52000000; POOLNEXT = 0x51000000; LOG = 0x51000004; LOGBUF = 0x51000100
STK = 0x7f000000
STATE = HK + (len(HOOK) - 52)

def asm_stub(hexs): return bytes.fromhex(hexs)
# alloc stub: d0 = *POOLNEXT; *POOLNEXT += 0x4c; clear fields like the real 0x400ee036; clobber d1/a1
ALLOC_STUB = (
    "20395100000"[:0] +  # placeholder removed below
    "")
def l(x): return struct.pack('>I', x & 0xffffffff)
def w(x): return struct.pack('>H', x & 0xffff)
ALLOC_STUB = (bytes.fromhex("2079") + l(POOLNEXT) +          # movea.l POOLNEXT,a0
              bytes.fromhex("2008") +                       # move.l a0,d0
              bytes.fromhex("43e8004c") +                   # lea 0x4c(a0),a1
              bytes.fromhex("23c9") + l(POOLNEXT) +         # move.l a1,POOLNEXT
              bytes.fromhex("4290") +                       # clr.l (a0)
              bytes.fromhex("42a80028") + bytes.fromhex("42a8002c") +
              bytes.fromhex("42a80044") + bytes.fromhex("42a80048") +
              bytes.fromhex("223c") + l(0xdead0001) +       # move.l #junk,d1
              bytes.fromhex("227c") + l(0xdead0002) +       # movea.l #junk,a1
              bytes.fromhex("4e75"))
POST_STUB = (bytes.fromhex("202f0004") +                    # move.l 4(sp),d0
             bytes.fromhex("2079") + l(LOG) +               # movea.l LOG,a0
             bytes.fromhex("20c0") +                        # move.l d0,(a0)+
             bytes.fromhex("23c8") + l(LOG) +               # move.l a0,LOG
             bytes.fromhex("203c") + l(0xdead0003) +
             bytes.fromhex("223c") + l(0xdead0004) +
             bytes.fromhex("207c") + l(0xdead0005) +
             bytes.fromhex("227c") + l(0xdead0006) +
             bytes.fromhex("4e75"))
NULL_ALLOC = bytes.fromhex("70004e75")                      # moveq #0,d0 ; rts

ALLREGS = [UC_M68K_REG_D0 + i for i in range(8)] + [UC_M68K_REG_A0 + i for i in range(7)]

class Dev:
    def __init__(self, patched=True, null_alloc=False):
        mu = Uc(UC_ARCH_M68K, UC_MODE_BIG_ENDIAN)
        mu.ctl_set_cpu_model(UC_CPU_M68K_CFV4E)
        mu.mem_map(0x40000000, 0x280000)
        img = bytearray(IMG)
        def put(a, bs): img[a - BASE:a - BASE + len(bs)] = bs
        put(ALLOC, NULL_ALLOC if null_alloc else ALLOC_STUB)
        put(POST, POST_STUB)
        jmp = bytes.fromhex("4ef9") + l(HK)
        if img[ENTRY - BASE:ENTRY - BASE + 6] == jmp:      # already-built v3 image: check it carries this hook
            assert bytes(img[HK - BASE:HK - BASE + len(HOOK)]) == HOOK, "image hook bytes differ from cable.bin"
            if not patched: put(ENTRY, bytes.fromhex("73b9421b5620"))   # reference = original function
        else:
            assert img[ENTRY - BASE:ENTRY - BASE + 6].hex() == "73b9421b5620"
            if patched:
                put(HK, HOOK)
                put(ENTRY, jmp)
        mu.mem_write(BASE, bytes(img))
        mu.mem_map(0x40900000, 0x200000)   # pattern array
        mu.mem_map(0x41970000, 0x40000)    # rx channels, Q/P pointers
        mu.mem_map(0x421b0000, 0x20000)    # MIDI out buffer
        mu.mem_map(Q, 0x10000); mu.mem_map(PSEQ, 0x40000)
        mu.mem_map(0x51000000, 0x10000); mu.mem_map(POOL, 0x100000)
        mu.mem_map(STK, 0x2000)
        self.mu = mu
        self.patched = patched

    def setup(self, rx, machines, flagwords, pat_idx=3, qptr=Q):
        mu = self.mu
        for t in range(16): mu.mem_write(RX + 4 * t, l(rx[t]))
        for t in range(8): mu.mem_write(Q + 0x20 + t * 0xa2 + 0x7e, bytes([machines[t]]))
        mu.mem_write(0x4199dc44, l(qptr))
        mu.mem_write(0x4199dc38, l(PSEQ))
        mu.mem_write(PSEQ + 0x1ec64, l(pat_idx))
        pb = PAT_BASE + pat_idx * 0x1ec68
        for t in range(16): mu.mem_write(pb + t * 0x38f + 0x382, w(flagwords[t]))
        mu.mem_write(OUTLEN, b'\0')
        mu.mem_write(POOLNEXT, l(POOL)); mu.mem_write(LOG, l(LOGBUF))
        mu.mem_write(POOL, bytes([0xa5]) * 0x10000)

    def send(self, bs):
        mu = self.mu
        mu.mem_write(LOG, l(LOGBUF))
        mu.mem_write(0x51000200, bytes(bs) + b'\0' * 4)
        ret = 0x40000500  # any address; we stop there
        sp = STK + 0x1000
        mu.mem_write(sp, l(ret) + l(len(bs)) + l(0x51000200))
        mu.reg_write(UC_M68K_REG_A7, sp)
        regs = {r: random.getrandbits(32) for r in ALLREGS}
        for r, v in regs.items(): mu.reg_write(r, v)
        mu.emu_start(ENTRY, ret, count=20000)
        assert mu.reg_read(UC_M68K_REG_PC) == ret, hex(mu.reg_read(UC_M68K_REG_PC))
        assert mu.reg_read(UC_M68K_REG_A7) == sp + 4
        out = {r: mu.reg_read(r) for r in ALLREGS}
        logp = struct.unpack('>I', mu.mem_read(LOG, 4))[0]
        msgs = [struct.unpack('>I', mu.mem_read(a, 4))[0] for a in range(LOGBUF, logp, 4)]
        return regs, out, [self.msg(m) for m in msgs]

    def msg(self, m):
        g = lambda o: struct.unpack('>I', self.mu.mem_read(m + o, 4))[0]
        return dict(kind=g(4), src=g(0xc), voice=g(8), vel=struct.unpack('>H', self.mu.mem_read(m + 0x14, 2))[0],
                    note=g(0x18), p28=g(0x28), lock=g(0x2c), flags=g(0x24), p44=g(0x44), len=g(0x30), m0=g(0), m48=g(0x48))

    def outbuf(self):
        n = self.mu.mem_read(OUTLEN, 1)[0]
        return bytes(self.mu.mem_read(OUTBUF, n))

    def state(self):
        s = self.mu.mem_read(STATE, 52)
        return list(s[0:8]), list(s[8:16]), list(struct.unpack('>8I', s[16:48])), struct.unpack('>I', s[48:52])[0]

# ---------------- Python reference model ----------------
class Model:
    def __init__(self):
        self.vnote = [0xff] * 8; self.vch = [0xff] * 8; self.age = [0] * 8; self.clock = 0
    def step(self, bs, rx, machines, flagwords, qptr=Q, alloc_ok=True):
        out = []
        if len(bs) != 3 or (bs[0] & 0xe0) != 0x80 or qptr == 0: return out
        ch, note, vel = bs[0] & 15, bs[1], bs[2]
        if not (bs[0] & 0x10): vel = 0
        group = [t for t in range(8) if rx[t] == ch and machines[t] == 4]
        if not group: return out
        c = group[0]
        if vel:
            if not (12 <= note <= 84): return out
            def key(t): return (self.age[t] if self.vnote[t] == 0xff else self.age[t] + 0x80000000) & 0xffffffff
            best = None
            for t in group:
                k = key(t)
                if k != 0xffffffff and (best is None or k < key(best)): best = t
            if best is None: return out
            self.clock += 1; self.age[best] = self.clock; self.vnote[best] = note; self.vch[best] = ch
            fw = flagwords[c]; fw = fw - 0x10000 if fw & 0x8000 else fw
            if alloc_ok:
                out.append(dict(kind=1, src=2, voice=best, vel=vel << 8, note=note, p28=0, lock=qptr + 0x20 + c * 0xa2,
                                flags=(fw | 0x10001) & 0xffffffff, p44=0, len=0, m0=0, m48=0))
        else:
            for t in range(8):
                if t in group and self.vnote[t] == note and self.vch[t] == ch:
                    self.vnote[t] = 0xff
                    if alloc_ok:
                        out.append(dict(kind=2, src=2, voice=t, vel=0, note=note, p28=0, lock=0, flags=0, p44=0, len=0, m0=0, m48=0))
                    break
        return out

def check_equiv(dev, ref, bs, rx, machines, fws, qptr=Q, alloc_ok=True, model=None):
    regs, out, msgs = dev.send(bs)
    rregs, rout, _ = ref.send(bs) if False else (None, None, None)
    exp = model.step(bs, rx, machines, fws, qptr, alloc_ok) if model else []
    assert msgs == exp, ("MSG MISMATCH", bytes(bs).hex(), msgs, exp)
    return regs, out

def run_pair(bs_list, rx, machines, fws, qptr=Q, null_alloc=False, seed=0):
    random.seed(seed)
    dev = Dev(True, null_alloc); dev.setup(rx, machines, fws, qptr=qptr)
    ref = Dev(False, null_alloc); ref.setup(rx, machines, fws, qptr=qptr)
    model = Model()
    for bs in bs_list:
        random.seed(hash((seed, bytes(bs))))
        regs, out, msgs = dev.send(bs)
        random.seed(hash((seed, bytes(bs))))
        rregs, rout, rmsgs = ref.send(bs)
        assert regs == rregs
        # the hook must be invisible to the caller: identical registers and MIDI-out bytes as the pristine function
        assert out == rout, ("REG DIFF", bytes(bs).hex(), {hex(k): (hex(out[k]), hex(rout[k])) for k in out if out[k] != rout[k]})
        assert dev.outbuf() == ref.outbuf(), ("OUTBUF DIFF", dev.outbuf().hex(), ref.outbuf().hex())
        exp = model.step(bs, rx, machines, fws, qptr, not null_alloc)
        assert msgs == exp, ("MSG MISMATCH", bytes(bs).hex(), msgs, exp)
        vn, vc, ag, ck = dev.state()
        assert vn == model.vnote and ag == model.age and ck == model.clock, ("STATE", vn, model.vnote, ag, model.age)
        dev.mu.mem_write(OUTLEN, b'\0'); ref.mu.mem_write(OUTLEN, b'\0')
    return dev, model

def on(ch, n, v=100): return [0x90 | ch, n, v]
def off(ch, n): return [0x90 | ch, n, 0]
def off8(ch, n): return [0x80 | ch, n, 64]

if __name__ == '__main__':
    OFF = 0xffffffff
    rx = [0, 1, 2, 3, 4, 4, 4, 4] + [8 + i for i in range(8)]
    mach = [0, 0, 0, 0, 4, 4, 4, 4]
    fws = [0x0080 + t for t in range(16)]
    fws[4] = 0x8283   # control word with bit15 -> sign extension path

    # 1. directed: 4 notes -> voices 4..7 in order, control = 4, lock = control block
    dev, m = run_pair([on(4, 60), on(4, 64), on(4, 67), on(4, 71)], rx, mach, fws)
    assert m.vnote[4:8] == [60, 64, 67, 71]
    # 2. steal oldest, release by note, free voice preferred, 0x8n off, unknown off, range, other channel, non-note
    seq = [on(4, 60), on(4, 64), on(4, 67), on(4, 71), on(4, 72),       # 72 steals voice 4 (oldest)
           off(4, 64), on(4, 74),                                       # 74 -> freed voice 5 (not busy 6)
           off8(4, 67), off(4, 99), off(4, 60),                         # 60 was stolen -> no message
           on(4, 11), on(4, 85), on(4, 12), on(4, 84),                  # range edges
           on(3, 60), on(5, 60), [0xb4, 1, 2], [0xc4, 5], [0xf8], [0x94, 60],
           off(4, 72), off(4, 74), off(4, 71), off(4, 12), off(4, 84)]
    dev, m = run_pair(seq, rx, mach, fws, seed=1)
    # 3. group edge cases: rx match but machine != POLY, POLY but other channel, single voice group, control not first
    rx2 = [7, 7, 9, 7, 7, 2, 7, 7] + [7] * 8          # MIDI tracks 8..15 also on 7: must be ignored (audio only)
    mach2 = [0, 4, 4, 2, 4, 4, 1, 4]                    # group on ch7 = {1,4,7}; control = 1
    run_pair([on(7, 50), on(7, 52), on(7, 55), on(7, 57), off(7, 52), on(7, 59), off(7, 50)], rx2, mach2, fws, seed=2)
    run_pair([on(9, 40), on(9, 41), off(9, 40), off(9, 41)], rx2, mach2, fws, seed=3)   # single-voice group {2}
    # 4. Q pointer null, alloc failure
    run_pair([on(4, 60), off(4, 60)], rx, mach, fws, qptr=0, seed=4)
    run_pair([on(4, 60), on(4, 62), off(4, 60), off(4, 62)], rx, mach, fws, null_alloc=True, seed=5)
    # 5. random fuzz against the model, random groups and channels
    for s in range(40):
        random.seed(1000 + s)
        rxr = [random.choice([0, 1, 2, 3, OFF]) for _ in range(16)]
        mr = [random.choice([0, 1, 2, 3, 4, 4, 4]) for _ in range(8)]
        fr = [random.getrandbits(16) for _ in range(16)]
        seq = []
        for _ in range(120):
            k = random.random()
            ch = random.choice([0, 1, 2, 3])
            n = random.choice([5, 11, 12, 36, 48, 60, 61, 62, 64, 67, 84, 85, 127])
            if k < 0.45: seq.append(on(ch, n, random.randint(1, 127)))
            elif k < 0.8: seq.append(off(ch, n))
            elif k < 0.9: seq.append(off8(ch, n))
            else: seq.append(random.choice([[0xb0 | ch, 7, 99], [0xc0 | ch, 3], [0xf8], [0x90 | ch, n]]))
        run_pair(seq, rxr, mr, fr, seed=1000 + s)
    print("cable hook: all emulator tests passed")
