# Risks - read before flashing

## Your unit
- **Bricking risk is low but not zero.** Only the MAIN OS section is modified; the bootloader (which provides the
  startup-menu OS upgrade) is untouched, so a unit that fails to start can be recovered by sending the official OS
  over **physical MIDI** from the startup menu ([docs/INSTALL.md](docs/INSTALL.md)). Keep a MIDI interface ready.
- **Warranty/support**: modified firmware may void the warranty. Revert to the official OS before any service.
- **Untested builds**: v3o (1.5a) and v3p (1.5b) have passed all emulator tests but not yet a hardware test.
  v3n (1.5Z) is the latest hardware-confirmed build.

## Your projects
- Tracks set to POLY store machine value 4. The official OS does not know it and loads such tracks as ONESHOT.
  Back up everything with the manufacturer's transfer app before flashing, and before reverting.
- Song mode is disabled: songs stored in a project cannot be played; a project saved in song mode opens in pattern mode.
- Don't use this OS for gigs until you have tested your own projects on it.

## Technical risks (what could still go wrong)
| area | risk | mitigation |
|---|---|---|
| Audio interrupt hooks (scope tap, voice-start count, POLY per-voice params) | timing overrun or register corruption -> glitches/crash | all hooks preserve registers; verified against the stock interrupt code in emulation; tap adds ~100 instructions per 0.67 ms block |
| MIDI cable (MIDI out task) | stuck POLY note if a note-off is lost | notes are released on the matching note-off; stop/restart sequencer; no panic function yet |
| CC cable | an external CC and a MIDI-track CC arriving at the same instant for the same POLY track (two tasks) | residual race; effect is at most one lost/overwritten value |
| Tuner | CPU use in the UI task (worst ~0.7 M instructions per estimate, every 4th frame) | runs outside the audio interrupt; UI may feel slightly slower with the scope open |
| Memory | scope/tuner data lives in reclaimed code space of removed song-mode screens; tuner allocates 1 KB once | all reclaimed ranges verified unreachable; allocation failure just disables the tuner |
| Knobs through the scope (v3p) | the main screen might not apply knob turns while covered | falls back to stock behaviour if so; close the scope to edit |
| Unknown | untested combinations (the manufacturer's USB audio/control software, sample transfer while the scope is open, long sessions) | report issues; revert if in doubt |

## Legal
Prebuilt images contain the manufacturer's copyrighted OS. Keep the repository **private**, don't redistribute
images, and see [DISCLAIMER.md](DISCLAIMER.md). Building from your own official OS file avoids distributing it.
