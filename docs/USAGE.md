# Usage

## POLY
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

## Scope
| key | action |
|---|---|
| "..." (three dots) | open scope (waveform) -> X-Y -> close |
| YES | fullscreen waveform on/off |
| NO | close the scope |
| PTN / BANK + trig | change pattern (scope stays open, green LEDs show patterns with data) |
| mutes, page keys, knobs, PLAY/STOP, FUNC combos | work as on the main screen |

- **Top bar**: pattern, name and tempo (hidden in fullscreen).
- **Bottom-right boxes**: tracks 1-8. Filled = the track just triggered (or a POLY note is held). A small line
  above a box marks a POLY track.
- **Bottom-left tuner**: note name, octave and cents (A4 = 440 Hz). `--` = no clear pitch or too quiet.
  It hears the main output: solo a track to tune it; a chord shows its common root.
- **X-Y**: mono = vertical line, left-only = "\", right-only = "/", out of phase = horizontal, wide = cloud.
- Knobs change the parameters of the selected page while the scope is open (the page is hidden behind the scope;
  close it to read values).

## Song mode
Disabled. Pattern chains work as usual.
