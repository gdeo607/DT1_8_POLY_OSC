# digi1_mods

*(formerly DT1_8_POLY_OSC)*

Unofficial, community-made patch set for the 8-track MK1 sampler groovebox ("DT1"), based on **OS 1.53**.
**POLY** (polyphony across the 8 audio tracks) is the core. The "..." (three dots) key gets a
**utility page** that you choose when building: **Scope** or **Spectrum**. Both include a tuner and track activity.

> **Unofficial and unsupported. Not affiliated with, endorsed by or supported by the hardware's manufacturer.
> Flashing modified firmware is at your own risk.** Read [DISCLAIMER.md](DISCLAIMER.md) and [RISKS.md](RISKS.md) first.

![scope](docs/img/scope.png)

## Builds

| page on the "..." key | release | unit shows | hardware |
|---|---|---|---|
| Scope (waveform) | v3p | 1.5b | not yet tested |
| Spectrum | v3q-spectrum | 1.5c | not yet tested |
| All three views (waveform, spectrum, X-Y) | v3r-all | 1.5d | **confirmed** |

Current elekloader build (you link it yourself from your official file, see below): core + digihealth +
**Digi Poly 1.0f + Digi Matrix 1.0b + Digi EQ 1.0b**, unit shows **2.0d** - checked in emulation, hardware not
yet tested.

## Features

