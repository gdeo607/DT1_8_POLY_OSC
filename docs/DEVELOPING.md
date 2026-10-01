# Developing on your own computer

One script, `tools/dev.sh`, runs the whole loop:

1. set up the tools (once);
2. check the synth engine;
3. build an OS file from your own official OS and the mods;
4. boot it in the digiemu emulator and play every Digi Mono machine there, checking the audio bit for bit;
5. open the emulator's window to play it yourself;
6. flash it on your unit when you are happy.

It never writes to your unit, and it never puts firmware in git: everything it makes goes to `out/dev/`,
which git ignores.

## The easy path: one elekloader app that keeps itself up to date

If you only want to pick mods and build your own `.syx`, this is all you need.

Once, on macOS, in Terminal:

```sh
brew install git python python-tk m68k-elf-binutils m68k-elf-gcc
git clone https://github.com/gdeo607/digi1_mods ~/digi1_mods
cd ~/digi1_mods && git checkout claude/digimono
tools/macos/install_app.sh ~/Desktop/Elektron     # your Elektron folder, the one holding "Digitakt 1"
```

That makes `elekloader.app` in the Elektron folder. It also moves older elekloader launchers to
`Digitakt 1/4_bin/old_launchers_<date>`, so only one is left; nothing is deleted. Double-click it:

- **It is elekloader's own window,** run from a copy of elekloader that it keeps current. The first
  time, it asks for your official `Digitakt_OS1.53.syx`, and remembers it.
- **When it opens, it checks GitHub** for new versions of elekloader, digi1_mods and the mods, and
  offers to update. **Check for updates** (top, next to the title) does the same at any time.
- **The Version tab** (next to Description, Changes, Requirements) says, for the selected mod, whether
  GitHub has something newer, which commit it was built from and where it comes from, with an
  **Update now** button. For a copy you installed by hand it says so, and whether a kept-up-to-date
  copy of the same mod is listed too.
- **Updating** fetches them, builds every mod from your OS file, lists the new mods in the window, puts
  them in `Digitakt 1/0_Latest_Mods`, and moves the previous ones to `Digitakt 1/4_bin/mods_<date>`.
  When elekloader itself changed, it offers to restart into the new version.
- **Only one window at a time:** opening it again while it is open says so.

Then tick the mods you want (it marks pairs that clash) and click BUILD FIRMWARE. Flash the `.syx` as in
step 6. Its log is `~/Library/Logs/elekloader.log`.

A mod you once added with "Install from file..." stays in elekloader's library and is listed instead of
a newer file of the same name: Uninstall it in the window.

Without the app (any system): `tools/dev.sh mods` builds the latest mods into `out/dev/elemods`, and
`tools/dev.sh loader` opens the window with them. `python3 tools/elekloader_app.py` is the window with
updates, as the app runs it.

## 1. What you need (once)

