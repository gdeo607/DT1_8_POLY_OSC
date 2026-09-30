# Usage

## Digi Poly (elekloader mod `digipoly`, 1.0c)
1. On any audio track press FUNC+SRC and choose **POLY** (after SLICE). The track keeps its sample, filter, amp
   and LFO settings as with any machine (POLY plays like ONESHOT).
2. **TRIG page**: on a POLY track it is the MIDI tracks' page: **NOT1** (the note), **NOT2-NOT4** (extra notes as
   semitone offsets from NOT1; the centre value = off), **VEL**, **LEN**, **PROB**, **LFO.T**, with the track's
   **LEV** fader beside them as on the other audio pages. Set them for the track, or hold a trig in grid recording
   and turn a knob to lock a step's own chord.
3. **Chords**: every trig plays NOT1 on the track's own voice and each of NOT2-NOT4 on a voice **borrowed** from
   another track. The borrowed voice plays the POLY track's whole sound and gets its own sound back at its own next
   trig. Which voice: the one whose last note started longest ago, never
   - a track you took out of the pool in SETTINGS > POLY,
   - a muted track,
   - a track with a trig at the same moment,
   - a voice holding a live note.
   With no voice left the extra note is skipped. Drum tracks that trig often are therefore borrowed last.
4. **Pressing the track's key** (its trig key, or a key of the FUNC+TRK keyboard) plays the whole chord. Recording
   still records the one note you played; the chord comes back from NOT2-NOT4 on playback.
5. **MIDI in**: notes on the POLY track's own MIDI channel play polyphonically, one voice per note: each note takes
   the track's own voice if it is free, else a borrowed one, and its note-off releases that same voice. No MIDI
   track or cable setup is needed.
6. **SETTINGS > POLY**: which tracks lend their voice to the POLY pool. LEFT/RIGHT choose a track (a bar over it),
   **YES** takes it out of the pool or puts it back. A track in the pool is shown inverted, and the checkbox on the
   left is ticked while the chosen track is in the pool. **This is part of the pattern**: it lives in the pattern's
   kit, so every pattern can lend different voices, and it is saved with the project and comes back after a
   power-off (since 2.0d; earlier builds lost it), like the sound settings around it. Loading a sound onto a
   track does not change it. Patterns that share a kit share the setting. Everything starts in the pool.
7. The POLY track's **LEVEL and every SRC / FLTR / AMP / LFO knob apply to the whole chord**, including voices
   borrowed later, while they are playing its notes.
8. Several tracks can be POLY; each plays its own chords.

## POLY (stand-alone builds and the earlier dt8poly mod)
1. On two or more audio tracks press FUNC+SRC and choose **POLY** (after SLICE). The lowest POLY track is the
   **control** track: its sample, filter and amp settings are used for every voice. Each POLY track keeps its own
   SRC TUNE and LFO.
2. **Sequencer**: trigs on the control track rotate across the POLY tracks.
3. **MIDI cable** (polyphonic playing/sequencing from a MIDI track):
   - Set the POLY tracks' MIDI *receive* channel to one channel, e.g. 13.
   - Set a MIDI track's *output* channel to the same channel. Notes and chords on that MIDI track (step-entered,
     live, or recorded from an external sequencer) now play the POLY tracks, one voice per note (free voice first,
     otherwise the oldest).
   - CCs (< 120) sent by that MIDI track are applied to all POLY tracks on the channel (e.g. filter sequencing).
   - Notes still go out of MIDI OUT as normal.

## Utility page (Scope or Spectrum, chosen at build time)
| key | action |
|---|---|
| "..." (three dots) | open the page (waveform or spectrum) -> X-Y -> close; in the all-views build: waveform -> spectrum -> X-Y -> close |
| YES | fullscreen on/off (main view only, no overlays) |
| NO | close the scope |
| PTN / BANK + trig | change pattern (scope stays open, green LEDs show patterns with data) |
| mutes, page keys, knobs, PLAY/STOP, FUNC combos | work as on the main screen |

- **Top bar**: pattern, name and tempo (hidden in fullscreen).
- **Bottom-right boxes**: tracks 1-8. Filled = the track just triggered (or a POLY note is held on its voice).
  A small line above a box marks a POLY track.
