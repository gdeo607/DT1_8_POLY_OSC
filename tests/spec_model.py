# Integer model of the Spectrum page (the asm must match it bit-exactly).
import math
N = 1024
SIN = [round(32767 * math.sin(2 * math.pi * k / N)) for k in range(257)]          # quarter wave, Q15
LT = [round(16 * math.log2(1 + f / 16)) for f in range(16)]                        # log2 fraction, 1/16 units
F0, F1, NCOL, FSPLIT = 30.0, 20000.0, 128, 350.0
def fcol(c): return F0 * (F1 / F0) ** (c / (NCOL - 1))
CSPLIT = next(c for c in range(NCOL) if fcol(c) >= FSPLIT)       # first column taken from the 48 kHz band
def _bin(c, low):
    return round(fcol(c) * (512 / 3000 if low else 1024 / 48000))
COLS = []                                                           # per column: (lo, count) in its band
for c in range(NCOL):
    low = c < CSPLIT
    lo = max(1, _bin(c, low)); hi = max(lo + 1, _bin(c + 1, low))
    hi = min(hi, 256 if low else 512); lo = min(lo, hi - 1)
    COLS.append((lo, hi - lo))
assert max(n for lo, n in COLS) <= 31
def col_of(f): return round((NCOL - 1) * math.log(f / F0) / math.log(F1 / F0))
MARKS = [col_of(100), col_of(1000), col_of(10000)]
L0, LRANGE = 48, 160                                                                # log2*16: 3 .. 13 (60 dB)
def sinq(i):
    i &= N - 1; q, r = i >> 8, i & 255
    return (SIN[r], SIN[256 - r], -SIN[r], -SIN[256 - r])[q]
def cosq(i): return sinq(i + 256)
def bitrev(i):
    r = 0
    for _ in range(10): r = (r << 1) | (i & 1); i >>= 1
    return r
def fft_mag(x, n):
    """x: n int16 samples (n = 512 or 1024) -> mag[0..n/2-1]; twiddles from the 1024-point table"""
    lg = n.bit_length() - 1; ts = N // n
    re = [0] * n; im = [0] * n
    for i in range(n):
        h = (32767 - cosq(i * ts)) >> 1
        r = 0; v = i
        for _ in range(lg): r = (r << 1) | (v & 1); v >>= 1
        re[r] = (x[i] * h) >> 15
    size = 2
    while size <= n:
        half = size >> 1; step = (n // size) * ts
        for j in range(half):
            c, s = cosq(j * step), sinq(j * step)
            for k in range(j, n, size):
                i2 = k + half
                tr = (c * re[i2] + s * im[i2]) >> 15
                ti = (c * im[i2] - s * re[i2]) >> 15
                ur, ui = re[k], im[k]
                re[k] = (ur + tr) >> 1; im[k] = (ui + ti) >> 1
                re[i2] = (ur - tr) >> 1; im[i2] = (ui - ti) >> 1
        size <<= 1
    mag = []
    for k in range(n // 2):
        a, b = abs(re[k]), abs(im[k])
        mx, mn = (a, b) if a >= b else (b, a)
        mag.append(mx + (mn >> 1))
    return mag
def log16(m):
    if m <= 0: return 0
    p = m.bit_length() - 1
    f = (m >> (p - 4)) & 15 if p >= 4 else (m << (4 - p)) & 15
    return p * 16 + LT[f]
HMAX = 63
def heights(mag_low, mag_high):
    out = []
    for c in range(NCOL):
        lo, n = COLS[c]
        m = mag_low if c < CSPLIT else mag_high
        M = max(m[lo:lo + n])
        h = (log16(M) - L0) * HMAX // LRANGE
        out.append(max(0, min(HMAX, h)))
    return out
def update_peaks(pk, h): return [max(p - 1, v) for p, v in zip(pk, h)]
