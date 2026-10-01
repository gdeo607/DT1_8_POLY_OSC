# digichain

An elekloader mod (core 2.1, Digitakt mk1 OS 1.53) that lets the SRC-machine mods **SOPHIE**
(digisophie), **NEIGHBOR** (digineighbor) and **DIGISLICER** (digislicer) share one build. On its
own it changes nothing.

## Why they clashed

Each of those mods takes over some of the same firmware places. elekloader allows one owner per
byte, so it refused the pairs:

| place | what it is | SOPHIE | NEIGHBOR | DIGISLICER |
|---|---|---|---|---|
| 0x400657cc | the SRC page's layout | jmp | jmp | |
| 0x4000fe8a, 0x4000feac | a knob's label and long name | jmp | jmp | |
| 0x4000f324, 0x400657ee | a knob's value text, the pop-up's | jmp | jmp | |
| 0x4000f2bc, 0x40065794 | a knob's graphic, its UI record | jmp | jmp | |
| 0x40077fba | the render, after playback | jsr | jsr | |
| 0x4000ff20, 0x400100c4, 0x4000f534, 0x4000f5fc | the callers of the range lookup 0x40078f0c | keep2 | | keep2 |

## How digichain fixes it

Every one of those handlers acts only for its own machine (SOPHIE 7, NEIGHBOR 4, DIGISLICER 5) and
otherwise goes on to the stock code. So digichain owns each place once and sends the call to the
handler of the machine it is for:

- **labels, values, knobs, UI records:** the machine whose SRC page asked for its layout last, as the
  mods themselves assume;
- **ranges:** the machine of the sound the lookup is for, found from the object as the mods find it;
- **the render step:** SOPHIE's voices, then NEIGHBOR's (so NEIGHBOR can take a SOPHIE track's sound).

**Machine menu icons (1.2).** The menu's row loop draws a row's icon only when its icon type
(`0x40029e80`: 1-4 for the stock four, 0 past them) differs from the row above's, so with core 2.1 only
an added machine right under SLICE got its icon. digichain gives each added machine a type of its own at
that call (`0x4002a382`), so SOPHIE's, DIGISLICER's and Digi Mono's icons show; the stock four are as
they were.

**NEIGHBOR's source (1.3).** Its SLOT (knob E) is SLICE's parameter underneath: 0..64, and 0 after a
switch, while only 1-8 pick a track (0, and its own track, are silence). So a new NEIGHBOR track played
nothing, and a quick turn went past 8. digichain gives SLOT the range 0..8 on a NEIGHBOR sound, and when a
track has been NEIGHBOR for half a second with SLOT at 0 (the menu switches as its cursor moves, so
passing over NEIGHBOR does not count), sets SLOT to the track on its left (track 2 for track 1); leaving
NEIGHBOR with SLOT still as set puts it back to 0 (`chain.c`, on `ev_tick`).

Checked in digiemu (`tests/digiemu_chain.py`): NEIGHBOR's page and value texts as the original's; its pitch
shifter (from a C4 saw: 262 Hz at TUNE 0, 368 at +6, 522 at +12, 127 at -12); a new NEIGHBOR track on track 2
takes track 1 and plays with nothing set; SLOT stops at 8; Digi Mono's defaults after the menu passes it.

Digi Mono (machines 20..25, 1.1) gets its page's layout, knob graphics, UI records and knob values through
it too; Digi Mono requires digichain.

The handlers are the mods' own code, unchanged. `tools/chain_patch.py` moves their sites for those
places out of their `mod.json` when `tools/dev.sh` builds them, adds digichain to what they require and
`-chain` to their version. It refuses (and the mod is built as it is) unless every site is exactly the
one it expects, so an upstream change can't be patched wrongly. Each handler is a weak import here: a
mod that is not in the build reads as core_zero, and its machine gets the stock code.

`CHAIN=0 tools/dev.sh ...` builds the three mods as they are.

## Checked

In digiemu (`tests/digiemu_chain.py`), a build with core, digichain, the chained SOPHIE and NEIGHBOR
and Digi Mono, and one with the chained SOPHIE and DIGISLICER, each against builds with one mod as it
is:

- SOPHIE's, NEIGHBOR's, DIGISLICER's, Digi Mono's and a stock ONESHOT SRC page: the same pixels;
- SOPHIE's MODEL and DIGISLICER's PLAY turned to their ends: the same maximums (31; 4, one past
  stock's);
- SOPHIE's voice, 32 notes, and NEIGHBOR's taking a Digi Mono track, 11 notes: every block the same,
  bit for bit, from each note's start;
- NEIGHBOR taking a SOPHIE track's sound: plays (not possible before);
- every pair of the ten mods `tools/dev.sh elemods` builds combines (COMPATIBILITY.txt).

Not yet on a unit.

## Memory

digichain takes 728 bytes. The three machines' own sizes still add up: all three fit (4 KB of the
128 KB left), but DIGISLICER (88 KB) with Digi Mono and four other mods does not.
