#!/usr/bin/env bash
# Develop the mods on your own computer: set up once, then build, test and run every change.
#
#   tools/dev.sh setup                     tools: elekloader, digiemu (+ patched Unicorn), digisophie
#   tools/dev.sh test                      the engine alone: what each machine does, ColdFire = PC
#   tools/dev.sh build [mods...]           your OS file: core 2.1 + the mods (default: digimono)
#   tools/dev.sh emu                       put the last build into digiemu (first boot, ~1 min)
#   tools/dev.sh emutest                   the build in digiemu, every Digi Mono machine, bit for bit
#   tools/dev.sh play                      open digiemu's window (play the build with mouse and keys)
#   tools/dev.sh all [mods...]             test, build, emu, emutest: run this after every change
#   tools/dev.sh update                    pull the latest of every mod and tool (instead of the pinned ones)
#   tools/dev.sh elemods                   every mod as an .elemod in out/dev/elemods, for the elekloader app,
#                                          with COMPATIBILITY.txt: which pairs combine
#
# Mods for build/all: digimono, digiutils, digimatrix, digieq (this repo); digisophie, digislicer,
# digifilter, digineighbor (fetched by setup). digipoly needs core 2.0a and is not built here.
# Not every pair combines: digisophie clashes with digislicer and with digineighbor (elekloader says
# where; `elemods` writes the full table); digimono combines with all of them.
#
# Settings (environment):
#   STOCK=path/to/Digitakt_OS1.53.syx      required: your own official file (never committed)
#   DEV=out/dev                            where tools, builds and logs go (git-ignored)
#   ELEKLOADER_CROSS=m68k-elf-             the cross toolchain's prefix if not m68k-linux-gnu-
#   VERSION=D001                           what the unit shows as its OS version (4 characters)
#
# Nothing here writes to your unit. Flash out/dev/build/<name>.syx yourself (docs/DEVELOPING.md),
# and keep your official file for recovery.
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
DEV=${DEV:-$ROOT/out/dev}
TOOLS=$DEV/tools
BUILD=$DEV/build
LOG=$DEV/log
VERSION=${VERSION:-D001}
CROSS=${ELEKLOADER_CROSS:-}

# The versions everything here was checked with.
ELEKLOADER_URL=https://github.com/irpina/elekloader
ELEKLOADER_REV=b95bcccc70f72e17ce0b8638e741eecd760ce1bb
DIGIEMU_URL=https://github.com/irpina/digiemu
DIGIEMU_REV=3206402661923d94f22a586ce7e971b263f70c6a
DIGISOPHIE_URL=https://github.com/soejrd/digisophie
DIGISOPHIE_REV=ef8998195030904641648f71e86612477833a0a5
DIGISLICER_URL=https://github.com/irpina/digislicer
DIGIFILTER_URL=https://github.com/DigiAlchemydsp/DigiFilter
DIGIFILTER_REV=dee3f93cc3f79f333d02a4cc119eb6f19f3d6068
DIGINEIGHBOR_URL=https://github.com/irpina/digineighbor
DIGINEIGHBOR_REV=83c34deefbee38a2ac6309d725a5359f324de557

say() { printf '\n== %s\n' "$*"; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }

need_stock() {
    [[ -n ${STOCK:-} ]] || die "set STOCK=path/to/Digitakt_OS1.53.syx (your own official file)"
    [[ -f $STOCK ]] || die "no such file: $STOCK"
    STOCK=$(cd "$(dirname "$STOCK")" && pwd)/$(basename "$STOCK")
}

find_cross() {
    if [[ -z $CROSS ]]; then
        for p in m68k-linux-gnu- m68k-elf-; do
            command -v "${p}gcc" >/dev/null 2>&1 && { CROSS=$p; break; }
        done
    fi
    [[ -n $CROSS ]] || die "no m68k cross toolchain (gcc, as, ld): Debian/Ubuntu/WSL: apt install gcc-m68k-linux-gnu binutils-m68k-linux-gnu; macOS: brew install m68k-elf-gcc m68k-elf-binutils"
    export ELEKLOADER_CROSS=$CROSS
}

# python with unicorn 2.1.4 (patched) and numpy: digiemu's venv
emupy() { echo "$TOOLS/digiemu/.venv/bin/python"; }

