# Digi Mono: Monomachine-style synth machines for the Digitakt mk1

Status: **engine built and verified in emulation; not yet hooked into the firmware** (no `mod.json` yet,
so `tools/build_elemods.py` does not build it and nothing about it reaches a unit).

## What it is

New SRC machines for the audio tracks that make their sound with oscillators instead of samples,
after the Monomachine's GND and SWAVE machines:

| machine | Monomachine name | what it plays |
|---|---|---|
| `SIN`  | GND-SIN    | a sine |
| `NOIS` | GND-NOIS   | noise: sample and hold (ST), darker (RED), pitched (STON) |
| `SAW`  | SWAVE-SAW  | band-limited saw, 1-3 detuned unison saws, two sub-oscillators (square..saw) |
| `PULS` | SWAVE-PULS | band-limited pulse with PWM, 2 detuned unison pulses, two square subs |
| `ENS`  | SWAVE-ENS  | four oscillators at set intervals, saw..pulse, with a chorus |

The engine renders a voice's oscillator as 16-bit mono samples, the form a sample voice's data has.
The Digitakt's own filter, amp envelope, LFOs, send effects and p-locks then work on it unchanged.

## Why a rewrite and not a port

The Monomachine's machines are DSP56300 assembly inside the Monomachine OS file. Monomodule
(github.com/shnolk/monomodule) runs that code in a DSP56300 emulator, at about 21 million DSP
instructions a second for one voice (figure from sd88me/mpc-vst-monomodule, HANDOFF.md). Each DSP56300
instruction does a multiply-accumulate and two parallel moves, which is several ColdFire instructions.

The Digitakt mk1 has no DSP: its render runs on the main ColdFire. digihealth measured it on a unit at
80.5 % load, or 72 % with FAST AUDIO, so about a quarter is free. A translation of the original code would
need several times that for one voice. It would also mean distributing (or building on the user's machine)
code derived from Elektron's DSP program. The sd88me MPC port needed a whole static recompiler to reach
real time on a faster ARM chip.

So this engine is written from scratch, in plain C. The sources are the Monomachine manual's machine and
parameter names and what the manual says each one does. It contains no Elektron code or data, and it is not
sample-exact to a Monomachine. Where the manual leaves a parameter's exact behaviour open, the
choices below are this engine's own. Check them by ear against a Monomachine or Monomodule (see
"A/B against the real thing").

## The engine (`mono.h`, `mono.c`, `mono_tables.h`)

- **API:** `mono_init`, `mono_trig` (note start), `mono_render(voice, machine, p[7], inc, out, n)`,
  `mono_pitch_inc(pitch)`. One `struct mono_voice` per voice, 1,072 bytes (1 KB of it is the ENS chorus
  delay line).
- **Pitch:** a 32-bit phase increment per 48 kHz sample, taken as constant over a block.
  `mono_pitch_inc` makes one from a note in 1/128 semitone, within 0.013 cent. The fundamental is capped
  at 12 kHz.
- **Numbers:** 32-bit integers only. No 64-bit maths, no floating point, no library calls (the
  MCF54455 has no FPU, and elekloader links with `-nostdlib`). It builds with elekloader's Digitakt mk1
  flags (`-mcpu=54455 -O2 -ffreestanding ...`) and for a PC, and both builds give the same samples.
- **Band-limiting:** polyBLEP. Every jump of a saw, square or pulse is smoothed by a two-sample
  polynomial, and the division that needs runs only on the one or two samples next to a jump.
- **Tables** (`tools/gen_mono_tables.py`, plain maths): sine, note increments, fine tune, intervals,
  detune curve, level curve, LFO rates.
- **Levels:** oscillator levels whose sum is over 1 are scaled back to 1 per block. The output
  saturates to 16 bits.

### The parameters

`p[0..6]` are the Monomachine SYN page's first seven knobs (raw 0..127). Its eighth, TUNE, is the
Digitakt's own SRC TUNE, which reaches the engine through the phase increment.

| | p0 | p1 | p2 | p3 | p4 | p5 | p6 |
|---|---|---|---|---|---|---|---|
| SIN  | - | - | - | - | - | - | - |
| NOIS | ST | RED | STON | - | - | - | - |
| SAW  | UNIL | UNIW | UNIX | - | SUBX | SUB1 | SUB2 |
| PULS | UNIL | UNIW | SUB1 | SUB2 | PW | PWAD | PWRS |
| ENS  | PCH2 | PCH3 | PCH4 | WAVE | PW | CHRL | CHRW |

