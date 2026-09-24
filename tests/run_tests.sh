#!/bin/sh
# Emulator test suite (ColdFire V4e in unicorn, running the REAL firmware code with the patches applied).
# Usage: tests/run_tests.sh <official section_3_MAIN_OS.bin> <patched section_3 .bin>
# Needs: python3, pip install unicorn pillow, and m68k-linux-gnu-nm (binutils) for two symbol lookups.
set -e
OFF="$1"; NEW="$2"
[ -f "$OFF" ] && [ -f "$NEW" ] || { echo "usage: $0 <official section_3.bin> <patched section_3.bin>"; exit 2; }
cd "$(dirname "$0")"; BIN=../bin
python3 emu_scope.py   "$NEW" $BIN/scope.sym                 # scope: TAP, waveform/X-Y/fullscreen pixels, dots, keys
python3 emu_tuner.py   "$NEW" $BIN/scope.sym $BIN/tuner.elf  # tuner: bit-exact vs model, TTAP, TDRAW
python3 emu_trig.py    "$OFF" "$NEW"                         # voice-start hook vs stock audio interrupt
python3 emu_cable.py   "$NEW" $BIN/cable.bin                 # MIDI-track -> POLY cable
python3 emu_cc.py      "$NEW" $BIN/cc.bin                    # CC cable
python3 emu_lock.py    "$NEW" $BIN/lock.bin 400ac4ec         # per-voice TUNE/LFO
python3 emu_songoff.py "$NEW" $BIN/songoff.bin               # song mode blocked
echo "ALL TESTS PASSED"
