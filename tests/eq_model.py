#!/usr/bin/env python3
"""Integer model of the Digi utilities master EQ (mods/digiutils/eq.c + eq_dsp.s), and its checks.

    python3 tests/eq_model.py          # response of the fixed-point EQ vs the floating-point design

Bands: 0 low shelf, 1 and 2 bells, 3 high shelf; each a trapezoidal state-variable filter (A. Simper,
"Linear trap SVF"), with the shelf/bell mixes. Coefficients as eq.c computes them (32-bit integer only);
processing as eq_dsp.s does it with the EMAC in fractional mode (each product kept to 8 bits below the
result LSB, the result truncated), samples in a x4 (26-bit) working range.
"""
import cmath, math, os, sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
import gen_eq_tables as T

TAB = T.tables()
ONE27 = 1 << 27
# band types (the order a type knob steps through)
HP, LSH, BELL, NOTCH, BP, HSH, LP = range(7)
TYPES = ("HP", "LSHF", "BELL", "NTCH", "BP", "HSHF", "LP")
FILTERS = (HP, NOTCH, BP, LP)                       # always active (their level knob is the band's level)


def mulsh(a, b, sh):
    return (a * b) >> sh


def div55(d):
    return (1 << 55) // d


def coef(fi, gi, qi, ty):
    """-> (a1, a2, a3, c0, c1, c2): a* in Q31, c* = mix/16 in Q31 (= mix in Q27, c0 = m0 - 1)."""
    A, A2 = TAB["A27"][gi], TAB["AA27"][gi]
    k = TAB["K27"][qi]
    g = TAB["G27"][fi]
    if ty == BELL:
        k = mulsh(k, TAB["A27"][48 - gi], 27)
        c0, c1, c2 = 0, mulsh(k, A2 - ONE27, 27), 0
    elif ty == LSH:
        g = mulsh(g, TAB["SQA27"][48 - gi], 27)
        c0, c1, c2 = 0, mulsh(k, A - ONE27, 27), A2 - ONE27
    elif ty == HSH:
        g = mulsh(g, TAB["SQA27"][gi], 27)
        c0, c1, c2 = A2 - ONE27, mulsh(mulsh(k, ONE27 - A, 27), A, 27), ONE27 - A2
    elif ty == LP:
        c0, c1, c2 = -ONE27, 0, A2
    elif ty == HP:
        c0, c1, c2 = A2 - ONE27, -mulsh(k, A2, 27), -A2
    elif ty == BP:
        c0, c1, c2 = -ONE27, mulsh(k, A2, 27), 0
    else:                                           # NOTCH
        c0, c1, c2 = A2 - ONE27, -mulsh(k, A2, 27), 0
    d24 = (1 << 24) + mulsh(g, g + k, 30)
    a1 = div55(d24)
    a2 = mulsh(g, a1, 27)
    a3 = mulsh(g, a2, 27)
    return (a1, a2, a3, c0, c1, c2)


def band_g_k(fi, gi, qi, ty):
    """the band's g and k (Q27), as coef() uses them"""
    k = TAB["K27"][qi]
    g = TAB["G27"][fi]
    if ty == BELL:
        k = mulsh(k, TAB["A27"][48 - gi], 27)
    elif ty == LSH:
        g = mulsh(g, TAB["SQA27"][48 - gi], 27)
    elif ty == HSH:
        g = mulsh(g, TAB["SQA27"][gi], 27)
    return g, k


def active(fi, gi, qi, ty):
    return ty in FILTERS or gi != 24


def udivq16(x, y):
    """floor(x * 65536 / y) for 0 <= x <= y < 2^30, by shift-and-subtract"""
    rem, q = x, 0
    for _ in range(16):
        rem <<= 1
        q <<= 1
        if rem >= y:
            rem -= y
            q |= 1
    return q


def log2q8(v):
    p = v.bit_length() - 1
    m = v >> (p - 8) if p >= 8 else v << (8 - p)
    return p * 256 + TAB["LOG2Q8"][m & 255]