This engine's reading of each parameter:

- **UNIL** level of the unison oscillators; **UNIW** their detune, 0..50 cents (curve (v/127)^2,
  fine at the bottom).
- **UNIX** (SAW) how many unison saws: 0-42 one (+w), 43-85 two (+w, -w), 86-127 three (+w, -w, +w/2).
- **SUB1 / SUB2** levels of the sub-oscillators one and two octaves down, locked to the main oscillator.
  **SUBX** (SAW) fades them from square to a (falling) saw.
- **PW** pulse width, 64 = 50 %, 1.2 %..98.4 %. **PWAD** PWM depth. **PWRS** PWM rate, 0.05..20 Hz
  (triangle).
- **PCH2..4** (ENS) oscillators 2-4 in semitones from oscillator 1, 63 = the same pitch, -36..+36.
  The oscillators also carry a fixed spread of +4, -4 and +7 cents. Without it, four oscillators at one
  pitch lock into a comb whose timbre depends on their random start phases, and a note can lose its
  fundamental. **WAVE** saw (0) to pulse (127). **CHRL / CHRW** chorus level and width (a 7 ms delay swung
  by up to +-2.5 ms at 0.6 Hz).
- **ST** (NOIS) sample and hold: 0 = white, up = fewer new values a second (about 20 kHz down to
  65 Hz). **RED** a one-pole low-pass (about 60 Hz at 127) with make-up gain. **STON** mixes in a sample
  and hold clocked at twice the note's pitch, so the noise becomes pitched.

## Verified (in software)

`python3 tests/mono_signal.py` (PC build, numpy) measures what each parameter does. Results:

- **Pitch:** fundamental within 0.35 cent of the note on SIN, SAW, PULS and ENS, notes 24..108.
- **SIN:** harmonics below -118 dB.
- **Aliasing** at notes 84 / 96 / 103: SAW -31 / -28 / -26 dB and PULS -32 / -32 / -30 dB, against
  -16 / -13 / -11 dB for a naive oscillator.
- **Subs:** each sits at 1/2 or 1/4 of the pitch. SUBX's square-to-saw difference has exactly the
  spectrum it should (harmonic 2 at -8.2 dB).
- **Unison:** partials at the detune UNIW asks for, and UNIX gives 1, 2 or 3 unison saws.
- **PULS:** duty within 1 % of PW. PWAD 127 swings it from 5 % to 94 %, and PWAD 0 holds it.
- **ENS:** intervals where PCH puts them. WAVE 127 at PW 64 removes the 2nd harmonic (-94 dB), and the
  chorus widens the fundamental.
- **NOIS:** RED moves the centroid from 12 kHz to 1.2 kHz within 5 dB of level. ST holds values, and
  STON changes value exactly every half period of the note.
- **Random settings:** 120 random settings and pitches stay bounded, with no DC above 0.4 % of full
  scale. The output is the same whatever the block size.

`python3 tests/emu_mono.py` builds the engine for the Digitakt's CPU and runs it on an emulated
ColdFire V4e (unicorn):

- **Bit-exact:** over 80 voices and 1,920 blocks (random machines, settings, pitches, block sizes,
  re-trigs), every sample and the voice state after every block equal the PC build's.
- **Calling convention:** the C calling convention is kept.
- **Linking:** the object needs no library code (9.3 KB of code and tables).

**Cost**, in instructions per voice per 32-frame block at note 48. The stock render is about 84,000
instructions a block; a block is 166,667 cycles at 250 MHz.

| machine | light | heavy (every oscillator and effect on) |
|---|---|---|
| SIN  | 610   | 610   |
| NOIS | 1,086 | 1,592 |
| SAW  | 1,218 | 5,733 |
| PULS | 1,437 | 5,491 |
| ENS  | 3,005 | 5,959 |

What this means for the CPU:

- **Light settings fit.** One SAW voice at light settings adds about 1.5 % to the render, and eight
  about 12 %, within the quarter digihealth measured free.