**Digi Poly** (elekloader mod `digipoly`, 1.0f) - the POLY machine, redesigned
- Any audio track set to POLY plays **chords from its own trigs**: its TRIG page becomes the MIDI tracks' page
  (NOT1-NOT4 piano roll, VEL, LEN, PROB, LFO.T, with the track's LEV fader); SRC, FLTR, AMP and LFO are as usual.
- Each extra note **borrows the voice of another track** (the one idle longest; never a muted track, a track
  that trigs at the same moment, or a track you took out of the pool). No MIDI track or loopback is needed.
- **Pressing the track's key plays the chord**; notes on the POLY track's **own MIDI channel** play
  polyphonically, one voice per note, and **recording them writes the chord into the piano roll** - up to
  four notes into the step's NOT1-NOT4, where the stock OS would record a bare trig with no note.
- On the POLY track's TRIG page the **LEVEL knob sets the track level** and the **LEV fader** beside NOT1
  shows it, the same size and in the same place as on the audio pages.
- The POLY track's **level and knobs apply to the whole chord**, borrowed voices included.
- **SETTINGS > POLY** chooses which tracks lend their voice. It lives in the pattern's kit, so each pattern has
  its own voice allocation and it is saved with the project.
- Several tracks can be POLY. POLY survives kit/project reload, and since 2.0d the pool survives a power cycle.

<table><tr><td align="center"><img src="docs/img/digipoly_trig.png" width="384" alt="POLY track TRIG page"><br><sub>A POLY track's TRIG page: NOT1-NOT4 piano roll and the LEV fader</sub></td><td align="center"><img src="docs/img/digipoly_pool.png" width="384" alt="SETTINGS > POLY"><br><sub>SETTINGS &gt; POLY: track 2 taken out of this pattern's voice pool</sub></td></tr></table>

**POLY in the stand-alone builds** (and the earlier `dt8poly` mod) - a 5th sample machine in the FUNC+SRC list
- Tracks set to POLY share one voice pool; the lowest POLY track is the *control* track (its sound is used).
- Sequencer trigs on the control track rotate across the POLY tracks.
- *MIDI cable*: notes and chords from a MIDI track (e.g. recorded from an external sequencer) play the POLY
  tracks whose MIDI receive channel equals the MIDI track's output channel - free voice first, else oldest.
- CCs from that MIDI track reach the POLY tracks (filter/amp sequencing); SRC TUNE and LFOs stay per voice.
- POLY survives kit/project reload.

**Utility page** - opens with the "..." (three dots) key; one per build: `--page scope` or `--page spectrum`
- *Scope*: live waveform. *Spectrum*: 30 Hz..20 kHz analyser (128 log columns, 60 dB, falling peaks;
  bass from a 170 ms window, highs from a 21 ms window).
- Both pages:
  - main view -> X-Y (stereo goniometer) -> close, with the same key. **YES** = fullscreen, **NO** = close.
  - bottom-right: activity boxes for all 8 audio tracks (flash on trig; POLY voices stay lit while held).
  - bottom-left: **tuner** (note + cents, ~12 Hz..3 kHz).
  - the top bar (pattern, name, tempo), mutes, pattern/bank change, page keys and **knobs** all keep working
    while the page is open, so you can tweak a sound and watch it change.

**Song mode** is disabled in the stand-alone builds (its code space is reused); chains still work. The elekloader
build (Digi utilities 1.7a+) keeps Song mode: the page opens on a held "..." instead.

**Digi Matrix** (elekloader mod `digimatrix`, 1.0b) - a modulation matrix for the LFOs
- **SETTINGS > MOD MATRIX** opens a page with **8 routing slots**. Each one sends **any track's LFO1 or LFO2**
  to **any parameter of any track**, with **its own depth** (-64..+64) - so one LFO can drive several
  parameters across several tracks, each by a different amount, while its own DEP keeps controlling only its
  own track.
- Per slot, **OWN** says whether that LFO still modulates its own track's DEST as well, or only what the
  matrix routes it to.
- UP/DOWN choose a slot, **YES** turns it on and off, **NO** leaves; knobs A-F edit the slot under the cursor
  (source track, source LFO, destination track, destination parameter, depth, OWN).
- The matrix lives in the pattern's kit, so **each pattern has its own**; it is saved with the project and
  (since 2.0d) survives a power cycle.

<table><tr><td align="center"><img src="docs/img/digimatrix_page.png" width="384" alt="MOD MATRIX page"><br><sub>SETTINGS &gt; MOD MATRIX: two slots routed, the second under the cursor</sub></td></tr></table>

**Digi EQ** (elekloader mod `digieq`, 1.0b) - a 4-band master EQ, on **every output**
- A master page (FUNC+LFO, after Compressor): 4 bands, each with level/Q (knobs A-D, press to switch) and
  frequency/type (knobs E-H, press to switch: HP, low shelf, bell, notch, band pass, high shelf, LP), with the
  response curve drawn above the knobs.
- It runs on the **master mix**, before the render hands it to the analog outputs and to the USB stream, so
  main outs, headphones and USB audio all carry it - as the compressor does. (Up to 1.8a it sat on the
  codec's transmit buffer, which is the analog path only, so USB audio came out unequalized.)
- **Per pattern**: the settings live in the pattern's kit, so every pattern has its own EQ, saved with the
  project and kept over a power-off.
- **SETTINGS > GLOBAL FX/MIX > MASTER EQ**, beside the firmware's own entries: with it on, the EQ you can hear
  overrides every pattern's own; with it off, each pattern goes back to its own.

<table><tr><td align="center"><img src="docs/img/digieq_page.png" width="384" alt="Master EQ page"><br><sub>The master EQ page: four bands and the response curve</sub></td><td align="center"><img src="docs/img/digieq_global.png" width="384" alt="GLOBAL FX/MIX with MASTER EQ"><br><sub>SETTINGS &gt; GLOBAL FX/MIX: the MASTER EQ entry, on</sub></td></tr></table>

<sub>Screens are the unit's 128 x 64 display, captured in an emulator running the mods and scaled 4x; the
pattern is renamed "DEMO". Only screenshots are published here - no firmware, and nothing derived from it.</sub>

Full controls: [docs/USAGE.md](docs/USAGE.md). Version history: [CHANGELOG.md](CHANGELOG.md).

## Getting it

- **Build it yourself** from your own copy of the official OS 1.53 file (recommended; identical result):

```sh
# get the MIT-licensed .syx container tool by mischa85 (GitHub) and build it with `make`, then:
python3 tools/build.py --official <official OS 1.53 .syx> --tool <path to the container tool> --page scope
# -> out/digi1_mods_v3p_1.5b.syx            SHA-256 f8cd0d721c265a07077078a5aae95908c265ce3fadd0c83cbbb377916b51b8b3
python3 tools/build.py --official <official OS 1.53 .syx> --tool <path to the container tool> --page spectrum
# -> out/digi1_mods_v3q-spectrum_1.5c.syx   SHA-256 3aeb2bb8c4a79c7a807d4ee62336ba8e045078d6ae3d122d64e53a0c8851564a
```

The build refuses any input that is not the exact official OS 1.53 file and checks every patched byte.
Flashing and **reverting**: [docs/INSTALL.md](docs/INSTALL.md).

## Building as elekloader mods

The code also builds as linkable mods for [elekloader](https://github.com/irpina/elekloader), so it can
run next to other mods for this OS (for example digihealth's FAST AUDIO / SYSTEM INFO and digislicer):

| mod | contents |
|---|---|
| `digipoly` | **Digi Poly**: the POLY machine; chords from a POLY track's own trigs (MIDI-style TRIG page with a working LEVEL knob and LEV fader), voice borrowing (borrowed voices follow the POLY track's knobs and level), chord preview on the track's key, polyphonic MIDI in on the track's channel that records as a chord, per-pattern SETTINGS > POLY pool that survives a power cycle (1.0f) |
| `digiutils` | **Digi utilities**: the utility page on a **held "..."** (waveform -> spectrum -> X-Y), tuner, activity boxes, **Song mode kept** (1.9a) |
| `digieq` | **Digi EQ**: the 4-band master EQ as a FUNC+LFO master page, on the master mix so every output carries it, kept per pattern in the kit and over a power cycle, with a MASTER EQ entry in SETTINGS > GLOBAL FX/MIX (1.0b) |
| `digimatrix` | **Digi Matrix**: the LFO modulation matrix; 8 cross-track routing slots with their own depth, on a SETTINGS > MOD MATRIX page, kept per pattern in the kit and over a power cycle (1.0b) |
| `dt8poly` | the earlier POLY mod (control track rotation, internal MIDI and CC cable, per-voice TUNE/LFO); superseded by `digipoly`, built only on request (`--mods dt8poly`) |

```sh
python3 tools/build_elemods.py --stock <official OS 1.53 .syx> --elekloader <elekloader checkout>
# -> out/elk/{digipoly,digiutils,digimatrix,digieq}/out/*.elemod
```

Then add them in elekloader's window (with its core mod), or on the command line:
`python -m elekloader.patch --stock <official .syx> --mod core-2.0a.elemod --mod digipoly-1.0f.elemod --mod digimatrix-1.0b.elemod --mod digieq-1.0b.elemod --out custom.syx --version 2.0d`.
Add `--mod digiutils-1.9a.elemod` for the "..." utility pages.
The `.elemod` files are built from your official file and are not stored here. Building needs an m68k cross toolchain
(binutils and gcc), which the SDK looks up as `m68k-linux-gnu-*`:

| platform | install |
|---|---|
| Linux (Debian/Ubuntu) | `sudo apt install binutils-m68k-linux-gnu gcc-m68k-linux-gnu` |
| macOS (Homebrew) | `brew install m68k-elf-gcc m68k-elf-binutils` |

`tools/build_elemods.py` falls back to Homebrew's `m68k-elf-` prefix on its own when `m68k-linux-gnu-gcc` is absent.
To use another toolchain, set `ELEKLOADER_CROSS` to its prefix (for example `ELEKLOADER_CROSS=m68k-elf-`) for the build.

The master EQ is in the elekloader build only; since 1.0a it is its own mod, `digieq`
([docs/USAGE.md](docs/USAGE.md)).

Checked in emulation (hardware: **not yet** for Digi Poly): the linked Digi utilities / dt8poly code is
instruction-for-instruction the stand-alone code (`tests/elk_equiv.py`); the mods lint and link alone, together,
and with digihealth + digislicer; a full walk-through boots in the digiemu emulator with FAST AUDIO on
(`tests/digiemu_scenario.py`); Digi Poly is checked twice: `tests/emu_poly.py` runs its own code in unicorn
without booting the firmware (voice choice, the settings row, the chord's messages, the knob and level mirroring,
the TRIG page's fader - seconds), and `tests/digiemu_poly.py` boots the firmware for what only it can show (the
page, the key's chord, chords while the sequencer runs, per-pattern pools). Digi Matrix is checked the same
way: `tests/emu_matrix.py` runs both engine passes, the clamps and the whole page in unicorn in seconds, and
`tests/digiemu_matrix.py` boots the firmware to show the SETTINGS row, the page, what its keys and knobs write
into the pattern's kit, and one track's LFO actually moving another track's parameter. Digi EQ likewise:
`tests/emu_eq.py` checks the knobs against the design model, the audio bit for bit against it, and the
settings in the kit and the global override; `tests/digiemu_eq.py` boots the firmware and measures a test
tone put into the master mix again in the bus the USB stream is built from, against what the model says the
settings should do. Differences from the stand-alone
build: the code runs from the loader's RAM area instead of reclaimed song-mode code, and the audio tap sits one
instruction later because FAST AUDIO owns the output-write call (see docs/TECHNICAL_NOTES.md).

## Repository layout

| path | contents |
|---|---|
| `src/` | assembly for every hook (ColdFire, GNU as `-mcpu=5475`) |
| `bin/` | the assembled hooks (committed; `make` rebuilds them) |
| `tools/build.py` | official .syx -> patched .syx, fully verified |
| `tools/patch_section3.py` | applies all patches to the MAIN OS section |
| `mods/`, `tools/build_elemods.py` | the elekloader mods (mod.json + mod-only sources; shared code from `src/`) |
| `tests/` | emulator tests: the real firmware code runs under unicorn with the patches (`tests/run_tests.sh <official s3> <patched s3> scope|spectrum`) |
| `docs/` | install/revert, usage, technical notes (reverse-engineering log) |

No firmware from the manufacturer is stored or distributed here; see [DISCLAIMER.md](DISCLAIMER.md).

## License

Our own code and docs: MIT ([LICENSE](LICENSE)). This does **not** cover the manufacturer's firmware.
