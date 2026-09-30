#!/usr/bin/env python3
"""Render Digi Mono's engine to a WAV file, to listen to it or hold it against a Monomachine.

    python3 tools/mono_render.py --machine SAW --syn 127,90,64,0,0,100,0 --note 48 --dur 2 --out saw.wav

--syn is the seven parameters p[0..6] in the engine's order (mods/digimono/mono.h): the Monomachine SYN
page's first seven knobs, raw 0..127 as a kit stores them. The same numbers go to Monomodule's
offline renderer (github.com/shnolk/monomodule, src/cli/mnm_render.cpp), which runs the real Monomachine
DSP code from your own Monomachine OS file, for an A/B by ear:

    mnm-render --machine "SWAVE SAW" --syn 127,90,64,0,0,100,0,64 --note 48 --dur 2 \\
               --amp 0,0,127,127,64,127,64,0 --filt 0,127,0,0,0,32,64,64 --out saw_mnm.wav

(the eighth --syn value there is TUNE, 64 = none; the --amp / --filt values hold the amp open and the
filters out of the way, so both files are the bare oscillator). Monomodule plays at 44.1 kHz and this
engine at the Digitakt's 48 kHz.

The output here is the oscillator alone, 48 kHz mono 16-bit: the Digitakt's own filter, amp and effects
come after it on the unit.
"""
import argparse, os, sys, wave

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tests"))
import numpy as np
import mono_lib as H

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("--machine", required=True, choices=H.NAMES)
ap.add_argument("--syn", default="0,0,0,0,0,0,0", help="seven values 0..127 (default all 0)")
ap.add_argument("--note", type=float, default=60.0, help="MIDI note, fractions allowed (default 60)")
ap.add_argument("--dur", type=float, default=2.0, help="seconds (default 2)")
ap.add_argument("--retrig", type=float, default=0.0, help="re-trigger every N seconds (default: never)")
ap.add_argument("--out", required=True)
a = ap.parse_args()

syn = [int(x) for x in a.syn.split(",")]
if len(syn) != 7 or not all(0 <= x <= 127 for x in syn):
    sys.exit("--syn needs seven values 0..127")
e = H.Engine(H.NAMES.index(a.machine), syn)
e.trig()
total = int(a.dur * H.FS)
step = int(a.retrig * H.FS) if a.retrig > 0 else total
parts, done = [], 0
while done < total:
    n = min(step, total - done)
    parts.append(e.render(n, note=a.note))
    done += n
    e.trig()
x = np.concatenate(parts)
with wave.open(a.out, "wb") as w:
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(H.FS)
    w.writeframes(np.clip(np.round(x * 32768), -32768, 32767).astype("<i2").tobytes())
print("wrote %s: %s %s note %g, %.2f s" % (a.out, a.machine, syn, a.note, a.dur))
