# Changelog

"Unit shows" = the version string displayed on the unit. HW = tested on real hardware by the owner.
All builds change only the MAIN OS section; bootloader, updater, I/O firmware and metadata stay official.

## elekloader app: old library copies (tools)
- **Old hand-installed copies no longer win over the updated mods.** elekloader lists its own library
  (~/.elekloader/mods) first; an old digichain or digimono installed there by hand, still ticked, was built
  instead of the new one (an old digichain leaves Digi Mono, SOPHIE and DIGISLICER without menu icons). At
  launch and after each update the app moves those copies to "Digitakt 1/4_bin/library_<date>".
- Checked: the full set (core, digichain 1.3, Digi Mono 0.9, SOPHIE and NEIGHBOR chained, digieq, DigiFilter,
  digihealth, digimatrix, digiutils) shows every added machine's icon in digiemu.
- `dev.sh elemods`: Digi Mono's pairs are checked with digichain (it requires it), no more false CLASHes.

## digichain 1.3 (HW: not yet)
- **NEIGHBOR plays when you pick it.** A new NEIGHBOR track takes the track on its left as its source
  (track 2 for track 1) once it has been NEIGHBOR for half a second; before, SLOT started at 0, silence.
- **NEIGHBOR's SLOT runs 0-8** (it was SLICE's 0-64, where 9-64 were silence too).
- Tested NEIGHBOR in digiemu: page, values, pitch shifter (within a few cents across +-12), source from
  SOPHIE and Digi Mono tracks; chained and original NEIGHBOR the same. tests/digiemu_chain.py --blocks-at
  reads the tracks before the mixer.

## Digi Mono 0.9, digichain 1.2 (HW: not yet)
- **MONO ENS about 35 % lighter at its defaults (~2,700 estimated ColdFire cycles a voice a block, was
  ~4,200; heaviest ~5,200, was ~8,200).** Its four saws are worked out as one ramp with corrections at the
  wraps, not four passes. Within 3 (16-bit) of 0.8's samples.
- **MONO VO lighter again (a vowel ~3,700, while a consonant sounds ~6,400; 0.7: ~12,300).** SH, H, T, K
  and P run at 24 kHz; the consonant and the vowel are separate loops. SH and H come out about 3 dB brighter
  in 1-12 kHz; the vowel is as before.
- **Icons in the machine menu:** MONO SIN, NOISE, SAW, PULSE, ENS and VO each have one
  (tools/gen_mono_icons.py). digichain 1.2 fixes the menu so every added machine's icon shows (core 2.1
  drew only the one right under SLICE): SOPHIE's and DIGISLICER's too.
- Checked: the engine's signal tests, ColdFire = PC bit for bit, all six machines bit for bit in digiemu,
  and the menu in digiemu with every icon.

## Digi Mono 0.8 (HW: not yet)
- **MONO VO about three times lighter:** an estimated ~4,400 ColdFire cycles a voice a block for a vowel
  (was ~12,300), ~7,100 while a consonant sounds. The vowel runs at 24 kHz (its formants are all under
  4 kHz), the consonant at 48 kHz while it lasts; no divides a sample; the filters' state stays in
  registers. The sound: the same formants and levels (every band to 12 kHz within 1 dB); above 12 kHz it
  is at most 48 dB under the voice.
- Checked: the engine's signal tests (formants, consonants), ColdFire = PC bit for bit, and in digiemu
  every block of a VO voice equal to the engine's.