def resp_db2(fi, gi, qi, ty, x):
    """the band's gain (half-dB units) at frequency step x, as eq.c computes it for the drawing"""
    g, k = band_g_k(fi, gi, qi, ty)
    _, _, _, c0, c1, c2 = coef(fi, gi, qi, ty)
    q = lambda v: v >> 11                           # Q27 -> Q16
    m0, m1, m2, kk = q(c0 + ONE27), q(c1), q(c2), q(k)
    a = m0 + m2
    b = mulsh(m0, kk, 16) + m1
    G = TAB["G27"][x]
    if G <= g:
        t = udivq16(G, g)
        t2 = mulsh(t, t, 16)
        n1 = a - mulsh(m0, t2, 16)
        d1 = 65536 - t2
    else:
        t = udivq16(g, G)
        t2 = mulsh(t, t, 16)
        n1 = mulsh(a, t2, 16) - m0
        d1 = t2 - 65536
    bt, kt = mulsh(b, t, 16), mulsh(kk, t, 16)
    n = mulsh(n1, n1, 16) + mulsh(bt, bt, 16)
    d = mulsh(d1, d1, 16) + mulsh(kt, kt, 16)
    if n <= 0:
        return -200
    if d <= 0:
        return 200
    return ((log2q8(n) - log2q8(d)) * 1541 + 32768) >> 16


def emac(*pairs):
    s = 0
    for x, y in pairs:
        s += (x * y) >> 23
    return s >> 8


def s32(v):
    v &= 0xffffffff
    return v - (1 << 32) if v & 0x80000000 else v


class EQ:
    """params: per band [fi, gi, qi, ty]."""
    DEFAULT = [[25, 24, 4, LSH], [55, 24, 5, BELL], [89, 24, 5, BELL], [114, 24, 4, HSH]]

    def __init__(self):
        self.p = [list(b) for b in self.DEFAULT]
        self.out, self.on = 24, 1
        self.st = [[[0, 0], [0, 0]] for _ in range(4)]      # band -> channel -> [ic1, ic2]
        self.was = [0, 0, 0, 0]

    def coefs(self):
        return [coef(*self.p[b]) for b in range(4)]

    def active(self):
        return [self.on and active(*self.p[b]) for b in range(4)]

    def block(self, buf):
        """buf: 64 ints (L, R interleaved, 24-bit). Returns the processed block (as eq_dsp.s)."""
        act = self.active()
        if not self.on or (not any(act) and self.out == 24):
            self.was = [0, 0, 0, 0]
            return list(buf)
        x = [s32(v << 2) for v in buf]
        cs = self.coefs()
        for b in range(4):
            if not act[b]:
                self.was[b] = 0
                continue
            if not self.was[b]:
                self.st[b] = [[0, 0], [0, 0]]
                self.was[b] = 1
            a1, a2, a3, c0, c1, c2 = cs[b]
            for ch in (0, 1):
                ic1, ic2 = self.st[b][ch]
                for i in range(ch, 64, 2):
                    v0 = x[i]
                    v3 = s32(v0 - ic2)
                    v1 = emac((a1, ic1), (a2, v3))
                    v2 = s32(ic2 + emac((a2, ic1), (a3, v3)))
                    ic1 = s32(2 * v1 - ic1)
                    ic2 = s32(2 * v2 - ic2)
                    r = emac((c0, v0), (c1, v1), (c2, v2))
                    x[i] = s32(v0 + s32(r << 4))
                self.st[b][ch] = [ic1, ic2]
        if self.out != 24:
            L = TAB["AA27"][self.out]
            x = [s32(emac((L, v)) << 4) for v in x]
        out = []
        for v in x:
            v = (v + 2) >> 2
            out.append(max(-(1 << 23) + 1, min((1 << 23) - 1, v)))
        return out


# ---------------- floating-point reference (the same SVF design, exact math) ----------------
def design(fi, gi, qi, ty):
    """(g, k, mix) of the band in exact arithmetic"""
    f, dbv = T.freq(fi), T.db(gi)
    A = 10 ** (dbv / 40)
    g0 = math.tan(math.pi * f / T.FS)
    k0 = 1 / T.qval(qi)
    L = A * A
    if ty == BELL:
        k = k0 / A
        return g0, k, (1, k * (A * A - 1), 0)
    if ty == LSH:
        return g0 / math.sqrt(A), k0, (1, k0 * (A - 1), A * A - 1)
    if ty == HSH:
        return g0 * math.sqrt(A), k0, (A * A, k0 * (1 - A) * A, 1 - A * A)
    return g0, k0, {LP: (0, 0, L), HP: (L, -k0 * L, -L), BP: (0, k0 * L, 0), NOTCH: (L, -k0 * L, 0)}[ty]


