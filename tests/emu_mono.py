#!/usr/bin/env python3
"""Digi Mono's engine built for the Digitakt's CPU, run on an emulated ColdFire V4e.

    python3 tests/emu_mono.py            (needs m68k-linux-gnu-gcc/ld/nm, gcc, unicorn, numpy)

1. Builds mods/digimono/mono.c with elekloader's flags for the Digitakt mk1 (-mcpu=54455 -O2
   -ffreestanding ...), and checks the object needs nothing from outside (no libgcc, no memset).
2. Bit-exact: many random voices (machine, parameters, pitch, block sizes, re-trigs) rendered block by
   block on the emulated ColdFire and by the PC build (tests/mono_lib.py): every sample and the voice
   state after every block must be the same. So what tests/mono_signal.py measures is what the unit plays.
3. Cost: instructions per 32-frame block for each machine at light and at heavy settings. The stock
   render runs about 84,000 instructions a block (docs/TECHNICAL_NOTES.md, Digi Matrix); the block is
   0.67 ms, 166,667 cycles at 250 MHz.
No firmware is needed: the engine is self-contained.
"""
import ctypes, os, random, struct, subprocess, sys, tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mono_lib as H
from unicorn import Uc, UC_ARCH_M68K, UC_MODE_BIG_ENDIAN, UC_HOOK_CODE
from unicorn.m68k_const import *

CFLAGS = ["-mcpu=54455", "-O2", "-ffreestanding", "-fno-builtin", "-nostdlib", "-fno-pic", "-fno-pie",
          "-fomit-frame-pointer", "-Wall", "-Werror"]
TEXT = 0x40100000
RAM, RAMSZ = 0x47b00000, 0x00100000
STACK = RAM + 0xf0000
SENT = RAM + 0x100                     # return address: emulation stops here
VOICE, PRM, OUT = RAM + 0x1000, RAM + 0x2000, RAM + 0x3000
FAIL = []


def check(ok, what):
    print(("  ok    " if ok else "  FAIL  ") + what)
    if not ok:
        FAIL.append(what)


def build():
    work = tempfile.mkdtemp(prefix="digimono_cf_")
    obj, elf, binf = (os.path.join(work, n) for n in ("mono.o", "mono.elf", "mono.bin"))
    subprocess.check_call(["m68k-linux-gnu-gcc"] + CFLAGS + ["-c", H.SRC, "-o", obj])
    und = subprocess.check_output(["m68k-linux-gnu-nm", "-u", obj], text=True).split()
    check(not und, "the ColdFire object needs nothing from outside (undefined: %s)" % (und or "none"))
    subprocess.check_call(["m68k-linux-gnu-ld", "-Ttext=0x%x" % TEXT, "-e", "mono_render", "-o", elf, obj])
    subprocess.check_call(["m68k-linux-gnu-objcopy", "-O", "binary", elf, binf])
    syms = {}
    for line in subprocess.check_output(["m68k-linux-gnu-nm", elf], text=True).splitlines():
        a, t, n = line.split()
        syms[n] = int(a, 16)
    size = int(subprocess.check_output(["m68k-linux-gnu-size", "-A", obj], text=True)
               .split(".text")[1].split()[0])
    print("  code + tables: %d bytes" % os.path.getsize(binf))
    return open(binf, "rb").read(), syms, size


class CF:
    def __init__(self, image, syms):
        self.uc = uc = Uc(UC_ARCH_M68K, UC_MODE_BIG_ENDIAN)
        uc.ctl_set_cpu_model(UC_CPU_M68K_CFV4E)
        uc.mem_map(TEXT, (len(image) + 0xffff) & ~0xffff)
        uc.mem_write(TEXT, image)
        uc.mem_map(RAM, RAMSZ)
        uc.mem_write(SENT, b"\x4e\x71")
        self.syms = syms
        self.count = 0
        self.counting = False
        uc.hook_add(UC_HOOK_CODE, self._hook)
        self.callee = [UC_M68K_REG_D2 + i for i in range(6)] + [UC_M68K_REG_A2 + i for i in range(5)]

    def _hook(self, uc, addr, size, data):
        if self.counting:
            self.count += 1

    def call(self, fn, *args, count=False):
        uc = self.uc
        sp = STACK - 4 * (len(args) + 1)
        uc.mem_write(sp, struct.pack(">I", SENT) + b"".join(struct.pack(">I", a & 0xffffffff) for a in args))
        uc.reg_write(UC_M68K_REG_A7, sp)
        marks = [0x11110000 + i for i in range(len(self.callee))]
        for r, m in zip(self.callee, marks):
            uc.reg_write(r, m)
        self.count, self.counting = 0, count
        uc.emu_start(self.syms[fn], SENT)
        self.counting = False
        kept = all(uc.reg_read(r) == m for r, m in zip(self.callee, marks)) and uc.reg_read(UC_M68K_REG_A7) == sp + 4
        return uc.reg_read(UC_M68K_REG_D0), kept, self.count

    def init(self):
        return self.call("mono_init", VOICE)

    def trig(self, m):
        return self.call("mono_trig", VOICE, m)

    def render(self, m, prm, inc, n, count=False):
        self.uc.mem_write(PRM, bytes(prm) + b"\0")
        _, kept, cnt = self.call("mono_render", VOICE, m, PRM, inc, OUT, n, count=count)
        return self.uc.mem_read(OUT, 2 * n), kept, cnt

    def voice(self):
        return bytes(self.uc.mem_read(VOICE, H.VOICE_SIZE))