- **Heavy settings on all eight tracks don't fit yet.** That would be about 55 % more.
- **What a synth voice saves is not measured yet.** It also skips the sample fetch and interpolation
  it replaces, but by how much is still to be seen.
- **The first optimisation is known.** gcc's inner saw loop is about 19 instructions a sample (it reloads
  constants and compares against the stack). A hand-written ColdFire loop should need about 9, which
  roughly halves the heavy settings.

## Integration: what is left

The engine is the half that needed no firmware. The other half needs the stock OS 1.53 file and digiemu,
which this work was done without. In order:

1. **Machine entries.** Add `MONO SIN`, `MONO NOIS`, `MONO SAW`, `MONO PULS` and `MONO ENS` to the
   FUNC+SRC list through core's `core_machines`, as digislicer does. Ids 4 (POLY) and 5 (DIGISLICER)
   are taken, so these would be ids 6..10. The kit load clamps unknown machine bytes
   (`0x4007a2d0`, `moveq #5,d2` → ONESHOT; see "POLY lost on reload" in docs/TECHNICAL_NOTES.md), so
   the clamp must let them through. The render's own reads of the machine byte (`0x4007725a` →
   `0x800018BC[voice]`) must treat them as ONESHOT everywhere except the sample fetch. That is the
   same aliasing Digi Poly uses.
2. **Parameters, with no new storage.** A MONO voice's SRC knobs other than TUNE and LEV (PLAY, BIT,
   SRR, SAMP, STRT, LEN, LOOP) become `p[0..6]`. Those are parameter slots the stock engine already
   copies, smooths per block (`0x40074b9e`, words at `0x80002772 + 106*v`), p-locks, LFO-modulates
   and saves with the sound. So MONO's knobs get all of that for free, and a stock OS loading the
   project sees an ordinary ONESHOT sound. What is left is the SRC page's labels and value text for
   MONO machines (the digislicer `play_fmt` / `grid_fmt` sites show where the page formats values).
3. **The render hook (the real work).** Find, in the render, where a voice reads its sample data at its
   playback rate. digislicer's sites are next to it: the SLICE window at `0x40074df2`, and the PLAY
   reads at `0x40075282` (voice 0) and `0x400759dc` (voices 1-7), which are two copies of the loop.
   For a MONO voice, skip the fetch and have `mono_render` write the voice's 32 samples, with
   `inc = rate × 2^32 × 261.63 / 48000` from the rate the stock computed (a C4-rooted sample at rate 1.0
   plays 261.63 Hz). That way note, TUNE, pitch LFO and portamento come from the stock pitch path. Which
   rate format and where the fetched samples go are exactly what digiemu has to show. Also call
   `mono_trig` where a voice starts a note (the type-3 message in the audio ISR, `0x40077420`), and
   make sure a MONO voice plays with no sample loaded.
4. **Memory:** 8 × 1,072 bytes of voice state and 9.3 KB of code and tables, all in the loader's DDR
   area.
5. **Tests**, in the pattern of the other mods:
   - `tests/emu_mono_hook.py`: the hook against the stock render in unicorn.
   - `tests/digiemu_mono.py`: select the machine, turn knobs, play notes, and check the output's pitch
     and spectrum against `mono_signal.py`'s expectations through the real filter and amp.
   - A CPU check with digihealth's SYSTEM INFO on the unit.

## A/B against the real thing

`tools/mono_render.py` writes this engine's oscillator to a WAV file.
Monomodule's `mnm-render` does the same with the real Monomachine DSP code, from your own Monomachine
OS 1.32B file. Use the same `--syn` values in both; the tool's help has both command lines. That is how
the parameter readings above should be tuned: by ear and by spectrum against the original, with the
Monomachine's code only ever running on your own machine.

## Files

| file | what |
|---|---|
| `mods/digimono/mono.h`, `mono.c` | the engine |
| `mods/digimono/mono_tables.h` | generated by `tools/gen_mono_tables.py` (`--check` verifies it is current) |
| `tests/mono_lib.py` | the PC build, loaded with ctypes |
| `tests/mono_signal.py` | what each machine and parameter does, measured |
| `tests/emu_mono.py` | the ColdFire build: bit-exact against the PC build, and its cost |
| `tools/mono_render.py` | render to WAV |