- **Bottom-left tuner**: note name, octave and cents (A4 = 440 Hz). `--` = no clear pitch or too quiet.
  It hears the main output: solo a track to tune it; a chord shows its common root.
- **Spectrum** (Spectrum build): bars 30 Hz (left) .. 20 kHz (right), about 60 dB tall; dots = falling peaks;
  small ticks under the bars at 100 Hz, 1 kHz, 10 kHz. Bass (< 350 Hz) is finer but reacts more slowly (170 ms window).
- **X-Y**: mono = vertical line, left-only = "\", right-only = "/", out of phase = horizontal, wide = cloud.
- Knobs change the parameters of the selected page while the scope is open (the page is hidden behind the scope;
  close it to read values).

## Digi utilities (elekloader mod `digiutils`, 1.8a and later)
- **Hold "..."** (about half a second) opens the page; a short press is the stock SONG MODE popup, so Song mode
  works as on the official OS (popup, EDIT, double press). Inside the page "..." cycles
  **waveform -> spectrum -> X-Y -> close**; NO closes. The page stays open through pattern / bank changes.

## Mod matrix (elekloader mod `digimatrix`, 1.0a and later)
**SETTINGS > MOD MATRIX** (YES on the row) opens a page of 8 routing slots. Each slot sends one LFO to one
parameter of one track:

```
MOD MATRIX                    DEP OWN
1 T1 L2 > T4 FLT.FREQ          32
2 T3 L1 > T3 AMP.PAN          -18  X
3 - - -
```

