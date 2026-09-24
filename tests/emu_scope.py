#!/usr/bin/env python3
# Unicorn (ColdFire V4e) tests for scope_v3o.s on the SHIPPED v3o section (real image, real vline 0x400c1040).
#  TAP : invisible to the audio ISR (registers, SP, output buffer identical to calling the writer directly);
#        appends 8 x {mid = sat(sum(L+R)>>11), side = sat(sum(L-R)>>11)} per block to the ring at 0x400ae290.
#  DRAW: MODE 0 waveform (pixel-exact model, = v3f on the mid channel), MODE 1 X-Y goniometer (pixel-exact),
#        POLY voice dots (pixel-exact), main-screen info rows 53..63 preserved, MODE reset when `this` changes.
#  TICK: original tick then invalidate, d0 kept.
#  KEY : id 5 press: MODE 0 -> 1 (no close), MODE 1 -> close + MODE 0; other id 5 events consumed;
#        id 12 (NO) without flag bit 1: press -> close + MODE 0, else consumed; with bit 1 -> not consumed;
#        id 6 -> MODE 0 + tail call to the original handler; all others (and NO with bit 1) -> NOT consumed (d0=0),
#        nothing called, so the controller passes them to the main screen like the stock song screen.
# Usage: python3 emu_scope_v3o.py <section_3_v3o.bin> <scope_v3o.sym> [png_dir]
import struct, random, sys, os, math
from unicorn import *
from unicorn.m68k_const import *

IMG = open(sys.argv[1], 'rb').read()
SYMS = {p[2]: int(p[0], 16) for p in (ln.split() for ln in open(sys.argv[2])) if len(p) == 3}
PNG = sys.argv[3] if len(sys.argv) > 3 else None
B = 0x40000400; BODY = 0x400abe9c
DRAW, TICK, TAP, KEY = (BODY + SYMS[k] for k in ('DRAW', 'TICK', 'TAP', 'KEY'))
assert DRAW == BODY
OUTWRITE, OLDTICK, INVAL, OLDKEY = 0x40071c20, 0x400aa8e2, 0x400c9812, 0x400ac8f0
DATA = 0x400ae280; IDXA, MODEA, LASTV, RING = DATA, DATA + 4, DATA + 8, DATA + 16
VSTATE = 0x400b907c; QP = 0x4199dc44; Q = 0x50000000
RINGN, WIN, SEARCH, MARGIN, XYN = 512, 128, 256, 16, 256
YMAX, YMID, YAMP, XMID, DOTX = 52, 26, 24, 64, 80
GEOM = {0: (52, 26, 24), 1: (63, 32, 30)}   # normal / fullscreen
FULLA = 0x400ae280 + 12
def l(x): return struct.pack('>I', x & 0xffffffff)
BUF = 0x51000000; LOG = 0x51000f00; STK = 0x7f000000; BMP = 0x52000000; BMPDATA = 0x52000100
MS, MSVT = 0x53005000, 0x53005100
ALL = [UC_M68K_REG_D0 + i for i in range(8)] + [UC_M68K_REG_A0 + i for i in range(7)]
SAVED = [UC_M68K_REG_D0 + i for i in range(2, 8)] + [UC_M68K_REG_A0 + i for i in range(2, 7)]

# shipped image checks
assert IMG[0x4007814a - B:0x4007814a - B + 6] == bytes.fromhex("4eb9") + l(TAP)
assert IMG[0x401b377c - B:0x401b3780 - B] == l(TICK) and IMG[0x401b3758 - B:0x401b375c - B] == l(KEY)
assert IMG[0x401b3760 - B:0x401b3764 - B] == l(DRAW)

W_STUB = (bytes.fromhex("206f0004") + bytes.fromhex("43f9") + l(BUF) + bytes.fromhex("7240") +
          bytes.fromhex("20d9") + bytes.fromhex("5381") + bytes.fromhex("66fa") +
          bytes.fromhex("203c") + l(0x1234) + bytes.fromhex("223c") + l(0xdead0001) +
          bytes.fromhex("207c") + l(0xdead0002) + bytes.fromhex("227c") + l(0xdead0003) + bytes.fromhex("4e75"))
T_STUB = (bytes.fromhex("202f0004") + bytes.fromhex("23c0") + l(LOG) + bytes.fromhex("7055") +
          bytes.fromhex("223c") + l(0xdead0004) + bytes.fromhex("4e75"))