## Digi Mono 0.7, digichain 1.1 (HW: not yet)
- **The SRC page says what each knob does.** Every knob a machine has gets its name, a plain round knob
  (not ONESHOT's PLAY, SAMP or LEV controls under it) and its value in its units: voices, semitones, duty %,
  mix %, ms, vowel and consonant names. Knobs a machine does not have are blank.
- **D and H are engine knobs.** D was the sample slot: it now carries PULSE's SUB2, ENS's pulse width and
  VO's breath (until now not on any knob), and no longer opens the sample list. H was the sample level,
  which also switched the voice off at 0: the voice now follows its amp envelope, and its level is the
  track's LEVEL.
- Digi Mono needs digichain (ticked with it); digichain 1.1 routes Digi Mono pages too.
- Checked in digiemu: all six machines bit for bit against the engine with D and H turned; each page's names
  and values; the sample list still opens on a ONESHOT track; SOPHIE's and NEIGHBOR's pages unchanged.
- Projects from 0.6: a PULSE, ENS or VO track's D holds the sample slot it had (often 0), now that parameter.

## digichain 1.0 (HW: not yet)
- New mod **digichain**: SOPHIE (digisophie), NEIGHBOR (digineighbor) and DIGISLICER (digislicer) now
  combine. It owns the SRC-page and render places they each patched and sends each call to the mod whose
  machine it is for; `tools/chain_patch.py` moves those mods' sites to it at build time (`-chain`
  versions), their code unchanged. mods/digichain/README.md.
- Checked in digiemu against the original mods: the same SRC pages pixel for pixel, the same ranges,
  SOPHIE's and NEIGHBOR's voices the same bit for bit; NEIGHBOR can now take a SOPHIE track.
- elekloader.app builds and updates the chained versions; the Version tab says when a mod is one.

## Digi Mono 0.6 (HW: not yet)
- New machine **MONO VO**, a formant voice after the Monomachine's VO-6:
  - three vowel resonators on a glottal source, from published vowel measurements;
  - VOC1 to VOC2 glide (V-SW), with the vowels shown by name;
  - consonants S, SH, F, H, T, K and P (CONS, CLEN, CVOL).
- **Shares a build with digisophie:**
  - machine ids move to 20..25 (SOPHIE is 7);
  - the render hook moves one instruction later (0x40077fc2);
  - the SRC page's name and value hooks sit at the functions' callers instead of their entries.
  - elekloader accepts core + digimono + digisophie (with digiutils, digimatrix, digieq); both machines
    work in one digiemu build.
- A project saved with 0.3's ids (6..10) loads those tracks as ONESHOT.

## Digi Mono 0.5
- The engine's audio goes in after the voice loop (0x40077fba), so the AMP envelope applies.
- The machines render as ONESHOT.
- The FLTR / AMP / LFO pages are measured in digiemu (tests/digiemu_mono_fx.py). One issue is open:
  part of the voice ignores FREQ and VOL.

## Digi Mono 0.3 (HW: not yet)
- New elekloader mod `digimono` (needs core 2.1): five SRC machines after the Monomachine's GND and SWAVE
  machines - MONO SIN, MONO NOISE, MONO SAW, MONO PULSE and MONO ENS - played by a clean-room synth engine
  (no Monomachine code or data) written for the Digitakt's ColdFire.
- The engine's block replaces the voice's resampled sample in the render (0x4007606e), so the track's
  filter, amp, LFOs, sends, p-locks, note locks and TUNE all apply. Pitch comes from the note and TUNE as
  a sample's does.
- The SRC page shows the machine's own knob names and 0..127 values; a switch to a Digi Mono machine sets
  its defaults.
- Checked in digiemu on the real OS 1.53 for all five machines: every block the voice hands on equals the
  engine's own, bit for bit (tests/digiemu_mono.py). The engine alone: tests/mono_signal.py (what each
  parameter does) and tests/emu_mono.py (ColdFire build = PC build).
- Cost: 3-8 % of the render per playing Digi Mono voice. Not in one build with Digi Poly 1.0f (core 2.1's
  machine sites).

## Repository renamed
The repository is now **digi1_mods** (it was DT1_8_POLY_OSC). Old links redirect. The stand-alone
builds are now written as `digi1_mods_<release>_<version>.syx`; their contents and SHA-256 are unchanged.

