# Digi Mono: Monomachine-style synth machines for the Digitakt mk1

Status: **built, checked in emulation (digiemu, the real OS 1.53 firmware); not yet run on a unit.**
An elekloader mod (`digimono`, 0.6) that needs **core 2.1**. It shares a build with digisophie.

## What it is

Five new SRC machines for the audio tracks. They make their sound with oscillators instead of samples,
after the Monomachine's GND and SWAVE machines:

| machine (menu) | after | what it plays |
|---|---|---|
| `MONO SIN`   | GND-SIN    | a sine |
| `MONO NOISE` | GND-NOIS   | noise: sample and hold (ST), darker (RED), pitched (STON) |
| `MONO SAW`   | SWAVE-SAW  | band-limited saw, 1-3 detuned unison saws, two sub-oscillators (square..saw) |
| `MONO PULSE` | SWAVE-PULS | band-limited pulse with PWM, 2 detuned unison pulses, a square sub |
| `MONO ENS`   | SWAVE-ENS  | four oscillators at set intervals, saw..pulse, with a chorus |
| `MONO VO`    | VO-6       | a formant voice: vowel 1 gliding to vowel 2, consonants at the note's start |

They are picked like any machine: FUNC+SRC, after SLICE. A Digi Mono track needs no sample. Its trigs,
note locks, TUNE, the FLTR, AMP and LFO pages, the sends, p-locks and the track level work on it as on a
sample: the engine's output goes to the voice where the resampled sample would have been.

## Why a rewrite and not a port