def svf_response(g, k, m, f):
    """H(e^jw) of the trapezoidal SVF with mix m."""
    z = cmath.exp(1j * 2 * math.pi * f / T.FS)
    s = (z - 1) / (z + 1) / g                      # bilinear, prewarped by g
    den = s * s + k * s + 1
    lp, bp, hp = 1 / den, s / den, s * s / den
    return m[0] * (hp + bp * k + lp) + m[1] * bp + m[2] * lp


def fixed_gain_db(eq, f, n=2400):
    """Steady-state gain (dB) of the integer model for a sine at f: quadrature correlation over the
    whole cycles of the second half of the run."""
    amp = 1 << 20
    ph, outs = 0, []
    nb = n // 32
    for blk in range(nb):
        buf = []
        for i in range(32):
            v = int(round(amp * math.sin(2 * math.pi * f * ph / T.FS)))
            ph += 1
            buf += [v, v]
        o = eq.block(buf)
        outs += o[0::2]
    start = len(outs) // 2
    per = T.FS / f
    cycles = int((len(outs) - start) / per)
    end = start + int(round(cycles * per))
    si = co = 0.0
    for i in range(start, end):
        w = 2 * math.pi * f * i / T.FS
        si += outs[i] * math.sin(w)
        co += outs[i] * math.cos(w)
    a = 2 * math.hypot(si, co) / (end - start)
    return 20 * math.log10(a / amp)


def main():
    worst = 0.0
    cases = [
        (25, 48, 4, LSH), (25, 0, 4, LSH), (0, 40, 8, LSH), (55, 48, 0, BELL), (55, 0, 15, BELL),
        (10, 36, 8, BELL), (89, 44, 12, BELL), (120, 10, 3, BELL), (114, 48, 4, HSH), (100, 0, 4, HSH),
        (127, 36, 4, HSH), (60, 24, 4, LP), (60, 30, 10, LP), (40, 24, 4, HP), (70, 18, 12, HP),
        (60, 24, 6, BP), (60, 24, 3, NOTCH), (90, 36, 9, NOTCH),
    ]
    for fi, gi, qi, ty in cases:
        g, k, m = design(fi, gi, qi, ty)
        for f in (25, 60, 150, 400, 1000, 2500, 6000, 12000, 18000):
            ref = 20 * math.log10(max(abs(svf_response(g, k, m, f)), 1e-9))
            eq2 = EQ(); eq2.p[0] = [fi, gi, qi, ty]; eq2.p[1][1] = eq2.p[2][1] = 24; eq2.p[3] = [114, 24, 4, HSH]
            got = fixed_gain_db(eq2, f, n=19200 if f < 100 else 4800)
            if ref < -40 and got < -40:
                continue                            # deep stopband: both far below anything audible
            err = abs(got - ref)
            worst = max(worst, err)
            if err > 0.1:
                print("fi %d gi %d qi %d %s  f %5d: design %+6.2f dB, fixed %+6.2f dB" % (fi, gi, qi, TYPES[ty], f, ref, got))
    print("worst |fixed - design| = %.3f dB over %d settings x 9 frequencies" % (worst, len(cases)))
    # the drawn curve (integer, eq.c) against the exact response of the same design
    wd = 0.0
    for fi, gi, qi, ty in cases:
        g, k, m = design(fi, gi, qi, ty)
        for x in range(0, 128, 3):
            ref = 20 * math.log10(max(abs(svf_response(g, k, m, T.freq(x))), 1e-9))
            if ref < -24:
                continue
            got = resp_db2(fi, gi, qi, ty, x) / 2.0
            wd = max(wd, abs(got - ref))
    print("drawn curve: worst error %.2f dB (above -24 dB)" % wd)
    return 0 if worst <= 0.1 and wd <= 0.35 else 1


if __name__ == "__main__":
    sys.exit(main())