## Digi Poly 1.0f + Digi Matrix 1.0b + Digi EQ 1.0b - unit shows 2.0d (HW: not yet)
- **The per-pattern settings survive a power cycle.** Digi Poly's voice pool, Digi Matrix's slots and
  Digi EQ's bands kept their settings in parameter slots 46..52 of each sound, which the firmware never
  writes to the +Drive. They now live in six bytes of every sound record that the firmware saves and
  loads but never uses itself: a reserved long at the start of the record and parameter slot 0, which no
  page edits. All 1024 sound records on the +Drive (kits and pool sounds) hold zero in both, so every
  existing kit reads as "not set". Measured: written, project saved, RAM wiped, project loaded - they come
  back; the LEVEL knob, sample changes and every knob of the SRC, FLTR, AMP and LFO pages leave them
  alone. Byte map: src/kitstore.h.
- Two other places were tried first and rejected: the low byte of each track's level word (saved, but the
  LEVEL knob rewrites the whole word and clears it) and the last four bytes of each sound (saved, but they
  are the tail of the sample reference, rewritten when the sample changes and reset at load when a track
  has no sample).
- **Loading a sound onto a track changes none of it.** A sound load replaces the six bytes with the loaded
  sound's (zero). Each mod keeps a marker in a RAM-only slot, which every load clears: if one track's
  marker is gone, a sound was loaded onto it and the mod puts its own bytes back; if all eight are, the
  kit or project was loaded and its saved settings are taken.
- **Digi EQ picks up a loaded project at once.** It used to reload its settings only when the pattern
  changed; after LOAD PROJECT (or a kit reload) the same kit is refilled in place, and the EQ kept playing
  the old settings. It now notices the load and takes the loaded pattern's EQ.
- **Fix: the POLY TRIG page's LEV fader showed the wrong level on tracks 2..8.** It read the levels as
  bytes at kit + 0x10 + track; they are the high bytes of words at kit + 0x10 + 2 * track, so only track 1
  was right.
- Checked: unit tests for all three mods (new: sound load keeps the settings, kit load brings its own,
  track 2's fader); the firmware suites for all three on the 2.0d build; and a firmware round trip -
  settings written, project saved, RAM wiped, project loaded: all bytes back and the EQ playing them.

## Digi Poly (digipoly) 1.0e - unit shows 2.0c (HW: not yet)
- **A recorded chord keeps all its notes.** 1.0d gathered a chord's notes to write them into NOT1..NOT4,
  but started a new chord on every UI frame: the sequencer's record step is -1 whenever a note is not
  being recorded, so it could not say whether two notes belonged together, and a frame between two of a
  chord's notes threw the first ones away - leaving one note. The chord is now held for a few frames
  after its last note instead. Checked in the firmware by calling the firmware's own live-note entry for
  four notes in a row, one a frame: NOT1..NOT4 come out as the whole chord.
- **Known in this version (fixed in 2.0d): none of the per-pattern settings survive a power-off.** Digi
  Poly's voice pool, Digi Matrix's slots and Digi EQ's bands live in parameter slots 46..52 of each track's
  sound, which the firmware keeps in RAM but does not write to the +Drive: measured by putting a different
  value in all 53 slots and saving the project - slots 0..45 come back out of the drive image, 46..52 never
  do. They are right per pattern while the unit is on; they are lost when it is turned off.

## Digi Poly (digipoly) 1.0d - unit shows 2.0b (HW: not yet)
- **Recording notes onto a POLY track.** The stock OS records a live note on an audio track as a bare
  trig: it clears the step's NOT1..NOT4, because an audio track has no notes. A POLY track does, so the
  notes are now written in - a chord's notes are gathered as they arrive (MIDI in sends one note-on each)
  and the whole chord is written each time, lowest note in NOT1 and the others as their offsets from it.
  Up to four notes go into the piano roll, and the step plays back what was played.
- **The LEVEL knob works on the POLY track's TRIG page.** The knob's event asks the view which parameter
  it is on this page, and the MIDI page has none for LEVEL, so the turn was dropped. For the LEVEL knob on
  a POLY track the page is the audio one again for the length of the stock call, so it answers "the track
  level". (The listener is reached through the view's +4 subobject, whose stock entry branches straight to
  the handler - replacing the primary vtable entry alone was not enough.)