The Monomachine's machines are DSP56300 assembly inside the Monomachine OS file. Monomodule
(github.com/shnolk/monomodule) runs that code in a DSP56300 emulator, at about 21 million DSP
instructions a second for one voice. The Digitakt mk1 has no DSP. Its render runs on the main ColdFire,
about 80 % loaded as it is (72 % with digihealth's FAST AUDIO, measured on a unit). So running the
original code even for one voice would cost several times the CPU there is. It would also mean
distributing, or building from the user's file, code derived from Elektron's DSP program.

This engine is written from scratch in plain C. Its only source is the Monomachine manual: the machine
names, the parameter names and what each is described to do. It contains no Elektron code or data, and it
is not sample-exact to a Monomachine. Where the manual leaves a parameter's behaviour open, the choices
below are this engine's own. Check them by ear against a Monomachine, or against Monomodule running your
own Monomachine OS file (`tools/mono_render.py` has the A/B commands).

## The engine (`mono.h`, `mono.c`, `mono_tables.h`)

- **API:** `mono_init`, `mono_trig` (note start), `mono_render(voice, machine, p[7], inc, out, n)` and
  `mono_pitch_inc(pitch)`. `struct mono_voice` is 1,072 bytes, 1 KB of it the ENS chorus delay line.
- **Arithmetic:** 32-bit integers only: no 64-bit maths, no floating point, no library calls. It builds
  with elekloader's Digitakt mk1 flags and for a PC, and the two builds give the same samples.
- **Band-limiting:** polyBLEP. Each jump of a saw, square or pulse is smoothed by a two-sample polynomial.
- **Tables:** `tools/gen_mono_tables.py`, plain maths.
- **Levels:** oscillator levels whose sum is over 1 are scaled back to 1 per block. The output saturates
  to 16 bits.

### The parameters and the SRC page

The engine takes seven parameters, `p[0..6]`: the Monomachine SYN page's first seven knobs, raw 0..127.
TUNE (its eighth) is the Digitakt's own SRC TUNE.

On the Digitakt, knob A stays TUNE and D stays SAMP (the sample slot, unused by these machines). The six
other SRC knobs carry the parameters, 0..127, under the machine's own names:

| machine | B | C | E | F | G | H | not on a knob |
|---|---|---|---|---|---|---|---|
| SIN   | - | - | - | - | - | - | |
| NOISE | ST | RED | STON | - | - | - | |
| SAW   | UNIL | UNIW | UNIX | SUBX | SUB1 | SUB2 | |
| PULSE | UNIL | UNIW | SUB | PW | PWAD | PWRS | SUB2 (0) |
| ENS   | PCH2 | PCH3 | PCH4 | WAVE | CHRL | CHRW | PW (64 = square) |
| VO    | VOC1 | VOC2 | V-SW | CONS | CLEN | CVOL | VOIC (0: fully voiced) |

A switch to a Digi Mono machine sets that machine's defaults. For ENS these are the Monomachine's: PCH2-4
at 63, the same pitch.

What each parameter does, as this engine reads the manual:

- **UNIL** is the level of the unison oscillators, and **UNIW** their detune, 0..50 cents (curve
  (v/127)^2, fine at the bottom).
- **UNIX** (SAW) sets how many unison saws play: 0-42 one (+w), 43-85 two (+w, -w), 86-127 three
  (+w, -w, +w/2).
- **SUB1 / SUB2** (PULSE: **SUB**) are the levels of the sub-oscillators one and two octaves down,
  locked to the main oscillator. **SUBX** (SAW) fades them from square to a falling saw.
- **PW** is the pulse width: 64 = 50 %, range 1.2 %..98.4 %. **PWAD** is the PWM depth and **PWRS** the
  PWM rate, 0.05..20 Hz (triangle).
- **PCH2..4** (ENS) put oscillators 2-4 in semitones from oscillator 1: 63 = the same pitch, range
  -36..+36. The oscillators also carry a fixed spread of +4, -4 and +7 cents. Without it, four
  oscillators at one pitch lock into a comb whose timbre depends on their random start phases, and a note
  can lose its fundamental.
- **WAVE** (ENS) fades from saw (0) to pulse (127). **CHRL / CHRW** are the chorus level and width: a
  7 ms delay swung by up to +-2.5 ms at 0.6 Hz.
- **VO** is a glottal source through three vowel resonators:
  - **The source:** a band-limited saw through a one-pole low-pass; VOIC mixes in breath noise.
  - **The vowels:** the resonators sit at the vowel's first three formants, from published averages of
    measured male vowels (Peterson and Barney, 1952). VOC1 and VOC2 pick vowels along a continuum OO, U,
    AW, AH, UH, AE, EH, IH, EE, ER, and their values show as those names.
  - **The glide:** V-SW glides from VOC1 to VOC2 after the note starts, 5 ms..2 s; 0 keeps VOC1.
  - **The consonant:** CONS picks one of 8 zones: none, S, SH, F, H, T, K, P. Each is a band of noise at
    the note's start that decays over CLEN (2..400 ms; the plosives T, K and P at most 30-40 ms) at level
    CVOL. The vowel fades in under it.
  - **Checks** (tests/mono_signal.py):
    - the formants of OO, AH and EE land within 20 % of the table: OO 327 / 916 Hz, AH 719 / 1112 Hz,
      EE 262 / 2289 Hz;
    - OO -> EE raises F2 over the glide;
    - an S puts a burst 45 dB above the held vowel's above 4 kHz;
    - the fundamental is exact;
    - the level is about 9 dB under a plain saw.
- **ST** (NOISE) is sample and hold: 0 = white; up = fewer new values a second, about 20 kHz down to
  65 Hz. **RED** is a one-pole low-pass (about 60 Hz at 127) with make-up gain. **STON** mixes in a sample
  and hold clocked at twice the note's pitch, which makes the noise pitched.

## How it sits in the firmware (OS 1.53; details in docs/TECHNICAL_NOTES.md)

- **Machines:** six descriptors in core 2.1's `core_machines`, ids 20..25, clear of NEIGHBOR / POLY (4),
  DIGISLICER (5) and SOPHIE (7). They have `params` = ONESHOT and `render` = ONESHOT, and digimono
  recognises its voices through core's `core_track_machine`.
- **Audio:** the voice loop `0x400757fe` resamples each voice's sample, 64 samples at 96 kHz. A half-band
  filter brings them to 48 kHz as 32 Q31 samples at `0x8000eb70`, and the filter stage `0x400761b8`
  reads them from there. Between the two, at `0x4007606e`, `digimono_rblock` overwrites the block of a
  Digi Mono voice with the engine's output (sample << 16: a full-scale 16-bit sample's level).
  - **Note starts** come from bit v of `0x80001228`.
  - **Pitch** is the note word `0x80001f28[v]` (MIDI note << 16) plus TUNE, `(word(17) - 16384) << 8`,
    in Q16 semitones. The render computes a sample's rate from the same inputs, so note locks, TUNE locks
    and pitch LFOs work. The knob words are the smoothed ones after the LFO stage
    (`0x80002772 + 106 v`), so LFOs and p-locks reach them too.
  - **A voice not playing** (its gain `0x8000edc4 + 94 v + 16` at 0, no start) is not rendered.
- **SRC page:** machines past the stock four get SLICE's page (parameter ids 0x84..0x8b). While the
  active track plays a Digi Mono machine, four entry hooks give B, C, E, F, G and H its values:
  - the short name, `0x4000fe8a`;
  - the long name, `0x4000feac`;
  - a 0..127 range, `0x40078f0c`;
  - plain numbers, `0x400657ee`.