I_STUB = (bytes.fromhex("202f0004") + bytes.fromhex("23c0") + l(LOG + 4) +
          bytes.fromhex("203c") + l(0xdead0005) + bytes.fromhex("4e75"))
KLOG = 0x51000800
LOGSTUB = (bytes.fromhex("2079") + l(KLOG) + bytes.fromhex("20ef0004") + bytes.fromhex("20ef0008") +
           bytes.fromhex("23c8") + l(KLOG) +
           bytes.fromhex("203c") + l(0x77) + bytes.fromhex("223c") + l(0xdead0001) +
           bytes.fromhex("207c") + l(0xdead0002) + bytes.fromhex("227c") + l(0xdead0003) + bytes.fromhex("4e75"))

def dev():
    mu = Uc(UC_ARCH_M68K, UC_MODE_BIG_ENDIAN); mu.ctl_set_cpu_model(UC_CPU_M68K_CFV4E)
    mu.mem_map(0x40000000, 0x280000)
    img = bytearray(IMG)
    def put(a, bs): img[a - B:a - B + len(bs)] = bs
    put(OUTWRITE, W_STUB); put(OLDTICK, T_STUB); put(INVAL, I_STUB)
    mu.mem_write(B, bytes(img))
    for a in (0x51000000, 0x52000000, 0x53000000, 0x421f0000, 0x41990000, Q): mu.mem_map(a, 0x10000)
    mu.mem_map(STK, 0x4000)
    mu.mem_write(QP, l(0)); mu.mem_write(0x400aeac4, l(0x53008000))   # tuner TBUF
    return mu

def call(mu, fn, args):
    mu.mem_write(KLOG, l(KLOG + 0x100))
    ret = 0x40000500; sp = STK + 0x3000
    mu.mem_write(sp, l(ret) + b''.join(l(a) for a in args))
    mu.reg_write(UC_M68K_REG_A7, sp)
    regs = {r: random.getrandbits(32) for r in ALL}
    for r, v in regs.items(): mu.reg_write(r, v)
    mu.emu_start(fn, ret, count=5_000_000)
    assert mu.reg_read(UC_M68K_REG_PC) == ret and mu.reg_read(UC_M68K_REG_A7) == sp + 4
    lp = struct.unpack('>I', mu.mem_read(KLOG, 4))[0]
    klog = [struct.unpack('>2I', mu.mem_read(a, 8)) for a in range(KLOG + 0x100, lp, 8)]
    return regs, {r: mu.reg_read(r) for r in ALL}, klog

def s32(x): return x - (1 << 32) if x & 0x80000000 else x
def rd(mu, a): return struct.unpack('>I', mu.mem_read(a, 4))[0]
def ring(mu):
    v = struct.unpack('>%dh' % (2 * RINGN), mu.mem_read(RING, RINGN * 4))
    return list(v[0::2]), list(v[1::2])
def sat(s): s = (s >> 8) >> 3; return max(-32768, min(32767, s))

# ---------------- TAP ----------------
def test_tap(blocks, mu=None):
    mu = mu or dev(); ref = dev()
    M, S = ring(mu); mi = rd(mu, IDXA)
    for bi, frames in enumerate(blocks):
        words = [w for f in frames for w in f]
        for m in (mu, ref): m.mem_write(BUF, b''.join(l(w) for w in words))
        OUT, IN = 0x53000000, 0x53001000
        for m in (mu, ref): m.mem_write(OUT, b'\x77' * 256)
        random.seed(bi); r1, o1, _ = call(mu, TAP, [OUT, IN, 0x12345678])
        random.seed(bi); r2, o2, _ = call(ref, OUTWRITE, [OUT, IN, 0x12345678])
        assert o1 == o2, ("TAP not transparent", {hex(k): (hex(o1[k]), hex(o2[k])) for k in o1 if o1[k] != o2[k]})
        assert mu.mem_read(OUT, 256) == ref.mem_read(OUT, 256)
        for k in range(8):
            L = [s32(words[k * 8 + 2 * j]) for j in range(4)]; R = [s32(words[k * 8 + 2 * j + 1]) for j in range(4)]
            M[mi % RINGN] = sat(sum(L) + sum(R)); S[mi % RINGN] = sat(sum(L) - sum(R)); mi += 1
        assert ring(mu) == (M, S) and rd(mu, IDXA) == mi & 0xffffffff, ("ring mismatch", bi)
    return mu