- **The LEV fader is the stock one.** It was too big and in the wrong place; it is now drawn at the size,
  position and scale marks measured off the audio TRIG page, follows the knob, and shows the value for a
  moment after a turn before going back to "LEV", as the stock pages do.

## Digi EQ (digieq) 1.0a + Digi utilities (digiutils) 1.9a - unit shows 2.0a (HW: not yet)
- **The master EQ is its own mod now.** Digi utilities keeps the "..." utility pages (waveform, spectrum,
  X-Y, tuner, activity) and nothing else; the EQ, its page and its audio are `digieq`. Load either without
  the other.
- **It is heard on every output.** Up to 1.8a the EQ ran on the codec's transmit buffer, which only the
  analog outputs are built from - USB audio came out unequalized. It now runs on the **master
  mix** (0x8000ea70), before the render hands it to the analog conversion and to the 12-channel bus the USB
  stream is built from, so main outs, headphones and USB all carry it, as they do the compressor. The master
  is 8 bits hotter than the words the outputs take, so the EQ shifts the block on the way in and out; the
  arithmetic inside, and the response, are unchanged.
- **Settings are per pattern**: the four bands (frequency, level, Q, type) live in the pattern's kit, in
  two unused parameter slots of each of the first four tracks' sounds, so each pattern has its own EQ.
  (This version said they were also saved with the project; they were not - see 2.0d.) Kits made before this read as "no EQ" and the
  EQ starts flat.
- **SETTINGS > GLOBAL FX/MIX > MASTER EQ**, a row added to the firmware's own list beside DELAY, REVERB,
  COMPRESSOR, INTERNAL MIXER and EXTERNAL MIXER. On: the EQ you can hear overrides every pattern's own, and
  each pattern the unit reaches is given these settings (so save the project to keep them). Off: every
  pattern goes back to its own.
- Checked: the fixed-point EQ still matches the exact design and the model bit for bit at the master's scale
  (tests/emu_eq.py, 960 blocks, all seven types), the settings round-trip through the kit and the override
  works (same test), and in the firmware a tone put into the master mix comes back out of the USB bus at the
  level the model predicts (tests/digiemu_eq.py) and out of the analog path within 0.19 dB over 11 settings
  (tests/digiemu_scenario.py PLAN=eq).
- Builds for the unit no longer include digislicer, which leaves about 100 KB of the loader's RAM free.

## Digi Matrix (digimatrix) 1.0a - unit shows 1.9e (HW: not yet)
- **New mod: a modulation matrix for the LFOs.** Stock, each of a track's two LFOs modulates one parameter of
  its own track. SETTINGS > **MOD MATRIX** adds 8 routing slots, each one
  **any track's LFO1 or LFO2 -> any parameter of any track**, with **its own depth** (-64..+64). One LFO can
  drive several parameters on several tracks by different amounts; the LFO's own DEP still controls only its
  own track's modulation.
- **OWN**, per slot: whether the source LFO keeps modulating its own track's DEST as well, or only what the
  matrix routes it to (the LFO is taken off its own destination for that block and given back afterwards).
- The page: UP/DOWN (or the LEVEL knob) choose a slot, **YES** turns it on and off, **NO** leaves. Knobs on the
  slot under the cursor: A source track, B source LFO, C destination track, D destination parameter, E depth,
  F OWN. The SETTINGS row shows how many slots are on.