| | macOS | Linux / Windows (WSL2, Ubuntu) |
|---|---|---|
| basics | `xcode-select --install`, then `brew install git python python-tk cmake uv` | `sudo apt install git python3 python3-pip cmake build-essential`, then install uv: `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| ColdFire cross compiler | `brew install m68k-elf-gcc m68k-elf-binutils` (found on its own) | `sudo apt install gcc-m68k-linux-gnu binutils-m68k-linux-gnu` |
| your official OS | `Digitakt_OS1.53.syx` from Elektron's Digitakt download page | same |

- **Windows:** use WSL2 (Ubuntu) for the script. digiemu's window runs there through WSLg on Windows 11.
  digiemu also has a Windows app of its own (its Releases page): Add firmware, pick a `.syx` the
  script built.
- **Your official OS file stays on your disk.** The script reads it, checks its SHA-256 (elekloader
  refuses any other file) and never copies it into the repository.

## 2. Set up (once, about 10 minutes)

```sh
git clone https://github.com/gdeo607/digi1_mods && cd digi1_mods
git checkout claude/digimono                     # or main, once it is merged
export STOCK=~/Elektron/Digitakt_OS1.53.syx      # your official file
tools/dev.sh setup
```

`setup` does four things:

- **checks the tools** listed above;
- **fetches the helper projects** into `out/dev/tools/`: elekloader (the mod loader that builds the OS
  file), digiemu (the emulator), digisophie, digislicer, DigiFilter and digineighbor, at the versions everything was checked with;
- **builds digiemu's patched Unicorn** (the CPU emulator; a few minutes);
- **boots your official OS** once in digiemu (about a minute).

## 3. The loop: after every change

```sh
tools/dev.sh all                       # Digi Mono alone
tools/dev.sh all digimono digisophie   # or with other mods: digisophie digineighbor digislicer digifilter digiutils digimatrix digieq
```

`all` runs the four steps below and stops at the first failure, naming its log in `out/dev/log/`.

| step | command | what it proves | time |
|---|---|---|---|
| engine | `tools/dev.sh test` | every machine and knob does what DESIGN.md says (pitch, formants, aliasing, levels...), and the ColdFire build gives exactly the PC build's samples; prints the CPU cost per machine | ~2 min |
| build | `tools/dev.sh build [mods]` | the mods build, pass elekloader's checks and combine; writes `out/dev/build/Digitakt_<VERSION>_<mods>.syx` | ~30 s |
| emulator | `tools/dev.sh emu` | the OS boots in digiemu (the real firmware on an emulated Digitakt) | ~1 min |
| in the firmware | `tools/dev.sh emutest` | each Digi Mono machine on track 1: the machine list, its SRC page names and defaults, knob ranges, a note at every trig, every block of audio bit for bit against the engine, the note on the master output. Leaves a recording (`out/dev/log/MONO_*.wav`) and screenshots (`out/dev/log/png_*/`) of each | ~4 min |

- **Engine only:** while working on the sound, `tools/dev.sh test` alone is enough.
- **Hearing it:** `python3 tools/mono_render.py --machine VO --syn 43,113,64,0,16,90,127 --note 45 --out x.wav`
  writes a WAV of the engine alone.
- **Changing the hooks, the SRC page or anything firmware-side:** run `all`.

Checks that are not in `all` yet:

- **FLTR / AMP / LFO pages:** `out/dev/tools/digiemu/.venv/bin/python tests/digiemu_mono_fx.py --digiemu
  out/dev/tools/digiemu --fw <folder>` runs those cases, the digiemu folder being what `tools/dev.sh emu`
  printed. Two of its checks (FREQ, VOL) fail until the open issue in mods/digimono/DESIGN.md is fixed.
- **CPU on a real unit:** that needs digihealth's SYSTEM INFO on hardware (step 5).

## 4. All the mods as .elemod files, for the elekloader app

```sh
tools/dev.sh update      # optional: the latest of every mod and of elekloader, instead of the pinned versions
tools/dev.sh elemods
```

`elemods` writes `out/dev/elemods/`:

- **Your repo's mods:** digimono, digiutils, digimatrix and digieq.
- **The others:** digisophie, digislicer, DigiFilter, digineighbor and digihealth.
- **core:** the elekloader app has core built in.
- **COMPATIBILITY.txt:** elekloader's check for every pair: `ok`, `CLASH` with the overlapping address,
  or `TOO BIG` when the two need more than the 128 KB of mod RAM. digisophie, digineighbor and
  digislicer are built for digichain (`-chain` versions, mods/digichain/README.md), so they combine with
  each other; on 2026-10-01 every pair of the ten combined. Several big mods together can still be too
  big for the RAM: the window says so.

Each `.elemod` is built from your own official OS file, so nothing of Elektron's is in it. Then:

1. Open the elekloader app (its Releases page has Windows and macOS builds).
2. Give it your official `Digitakt_OS1.53.syx` the first time.
3. Add the `.elemod` files from `out/dev/elemods/` and tick the mods you want; it refuses a pair that
   clashes.
4. BUILD FIRMWARE: it writes and verifies the `.syx`. Flash it as in step 6.

The app's core and the core the mods were built against must match. After `update`, use an app at least
as new as the elekloader commit `update` printed, or build from the command line (`tools/dev.sh build
<mods>`), which uses the same checkout as the mods.

## 5. Play it yourself in the emulator

```sh
tools/dev.sh play
```

This opens digiemu's window with the builds you added. Click the keys, use the mouse wheel on the
knobs, and listen. FUNC+SRC then scroll past SLICE picks a Digi Mono machine. The factory samples are not
in digiemu, but Digi Mono needs none.

## 6. On your unit

Flash the `.syx` from `out/dev/build/` the way docs/INSTALL.md describes (back up first, keep the official
file, know the recovery route). For each build, before you rely on it:

1. Check that the unit shows the version you built (`VERSION=D002 tools/dev.sh build` sets it).
2. Put one Digi Mono machine on one track, play it, and turn its knobs and the FLTR / AMP pages.
3. With digihealth in the build, watch SYSTEM INFO's DSP load as you add Digi Mono tracks. The engine
   costs 3-8 % of the render per playing voice; note where the unit starts to click.
4. Write what you saw in CHANGELOG.md (the "HW:" line of that build).

Only a build that ran on the unit counts as hardware-verified.

## 7. Keeping your work

- **Branches:** one per change (`git checkout -b my-change`). Commit the sources and their tests, never
  `out/` or a `.syx`.
- **Versions:** bump `mods/digimono/mod.json`'s `version` when the mod changes, and set `VERSION` so each
  flashed build shows a different number on the unit.
- **Sound changes:** a change to mono.c's behaviour needs its check in tests/mono_signal.py. A change to
  where the mod hooks the firmware needs docs/TECHNICAL_NOTES.md (how the address was found) and a
  `tools/dev.sh all` run.
- **New helper versions:** `tools/dev.sh` pins elekloader, digiemu and digisophie. To move to newer ones,
  change the `*_REV` lines and run `setup` and `all` again.