- **Defaults:** `ev_tick` watches the UI kit for a switch.

## Verified

- **`tests/mono_signal.py`** (the engine, PC build) measures every machine and parameter:
  - **pitch:** within 0.35 cent over notes 24..108;
  - **SIN:** harmonics below -118 dB;
  - **aliasing:** against a naive oscillator, SAW -31 / -28 / -26 dB and PULSE -32 / -32 / -30 dB at notes
    84 / 96 / 103, where the naive one gives -16 / -13 / -11;
  - **subs:** at 1/2 and 1/4 of the pitch;
  - **unison:** partials at the detune UNIW asks for;
  - **PULSE:** duty within 1 % of PW, and a PWM swing;
  - **ENS:** the intervals and the chorus;
  - **NOISE:** the RED, ST and STON behaviour;
  - **random settings:** bounded, with no DC.
- **`tests/emu_mono.py`** runs the engine built for the ColdFire on an emulated ColdFire V4e. It equals the
  PC build bit for bit (80 voices, 1,920 blocks), keeps the C calling convention and needs no library code.
- **`tests/digiemu_mono.py`** boots a core 2.1 + digimono build of the real OS 1.53 in digiemu, puts each
  machine on track 1 of an empty pattern, turns knobs, records trigs and plays. For all five machines:
  - **machine:** the track takes it;
  - **defaults and ranges:** the defaults land, and turned knobs move over 0..127;
  - **starts:** the voice starts at every trig;
  - **samples:** every block the voice hands on (over 21,000 a run) equals the engine's own, replayed on
    the PC from the same starts, notes and knob words, bit for bit; a voice not playing is silence;
  - **master:** the master mix has the note (262 Hz at C4) or, for ENS, the note and its PCH intervals.

## Cost

Measured in the real render: instructions a block in the mods' code (core + digimono) while track 1
plays. The stock render is about 84,000 a block.

| | instructions a block |
|---|---|
| MONO SAW at its defaults | ~2,400 |
| MONO SAW, every oscillator on | ~5,900 |
| MONO ENS with the chorus | ~6,600 |
| a Digi Mono track not playing | ~100 |

Each playing Digi Mono voice adds 3-8 % to the render. The render already runs at about 80 % (72 % with
FAST AUDIO), so **two to four Digi Mono tracks playing at once is the safe range until it is measured on
a unit** with digihealth's SYSTEM INFO. Eight heavy ones would overload it. Ways to make it cheaper:

- **hand-written inner loops:** gcc's saw loop is about 19 instructions a sample, and a hand-written
  ColdFire loop should need about 9;
- **the `.fast` section:** placing the inner loops in on-chip SRAM, as FAST AUDIO does with the stock
  render;
- **skipping silent voices:** not rendering a voice whose amp envelope has closed (the envelope is applied
  after the filter stage and has not been located yet).

## The Digitakt's pages on a Digi Mono track (0.5, tests/digiemu_mono_fx.py)

0.3 wrote the engine's block right after the resampler (0x4007606e). Measured at the codec output
in digiemu, that version ignored the AMP envelope and VOL. 0.5 renders the machines as ONESHOT, picks
Digi Mono voices by core's `core_track_machine`, and writes into `0x80001a18 + 128 v` after the voice
loop (0x40077fba), which is also where digisophie injects. The stages after that point work on the
block in place: 0x40072478, 0x40073280, 0x40073100, 0x40072300, then the mixer.

What works on a Digi Mono track in 0.5, measured on the firmware's own codec output:
- **AMP:** the envelope (HOLD and DEC down: notes sound 28 % of the time instead of 75 %) and PAN.
- **FLTR:** RESO, and FREQ, which darkens the voice.
- **LFO:** an LFO on a Digi Mono knob (PULSE PW) swings the pulse width 0.41..0.81.
- **VOL:** silences most of the voice.

**Open issue.** Part of the voice reaches the output unaffected by FREQ, VOL and the sends. Every stage
between the hook and the mixer processes the buffer in place, and the stock firmware makes no sound in
the same sequence, so this part comes from Digi Mono through a route not yet identified. Until it is
found, the FLTR and VOL checks of tests/digiemu_mono_fx.py fail, and a Digi Mono track can sound
brighter and louder than its FREQ and VOL settings say.

## Sharing a build with digisophie (0.6)