fetch() {   # fetch NAME URL REV
    local dir=$TOOLS/$1
    if [[ ! -d $dir/.git ]]; then
        git clone -q "$2" "$dir"
    fi
    if [[ -n ${3:-} ]]; then
        git -C "$dir" fetch -q origin "$3" 2>/dev/null || git -C "$dir" fetch -q origin
        git -C "$dir" checkout -q "$3"
    fi
}

cmd_setup() {
    mkdir -p "$TOOLS" "$BUILD" "$LOG"
    say "checking tools"
    for t in git python3 gcc cmake; do
        command -v $t >/dev/null || die "$t is missing"
    done
    find_cross
    echo "cross toolchain: ${CROSS}gcc"
    command -v uv >/dev/null || die "uv is missing (digiemu's Python manager): https://docs.astral.sh/uv/"
    say "fetching elekloader, digiemu, digisophie, digislicer (pinned)"
    fetch elekloader "$ELEKLOADER_URL" "$ELEKLOADER_REV"
    fetch digiemu "$DIGIEMU_URL" "$DIGIEMU_REV"
    fetch digisophie "$DIGISOPHIE_URL" "$DIGISOPHIE_REV"
    fetch digislicer "$DIGISLICER_URL" ""
    fetch digifilter "$DIGIFILTER_URL" "$DIGIFILTER_REV"
    fetch digineighbor "$DIGINEIGHBOR_URL" "$DIGINEIGHBOR_REV"
    say "digiemu: Python environment and the patched Unicorn (a few minutes, once)"
    (cd "$TOOLS/digiemu" && uv sync -q && tools/install-patched-unicorn.sh > "$LOG/unicorn.log" 2>&1) \
        || die "patched Unicorn failed: see $LOG/unicorn.log"
    (cd "$TOOLS/digiemu" && uv pip install -q --python .venv/bin/python numpy)
    "$(emupy)" -c "import unicorn, numpy; print('unicorn', unicorn.__version__, '+ numpy ok')"
    if [[ -n ${STOCK:-} ]]; then
        need_stock
        say "digiemu: your official OS (first boot, about a minute)"
        (cd "$TOOLS/digiemu" && .venv/bin/python -m emu.portable --add "$STOCK" --yes > "$LOG/stock-add.log" 2>&1) \
            || die "see $LOG/stock-add.log"
    fi
    say "set up in $DEV. Next: STOCK=... tools/dev.sh all"
}

cmd_test() {
    say "engine: tables current"
    python3 "$ROOT/tools/gen_mono_tables.py" --check
    say "engine: what each machine and parameter does (tests/mono_signal.py)"
    "$(emupy)" "$ROOT/tests/mono_signal.py" | tee "$LOG/mono_signal.log" | tail -1
    grep -q "ALL SIGNAL CHECKS PASSED" "$LOG/mono_signal.log" || die "signal checks failed: $LOG/mono_signal.log"
    say "engine: the ColdFire build against the PC build, and its cost (tests/emu_mono.py)"
    "$(emupy)" "$ROOT/tests/emu_mono.py" | tee "$LOG/emu_mono.log" | tail -12
    grep -q "ALL EMULATOR CHECKS PASSED" "$LOG/emu_mono.log" || die "emulator checks failed: $LOG/emu_mono.log"
}

