#!/usr/bin/env python3
"""Digi Mono's engine, measured: does each machine do what its parameters say?

    python3 tests/mono_signal.py            (needs gcc and numpy)

Runs the engine built for this PC (tests/mono_lib.py; tests/emu_mono.py shows the ColdFire build gives the
same samples) and checks, with numbers printed:
  pitch        every machine's fundamental against the note, across the keyboard
  SIN          purity (harmonic distortion)
  SAW / PULS   aliasing, against a naive (not band-limited) oscillator at the same pitch
  SAW          sub 1 / sub 2 at 1/2 and 1/4 of the pitch; SUBX moving sub 1 from square to saw;
               UNIL / UNIW / UNIX: unison partials at the detune UNIW asks for, and how many
  PULS         duty cycle from PW; PWAD / PWRS sweeping it
  ENS          PCH2..4 as intervals; WAVE saw -> pulse; CHRL / CHRW chorus
  NOIS         ST (sample and hold), RED (darker), STON (pitched)
  VO           the formants of three vowels; VOC1 -> VOC2 by V-SW; a consonant at the start; pitch; level
  all          random settings and pitches: bounded, no DC, block size makes no difference
"""
import math, os, random, sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mono_lib import FS, SIN, NOIS, SAW, PULS, ENS, VO, NAMES, Engine, play, pitch_inc, note_hz

FAIL = []


def check(ok, what):
    print(("  ok    " if ok else "  FAIL  ") + what)
    if not ok:
        FAIL.append(what)


def spectrum(x):
    w = np.blackman(len(x))
    s = np.abs(np.fft.rfft(x * w)) ** 2
    return s, np.fft.rfftfreq(len(x), 1 / FS)


def peak_hz(x, lo=20, hi=20000):
    """The strongest frequency, refined by a parabola through the three bins around it."""
    s, f = spectrum(x)
    m = (f >= lo) & (f <= hi)
    i = int(np.argmax(np.where(m, s, 0)))
    a, b, c = np.log(s[i - 1] + 1e-30), np.log(s[i] + 1e-30), np.log(s[i + 1] + 1e-30)
    d = 0.5 * (a - c) / (a - 2 * b + c)
    return (i + d) * FS / len(x)


def band_db(x, f0, width=3.0):
    """Energy within +-width Hz of f0, relative to all of it, in dB."""
    s, f = spectrum(x)
    return 10 * math.log10(s[np.abs(f - f0) <= width].sum() / s.sum() + 1e-30)


def alias_db(x, f0, guard=4.0):
    """Energy away from every harmonic of f0 (below fs/2), relative to all of it, in dB."""
    s, f = spectrum(x)
    k = np.round(f / f0)
    near = (np.abs(f - k * f0) <= guard) & (k >= 1)
    return 10 * math.log10(s[~near].sum() / s.sum() + 1e-30)


def cents(a, b):
    return 1200 * math.log2(a / b)


def naive_saw(f0, n):
    t = (np.arange(n) * f0 / FS) % 1.0
    return 2 * t - 1


def naive_pulse(f0, n, d):
    t = (np.arange(n) * f0 / FS) % 1.0
    return np.where(t < d, 1.0, -1.0)