def host_render(v, m, prm, inc, n):
    p = (ctypes.c_uint8 * 7)(*prm)
    out = (ctypes.c_int16 * n)()
    H.LIB.mono_render(ctypes.byref(v), m, p, inc, out, n)
    return bytes(out)


def swap16(b):
    return b"".join(b[i + 1:i + 2] + b[i:i + 1] for i in range(0, len(b), 2))


def host_state_be(v):
    """The PC's voice state in the ColdFire's byte order (the struct's layout is the same on both)."""
    return H.swap_state(bytes(v.raw))


def main():
    print("build")
    image, syms, _ = build()
    cf = CF(image, syms)

    print("bit-exact against the PC build")
    rnd = random.Random(7)
    cases = blocks = 0
    same = kept_all = True
    for case in range(80):
        m = rnd.randrange(6) if case % 10 else 6                  # 6: out of range, must be silence
        cf.init()
        hv = H.Voice()
        H.LIB.mono_init(ctypes.byref(hv))
        prm = [rnd.randrange(128) for _ in range(7)]
        for b in range(24):
            if b % 8 == 0:
                cf.trig(m)
                H.LIB.mono_trig(ctypes.byref(hv), m)
            if rnd.random() < 0.3:
                prm[rnd.randrange(7)] = rnd.randrange(128)
            inc = H.pitch_inc(rnd.uniform(0, 130)) if rnd.random() < 0.9 else rnd.getrandbits(32)
            n = 32 if rnd.random() < 0.8 else rnd.randrange(1, 64)
            a, kept, _ = cf.render(m, prm, inc, n)
            h = host_render(hv, m, prm, inc, n)
            kept_all &= kept
            if bytes(a) != swap16(h) or cf.voice() != host_state_be(hv):
                if same:
                    print("  first difference: case %d block %d machine %d prm %s inc %#x n %d" % (case, b, m, prm, inc, n))
                same = False
            blocks += 1
        cases += 1
    check(same, "%d voices, %d blocks: every sample and the voice state equal to the PC build's" % (cases, blocks))
    check(kept_all, "d2-d7 / a2-a6 and the stack kept by every call (the C calling convention)")
    ok = all(cf.call("mono_pitch_inc", p)[0] == H.LIB.mono_pitch_inc(p) for p in range(-200, 131 * 128, 37))
    check(ok, "mono_pitch_inc equal to the PC build's over its whole range")

    print("cost: instructions per 32-frame block (note 48; the average of 16 blocks after 4)")
    setups = [
        ("SIN", H.SIN, [0] * 7, [0] * 7),
        ("NOIS", H.NOIS, [0] * 7, [64, 64, 64, 0, 0, 0, 0]),
        ("SAW", H.SAW, [0] * 7, [127, 127, 127, 0, 64, 127, 127]),
        ("PULS", H.PULS, [0, 0, 0, 0, 64, 0, 0], [127, 64, 127, 127, 64, 127, 64]),
        ("ENS", H.ENS, [63, 63, 63, 0, 64, 0, 0], [67, 70, 75, 64, 64, 127, 127]),
        ("VO", H.VO, [42, 113, 64, 0, 0, 40, 100], [42, 113, 64, 64, 20, 127, 127]),
    ]
    inc = H.pitch_inc(48)
    worst = 0
    print("  %-5s %8s %8s   (heavy: all oscillators and effects on)" % ("", "light", "heavy"))
    for name, m, light, heavy in setups:
        row = []
        for prm in (light, heavy):
            cf.init()
            cf.trig(m)
            for _ in range(4):
                cf.render(m, prm, inc, 32)
            tot = sum(cf.render(m, prm, inc, 32, count=True)[2] for _ in range(16))
            row.append(tot / 16)
        worst = max(worst, row[1])
        print("  %-5s %8.0f %8.0f   = %4.1f %% of the stock render, %4.1f %% of a block's cycles at 1 cycle each"
              % (name, row[0], row[1], 100 * row[1] / 84000, 100 * row[1] / 166667))
    check(worst < 8000, "the heaviest machine setting costs under 8,000 instructions a voice a block (%.0f)" % worst)
    print()
    if FAIL:
        print("%d FAILED" % len(FAIL))
        sys.exit(1)
    print("ALL EMULATOR CHECKS PASSED")


if __name__ == "__main__":
    main()