build_one() {   # build_one NAME SOURCEDIR -> echo the .elemod
    local stage=$BUILD/mods/$1
    rm -rf "$stage"
    cp -r "$2" "$stage"
    PYTHONPATH=$TOOLS/elekloader python3 -m elekloader.sdk.build "$stage" --stock "$STOCK" > "$LOG/build-$1.log" 2>&1 \
        || die "$1 failed to build: $LOG/build-$1.log"
    ls "$stage"/out/*.elemod
}

cmd_build() {
    need_stock
    find_cross
    local mods=("$@")
    [[ ${#mods[@]} -gt 0 ]] || mods=(digimono)
    mkdir -p "$BUILD/mods" "$LOG"
    say "building core 2.1 and ${mods[*]}"
    local files=()
    files+=("$(build_one core "$TOOLS/elekloader/mods/core")")
    for m in "${mods[@]}"; do
        case $m in
            digimono) files+=("$(build_one digimono "$ROOT/mods/digimono")") ;;
            digisophie) files+=("$(build_one digisophie "$TOOLS/digisophie")") ;;
            digislicer) files+=("$(build_one digislicer "$TOOLS/digislicer")") ;;
            digifilter) files+=("$(build_one digifilter "$TOOLS/digifilter")") ;;
            digineighbor) files+=("$(build_one digineighbor "$TOOLS/digineighbor")") ;;
            digiutils|digimatrix|digieq)
                PYTHONPATH=$TOOLS/elekloader python3 "$ROOT/tools/build_elemods.py" --stock "$STOCK" \
                    --elekloader "$TOOLS/elekloader" --out "$BUILD/mods" --mods "$m" > "$LOG/build-$m.log" 2>&1 \
                    || die "$m failed to build: $LOG/build-$m.log"
                files+=("$(ls "$BUILD/mods/$m"/out/*.elemod)") ;;
            *) die "unknown mod: $m" ;;
        esac
    done
    for f in "${files[@]}"; do echo "  $(basename "$f")"; done
    say "lint, combine, write the OS"
    local args=() name
    for f in "${files[@]}"; do args+=(--mod "$f"); done
    name=Digitakt_${VERSION}_$(IFS=+; echo "${mods[*]}")
    PYTHONPATH=$TOOLS/elekloader python3 -m elekloader.patch --stock "$STOCK" "${args[@]}" --check > "$LOG/check.log" 2>&1 \
        || { cat "$LOG/check.log"; die "the mods do not combine"; }
    PYTHONPATH=$TOOLS/elekloader python3 -m elekloader.patch --stock "$STOCK" "${args[@]}" \
        --out "$BUILD/$name.syx" --version "$VERSION" > "$LOG/patch.log" 2>&1 || { cat "$LOG/patch.log"; die "patch failed"; }
    tail -2 "$LOG/patch.log"
    printf '%s\n' "${files[@]}" > "$BUILD/last.mods"
    echo "$BUILD/$name.syx" > "$BUILD/last.syx"
    say "built $BUILD/$name.syx (shows as $VERSION on the unit)"
}

last_syx() { [[ -f $BUILD/last.syx ]] || die "nothing built yet: tools/dev.sh build"; cat "$BUILD/last.syx"; }

emu_folder() {   # the digiemu folder for the last build (by its sha256)
    local sha
    sha=$(python3 -c "import hashlib,sys;print(hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest()[:8])" "$(last_syx)")
    ls "$TOOLS/digiemu/portable/firmware" | grep -- "-$sha\$" | head -1
}

cmd_emu() {
    local syx
    syx=$(last_syx)
    say "digiemu: $(basename "$syx") (first boot, about a minute)"
    (cd "$TOOLS/digiemu" && .venv/bin/python -m emu.portable --add "$syx" --yes > "$LOG/emu-add.log" 2>&1) \
        || die "see $LOG/emu-add.log"
    echo "digiemu folder: $(emu_folder)"
}

cmd_emutest() {
    need_stock
    local fw before=0
    fw=$(emu_folder)
    [[ -n $fw ]] || die "the last build is not in digiemu yet: tools/dev.sh emu"
    grep -q digisophie "$BUILD/last.mods" && before=$((before + 1))
    grep -q digislicer "$BUILD/last.mods" && before=$((before + 1))
    grep -q digineighbor "$BUILD/last.mods" && before=$((before + 1))
    local mods=()
    while IFS= read -r line; do mods+=("$line"); done < "$BUILD/last.mods"   # (bash 3.2 has no mapfile)
    local ok=1
    for m in SIN NOIS SAW PULS ENS VO; do
        say "digiemu: MONO $m on track 1"
        "$(emupy)" "$ROOT/tests/digiemu_mono.py" --digiemu "$TOOLS/digiemu" --fw "$fw" --machine "$m" \
            --menu-before "$before" --png "$LOG/png_$m" --wav "$LOG/MONO_$m.wav" \
            --stock "$STOCK" --elekloader "$TOOLS/elekloader" --mods "${mods[@]}" > "$LOG/digiemu_$m.log" 2>&1 || true
        grep -E "^  (ok|FAIL)" "$LOG/digiemu_$m.log" | sed 's/^/  /'
        grep -q "ALL DIGIEMU CHECKS PASSED" "$LOG/digiemu_$m.log" || ok=0
    done
    [[ $ok == 1 ]] || die "some digiemu checks failed: $LOG/digiemu_*.log"
    say "every machine passed; recordings in $LOG/MONO_*.wav, screens in $LOG/png_*"
}

ELEMOD_ALL=(digimono digiutils digimatrix digieq digisophie digislicer digifilter digineighbor)

cmd_update() {   # the latest of every fetched project (instead of the pinned versions)
    say "pulling the latest elekloader, digiemu and mods"
    for d in elekloader digiemu digisophie digislicer digifilter digineighbor; do
        [[ -d $TOOLS/$d/.git ]] || { echo "  $d: not fetched (run setup)"; continue; }
        local b
        b=$(git -C "$TOOLS/$d" remote show origin 2>/dev/null | sed -n 's/.*HEAD branch: //p')
        git -C "$TOOLS/$d" fetch -q origin && git -C "$TOOLS/$d" checkout -q "origin/${b:-main}" \
            && echo "  $d: $(git -C "$TOOLS/$d" log -1 --format='%h %cs %s' | cut -c1-70)"
    done
    git -C "$ROOT" pull -q --ff-only 2>/dev/null && echo "  digi1_mods: $(git -C "$ROOT" log -1 --format='%h %cs %s' | cut -c1-70)" \
        || echo "  digi1_mods: not pulled (local changes, or no upstream); pull it yourself"
    echo "  (digiemu changed? run setup again for its Python environment)"
}

cmd_elemods() {   # every mod as an .elemod, in one folder, with which pairs combine
    need_stock
    find_cross
    local out=$DEV/elemods
    rm -rf "$out"; mkdir -p "$out" "$BUILD/mods" "$LOG"
    say "building every mod's .elemod into $out"
    cp "$(build_one core "$TOOLS/elekloader/mods/core")" "$out/"
    local ok=() m f
    for m in "${ELEMOD_ALL[@]}"; do
        case $m in
            digimono) f=$(build_one digimono "$ROOT/mods/digimono") ;;
            digiutils|digimatrix|digieq)
                PYTHONPATH=$TOOLS/elekloader python3 "$ROOT/tools/build_elemods.py" --stock "$STOCK" \
                    --elekloader "$TOOLS/elekloader" --out "$BUILD/mods" --mods "$m" > "$LOG/build-$m.log" 2>&1 \
                    || { echo "  $m: FAILED (see $LOG/build-$m.log)"; continue; }
                f=$(ls "$BUILD/mods/$m"/out/*.elemod) ;;
            *) [[ -d $TOOLS/$m ]] || { echo "  $m: not fetched (run setup)"; continue; }
               f=$(build_one "$m" "$TOOLS/$m") ;;
        esac
        cp "$f" "$out/" && ok+=("$out/$(basename "$f")") && echo "  $(basename "$f")"
    done
    say "which pairs combine (elekloader --check, with core)"
    local core i j a b
    core=$(ls "$out"/core-*.elemod)
    : > "$out/COMPATIBILITY.txt"
    for ((i = 0; i < ${#ok[@]}; i++)); do
        for ((j = i + 1; j < ${#ok[@]}; j++)); do
            a=${ok[i]}; b=${ok[j]}
            if PYTHONPATH=$TOOLS/elekloader python3 -m elekloader.patch --stock "$STOCK" --mod "$core" \
                    --mod "$a" --mod "$b" --check > "$LOG/pair.log" 2>&1; then
                echo "ok      $(basename "$a") + $(basename "$b")" >> "$out/COMPATIBILITY.txt"
            else
                echo "CLASH   $(basename "$a") + $(basename "$b"): $(grep -E 'overlap|claim|both|conflict' "$LOG/pair.log" | head -1 | sed 's/^ *//')" \
                    >> "$out/COMPATIBILITY.txt"
            fi
        done
    done
    grep CLASH "$out/COMPATIBILITY.txt" || echo "  every pair combines"
    say "done: open elekloader, add the .elemod files from $out (core is built in), tick the ones you want"
}

cmd_play() {
    cd "$TOOLS/digiemu" && exec .venv/bin/python -m emu.portable
}

cmd_all() {
    cmd_test
    cmd_build "$@"
    cmd_emu
    cmd_emutest
}

case ${1:-} in
    setup) shift; cmd_setup "$@" ;;
    test) shift; cmd_test "$@" ;;
    build) shift; cmd_build "$@" ;;
    emu) shift; cmd_emu "$@" ;;
    emutest) shift; cmd_emutest "$@" ;;
    play) shift; cmd_play "$@" ;;
    update) shift; cmd_update "$@" ;;
    elemods) shift; cmd_elemods "$@" ;;
    all) shift; cmd_all "$@" ;;
    *) sed -n "2,27p" "$0" | sed 's/^# \{0,1\}//'; exit 2 ;;
esac