def main():
    print("pitch")
    worst = 0
    for m, prm in ((SIN, [0] * 7), (SAW, [0] * 7), (PULS, [0, 0, 0, 0, 64, 0, 0]), (ENS, [75, 87, 99, 0, 64, 0, 0])):
        for note in (24, 36.5, 48, 60, 69, 84, 96, 108.25):
            x = play(m, prm, note, 1.0)
            f = note_hz(note)          # ENS: its oscillators 2..4 an octave or more up, osc 1 alone near f
            worst = max(worst, abs(cents(peak_hz(x, f * 0.98, f * 1.02), f)))
    check(worst < 0.5, "fundamental within 0.5 cent of the note, SIN/SAW/PULS/ENS, notes 24..108 (worst %.3f)" % worst)
    exact = max(abs(cents(pitch_inc(n) / 2 ** 32 * FS, note_hz(round(n * 128) / 128))) for n in np.arange(0, 126, 0.37))
    check(exact < 0.02, "mono_pitch_inc within 0.02 cent over notes 0..126 (worst %.4f)" % exact)

    print("SIN")
    x = play(SIN, [0] * 7, 57, 1.0)
    h = max(band_db(x, k * note_hz(57)) for k in range(2, 10))
    check(h < -90, "harmonics below -90 dB (strongest %.1f dB)" % h)

    print("SAW / PULS aliasing (band-limited against naive)")
    for note in (84, 96, 103):
        f0 = note_hz(note)
        a = alias_db(play(SAW, [0] * 7, note, 1.0), f0)
        b = alias_db(naive_saw(f0, FS), f0)
        check(a < b - 12 and a < -25, "SAW note %d: alias %.1f dB, naive %.1f dB" % (note, a, b))
        a = alias_db(play(PULS, [0, 0, 0, 0, 64, 0, 0], note, 1.0), f0)
        b = alias_db(naive_pulse(f0, FS, 0.5), f0)
        check(a < b - 12 and a < -30, "PULS note %d: alias %.1f dB, naive %.1f dB" % (note, a, b))

    print("SAW sub-oscillators, SUBX")
    f0 = note_hz(48)
    x = play(SAW, [0, 0, 0, 0, 0, 127, 0], 48, 1.0)
    check(band_db(x, f0 / 2) > -6, "SUB1 127: strong partial at f/2 (%.1f dB)" % band_db(x, f0 / 2))
    x0 = play(SAW, [0] * 7, 48, 1.0)
    check(band_db(x0, f0 / 2) < -80, "SUB1 0: nothing at f/2 (%.1f dB)" % band_db(x0, f0 / 2))
    x = play(SAW, [0, 0, 0, 0, 0, 0, 127], 48, 1.0)
    check(band_db(x, f0 / 4) > -6, "SUB2 127: strong partial at f/4 (%.1f dB)" % band_db(x, f0 / 4))
    # SUBX: the difference between SUBX 127 and SUBX 0 is (falling saw - square) of the sub alone. Its odd
    # harmonics are -2/(pi k), its even ones 2/(pi k): harmonic 2 then holds 1/(4 * 1.234 + 4 * 0.411)
    # of the energy, -8.2 dB. (Were the saw rising, the odd ones would be -6/(pi k) and harmonic 2 -16.6 dB.)
    a = play(SAW, [0, 0, 0, 0, 0, 127, 0], 36, 1.0)
    b = play(SAW, [0, 0, 0, 0, 127, 127, 0], 36, 1.0)
    f1 = note_hz(36) / 2
    h2 = band_db(b - a, 2 * f1)
    check(abs(h2 - (-8.2)) < 1.0, "SUBX 127 - SUBX 0 is falling saw - square: harmonic 2 at %.1f dB (-8.2 expected)" % h2)
    h1a, h1b = band_db(a, f1), band_db(b, f1)
    check(abs(h1b - h1a) < 4, "SUBX keeps the sub's fundamental (%.1f dB square, %.1f dB saw)" % (h1a, h1b))

    print("SAW unison")
    f0 = note_hz(57)
    for uniw in (40, 127):
        det = 50 * (uniw / 127) ** 2
        up = f0 * 2 ** (det / 1200)
        x = play(SAW, [127, uniw, 0, 0, 0, 0, 0], 57, 2.0)
        check(band_db(x, up, 1.0) > -12, "UNIW %d: a partial %.2f cents up at %.2f Hz (%.1f dB)" % (uniw, det, up, band_db(x, up, 1.0)))
    x = play(SAW, [0, 127, 0, 0, 0, 0, 0], 57, 2.0)
    check(band_db(x, f0 * 2 ** (50 / 1200), 1.0) < -60, "UNIL 0: no unison partial (%.1f dB)" % band_db(x, f0 * 2 ** (50 / 1200), 1.0))
    counts = []
    for unix in (0, 64, 127):
        x = play(SAW, [127, 127, unix, 0, 0, 0, 0], 57, 2.0)
        seen = sum(band_db(x, f0 * 2 ** (c / 1200), 1.0) > -20 for c in (50, -50, 25))
        counts.append(seen)
    check(counts == [1, 2, 3], "UNIX 0 / 64 / 127: %s unison saws (+50, -50, +25 cents)" % counts)

    print("PULS duty and PWM")
    for pw in (16, 64, 112):
        x = play(PULS, [0, 0, 0, 0, pw, 0, 0], 33, 1.0)
        d = float(np.mean(x > np.mean(x)))
        want = (32768 + (pw - 64) * 500) / 65536           # the part of a cycle above the mean
        check(abs(d - want) < 0.01, "PW %d: duty %.3f (expected %.3f)" % (pw, d, want))
    inc50 = round(2 ** 32 * 50 / FS)                   # 50 Hz: 960 samples a cycle, duty over whole cycles
    duty = lambda y: float(np.mean(y > np.mean(y)))
    e = Engine(PULS, [0, 0, 0, 0, 64, 127, 64]); e.trig()
    d = [duty(e.render(960, inc=inc50)) for _ in range(60)]
    check(max(d) - min(d) > 0.5, "PWAD 127 PWRS 64: duty swings %.2f..%.2f" % (min(d), max(d)))
    e = Engine(PULS, [0, 0, 0, 0, 64, 0, 64]); e.trig()
    d = [duty(e.render(960, inc=inc50)) for _ in range(60)]
    check(max(d) - min(d) < 0.01, "PWAD 0: duty holds (%.3f..%.3f)" % (min(d), max(d)))

    print("ENS")
    f0 = note_hz(48)
    for pch, st in (((67, 70, 75), (4, 7, 12)), ((51, 63, 99), (-12, 0, 36))):
        x = play(ENS, [pch[0], pch[1], pch[2], 0, 64, 0, 0], 48, 2.0)
        # oscillators 2..4 also carry the fixed ensemble spread: +4, -4, +7 cents
        lv = [band_db(x, f0 * 2 ** (s / 12 + c / 1200), 1.5) for s, c in zip(st, (4, -4, 7))]
        check(all(v > -25 for v in lv), "PCH2..4 = %s: partials at +%s semitones (%s dB)" % (pch, st, ["%.1f" % v for v in lv]))
    a = play(ENS, [63, 63, 63, 0, 64, 0, 0], 48, 1.0)
    b = play(ENS, [63, 63, 63, 127, 64, 0, 0], 48, 1.0)
    ev_a, ev_b = band_db(a, 2 * f0, 2), band_db(b, 2 * f0, 2)
    check(ev_b < ev_a - 20, "WAVE 0 -> 127 at PW 64: 2nd harmonic %.1f -> %.1f dB (saw -> square)" % (ev_a, ev_b))
    a = play(ENS, [63, 63, 63, 0, 64, 0, 127], 48, 2.0)
    b = play(ENS, [63, 63, 63, 0, 64, 127, 127], 48, 2.0)
    diff = 20 * math.log10(np.std(b - a) / np.std(a))
    check(diff > -20, "CHRL 127 changes the sound (difference %.1f dB)" % diff)
    b0 = play(ENS, [63, 63, 63, 0, 64, 127, 0], 48, 2.0)
    s1, f = spectrum(b)
    s0, _ = spectrum(b0)
    m = (f > f0 * 0.97) & (f < f0 * 1.03)
    wid = lambda s: float(np.sqrt((s[m] * (f[m] - f0) ** 2).sum() / s[m].sum()))
    check(wid(s1) > wid(s0) * 1.3, "CHRW 127 widens the fundamental (%.2f Hz vs %.2f Hz at CHRW 0)" % (wid(s1), wid(s0)))

    print("NOIS")
    cen = lambda x: float((spectrum(x)[0] * spectrum(x)[1]).sum() / spectrum(x)[0].sum())
    w, r = play(NOIS, [0, 0, 0] + [0] * 4, 60, 1.0), play(NOIS, [0, 100, 0] + [0] * 4, 60, 1.0)
    check(cen(r) < cen(w) / 4, "RED 100 darker: centroid %.0f Hz -> %.0f Hz" % (cen(w), cen(r)))
    check(abs(20 * math.log10(np.std(r) / np.std(w))) < 12, "RED keeps the level within 12 dB (%.1f dB)" % (20 * math.log10(np.std(r) / np.std(w))))
    h = play(NOIS, [127, 0, 0] + [0] * 4, 60, 1.0)
    runs = np.mean(np.diff(h) != 0)
    check(runs < 0.02, "ST 127: sample and hold, a new value every %.0f samples" % (1 / max(runs, 1e-9)))
    check(cen(h) < cen(w) / 4, "ST 127 darker (centroid %.0f Hz)" % cen(h))
    # STON: sample and hold clocked twice a cycle of the note, so its values repeat in no way but its
    # changes are locked to the pitch: the spectrum's nulls fall at multiples of 2 f (sinc of the hold)
    # and the time between changes is exactly half a period.
    t = play(NOIS, [0, 0, 127] + [0] * 4, 57, 1.0)
    ch = np.flatnonzero(np.diff(t))
    gaps = np.diff(ch)
    half = FS / note_hz(57) / 2
    check(abs(float(np.mean(gaps)) - half) < 0.5 and gaps.max() - gaps.min() <= 1,
          "STON 127: a new value every half period of the note (%.2f samples, expected %.2f)" % (np.mean(gaps), half))
    null, peak = band_db(t, 2 * note_hz(57), 3), band_db(t, note_hz(57), 3)
    check(null < peak - 20, "STON 127: null at 2 f (%.1f dB) against f (%.1f dB)" % (null, peak))

    print("VO")
    VOW = {"oo": (0, 300, 870), "ah": (3, 730, 1090), "ee": (8, 270, 2290)}
    def formants(x, f0, f2lo):
        """F1 and F2 from the harmonics' levels: the strongest harmonic in 200..950 Hz, then above f2lo."""
        sp = np.abs(np.fft.rfft(x * np.blackman(len(x))))
        fr = np.fft.rfftfreq(len(x), 1 / FS)
        # each harmonic's level over the source's own (a saw, 1/k, through the one-pole low-pass
        # y += (x - y) / 4): what is left is the resonators' response
        src = lambda f: 0.25 / abs(1 - 0.75 * np.exp(-2j * np.pi * f / FS))
        hs = [(k * f0, sp[np.argmin(abs(fr - k * f0))] * k / src(k * f0)) for k in range(1, int(3200 / f0))]
        f1 = max((h for h in hs if 200 <= h[0] <= 950), key=lambda h: h[1])[0]
        f2 = max((h for h in hs if max(f2lo, f1 * 1.45) <= h[0] <= 2700), key=lambda h: h[1])[0]
        return f1, f2
    f0 = note_hz(36)
    for name, (k, F1, F2) in VOW.items():
        voc = int(math.ceil(k * 127 / 9))
        x = play(VO, [voc, voc, 0, 0, 0, 0, 0], 36, 1.0)
        e1, e2 = formants(x[FS // 4:], f0, 700)
        check(abs(e1 / F1 - 1) < 0.2 and abs(e2 / F2 - 1) < 0.2,
              "VOC %s: F1 %.0f Hz (%d), F2 %.0f Hz (%d)" % (name, e1, F1, e2, F2))
    e = Engine(VO, [0, 113, 64, 0, 0, 0, 0]); e.trig()               # oo -> ee (VOC 113)
    x = e.render(FS, note=36)
    a2 = formants(x[:2400], f0, 700)[1]
    b2 = formants(x[FS // 2:], f0, 700)[1]
    check(b2 > a2 + 800, "V-SW 64, oo -> ee: F2 %.0f Hz at the start, %.0f Hz after 0.5 s" % (a2, b2))
    x0 = play(VO, [127, 127, 0, 0, 0, 0, 0], 36, 1.0)
    check(abs(formants(x0[FS // 2:], f0, 700)[1] - formants(x0[:2400], f0, 700)[1]) < 150,
          "V-SW 0: the vowel stays")
    def hi(x):
        sp = np.abs(np.fft.rfft(x * np.hanning(len(x)))) ** 2
        fr = np.fft.rfftfreq(len(x), 1 / FS)
        return 10 * math.log10(sp[fr > 4000].sum() + 1e-12)
    xs = play(VO, [43, 43, 0, 0, 16, 90, 127], 36, 1.0)             # CONS 16: S
    check(hi(xs[:1440]) > hi(xs[FS // 2:FS // 2 + 1440]) + 15,
          "CONS S: noise above 4 kHz at the start %.1f dB over the held vowel's" % (hi(xs[:1440]) - hi(xs[FS // 2:FS // 2 + 1440])))
    xn = play(VO, [43, 43, 0, 0, 0, 90, 127], 36, 1.0)
    check(abs(hi(xn[:1440]) - hi(xn[FS // 2:FS // 2 + 1440])) < 6, "CONS 0: no burst")
    xv = play(VO, [43, 43, 0, 0, 0, 0, 0], 57, 1.0)
    pv = peak_hz(xv[FS // 4:], 200, 240)
    check(abs(cents(pv, note_hz(57))) < 1, "pitch: fundamental %.2f Hz at note 57 (%.2f)" % (pv, note_hz(57)))
    lv = 20 * math.log10(np.std(xv) / np.std(play(SAW, [0] * 7, 57, 1.0)))
    check(-18 < lv < 3, "level: %.1f dB against a plain saw" % lv)

    print("all machines, random settings")
    rnd = random.Random(1)
    worst_dc = 0
    for i in range(120):
        m = rnd.randrange(6)
        prm = [rnd.randrange(128) for _ in range(7)]
        note = rnd.uniform(36, 120)
        x = play(m, prm, note, 1.0)
        check_ok = np.all(np.isfinite(x)) and np.max(np.abs(x)) <= 1.0
        if not check_ok:
            check(False, "%s %s note %.1f bounded" % (NAMES[m], prm, note))
        if m != NOIS:
            worst_dc = max(worst_dc, abs(float(np.mean(x[FS // 20:]))))
    check(worst_dc < 0.01, "no DC offset above 1 %% of full scale (worst %.4f)" % worst_dc)
    same = True
    for m in (SIN, SAW, NOIS):
        prm = [rnd.randrange(128) for _ in range(7)]
        a = play(m, prm, 50.3, 0.1, block=32)
        b = play(m, prm, 50.3, 0.1, block=7)
        same &= bool(np.array_equal(a, b))
    check(same, "SIN / SAW / NOIS: the same samples in 32- or 7-frame blocks (state carries across blocks)")

    print()
    if FAIL:
        print("%d FAILED" % len(FAIL))
        sys.exit(1)
    print("ALL SIGNAL CHECKS PASSED")


if __name__ == "__main__":
    main()
