#!/bin/bash
# Double-click in Finder: the latest Digitakt 1 mods and elekloader, ready to pick in elekloader's window.
#
# Put this file in your Elektron folder (the one holding "Digitakt 1"). Each run:
#   1. pulls the latest digi1_mods (Digi Mono and the other mods of this repo);
#   2. pulls the latest elekloader, digisophie, digislicer, DigiFilter and digineighbor, and builds every
#      mod as an .elemod from your official OS file;
#   3. moves the previous mods from "Digitakt 1/0_Latest_Mods" to "Digitakt 1/4_bin/mods_<date>", and puts
#      the new ones there, with COMPATIBILITY.txt (which pairs combine);
#   4. pulls the elekloader folder next to this file, if it is a git checkout;
#   5. offers to open elekloader's window with the new mods.
# Nothing here writes to your unit.
#
# Change these if your folders differ:
HERE=$(cd "$(dirname "$0")" && pwd)
REPO=${REPO:-$HOME/digi1_mods}
BRANCH=${BRANCH:-claude/digimono}
DT1="$HERE/Digitakt 1"
for d in "$HERE/Digitakt 1"*; do      # the folder's name may end in a space
    if [[ -d $d ]]; then DT1=$d; break; fi
done
STOCK=${STOCK:-"$DT1/1_official_firmware/Digitakt_OS1.53.syx"}
MODS_DIR="$DT1/0_Latest_Mods"
BIN_DIR="$DT1/4_bin"

export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
export STOCK

finish() {
    echo
    read -r -p "Press Enter to close this window. " _
    exit "${1:-0}"
}
fail() {
    printf '\nerror: %s\n' "$*"
    finish 1
}

echo "== Digitakt 1 mods: update"
[[ -d $DT1 ]] || fail "no \"Digitakt 1\" folder next to this file ($HERE)"
[[ -f $STOCK ]] || fail "your official OS file is not at $STOCK"

if [[ ! -d $REPO/.git ]]; then
    echo "== getting digi1_mods into $REPO"
    git clone https://github.com/gdeo607/digi1_mods "$REPO" || fail "git clone failed"
fi
echo "== digi1_mods: pulling $BRANCH"
git -C "$REPO" checkout -q "$BRANCH" || fail "could not switch $REPO to $BRANCH (local changes?)"
git -C "$REPO" pull -q --ff-only origin "$BRANCH" || fail "could not pull $REPO (local changes?)"
git -C "$REPO" log -1 --format='   %h %cs %s'

"$REPO/tools/dev.sh" mods || fail "building the mods failed (the logs are in $REPO/out/dev/log)"
NEW="${DEV:-$REPO/out/dev}/elemods"
ls "$NEW"/*.elemod > /dev/null 2>&1 || fail "no .elemod files were built"

echo
echo "== $MODS_DIR"
mkdir -p "$MODS_DIR" "$BIN_DIR"
if [[ -n $(ls -A "$MODS_DIR" 2>/dev/null) ]]; then
    OLD="$BIN_DIR/mods_$(date +%Y-%m-%d_%H%M)"
    mkdir -p "$OLD"
    mv "$MODS_DIR"/* "$OLD"/
    echo "   the previous mods are in 4_bin/$(basename "$OLD")"
fi
cp "$NEW"/*.elemod "$NEW"/COMPATIBILITY.txt "$MODS_DIR"/
for f in "$MODS_DIR"/*.elemod; do echo "   $(basename "$f")"; done
grep CLASH "$MODS_DIR/COMPATIBILITY.txt" | sed 's/^/   /'

if [[ -d $HERE/elekloader/.git ]]; then
    echo
    echo "== $HERE/elekloader: pulling"
    git -C "$HERE/elekloader" pull -q --ff-only \
        && git -C "$HERE/elekloader" log -1 --format='   %h %cs %s' \
        || echo "   not pulled (local changes?); the window below uses its own up-to-date copy anyway"
fi

echo
read -r -p "Open elekloader now, with these mods? [Y/n] " a
case $a in
    [nN]*) ;;
    *) "$REPO/tools/dev.sh" loader || fail "elekloader did not open" ;;
esac
finish 0