| control | what it does |
|---|---|
| UP / DOWN, or the LEVEL knob | choose a slot |
| YES | turn the slot on (it starts on the cursor's own track) or off again |
| NO | leave the page |
| knob A | source track, 1-8 |
| knob B | source LFO, 1 or 2 |
| knob C | destination track, 1-8 |
| knob D | destination parameter |
| knob E | depth, -64 .. +64 (2 a notch) |
| knob F | OWN: whether that LFO still modulates its own track's DEST as well (blank), or only what the matrix routes it to (`X`) |

- Destinations are named by their page: `SRC.A`..`SRC.H` (the track's SRC page, whatever its machine calls
  them), `FLT.TYPE`/`FREQ`/`RESO`/`ENV`/`ATK`/`DEC`/`SUS`/`REL`, `FLT2.A`..`FLT2.E` (the second filter page),
  `AMP.ATK`/`HOLD`/`DEC`/`OVER`/`DEL`/`REV`/`PAN`/`VOL`, and `L1.*` / `L2.*` (an LFO can modulate the other
  one's speed, depth, and so on).
- Each slot has its own depth, so one LFO can move four parameters by four different amounts. The LFO's own
  **DEP** on its LFO page keeps controlling only its own track's modulation.
- The source LFO runs as it always did: its SPD, MULT, WAVE, PHAS, FADE and trig MODE are on its own track's
  LFO page. A trig-mode LFO only moves when its own track trigs.
- The matrix is part of the **pattern's kit**: each pattern has its own, it is saved with the project and it
  survives power-off (since 2.0d). Loading a *sound* onto a track leaves the matrix as it is.
- A slot at depth 0, or one that is off, costs nothing audible: the whole matrix is about 0.4 % of the audio
  time even with all 8 slots on.

## Recording onto a POLY track (Digi Poly 1.0d and later)
With the sequencer recording, notes played into a POLY track - over MIDI on its own channel, or from the
unit's keyboard - are written into the step, not just as a trig: the lowest note goes into **NOT1** and
the next three into **NOT2-NOT4** as their offsets from it, so a chord of up to four notes comes back
from the piano roll. Notes arriving at the same step are gathered into one chord; a step that gets a
single note plays a single note (NOT2-NOT4 are cleared), so what you played is what you hear.

On the POLY track's TRIG page the **LEVEL knob sets the track level**, and the **LEV fader** in the left
column shows it - the same fader as on the audio pages, with the value shown for a moment after a turn.

## Master EQ (elekloader mod `digieq`, 1.0a and later)
A 4-band EQ on the **master mix** - main outputs, headphones and USB audio alike, like the
compressor - as a **master page**: FUNC+LFO steps through
**Compressor (1/4) -> Master EQ (2/4) -> Internal Mixer (3/4) -> External Mixer (4/4)**.
One page, one band per column (bands 1-4 = knobs A/E, B/F, C/G, D/H):

| knob | turn | after a **press** of that knob (press again to go back) |
|---|---|---|
| A-D | band level, -12 .. +12 dB in 0.5 dB steps | band **Q**, 0.3 .. 8 (16 steps) |
| E-H | band frequency, 20 Hz .. 20 kHz (128 steps, about a semitone a notch) | band **type**: HP, LSHF (low shelf), BELL, NTCH (notch), BP (band pass), HSHF (high shelf), LP |

- A knob switched to its second setting shows it inverted; the knob turned last is underlined.
- For BELL and shelves the level is the boost or cut. For HP, LP, BP and NTCH (12 dB/octave, resonance = Q)
  the level is that band's output level, and the band is always on.
- The graph: the EQ's response (0 dB dotted, +-12 dB top/bottom), band points 1-4 (the band last touched filled),
  ticks at 100 Hz, 1 kHz, 10 kHz.
- Defaults: 1 low shelf 78 Hz, 2 bell 398 Hz, 3 bell 2.5 kHz, 4 high shelf 9.9 kHz, all at 0 dB (the EQ is off
  until a band is changed).
- **Each pattern has its own EQ.** The settings live in the pattern's kit, so they are saved and loaded with
  the project and survive a power-off (since 2.0d). Loading a sound onto a track does not change them;
  loading a project brings back each pattern's own EQ at once. A pattern whose kit was made before this
  starts flat.
- **SETTINGS > GLOBAL FX/MIX > MASTER EQ** (with the firmware's own DELAY, REVERB, COMPRESSOR, INTERNAL MIXER
  and EXTERNAL MIXER): **on**, the EQ you can hear overrides every pattern's own - each pattern you reach is
  given these settings, so save the project if you want them kept; **off**, every pattern goes back to its
  own saved EQ.
- The LEVEL knob works as on every page. As on the other master pages, the title bar returns to the pattern name
  after a while.
- A band at 0 dB (bell/shelf) costs nothing; four active bands cost about 5 % of the audio time (see RISKS.md).

## Digi Mono (elekloader mod `digimono`, 0.3)
- **Pick a machine:** FUNC+SRC on an audio track, then scroll past SLICE: MONO SIN, MONO NOISE, MONO SAW,
  MONO PULSE, MONO ENS. YES to confirm. The track needs no sample.
- **Play it:** from trigs, the track key, the keyboard (FUNC+TRK) or MIDI, like a sample track. The note
  and knob A (TUNE) set the pitch.
- **SRC page:** knob A is TUNE and knob D is the (unused) sample slot. The other six are the machine's:

  | machine | B | C | E | F | G | H |
  |---|---|---|---|---|---|---|
  | SIN   | - | - | - | - | - | - |
  | NOISE | ST (sample and hold) | RED (darker) | STON (pitched) | - | - | - |
  | SAW   | UNIL (unison level) | UNIW (detune) | UNIX (1-3 unison saws) | SUBX (sub square..saw) | SUB1 (-1 oct) | SUB2 (-2 oct) |
  | PULSE | UNIL | UNIW | SUB (-1 oct) | PW (64 = square) | PWAD (PWM depth) | PWRS (PWM rate) |
  | ENS   | PCH2 | PCH3 | PCH4 (63 = same pitch, 1 = a semitone) | WAVE (saw..pulse) | CHRL (chorus level) | CHRW (chorus width) |

- **Everything else works as usual:** the FLTR, AMP and LFO pages, p-locks, parameter locks on these
  knobs, the sends and the track level.
- **Keep it to a few tracks:** each playing Digi Mono track costs 3-8 % of the audio engine. If you hear
  clicks, use fewer Digi Mono tracks at once, and switch digihealth's FAST AUDIO on.

## Song mode
Stand-alone builds (tools/build.py): disabled, pattern chains work as usual.
Digi utilities 1.7a and later (elekloader): Song mode works as stock; the utility page opens on a held "...".