def frames_from(fn, n0, n=32):
    out = []
    for i in range(n):
        a, b = fn(n0 + i)
        c = lambda v: max(-(1 << 23), min((1 << 23) - 1, int(v))) & 0xffffffff
        out.append((c(a), c(b)))
    return out

# ---------------- DRAW model ----------------
def tdiv(a, b): q = abs(a) // abs(b); return q if (a >= 0) == (b > 0) else -q
def model_wave(M, ix, full=0):
    YMAX, YMID, YAMP = GEOM[full]
    g = lambda i: M[i & (RINGN - 1)]
    st = s32((ix - MARGIN - WIN) & 0xffffffff); cand = st
    for _ in range(SEARCH):
        if g(cand - 1) < 0 and g(cand) >= 0: st = cand; break
        cand -= 1
    peak = 512
    for x in range(WIN): peak = max(peak, abs(g(st + x)))
    px = [[0] * 128 for _ in range(YMAX + 1)]; prev = -1
    for x in range(WIN):
        y = max(0, min(YMAX, tdiv(g(st + x) * YAMP, peak) + YMID))
        y0 = prev if prev >= 0 else y
        for yy in range(min(y0, y), max(y0, y) + 1): px[yy][x] = 1
        prev = y
    return px

def model_xy(M, S, ix, full=0):
    YMAX, YMID, YAMP = GEOM[full]
    st = s32((ix - XYN) & 0xffffffff)
    idx = [(st + k) & (RINGN - 1) for k in range(XYN)]
    peak = max([512] + [abs(M[i]) for i in idx] + [abs(S[i]) for i in idx])
    px = [[0] * 128 for _ in range(YMAX + 1)]
    for i in idx:
        y = max(0, min(YMAX, tdiv(M[i] * YAMP, peak) + YMID))
        x = max(0, min(127, tdiv(S[i] * -YAMP, peak) + XMID))
        px[y][x] = 1
    return px

TRIGCNT = RING + RINGN * 4; LASTCNT = TRIGCNT + 8; HOLD = TRIGCNT + 16; FLASHN = 4
def model_dots(px, mach, vnote, qset, st):
    """st = [trig[8], last[8], hold[8]] -> updated in place, like DRAW."""
    trig, last, hold = st
    for t in range(8):
        x0 = DOTX + 6 * t
        for x in range(x0 - 1, x0 + 5):
            for y in range(0, 7): px[y][x] = 0
        if trig[t] != last[t]: last[t] = trig[t]; hold[t] = FLASHN
        active = hold[t] > 0
        if hold[t]: hold[t] -= 1
        poly = qset and mach[t] == 4
        if poly and vnote[t] != 0xff: active = True
        for x in range(x0, x0 + 4):
            for y in range(4):
                if active or x in (x0, x0 + 3) or y in (0, 3): px[y][x] = 1
        if poly: px[5][x0 + 1] = px[5][x0 + 2] = 1

def bitmap_setup(mu):
    mu.mem_write(BMP, l(0) + l(128) + l(64) + l(2) + l(BMPDATA))
    mu.mem_write(BMPDATA, bytes(random.getrandbits(8) for _ in range(128 * 8)))

def bitmap_read(mu):
    raw = mu.mem_read(BMPDATA, 128 * 8); px = [[0] * 128 for _ in range(64)]
    for x in range(128):
        for wi in range(2):
            wv = struct.unpack('>I', raw[(x * 2 + wi) * 4:(x * 2 + wi) * 4 + 4])[0]
            for b in range(32):
                if wv & (0x80000000 >> b): px[wi * 32 + b][x] = 1
    return px

def ms_setup(mu, present):
    stub = (bytes.fromhex("206f0008") + bytes.fromhex("20680010") + bytes.fromhex("203c") + l(256) +
            bytes.fromhex("223c") + l(0xa5a5a5a5) + bytes.fromhex("20c1") + bytes.fromhex("4681") +
            bytes.fromhex("5380") + bytes.fromhex("66f8") + bytes.fromhex("4e75"))
    mu.mem_write(0x53006000, stub); mu.mem_write(MSVT + 16, l(0x53006000)); mu.mem_write(MSVT + 8, l(0x53006800))
    mu.mem_write(0x53006800, LOGSTUB); mu.mem_write(MS, l(MSVT))
    mu.mem_write(0x421f9b50, l(MS if present else 0)); mu.mem_write(0x421f9b54, l(0x53007000 if present else 0))