- **Kept per pattern**, in the kit (two unused parameter slots of each track's sound), so it is saved with the
  project and each pattern has its own matrix. Kits made before this read as an empty matrix.
- The matrix runs once per audio block, right after the engine's own LFO stage, with the same clamp; idle cost
  is about 350 instructions a block (0.4 % of one block's budget).
- Checked twice, as Digi Poly is: `tests/emu_matrix.py` (both engine passes, the clamps, the keys, the knobs,
  the drawing - seconds) and `tests/digiemu_matrix.py` (the firmware: the SETTINGS row, the page, what its keys
  and knobs write into the pattern's kit, one track's LFO moving another track's parameter word).

## Digi Poly (digipoly) 1.0c - unit shows 1.9c / 1.9d (HW: not yet)
- **The voice pool is part of the pattern.** SETTINGS > POLY now writes the pattern's own kit (an unused
  parameter slot of each track's sound), so every pattern can lend different voices, it is saved with the project
  and it survives a power-off. Patterns that share a kit share the setting; kits made before this read as "all
  tracks in the pool", which is what the mod did before.
- **The checkbox reads the other way round**: ticked = the chosen track lends its voice to the POLY pool (the
  track's number is shown inverted); unticked = its voice is kept for itself.
- **The POLY track's TRIG page keeps its LEV fader**, as the ONESHOT page has it, beside NOT1-NOT4.
- **Pressing the track's key plays the whole chord** (its trig key, or a key of the FUNC+TRK keyboard). The note
  you played still goes through the firmware, so recording records one note and the chord comes back from
  NOT2-NOT4; the chord's other notes go straight to the audio engine.
- Checked that a voice borrowed for the first time *after* a knob was turned also plays the new value, and that
  the POLY track's LEVEL moves the whole chord.
- Testing is now in two parts: `tests/emu_poly.py` runs Digi Poly's own code in unicorn with the firmware's
  routines stubbed (seconds), and `tests/digiemu_poly.py` boots the firmware only for what needs it (~30 s).

## Digi utilities (digiutils) 1.8a + Digi Poly (digipoly) 1.0b - unit shows 1.9a / 1.9b (HW: not yet)
- **Master EQ moved to the master pages**: FUNC+LFO now steps Compressor (1/4) -> **Master EQ (2/4)** -> Internal
  Mixer (3/4) -> External Mixer (4/4). The "..." utility page is back to waveform -> spectrum -> X-Y -> close.
- **One EQ page**: knobs A-D band level, E-H band frequency. **Pressing a knob** switches it (press again to switch
  back): A-D to the band's **Q**, E-H to the band's **type** - HP, low shelf, bell, notch, band pass, high shelf, LP.
  Switched knobs are shown inverted; the response curve (all types) is drawn above the knobs. Every band has a Q
  now (shelves too); HP/LP/BP/notch use the level as the band's output level. Output level and on/off are gone
  (the EQ costs nothing while every bell/shelf is at 0 dB and no filter type is chosen).
- Checked: the fixed-point EQ matches the exact design within 0.014 dB for all seven types (tests/eq_model.py); the
  unit's code is bit-exact with the model over 960 blocks with every type (tests/emu_eq.py); in digiemu the page
  sits between Compressor and Internal Mixer, knobs and knob presses set it, and the measured output level
  matches the model within 0.01 dB (tests/digiemu_scenario.py, PLAN=eq).
- **Digi Poly 1.0b**: stolen voices follow the POLY track's knobs. Turning the track's LEVEL or any SRC / FLTR /
  AMP / LFO knob while a chord plays now changes every voice of the chord, not only NOT1's (checked in digiemu:
  every parameter word of the stolen voices equals the POLY voice's after the turns, and they play at its level).

## Digi Poly (digipoly) 1.0a - unit shows 1.8a (HW: not yet)
- New elekloader mod **Digi Poly** replaces `dt8poly`. The POLY machine stays (FUNC+SRC, name, icon, kits load as
  ONESHOT on the stock OS); how it plays is new:
  - **Chords from the POLY track's own trigs.** Its TRIG page is the MIDI tracks' page (NOT1-NOT4 piano roll, VEL,
    LEN, PROB, LFO.T); NOT2-NOT4 are semitone offsets, per track or locked per step.
  - **Voice stealing.** NOT1 plays on the track's own voice, each extra note on another track's voice: the one idle
    longest, never a muted track, a track that trigs at the same moment, a voice holding a live note or a track
    locked in the new **SETTINGS > POLY** row. A stolen voice plays the POLY sound and gets its own back at its
    own next trig.
  - **MIDI in** on the POLY track's own channel plays polyphonically (note-offs release the voice that holds
    the note). No MIDI track, loopback or shared channel needed.
- Removed with the old design: the internal MIDI cable, the CC cable, the control track rotation over several POLY
  tracks and the per-voice TUNE/LFO lock. Several tracks can still be POLY; each plays its own chords.
- Digi utilities' activity boxes show POLY live notes held on a voice (the mod provides the same `dt8poly_vstate`).
- Checked in digiemu (`tests/digiemu_poly.py`): chords on 4 voices with the track's sound, a step's own NOT4 lock,
  locked and simultaneous tracks never stolen, notes skipped when no voice is left, a live 3-note chord on 3 voices
  and released by its note-offs, MIDI-style TRIG page on the POLY track only.

## Digi utilities (digiutils) 1.7a - unit shows 1.7a / 1.7b (HW: not yet)
- **Song mode is back**: a short "..." press is the stock SONG MODE popup again (Song mode on/off, EDIT, double
  press to the Song edit screen). **Hold "..."** (about half a second) opens the utility page.
- The page is no longer the Song edit screen's class: the one Song edit view opened by the hold gets its own copy
  of the class table (draw, keys, tick, knobs, LEDs pointed at the page), so the stock Song edit screen is untouched.
  Pattern / bank changes close the stock Song edit screen as before and keep the page open.
- **EQ view indicators**, in the style of a hardware EQ page: header `MASTER EQ (1/2)`, framed graph with 100 Hz /
  1 kHz / 10 kHz ticks and 20 / 1K / 20K labels, numbered band points (the band being edited as a circle), the
  spectrum as dots, and all eight knob values of the page (the last changed underlined).

## Digi utilities (digiutils) 1.6a - unit shows 1.6a / 1.6b (HW: not yet)
- The utility mod is now called **Digi utilities** (`digiutils`, was `dt8osc`).
- **Master EQ**, a 4th view after X-Y: low shelf, two bells (with Q), high shelf, output level, on/off. The curve is
  drawn over the live spectrum; knobs A-H set gains and frequencies (page P1) or Q, output, on/off (page P2, YES).
  It runs on the main output right after the render, before the scope/spectrum/tuner, so they show what you hear.
- Trapezoidal state-variable filters on the EMAC (fractional), coefficients in 32-bit integer arithmetic;
  bit-exact against tests/eq_model.py in the emulator, within 0.002 dB of the floating-point design.
- Knob turns count 4 per notch (one step per notch); flat bands cost nothing.

## elekloader mods dt8poly / digiutils - 1.5e (HW: not yet)
- The same features as v3r-all, as two linkable mods for elekloader: `dt8poly` (POLY) and `digiutils` (utility page
  with all three views, song mode off). They combine with each other and with other mods (checked with digihealth
  and digislicer). Built by `tools/build_elemods.py` from the same `src/` (assembled with `ELK` defined).
- Code and data live in the loader's RAM area instead of reclaimed song-mode code; stock sites are the same, except
  the audio tap, now right after the output write (0x40078150), which FAST AUDIO may run from its SRAM copy.
- The stand-alone builds are unchanged (same SHA-256 for scope, spectrum and all).

## v3r-all - 1.5d (HW: **confirmed**)
- All three views in one OS: the "..." key cycles **waveform -> spectrum -> X-Y -> close** (`--page all`).
  Tuner and activity boxes in waveform and spectrum; YES fullscreen and NO close in every view; keys, knobs and
  pattern change as before. Only the view on screen does any work (the spectrum capture/FFT stops when you leave it).
- The trig counter (audio-interrupt hook) moves next to the spectrum code in this build to make room; the scope and
  spectrum builds are byte-identical to before.

## v3q-spectrum - 1.5c (HW: not yet)
- New build option: the three-dots utility page can be **Spectrum** instead of Scope (`tools/build.py --page spectrum`).
  Everything else (POLY, tuner, activity boxes, X-Y, YES/NO, keys/knobs/pattern change) is identical.
- Spectrum: 128 log-spaced columns 30 Hz..20 kHz, 60 dB, falling peaks, ticks at 100 Hz / 1 kHz / 10 kHz.
  Below 350 Hz from a 512-point FFT of the tuner's 170 ms 3 kHz history (5.9 Hz bins); above from a 1024-point FFT
  of a 21 ms full-rate capture taken on request by the audio tap. Fixed-point, bit-exact to tests/spec_model.py.
- Uses the old song-edit knob/LED routines (dead since v3l/v3p) for code; 6 KB allocated once.
- The build is now split into POLY core + page shell + page; `--page scope` still reproduces 1.5b byte for byte.

## v3p - 1.5b (HW: not yet)
- The DATA ENTRY knobs pass through the scope to the main screen: pick TRIG/SRC/FLTR/AMP/LFO and turn knobs
  while watching the waveform/tuner. (The inherited song-edit knob handler used to swallow every turn.)

## v3o - 1.5a (HW: not yet)
- **Tuner** in the scope (bottom-left): note + cents, ~12 Hz..3 kHz, within +-3 cents in emulation (A0..C7).
- Screen orientation fixed: the LCD is vertically flipped relative to video memory. The waveform had been drawn
  upside down since v3c and the X-Y left/right diagonals were swapped. Now: positive = up; X-Y mono = vertical,
  left-only = "\", right-only = "/".
- SETTINGS key on the scope handled by the scope itself (stock behaviour kept).

## v3n - 1.5Z (HW: **confirmed**, "everything working really well")
- Track activity boxes flash for every trig (ONESHOT and all machines). v3k's hook sat inside an optional block of
  the audio interrupt and missed most sequencer trigs; now hooked at the merge point.

## v3m - 1.5Y
- YES toggles a fullscreen waveform (no top bar, no boxes); NO closes the scope.
- Fix: v3i-v3l closed the scope on YES (key ids: 12 = YES, 13 = NO, confirmed from the stock confirm dialog).

## v3l - 1.5X
- Pattern/bank change from the scope: the scope stays open and the green "pattern has data" LEDs show every time.
  (The stock code closed any song-edit screen after a pick; the scope's inherited LED handler hid the LEDs.)

## v3k - 1.5W
- Activity boxes for all 8 audio tracks (POLY tracks marked). *Missed most trigs - fixed in v3n.*

## v3j - 1.5V
- Keys not used by the scope fall through to the main screen the stock way (no double handling):
  fixes intermittent pattern selection with the scope open.

## v3i - 1.5U
- Intended "NO closes the scope" - mapped to the wrong key (it was YES). Fixed in v3m.

## v3h - 1.5T
- Stereo X-Y (goniometer) mode on the scope; POLY voice boxes.

## v3g - 1.5S
- Song mode can never become active (it had no way back since its popup was replaced); projects saved in song
  mode load in pattern mode; chains unaffected.

## v3f - 1.5R (HW: **confirmed**)
- Scope drawn over the main screen: top bar (pattern, name, tempo) stays; mutes and other keys work.

## v3e - 1.5Q
- POLY voices keep their own SRC TUNE and LFO settings; filter/amp come from the control track.

## v3d - 1.5P
- Scope opens directly with the "..." key. CCs from the MIDI track reach the POLY tracks (cc < 120).

## v3c - 1.5N
- Live oscilloscope (audio-interrupt tap, <1 block latency, read-only on the audio).

## v3b - 1.5M
- POLY machine survives kit/project reload.

## v3 - 1.5L ("cable")
- MIDI track -> POLY tracks: notes/chords from a MIDI track play the POLY tracks sharing its channel, with voice
  allocation (free first, else oldest) and the control track's sound.

## v2 series (superseded)
- v2a: POLY machine in the FUNC+SRC list (plays as ONESHOT). v2b: sequencer trigs of the control track rotate over
  the POLY tracks. chord12-chord18: MIDI-track chord experiments (chord16 HW-confirmed); replaced by the v3 cable.
- v1: first proof of concept.
