# Integer model of the scope tuner (exactly what the asm will do).
import math
RN = 512
TR = [round(65536 * 2 ** (j / 12)) for j in range(13)]
PA4 = 6982                      # A4 period at 12 kHz in 1/256 samples (12000/440*256 = 6981.8)
NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
W = 256
def tdiv(a, b): q = abs(a) // abs(b); return q if (a >= 0) == (b > 0) else -q
def dfun(x, L):
    d = 0
    for i in range(W):
        e = x[i] - x[i + L]; d += e * e
    return d
def parab(a, b, c):
    """offset of the minimum in 1/256 samples; values scaled so (a-c)*128 fits 32 bits"""
    m = max(a, b, c); s = 0
    while (m >> s) >= (1 << 23): s += 1
    a >>= s; b >>= s; c >>= s
    den = a - 2 * b + c
    if den <= 0: return 0
    off = tdiv((a - c) * 128, den)
    return max(-128, min(128, off))
def yin(x, lmin, lmax, thr_num=30):
    """returns period*256 or None"""
    cum = 0
    d8 = [0] * (lmax + 2)
    for L in range(1, lmax + 2): d8[L] = dfun(x, L) >> 8
    found = None
    for L in range(1, lmax + 1):
        cum += d8[L]
        if L < lmin: continue
        if d8[L] * L < (cum // 100) * thr_num:
            while L + 1 <= lmax and d8[L + 1] < d8[L]: L += 1
            if L >= lmax: return None            # still falling at the edge: period out of range
            found = L; break
    if found is None: return None
    L = found
    P = L * 256 + parab(dfun(x, L - 1), dfun(x, L), dfun(x, L + 1))
    # refine at the largest multiple k*P <= lmax: error / k
    k = (lmax * 256) // P
    if k >= 2:
        Lk = (k * P + 128) // 256
        # local minimum of d around Lk (+-2)
        best = Lk; bv = dfun(x, Lk)
        for t in (Lk - 2, Lk - 1, Lk + 1, Lk + 2):
            if 2 <= t <= lmax:
                v = dfun(x, t)
                if v < bv: best, bv = t, v
        if 2 <= best < lmax + 1:
            Pk = best * 256 + parab(dfun(x, best - 1), bv, dfun(x, best + 1))
            P = (Pk + k // 2) // k
    return P
def normalise(seg):
    pk = max(abs(v) for v in seg)
    sh = 0
    while (pk >> sh) > 1023: sh += 1
    return [v >> sh for v in seg], pk
def note_of(P12):
    """P12 = period at 12 kHz in 1/256 samples -> (midi, cents)"""
    q = (PA4 << 16) // P12
    octv = 0
    while q < 65536: q <<= 1; octv -= 1
    while q >= 131072: q >>= 1; octv += 1
    j = 11
    while TR[j] > q: j -= 1
    y = ((q - TR[j]) << 16) // TR[j]           # 16.16, < 0.0595
    c = (1731 * y - ((865 * ((y * y) >> 16)))) >> 16   # 1731.23*(y - y^2/2)
    semis = octv * 12 + j
    if c >= 50: semis += 1; c -= 100
    return 69 + semis, c
def tune(ring12, idx12, ring3, idx3, minpk=256):
    seg = [ring12[(idx12 - 16 - (W + 201) + k) % RN] for k in range(W + 201)]
    x, pk = normalise(seg)
    if pk < minpk: return None
    P = yin(x, 4, 200)
    if P is None:
        seg3 = [ring3[(idx3 - 2 - (W + 251) + k) % RN] for k in range(W + 251)]
        x3, pk3 = normalise(seg3)
        if pk3 < minpk: return None
        P3 = yin(x3, 45, 250)
        if P3 is None: return None
        P = P3 * 4
    return note_of(P)
