import math, random
from tuner_model import *
def rings(fn, n48=48000):
    # emulate TAP: mid = sat(sum over 4 frames (L+R) >> 11); tuner 3k = sum of 4 mids >> 2
    r12 = [0] * RN; r3 = [0] * RN; i12 = 0; i3 = 0; acc = []
    total_blocks = 400
    for blk in range(total_blocks):
        for k in range(8):
            s = 0
            for f in range(4):
                n = blk * 32 + k * 4 + f
                v = fn(n); s += 2 * v
            m = max(-32768, min(32767, (s >> 8) >> 3))
            r12[i12 % RN] = m; i12 += 1; acc.append(m)
            if len(acc) == 4:
                r3[i3 % RN] = sum(acc) >> 2; i3 += 1; acc = []
    return r12, i12, r3, i3
def midi_cents(f):
    m = 69 + 12 * math.log2(f / 440); n = round(m); return n, (m - n) * 100
if __name__ == '__main__':
    worst = 0; fails = []
    for f in [27.5, 32.7, 41.2, 55, 61.7, 65.4, 73.4, 82.4, 110, 146.8, 220, 261.6, 329.6, 440, 523.3, 880, 1046.5, 1318.5, 1760, 2093]:
        for det in (-37, -12, 0, 8, 23, 44):
            ff = f * 2 ** (det / 1200)
            for wave in ('sine', 'saw', 'square'):
                amp = 3e6
                if wave == 'sine': fn = lambda n: int(amp * math.sin(2 * math.pi * ff * n / 48000))
                elif wave == 'saw': fn = lambda n: int(amp * (2 * ((ff * n / 48000) % 1) - 1))
                else: fn = lambda n: int(amp * (1 if (ff * n / 48000) % 1 < 0.5 else -1))
                r12, i12, r3, i3 = rings(fn)
                res = tune(r12, i12, r3, i3)
                en, ec = midi_cents(ff)
                if res is None: fails.append((round(ff, 1), wave, 'none')); continue
                n, c = res
                err = (n - en) * 100 + (c - ec)
                if abs(err) > 3: fails.append((round(ff, 1), wave, n, c, en, round(ec, 1)))
                worst = max(worst, abs(err))
    print("worst error (cents) among ok:", round(worst, 1)); print("fails:", len(fails)); print(fails[:30])