digisophie (github.com/soejrd/digisophie, MIT) adds SOPHIE, a metallic percussion machine, on the same
framework. 0.5 could not share a build with it: both claimed machine 7, and both patched four of the same
places. 0.6 moves or re-routes all five clashes:

| clash | 0.5 | 0.6 |
|---|---|---|
| machine id | 7 (MONO NOISE) | ids 20..25 |
| render hook | 0x40077fba, the same as digisophie's | 0x40077fc2 (`pea 0x80001a18`, done in the hook), one instruction later, so both run |
| short name | the entry 0x4000fe8a | its only caller, 0x40030daa (`keep2`), then on to 0x4000fe8a |
| long name | the entry 0x4000feac | its only caller, 0x40032d36 |
| value text | the entry 0x400657ee | its five callers (0x40032d16, 0x40038714, 0x40038854, 0x40039142, 0x400392ea) |

The range hook stays at the entry of 0x40078f0c; digisophie and digislicer wrap its callers, so their
wrappers reach it. Checked:

- **elekloader:** `elekloader.patch --check` accepts core + digimono + digisophie, and with digiutils,
  digimatrix and digieq added; core + digimono + digislicer also combine. digisophie and digislicer do
  not combine with each other: they wrap the same two range callers.
- **digiemu, the combined build:** MONO SAW and MONO VO pass tests/digiemu_mono.py bit for bit (with
  `--menu-before 1`, as SOPHIE is listed first), SOPHIE's own SRC page shows its knobs, and a SOPHIE
  track sounds.

## Other mods (checked with `elekloader.patch --check`, 2026-10-01)

| mod | what | with Digi Mono |
|---|---|---|
| digisophie 0.1.7 | SOPHIE percussion machine (id 7) | combines; checked in digiemu |
| digineighbor 0.6 (irpina) | NEIGHBOR machine (id 4) | combines; does not combine with digisophie (same SRC page entries) |
| DigiFilter 1.0i (DigiAlchemydsp) | filter TYPEs BP, BP2, COMB, TRASH | combines, also with digisophie or digineighbor |
| digislicer 2.0 | DIGISLICER machine (id 5) | combines; does not combine with digisophie (same range callers) |
| digiutils, digimatrix, digieq (this repo) | | combine |
| Digi Poly 1.0f (this repo) | POLY (id 4, core 2.0a) | does not combine (core 2.1's machine sites) |
| RingTone (DigiAlchemydsp) | master FX for the **Digitone** mk1 | another device: not applicable |

DigiFilter's notes place the stock per-voice filter: `0x40072844(params, buffer, active, voice)`, called
at 0x400780c4 for each voice on `0x80001a18 + 128 v` in place, after Digi Mono's block is written. So
DigiFilter's types should also act on Digi Mono tracks. The filter envelope's level per voice is at
0x4199df58 + 12 v (the stage 0x40073304); FREQ is params + 2.

## Known limits

- **Not run on a unit.** Only emulation so far (digiemu).
- **Needs core 2.1.** Digi Poly 1.0f patches six of the sites core 2.1 owns for its machine slots, so Digi
  Mono and Digi Poly 1.0f cannot be in one build until Digi Poly adds POLY through `core_machines`. Digi
  Mono combines with digiutils, digimatrix, digieq and digislicer (`elekloader.patch --check`).
- **No dials on the SRC page.** The SRC page draws no knob dials for these machines (as for a SLICE track
  without a sample); a knob's value shows while it turns.
- **Two parameters have no knob.** PULSE's SUB2 and ENS's PW are fixed.
- **The stock OS falls back.** A project saved with Digi Mono machines loads them as ONESHOT on the
  stock OS, or on a build without digimono.

## Files

| file | what |
|---|---|
| `mods/digimono/mod.json`, `glue.s` | the elekloader mod: machines, the render hook, the SRC page hooks |
| `tests/digiemu_mono_fx.py` | the FLTR, AMP and LFO pages on a Digi Mono track, in digiemu |
| `mods/digimono/digimono.c` | the render side, the SRC page's names, ranges and values, defaults on a switch |
| `mods/digimono/mono.h`, `mono.c` | the engine |
| `mods/digimono/mono_tables.h` | generated by `tools/gen_mono_tables.py` (`--check` verifies it is current) |
| `tests/mono_lib.py` | the PC build of the engine, loaded with ctypes |
| `tests/mono_signal.py` | what each machine and parameter does, measured |
| `tests/emu_mono.py` | the ColdFire build: bit-exact against the PC build, and its cost |
| `tests/digiemu_mono.py` | the mod in the real firmware (digiemu) |
| `tools/mono_render.py` | render the engine to WAV |
