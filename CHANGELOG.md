# Changelog

"Unit shows" = the version string displayed on the unit. HW = tested on real hardware by the owner.
All builds change only the MAIN OS section; bootloader, updater, I/O firmware and metadata stay official.

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