THIS = 0x53002000
def test_draw(M, S, ix, mode, name, ms=True, mach=None, vnote=None, qset=True, this=THIS, lastv=THIS, mu=None, st=None, frames=1, full=0):
    mu = mu or dev()
    mu.mem_write(FULLA, l(full))
    st = st or [[random.randrange(256) for _ in range(8)] for _ in range(2)] + [[random.choice([0, 0, 1, 3, 4, 200]) for _ in range(8)]]
    mu.mem_write(TRIGCNT, bytes(st[0] + st[1] + st[2]))
    ms_setup(mu, ms)
    mach = mach or [0] * 8; vnote = vnote or [0xff] * 8
    mu.mem_write(RING, b''.join(struct.pack('>hh', M[i], S[i]) for i in range(RINGN)))
    mu.mem_write(IDXA, l(ix)); mu.mem_write(MODEA, l(mode)); mu.mem_write(LASTV, l(lastv))
    for t in range(8): mu.mem_write(Q + 0x9e + t * 0xa2, bytes([mach[t]]))
    mu.mem_write(QP, l(Q if qset else 0)); mu.mem_write(VSTATE, bytes(vnote))
    for fr in range(frames):
        bitmap_setup(mu); before = bitmap_read(mu)
        r_in, r_out, _ = call(mu, DRAW, [this, BMP])
        for r in SAVED: assert r_in[r] == r_out[r], ("DRAW reg leak", r)
        eff = mode if this == lastv else 0
        ef = full if this == lastv else 0
        assert rd(mu, MODEA) == eff and rd(mu, LASTV) == this and rd(mu, FULLA) == ef
        lastv = this
        px = bitmap_read(mu)
        exp = model_wave(M, ix, ef) if eff == 0 else model_xy(M, S, ix, ef)
        if not ef: model_dots(exp, mach, vnote, qset, st)
        assert list(mu.mem_read(TRIGCNT, 24)) == st[0] + st[1] + st[2], ("dot state", name, fr)
        ym = GEOM[ef][0]
        for y in range(ym + 1):
            if not ef and y <= 6:                     # tuner box x 0..31 (emu_tuner_v3o.py)
                px[y][:32] = exp[y][:32] = [0] * 32
            assert px[y] == exp[y], ("pixel mismatch", name, fr, y, [x for x in range(128) if px[y][x] != exp[y][x]])
        for x in range(128):
            for y in range(ym + 1, 64):
                want = (0xa5 if (x * 2 + y // 32) % 2 == 0 else 0x5a) >> (7 - (y % 32) % 8) & 1 if ms else before[y][x]
                assert px[y][x] == want, ("info line damaged", name, x, y)
    if PNG:
        from PIL import Image
        im = Image.new('L', (128, 64)); im.putdata([255 if px[y][x] else 0 for y in range(64) for x in range(128)])
        im.resize((512, 256), Image.NEAREST).save(os.path.join(PNG, name + '.png'))
    return px

# ---------------- KEY ----------------
def test_key():
    for ms in (True, False):
        mu = dev(); ms_setup(mu, ms)
        VT, EV, CLOSE = 0x52001200, 0x52001300, 0x52001400
        mu.mem_write(CLOSE, LOGSTUB); mu.mem_write(THIS, l(VT)); mu.mem_write(VT + 40, l(CLOSE))
        for kid in list(range(-2, 60)) + [0x7fffffff]:
            for flags in (0, 1, 2, 3, 4, 5, 8, 9, 0x1f):
                for mode, full in ((0, 0), (1, 0), (0, 1), (1, 1)):
                    mu.mem_write(MODEA, l(mode)); mu.mem_write(FULLA, l(full))
                    mu.mem_write(EV + 12, l(kid)); mu.mem_write(EV + 16, l(flags))
                    random.seed(kid * 97 + flags * 3 + mode + 7 * full)
                    regs, out, lg = call(mu, KEY, [THIS, EV])
                    m2 = rd(mu, MODEA); f2 = rd(mu, FULLA)
                    pressed = (flags & 1) and not (flags & 8)
                    if kid == 5:
                        assert out[UC_M68K_REG_D0] & 0xff == 1
                        if pressed and mode == 0: assert lg == [] and m2 == 1 and f2 == full, (kid, flags, mode, lg)
                        elif pressed: assert [x[0] for x in lg] == [THIS] and m2 == 0 and f2 == 0, (kid, flags, mode, lg)
                        else: assert lg == [] and m2 == mode and f2 == full
                    elif kid == 12 and not (flags & 2):          # YES
                        assert out[UC_M68K_REG_D0] & 0xff == 1 and lg == [] and m2 == mode, (kid, flags, lg)
                        assert f2 == (full ^ 1 if pressed else full), (kid, flags, full, f2)
                    elif kid == 13 and not (flags & 2):          # NO
                        assert out[UC_M68K_REG_D0] & 0xff == 1
                        if pressed: assert [x[0] for x in lg] == [THIS] and m2 == 0 and f2 == 0, (kid, flags, mode, lg)
                        else: assert lg == [] and m2 == mode and f2 == full, (kid, flags, mode, lg)
                    elif kid == 6:                               # stock SETTINGS semantics, now in KEY
                        if flags & 2: assert lg == [] and out[UC_M68K_REG_D0] & 0xff == 0 and m2 == mode and f2 == full
                        elif not flags & 1: assert [x[0] for x in lg] == [THIS] and out[UC_M68K_REG_D0] & 0xff == 0 and m2 == 0 and f2 == 0, (kid, flags, lg)
                        else: assert lg == [] and out[UC_M68K_REG_D0] & 0xff == 1 and m2 == mode and f2 == full, (kid, flags, lg)
                    else:   # not consumed: the controller hands it to the main screen; nothing called here
                        assert lg == [] and out[UC_M68K_REG_D0] & 0xff == 0 and m2 == mode and f2 == full, (kid, flags, lg)
                    for r in SAVED: assert regs[r] == out[r], ("KEY reg leak", kid, flags, r)

if __name__ == '__main__':
    random.seed(1)
    blocks = [[(random.getrandbits(24) - (1 << 23), random.getrandbits(24) - (1 << 23)) for _ in range(32)] for _ in range(5)]
    blocks += [[((1 << 23) - 1, (1 << 23) - 1)] * 32, [(-(1 << 23), -(1 << 23))] * 32,
               [((1 << 23) - 1, -(1 << 23))] * 32, [(-(1 << 23), (1 << 23) - 1)] * 32]
    blocks = [[(a & 0xffffffff, b & 0xffffffff) for a, b in bl] for bl in blocks]
    test_tap(blocks)
    mu = dev(); mu.mem_write(IDXA, l(0xfffffff0))                          # index wrap
    test_tap([frames_from(lambda n: (3e6 * math.sin(n / 7), -2e6 * math.cos(n / 5)), k * 32) for k in range(70)], mu)
    mu = dev(); r_in, r_out, _ = call(mu, TICK, [0x53004000])
    assert struct.unpack('>II', mu.mem_read(LOG, 8)) == (0x53004000, 0x53004000) and r_out[UC_M68K_REG_D0] == 0x55
    for r in SAVED: assert r_in[r] == r_out[r]
    sine = lambda f, a, b, ph=0: (lambda n: (a * math.sin(2 * math.pi * f * n / 48000), b * math.sin(2 * math.pi * f * n / 48000 + ph)))
    cases = {'mono_110': sine(110, 3e6, 3e6), 'left_only': sine(220, 4e6, 0), 'right_only': sine(220, 0, 4e6),
             'antiphase': sine(330, 3e6, -3e6), 'quad_90deg': sine(150, 3e6, 3e6, math.pi / 2),
             'wide_noise': lambda n: (random.gauss(0, 1e6), random.gauss(0, 1e6)), 'silence': lambda n: (0, 0),
             'loud_clip': sine(440, 8e6, 8e6), 'quiet': sine(1000, 2e5, 1e5)}
    dotsets = [([0] * 8, [0xff] * 8), ([0, 0, 0, 0, 4, 4, 4, 4], [0xff, 0xff, 0xff, 0xff, 60, 0xff, 64, 0xff]),
               ([4] * 8, [0, 0xff, 1, 0xff, 127, 0xff, 0xfe, 0xff]), ([1, 4, 0, 4, 2, 4, 3, 4], [5] * 8)]
    for k, (name, fn) in enumerate(cases.items()):
        mu = test_tap([frames_from(fn, j * 32) for j in range(80)])
        M, S = ring(mu); ix = rd(mu, IDXA)
        mach, vn = dotsets[k % len(dotsets)]
        for mode in (0, 1):
            test_draw(M, S, ix, mode, '%s_%s' % (name, 'xy' if mode else 'wave'), mach=mach, vnote=vn)
    for k, (name, fn) in enumerate(list(cases.items())[:5]):
        mu = test_tap([frames_from(fn, j * 32) for j in range(80)])
        M, S = ring(mu); ix = rd(mu, IDXA)
        for mode in (0, 1):
            test_draw(M, S, ix, mode, 'FULL_%s_%s' % (name, 'xy' if mode else 'wave'), mach=[4] * 8, full=1)
    for s in range(40):
        random.seed(100 + s)
        M = [random.randint(-32768, 32767) if random.random() < 0.5 else random.randint(-300, 300) for _ in range(RINGN)]
        S = [random.randint(-32768, 32767) if random.random() < 0.5 else random.randint(-300, 300) for _ in range(RINGN)]
        mach = [random.choice([0, 1, 4, 4]) for _ in range(8)]; vn = [random.choice([0xff, 0xff, 3, 60]) for _ in range(8)]
        test_draw(M, S, random.choice([0, 5, 143, 144, 255, 256, 511, 512, random.getrandbits(32)]), s % 2, 'rand%d' % s,
                  ms=(s % 3 != 0), mach=mach, vnote=vn, qset=(s % 5 != 0),
                  this=THIS, lastv=(THIS if s % 4 else 0x53009999), full=(s // 2) % 2)       # new view object -> waveform
    # X-Y race: the ISR overwrites the ring (full-scale) between the peak pass and the plot pass
    # (UI task preempted > 21 ms). Every vline call must stay inside x 0..127, y 0..52.
    for mode, full in ((0, 0), (1, 0), (0, 1), (1, 1)):
        mu = dev(); ms_setup(mu, True); mu.mem_write(FULLA, l(full))
        M = [random.randint(-300, 300) for _ in range(RINGN)]
        mu.mem_write(RING, b''.join(struct.pack('>hh', M[i], -M[i]) for i in range(RINGN)))
        mu.mem_write(IDXA, l(1000)); mu.mem_write(MODEA, l(mode)); mu.mem_write(LASTV, l(THIS))
        bitmap_setup(mu); seen = []
        def hk(uc, addr, size, _):
            sp = uc.reg_read(UC_M68K_REG_A7)
            a = struct.unpack('>5i', uc.mem_read(sp + 4, 20)); seen.append(a[1:])
            if a[4] == 1 and len(seen) > 5 and not getattr(hk, 'done', False):
                hk.done = True
                uc.mem_write(RING, b''.join(struct.pack('>hh', random.choice([32767, -32768]), random.choice([32767, -32768]))
                                            for _ in range(RINGN)))
        hk.done = False
        mu.hook_add(UC_HOOK_CODE, hk, begin=0x400c1040, end=0x400c1040)
        call(mu, DRAW, [THIS, BMP])
        ym = GEOM[full][0]
        assert hk.done and all(0 <= x <= 127 and 0 <= y0 <= ym and 0 <= y1 <= ym for x, y0, y1, c in seen), mode
    # TRIG: site check here; ISR behaviour (both paths, regs, memory, counts) is tested by emu_trig_v3o.py
    TRIG = BODY + SYMS['TRIG']
    assert IMG[0x40077d72 - B:0x40077d7a - B] == bytes.fromhex("4eb9") + l(TRIG) + bytes.fromhex("4e71")
    assert IMG[0x40077d6c - B:0x40077d72 - B] == bytes.fromhex("42b94199e130")
    # flash timing: one trig on tracks 0 and 5 -> filled for exactly FLASHN frames, POLY-held stays filled
    random.seed(7)
    M = [0] * RINGN; S = [0] * RINGN
    st = [[1, 0, 0, 0, 0, 1, 0, 0], [0] * 8, [0] * 8]
    test_draw(M, S, 0, 0, 'flash', mach=[0, 4, 0, 0, 1, 2, 4, 4], vnote=[0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 60, 0xff],
              st=st, frames=FLASHN + 2)
    assert st[2] == [0] * 8
    test_key()
    print("scope v3o (TAP mid/side, wave, X-Y, voice dots, TICK, KEY): all emulator tests passed")
