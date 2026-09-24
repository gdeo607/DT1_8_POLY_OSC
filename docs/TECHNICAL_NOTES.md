# Technical notes (reverse-engineering log)

Chronological working notes from the development of every build (v1 .. v3p), kept verbatim for reference:
addresses in the MAIN OS (load address 0x40000400), data structures, call paths, and how each hook was verified.
File paths inside refer to the original working folders (poly_v2/..., analysis/...); in this repository the
sources are in src/, the build in tools/, the tests in tests/. Latest findings are at the end
(display orientation, key ids, knob/key/LED dispatch, reclaimed code ranges).

---

# OS 1.53 - reverse engineering notes (Ghidra, ColdFire, base 0x40000400)

## MIDI input path
- 40008c6e  Brain::processMidiEvent (dispatcher, 1274 B)
  - 400c507e  get event struct: +0x8 channel/track, +0x10 note, +0x11 velocity, +0x12 note-off flag, +0x14 value, +0x1c, +0x1e
  - 4001c10a  note -> record into pattern (track 0-15, step clamped 0-63), then push 16-byte event
             {time, track, step, note} into per-track queue at seqObj+0x39d88+track*0x28
  - 4001aca4  CC -> parameter update (1192 B)
  - 400088b6  note -> trig edit helper
- 4013865a  getter for the big sequencer/player object (used by ~390 functions)
- 40012a02(40015786(obj), track) -> per-track pattern object; 40024xxx = trig getters/setters (note, vel, length...)

## Per-track queue helpers
- 40017416 clear all 16 queues; 40016538 search queue; 40140e3e destructor

## Parameter storage
- 4000e2b4  KitActive::updateSingleMirror - copies 8 words per track, track stride 0xA00 (persistence mirror)
- 400227f2  Sound::updateMirror, 400267a2 Track::updateMirror

## Song mode (candidate space to reclaim, ~19 KB, 0x401b3498-0x401b6d78 vtables)
- SongEditView, SongMenuView, SongTempoMenuView, SongSelectCreateMenuView, SongModePopup, SongSelectMenuView, SongBrowserView, Song

## Audio side (unresolved)
- 40067782  hardware self-test (audio interrupt / codec checks)
- 35 EMAC-using functions around 40071000-40077fff and 400ed000, using internal SRAM 0x8000xxxx
- section 8 = Cortex-M I/O coprocessor (USB, MIDI, flash, calibration) - not voice related
- Where trigs become sound: NOT FOUND YET

## AUDIO ENGINE (found)
- 40077420  audio interrupt handler (ends in rte). Runs on the ColdFire. Pops messages from a queue (400edf00),
  message+0 = type, message+0x8 = VOICE INDEX (0-7), +0xc id, +0x14 level, +0x18 sample, +0x24 flags,
  +0x28 voice buffer ptr, +0x34/+0x38 retrig/time, +0x3c, +0x44 p-lock block. Message size 0x4c.
  Per-voice state: 0x4399dca8 (stride 0x14), 0x4399dc80, 0x4399db54 (last id per voice), mute mask 0x4199e47c.
- 4007041c  sequencer clock interrupt (timer). Posts messages to the audio queue.
- 400ee036  allocate message, 400ee1bc post message.

## INTERNAL TRIG PATH (patch target)
- 4006fb82  per-step loop over 16 tracks. Audio tracks 0-7 -> 4006f4be, MIDI tracks 8-15 -> 4006f846 (chords)
- 4006f4be  build audio-track trig message. At 4006f76a/4006f76e:
      4006f76a  move.l D0,(0xc,A2)
      4006f76e  move.l D5,(0x8,A2)     <- voice index = track (D5)
  After this, D5 is only used as a voice index (buffer ptr at 4006f7c4). No branches land in 4006f76a-4006f775.
- MIDI input does NOT pass through 4006f4be.

## POLY v1 PATCH DESIGN (not built yet)
- Replace 8 bytes at 4006f76a with: jsr HOOK (6 bytes) + nop (2 bytes)
- HOOK:
      move.l  D0,(0xc,A2)        ; original instruction
      tst.l   D5                 ; only track 1 (index 0) is redirected
      bne.b   .store
      move.l  (counter,PC),D5
      addq.l  #1,D5
      cmpi.l  #N,D5              ; N = group size (e.g. 4)
      blt.b   .ok
      moveq   #0,D5
  .ok lea     (counter,PC),A0    ; A0 is reloaded by caller at 4006f77c
      move.l  D5,(A0)
  .store
      move.l  D5,(0x8,A2)
      rts
  counter: dc.l 0
- Placement: no padding exists in the code region; hook must go in reclaimed song-mode code.
- v1 limitations: tracks 2..N must be left with no trigs and hold a copy of track 1's sound;
  do not mute tracks 2..N (mute is per voice); prefer AHD amp envelope (note-length handling keyed to track unverified);
  live knob changes on track 1 are not yet mirrored to 2..N; trig-key live play uses another path (4006edf4), not covered.

## SESSION 2 FINDINGS (UI + param sharing design)
Tooling on the Mac VM (persisted outside the folder, may vanish): $HOME/tools/{jdk-21.0.8+9,ghidra_12.1.3_PUBLIC}, project $HOME/gp.
GitHub is reachable from the device VM (not from the cloud container). Full disassembly dump: gp/out/all.txt (regenerate with AllAsm.java).

### PLAY MODE (the "sample mode list") - UI facts
- Param descriptor tables for Play Mode ("Play Mode", short "PLAY"): 401ab3e8 (Sample machine), 401ab588 (Werp), 401ab728, 401ab8c8.
  Layout per param: [.. 0, idx, min, max, default, 1 | header 0011ffff,0x81,0x6f,0xe00,nameptr,catptr,shortptr].
  Play Mode block = {0, 0x12, 0, 0x300, 0x300, 1}: max=0x300 (3<<8), default 0x300 (=FWD). Values are 8.8 fixed point.
  => to add a 5th entry POLY: raise max 0x300 -> 0x400 in the 4 tables (word located 3 words before each 0011ffff header... verify by dumping).
- Value->text formatter: function 4005f91c (ptr stored into RAM vtable at 4197c768 by init code near 40152240).
  value(>>8): 0="REV"(401cca7c), 1="REV.L"(401c65e5), 2="FWD.L"(401c65eb), 3="FWD"(401c65f1). Falls to rts (no text) otherwise.
  Uses jmp 40000e82 (snprintf). Region 4005f8ec..4005f97a is not auto-disassembled (use ForceDis.java).
  => add case 4 -> "POLY" (needs 5 bytes string + ~12 bytes code in reclaimed song-mode space).

### SOUND PARAM PATH TO THE AUDIO ENGINE (critical for poly)
- Message builder 4006f4be builds audio msg. msg+0x28 = pointer to the track's 0xa2-byte live param block
  (base = *(0x800019ac) + 0x20 + track*0xa2). msg+0x8 = voice index. Voice pointer computed from D5 AFTER the voice store,
  so the hook must NOT modify D5; store the chosen voice into (0x8,A2) from a scratch reg (D1/D6/D7/A0/A1 are dead at 4006f76a).
- Engine (ISR 40077420, handler at ~40077b4a): if msg+0x28 !=0 and != stored ptr[voice] (table S[0x131+voice], S=0x800014F0)
  -> 40077282(ptr,voice): stores ptr, copies 0x6a bytes from ptr+0x14 into per-voice state, 400749cc expands 53 words to 32-bit
  (value<<16) at 0x80002B50+voice*0xd4. If ptr equals stored -> only dirty words are re-copied (40074a40, dirty mask 0x4399db14+voice*8).
  msg+0x44 = p-lock {idx,value} block applied by 40074b0a.
- DESIGN: for a POLY control track, every trig message keeps msg+0x28 = CONTROL track's param block and only msg+0x8 changes to the
  chosen poly voice. No parameter mirroring is needed. To avoid stale copies after knob edits, the hook also clears
  S[0x131+voice] (0x800014F0+(0x131+voice)*4) so the engine does a full 0x6a-byte copy at every trig.
- Open question: engine reads of Play Mode value 4 (unknown handling in undisassembled EMAC region). Options: (a) clamp
  value 4 -> 3 right after the 3 copy routines (400749cc, 40074a40, 40074b0a), (b) keep value 3 and store POLY as a separate flag.

### CORRECTION (owner clarified): POLY goes in the FUNC+SRC MACHINE list (ONESHOT, WERP, REPITCH, SLICE), NOT in Play Mode.
The Play Mode analysis above is NOT the UI target (the 4 "Play Mode" tables are per-machine param tables, one per machine).
- Machine name tables: 401a9a40 = {long,short} x4: ONESHOT/SAMP, WERP/WERP, REPITCH/PTCH, SLICE/SLIC (8 bytes per machine).
  401a9a00.. holds BD,SD,.. MA..MH names before it; 401a9a60 immediately follows with an unrelated table => the name table has NO room to grow, must be relocated.
- Getters with hard bounds (cmp #3 => index 0..3): 4007910c (long name, else "?" 401c4084), 4007912c (short name), 4007914c (short name; idx>=4 falls to table 401a99c4).
  Callers: 4002a0f2 (menu text), 4003a638/4003b272/4003bbfe, 400a4342.
- Param descriptors: one flat array at 401a9d9c, stride 0x34, ~0xa4 entries (getter 40078ff6). Per-machine 8-param blocks (0x1a0 bytes) for SRC page:
  first block (ONESHOT, cat "Sample") ~401ab39c, second (WERP, cat 0x401ccae6) ~401ab53c, 401ab6dc, 401ab87c. Machine->param-id mapping table NOT found yet.
- Classes: MachineListView (ctor args: int, trackID, machineType_t, synthParams_t, int, int, bool), MachineParameterPageView (showAndUpdateMachineList, getMachineTypeToShow).
- TODO: locate list population/count (4), machine->param table, per-track machine storage, and how the audio message/engine treats machineType (POLY should behave as ONESHOT there).

### MACHINE LIST (FUNC+SRC) - constructor located (owner: add a 5th entry, replace nothing)
- 4002a736 = MachineListView ctor (vtable 40182434). It builds the item list from a std::vector<int> made by 40022f6a.
- 40022f6a: builds vector {0,1,2,3}: loop `40022fe6 moveq 4,D0 ; cmp D2,D0 ; bne` => change 0x7004 -> 0x7005 to also push id 4
  (vector capacity is 16 bytes/4 ints; the 5th push_back goes through the realloc path 40142826, already handled).
- Cursor placement in ctor at 4002a9e8: `moveq 4,D4 ; cmp D1,D4 ; bcs` (D1 = currentMachine+1) => change 0x7804 -> 0x7805 so id 4 can be pre-selected.
- Item text: name getters 4007910c/4007912c/4007914c index table 401a9a40 (8 B/machine) with `cmp #3` bound; table has no room => relocate to reclaimed space, 5 entries, patch 3 lea + 3 bounds.
- WARNING: machine id 4 is ALSO used by getter 4007914c's fallback (ids >=4 -> table 401a99c4 = AMP,SRC,FILT,REV,DEL,COMP,EXT,ERR,SRC,CC,CC,LFO1,LFO2,TRIG,META = page names).
  Check whether that shares the machineType_t enum before choosing id 4 (alternative: a new id such as 0x10+ mapped to name POLY).
- Per-machine SRC param blocks use param ids ONESHOT 0x6e.., WERP 0xb7.. (descriptor header word 3). Machine->param-id mapping still to find
  (code near 40152058 uses 0x6e/0x6f/0x76 immediates, 400130c4 pushes 0x6e).
- Still to trace: selection callback (4002a56e is called with view,0 from the ctor lambdas), where machine type is stored per track/kit,
  engine handling of machine type.

### MACHINE TYPE PLUMBING (traced, session 2)
- Per-track machine type = BYTE at (0x7e) of the track's sound-param object (the 0xa2-byte block at *(0x800019ac)+0x20+track*0xa2; saved with kit).
  Getter: 4002200a (returns byte, -1 if no object; ~21 callers: 40015e00 4001928a 40019312 40019466 4001956c 400220fc 40022ff8 40028f3c 4002ae0a 4002b6bc
  4002b9aa 4002bb9c 40039e3c 4003af46 4003b272 4003bbfe 4003bee8 4006cd1a 4006d790(x2) 400a16c4).
- Setter: 400225ca(soundObj, machine, ?, flag): REJECTS machine>3 (400225f0 `moveq 3,D0; cmp D2,D0; bcs`) -> change 7003 -> 7004.
  Stores (0x7e); if changed calls 400220fc (reset the machine's params), then sends 0xe7/0xf messages (400d6d68/400d6d20).
- Wrapper 4000d9fc(kit, track(0..7), machine, flag) -> soundObj = kit+0x60+track*0xc8. Callers: 40018f46, 4002a56e (list confirm), 4002bb9c.
- Param slot->param-id lookup 40078f44(slot, machine): slots 0x11..0x18 (8 machine params) use RAM table 4199e9c4[machine*8+slot-0x11]; machine>3 -> returns 0.
  RAM table is built by 40078b20 from ROM descriptors (flat array 401a9d9c, stride 0x34; descriptor word0 = machine id, word1 = slot). Table has NO room
  for machine 4 (4199ea44 follows and is used) => ALIAS machine 4 -> 0 inside 40078f44 (and 40084ef6 default-init uses it too).
- Engine side: 4007725a copies byte ptr+0x7e into per-voice array at 0x800018BC[voice] (machine type used by the audio ISR) => alias 4->0 there.
  4007a2fe/4007a314 (another engine-facing copy into (0x80,A2)) already clamps: value>3 -> 0, so POLY is safe on that path.
- SAFEST v2a APPROACH: POLY == ONESHOT everywhere except (a) list/UI names, (b) poly voice logic. Alias in the getter 4002200a (return 0 for 4) and give the
  UI callers a raw-getter copy; alias in 40078f44 and 4007725a.
- Machine-list ctor 4002a736: item vector from 40022f6a ({0..3}); cursor limit at 4002a9e8. Confirm handler 4002a56e -> 4000d9fc.
- id 4 vs page-name enum (401a99c4) collision is only in name getter 4007914c's fallback branch; the 4 sample-machine getters index 401a9a40 directly.

### v2a / v2b BUILT (poly_v2/)
- v2a: machine list entry + aliasing (see make_v2a.py). v2b adds the voice logic hook at 4006f76a (HK at 400b8d9c, 192 bytes, GNU as -mcpu=5475).
- Free space used: body of SongTempoMenuView draw slot 400b8cf8 (only vtable ref 401b5a84; 1608 B contiguous code; ends 400b9340). v2b uses up to 400b8e5c.
- Counter: 0x4208c8a8 = static word referenced only by song-mode code (400b8072). Engine table cleared per poly voice: 0x800019b4+4*voice.
- Builder arg3 (function (0x48,SP)) = params base; block(t) = base+0x20+t*0xa2; machine byte at +0x7e (POLY=4).
- Tools: cloud container has binutils-m68k (m68k-linux-gnu-as -mcpu=5475) and unicorn; emu_test_v2b.py runs on the Mac VM too (pip install --user unicorn).

### v2a FIRST HARDWARE RESULT: POLY did not appear (list still 4 rows) -> fixed
- Cause: MachineListView builds its scroll model with page size 6 (4002a76e `pea 6`; model 400c39b6 stores it at +0x1c; scroll offset = max(0, sel-page+1)
  in 400c33ee) but its draw loop (4002a2f8..4002a306) only draws 4 rows. With 4 items no scrolling was ever needed; the 5th item sat on an undrawn row.
- Fix (patch 9 in make_v2a/v2b): page size 6 -> 4 (4878 0006 -> 4878 0004). Rebuilt v2a/v2b syx (sha256 in recovery/SHA256SUMS.txt).

## Cursor fix (patch 10)
Cursor could not reach POLY: the by-index select helper at 0x4002a4c6 (called by up/down key cases via 0x4002a56e) had `moveq #4,D1` (idx+1<=4 -> model select), limiting idx to 3. Patched 0x4002a4ca 7204->7205. List model move fn 0x400c32a4 verified in unicorn (count 5, page 4, margin 1 reaches sel 4). v2a sha 43a91fee..., v2b sha b58357fd....

## POLY icon (patch 11, poly_v2/icon_patch.py)
List row icons: group getter 0x40029e80 (table 01..04) -> icon draw 0x40029e9c selects static 7x11 bitmap objects (RAM 0x421f96fc/961c/9420/935c, init in 0x40106b54; obj = vtable 401b73b4,h,w,words,glyph,mask). Added group 5: static bitmap object (capital P) at 0x400b9100 + hook at 0x400b9190 (via 0x40029f60 default exit), table at 0x400b9180.
Lesson: ColdFire max insn length is 6 bytes; 'move.l #imm,(d16,An)' (8 bytes) is illegal -> Exception at 400b91a2. Fixed via D0. Audit hooks for >6-byte insns.

## v2c chord input
Entry hook at builder 4006f4be (patched to jmp 400b8e60, ORIG stub inside hook re-executes the 2 replaced insns and jumps to 4006f4c4). Hook: if track t is POLY rank r and control c (lowest POLY) has trig at step and MIDI track c+8 has trig at step, MIDI note arrays (0x280+i*0x40, defaults 0x384+i) give offsets (raw-0x40; 0x40 = off); r==0 -> normal call, msg+8=c; r>=1 with offset r-1 -> builder called with track:=c (control data, control params ptr), then msg+8=t, msg+0x18 += offset, engine table[t] cleared. emu_test_chord.py checks model vs hook (registers, sp, NULL args). ColdFire max insn len 6 bytes: all assembled with GNU as -mcpu=5475.
v2c: msg+0x18 note is only used by ISR when msg+0x24 bit16 (note p-lock flag) is set -> hook sets it whenever it applies a pitch delta.

## v2c condition gate
Chord hook (692 bytes at 0x400b8e60) calls eaac8(default cond) if lock==-1, then eab10(m,step,lock,1); state byte
0x421ed5f4[m] restored. Result stored as marker at control slot+0x48 (set before and after the builder call, as
the builder may clear the slot); followers read it. Emulator test: /tmp/w/emu_chord7.py (multi-track pass).

## Freeze on v2c condition-gate build (owner report, 2026-09-22)
Flashing the condition-gate build (calls into 0x400eaac8 / 0x400eab10 from inside the trig-message builder hook) froze
the whole machine (no exception screen, unlike the earlier illegal-instruction crash). Not yet root-caused. Found while
investigating: 0x400eab10's real per-machine state array is at 0x421ed638 (LONGWORD-indexed, a0*4), NOT the byte array
0x421ed5f4 the hook was snapshotting/restoring - the snapshot/restore was a no-op against the wrong address, not
itself the hang cause, but it shows the calling assumptions into that routine were incomplete. Do not call
eaac8/eab10 from this hook again without confirming call-context safety (interrupt state, reentrancy) on real hardware
via a minimal isolated test first.
Mitigation shipped: poly_v2/DT_OS1.53_POLY_v2c_safe.syx = chord5.bin hook (470 B, no condition gate, same logic
verified working on hardware before the condition-gate change) repacked fresh from official OS. sha e505207e...

## v2c_safe confirmed working on hardware (owner, 2026-09-22)
poly_v2/DT_OS1.53_POLY_v2c_safe.syx (sha e505207e...) flashed and confirmed working as expected. This is the
current known-good baseline: POLY rotation + MIDI-partner chord entry (NOT1 = root, per-track pitch offset), no
trig-condition gating on the MIDI track. Use this as the base for any further changes (condition gate retry, v2d
per-voice tune/LFO independence + filter/amp offsets) rather than building on the frozen condition-gate binary.

## Register-preservation bug found while building the v2_probe test (2026-09-22)
The chord hook's outer save/restore only covers d2-d7/a2-a3 (movem mask matching chord5/6/7/8/9's
"lea -32(sp),sp; movem d2-d7/a2-a3,(sp)" prologue). But the function it replaces, ORIG at 0x4006f4c4, saves
d2-d7/a2-a6(fp) (movem mask 7cfc = a2,a3,a4,a5,a6 all included) - the hook is missing a4/a5/a6 protection.
This was invisible on hardware so far because the hook's own code never used a4-a6 as scratch, so nothing
ever clobbered them - but a called function that DOES use a4-a6 internally (unconfirmed for eaac8/eab10's
condition-type handlers, not fully disassembled) would leak corrupted values to the caller with no crash at
the call site itself, a classic source of a later silent hang. Caught by an emulator test (emu_probe2.py)
using a stub that deliberately clobbers every register a well-behaved callee is free to use as scratch
(everything outside its own explicit save list) - the real eaac8 (fully disassembled, 14 instructions, only
touches d0/d1/d2, saves/restores d2) does NOT do this, but eab10's deeper jump-table condition handlers were
never fully disassembled, so the stub represents a worst-case, not a confirmed behavior.
Fix: local save/restore of d2-d7/a2-a6 (44 B) wrapped around the eaac8+eab10 probe calls specifically
(chord11_probe.s / poly_v2/DT_OS1.53_POLY_v2_probe2.syx, sha e604f1fa...), rather than widening the
whole hook's frame (which would require shifting every caller-argument stack offset used elsewhere in the
hook - higher risk to get right by hand). Recommend applying the same local-save pattern to any future hook
code that calls into firmware functions whose internal register usage isn't fully confirmed.

## Conditional trigs, real gate wiring: chord12.s / v2_chord12 (2026-09-22)
Following the two confirmed-safe probes (probe: call eaac8 only, discard result; probe2: call eaac8+eab10,
discard results, with the d2-d7/a2-a6 local-save fix), built the real gate: chord12.s, based on chord5.s
(the confirmed-safe no-gate chord baseline), 620 B.

What it does: on the rank-0 (control) poly track's chord hook invocation, before playing the control trig,
evaluates the MIDI partner track's own trig-condition byte (msg+0x38c default / per-step 0x200 array, same
byte layout the firmware itself uses) exactly as the firmware would - percentage/probability conditions via
0x400eaac8, the fuller X:Y/FILL/PRE/NEI/1ST/negation set via 0x400eab10's jump table - and blocks (falls
through to the ORIGINAL unmodified per-track trig, i.e. normal DT1 behavior with no poly/chord effect)
if the condition fails. The pass/fail decision is cached per pattern-step call into a marker byte at
SLOT+0x48 (cleared at rank-0 entry, set on pass) so that rank>=1 poly tracks (processed after rank-0 in the
same step) read the CACHED decision rather than re-evaluating the condition (re-evaluating a probability
condition per poly-track would give each voice an independent coin flip instead of one decision for the
whole chord).

Three bugs found and fixed via unicorn tracing before this ever touched hardware (see emu_chord12.py):
1. Register clobber in the marker-pointer computation: used a1 (still live, needed later by the .Loff
   default-note-read loop) as scratch instead of a3. Silent corruption, no crash at the point of the bug -
   exactly the class of bug that plausibly caused the original v2c freeze.
2. a0 clobbered by the real eaac8 (it internally does moveal 0x4020db1c,a0) broke a now-provably-unnecessary
   "refetch the condition byte" instruction placed after the eaac8 call - a0 was 0 at that point, so the
   refetch faulted (UC_ERR_READ_UNMAPPED in emulation; would likely have hung/crashed hardware the same way
   v2c did). Fixed by widening the local save around the eaac8/eab10 calls to d0-d7/a0-a6 (60 B, matching
   and slightly exceeding probe2's already-safe d2-d7/a2-a6 pattern) AND removing the unnecessary refetch
   entirely (the condition byte's value at that point is already known: it's the entry condition for calling
   eaac8 in the first place), replacing it with a plain moveq #-1,d1.
3. The eab10 pass/block decision was computed into d7 and then immediately clobbered by the hook's own
   movem restore, since d7 is itself one of the registers being restored. Always test the decision register
   (d0, straight off the jsr) BEFORE performing any restore that includes it - mirrors the eaac8 check,
   which was already correct this way.

Validated in emu_chord12.py against a Python behavioral model (chord present/absent, poly-track count <2,
condition default(-1)->eaac8, non-default->eab10, pass->control/voice trig with correct pitch/flags/engine-
table-clear, block->passthrough with untouched slot/table) across 6+ seeds and ~9000 total per-track
evaluations (both eaac8 and eab10 stubbed deterministically for the correctness check - eaac8's REAL PRNG
bytes were separately confirmed register-safe on hardware in the probe2 build, so restating its probability
math in the Python model wasn't needed/useful): all passed, no assertion failures, register/pattern-word
restoration confirmed on every call.

Built: poly_v2/make_v2_chord12.py -> poly_v2/section_3_MAIN_OS_v2_chord12.bin (1192 changed bytes vs
official, matches make_v2_chord12.py's own byte-diff report) -> poly_v2/DT_OS1.53_POLY_v2_chord12.syx
(sha 5daaf5b1..., see recovery/SHA256SUMS.txt). Confirmed section-3-only diff against
recovery/DT_OS1.53_OFFICIAL.syx (sections 2/4/5/8 byte-identical) - revertible via the normal FUNC-hold
startup menu path same as every prior build.

NOT YET flashed/tested on hardware as of this note - this is the first real gate-logic build since the v2c
freeze, so despite the emulator confidence it should be treated with the same caution as v2c was: expect the
user to test it deliberately (e.g. one MIDI track step with a probability condition, one with an X:Y ratio
condition) rather than assuming safety from emulation alone.

## Conditional trigs actually not gating: the eab10 arg4 bug, chord12 -> chord13 (2026-09-22)
User flashed v2_chord12 and reported: "conditional trigs still not working" (no freeze - the pass/block
gating itself simply didn't work as expected). Root-caused by disassembling the REAL firmware's own
condition-check code (0x4006f4c4, the exact function our hook replaces - it turns out to contain this
same eaac8/eab10 gating logic natively, for the firmware's own normal per-track trig evaluation), rather
than continuing to guess eab10's calling convention.

Ground truth from 0x4006f524-0x400f582 (m68k-linux-gnu-objdump -m 5407 against the official
extracted_1.53/section_3_MAIN_OS.bin - "-m 5407" is required, plain "-m 68000" cannot decode ColdFire
mvs/mvz opcodes and silently emits garbage ".short" placeholders that look like plausible-but-wrong
instructions): eab10 is called as eab10(track, step, condition_byte, flag), 4 arguments, pushed in
reverse (so flag is pushed first / ends up deepest). The bug: chord12.s hardcoded flag = 1
(moveq #1,%d0) for every call. The REAL firmware computes flag from the SAME d0 that held the condition
byte (override path) or eaac8's return value (default path), via "ori.l #0xff,d0" (equivalent to the
original's "tstl <output-ptr>; sne d0" when that pointer is never null, which it never is in our case -
proved by replacing the null-pointer test with a flat OR since the branch always goes the same way) then
"neg.l d0" on the FULL 32-bit register (not just the byte) - meaning the result depends on the UPPER bits
of d0 at that point, which differ by path:
  - per-step override present, condition byte >= 0 (non-negated: %, X:Y, FILL, PRE, 1ST etc as normally
    entered): flag ends up 0xFFFFFF01 (-255).
  - per-step override present, condition byte < 0 (bit7 set - DT1's encoding for NOT-negated
    condition variants): flag ends up 0x00000001 (1).
  - default condition (eaac8 percentage check passed): flag ends up 0xFFFFFF01 (-255), same as the
    non-negated override case (eaac8 only ever returns 0 or 1, confirmed by fully disassembling it -
    14 instructions, LCG-style PRNG state at 0x4020db18/0x4020db1c, clean 0/1 return).
So flag isn't a generic "is this real" boolean at all - it's a signal to eab10 distinguishing negated vs
non-negated conditions, and since almost every condition a user would actually set is non-negated, our
hardcoded flag=1 was telling eab10 "treat this as negated" on virtually every real trig, explaining why
gating looked broken (eab10's negated-vs-not code paths are still not fully disassembled, so the exact
resulting misbehavior isn't pinned down further than "wrong argument, wrong path taken").

Fix (chord12.s -> chord13.s, 620 -> 632 B): compute flag with the exact same instruction pair the real
firmware uses (ori.l #0xff,d0 ; neg.l d0) applied to whichever d0 the two paths already produce, instead
of a hardcoded moveq. Verified two ways before touching hardware:
  1. emu_flag_check.py: an eab10 stub that just records its 4 pushed arguments (doesn't evaluate
     anything) - confirmed the flag value chord13.s produces exactly matches the hand-derived formula
     above, for both negated/non-negated override bytes and the default(eaac8-pass) path, using the REAL
     eaac8 bytes (not a stub) so the default-path number is the genuine one, not a guess.
  2. emu_chord13.py / emu_chord13_regsafety.py: reran the full functional-correctness suite (6+ seeds,
     ~9000 evaluations) and a register-safety suite with an aggressively-clobbering eab10 stub (writes
     junk to d0-d7/a0-a6 before returning) across seeds including negative/negated condition bytes
     (0x81, 0x90) to exercise the new .Loverride/.Lflag branch - all passed, no register leaks, no
     crashes, pattern-word/marker restoration all confirmed.

Built: poly_v2/make_v2_chord13.py -> poly_v2/section_3_MAIN_OS_v2_chord13.bin (1196 changed bytes vs
official) -> poly_v2/DT_OS1.53_POLY_v2_chord13.syx (sha 5980961f..., see SHA256SUMS.txt). Confirmed
section-3-only diff against recovery/DT_OS1.53_OFFICIAL.syx - revertible via the normal FUNC-hold
startup menu path same as every prior build.

Lesson for any future work on this condition-gate logic: the REAL firmware's own trig-condition-check
code lives right inside 0x4006f4c4 (the very function we hook/wrap), fully readable with
`m68k-linux-gnu-objdump -D -b binary -m 5407 --adjust-vma=0x40000400 extracted_1.53/section_3_MAIN_OS.bin
--start-address=0x4006f4c4 --stop-address=0x4006f950` - this should have been the FIRST thing checked
before chord12, rather than guessing eab10's argument conventions from scratch. Only "-m 5407" (a
ColdFire variant recognized by binutils) decodes the mvs/mvz opcodes correctly; "-m 68000" or no -m
produces wrong-looking-but-plausible ".short" garbage that can mislead analysis silently.

## Conditional trigs still "always firing" on hardware after chord13 - real-function validation + chord14 diagnostic build

User reported chord13.syx (the flag-argument fix above) still showed the chord always triggering on
hardware with a MIDI-partner-track condition set to 4%, observed over 10+ pattern loops, with track
selection and POLY re-flash both confirmed correct via follow-up questions. This contradicted the
emulator suites above, which only ever exercised chord13.s against STUBBED eaac8/eab10 (deterministic
or register-clobbering, but not the real firmware math) - so the logic wrapping the calls was proven
correct, but the actual eaac8/eab10 arithmetic itself was not yet exercised end-to-end.

Closed that gap with emu_real_percent2.py: maps chord13.bin as the hook, the GENUINE extracted eaac8 and
eab10 bytes (not stubs) as the firmware functions, populates the real 21-entry percentage threshold table
at 0x401bc9c4 and the PRNG state globals at 0x4020db18/0x4020db1c, then drives a fixed MIDI-trig
condition through N=20000 loop iterations, checking slot+0x24 bit16 (chord-fired) per iteration.

First pass showed ~100% "fires" for every condition value including very low percentages - looked like it
confirmed the hardware report. Root-caused to a test-harness bug, not a firmware/logic bug: the loop
wasn't resetting SLOT+t*0x4c (specifically the +0x24 flags field) between iterations, and since the
.Lblk (blocked) path never touches that field, a stale "fired" bit set during an early iteration (when
the LCG PRNG state was still small enough to pass almost any percentage check) stuck for every later
iteration regardless of the real per-iteration block/pass decision. Fixed by fully zeroing
SLOT+t*0x4c and resetting TBL+4*t at the top of every iteration. After the fix, results tracked the
expected the stock percentage steps closely: cond=0(1%)->1.14%, cond=1(2%)->2.14%, cond=2(4%)->4.08%,
cond=5(13%)->13.11%, cond=10(50%)->49.58%, cond=15(87%)->86.79%, cond=20(99%)->99.00% (all N=20000).

So chord13.s's percentage-gating logic, run against the REAL eaac8/eab10 firmware bytes rather than
stubs, is correct and reproduces stock DT1 percentage semantics. That leaves a real, unexplained gap
between this now-rigorously-validated emulation and the user's hardware report - possible causes not yet
distinguished: a stale/wrong file actually flashed, some hardware-only difference the emulation model
doesn't capture (e.g. state/memory layout assumption still wrong for the real device), or a genuine logic
bug specific to conditions arriving via live/real trig timing that the emulator's synthetic single-call
harness doesn't exercise.

To narrow this without further guessing, built a binary diagnostic: chord14_forceblock.s, chord13.s with
one line inserted right after the rank0/rank>=1 gate (`bra .Lnormal` immediately before the condition-gate
setup block), forcing every MIDI-triggered rank-0 (chord-root) evaluation to unconditionally skip the
ENTIRE condition-gate and chord/voice-steal logic - i.e. with this build flashed, POLY chords triggered via
the MIDI partner track should NEVER fire, regardless of any condition setting (100% silent, by design).
Validated in emulator: 0% pass rate across the standard suite, and a register-safety pass confirming no
crashes (the suite's functional-mismatch assertion at the first differing iteration is expected/ignored,
since this build deliberately disables the feature).

Built: poly_v2/make_v2_chord14_forceblock.py -> poly_v2/section_3_MAIN_OS_v2_chord14_forceblock.bin
(1198 changed bytes vs official) -> poly_v2/DT_OS1.53_POLY_v2_chord14_forceblock.syx
(sha e9d330da..., see SHA256SUMS.txt). Confirmed section-3-only diff against
recovery/DT_OS1.53_OFFICIAL.syx (only section_3_MAIN_OS.bin differs, all other sections
byte-identical) - revertible via the normal FUNC-hold startup menu path same as every prior build.

Purpose: this is a diagnostic, not a fix. If flashed and the chord still always fires on hardware, that
proves the gate code isn't being reached/exercised at all, pointing at a build/flash pipeline issue rather
than eab10/eaac8 logic. If the chord goes completely silent, that proves the gate mechanism IS reached on
real hardware, narrowing the remaining bug specifically to how the condition byte is read/evaluated in
the live-trig path versus this session's synthetic single-call emulator harness.

## chord14_forceblock still audible on hardware, even with no trigs on tracks 2/3/4 -> chord15_killswitch

Follow-up to the chord14_forceblock entry above. The user tested it and reported: tracks 2/3/4's step
LEDs light during playback but track 1's doesn't, and a multi-pitch chord is STILL clearly audible.
Confirmed via follow-up questions this was genuinely the forceblock build (not a mix-up with chord13),
and critically: tracks 2/3/4 have NO trigs of their own programmed in the pattern - only the MIDI
partner track has trigs. That rules out the innocent explanation ("it's just ordinary independent
multi-track playback that happens to sound like a chord, nothing to do with our patch") - if 2/3/4 have
no native trigs, any sound from them can only be coming from the voice-stealing mechanism, meaning
chord14_forceblock's block is not actually taking effect on hardware.

Re-verified everything about that build end-to-end, all clean:
- Reassembled chord14_forceblock.s from source with m68k-linux-gnu-as -mcpu=5475 fresh in this session;
  sha256 of the reassembled bytes (c98972d6...) matches BOTH the HK_CHORD_BYTES hardcoded in
  make_v2_chord14_forceblock.py AND the bytes physically present in the shipped .syx's section 3 at the
  hook address (0x400b8e60), extracted directly and hashed. So the built/shipped file is provably not
  corrupted or stale relative to the intended source.
- Re-walked the control flow by hand a second time: the inserted `bra .Lnormal` sits right after
  `tst.l %d6 ; bne .Lgrd`, i.e. it only fires for the CONTROL track's own call (d6==0); voice tracks
  (d6!=0) still go through .Lgrd, which reads the cached "did the chord pass" flag at the control
  track's own SLOT+0x48. Since the control track unconditionally clears that flag every time ITS OWN
  hook call runs (in .Lskipclr, before any condition check), and per the existing HK_POLY/HK_CHORD
  design every POLY track's hook is invoked every step regardless of whether that specific track has
  its own native trig (confirmed by the fact voice tracks with zero trigs of their own already produce
  sound in the known-good v2c_safe/chord12/13 baselines), the control track's call should always run
  first in track-index order and clear the flag before any voice track reads it. So by this analysis
  chord14_forceblock should silence rank>=1 tracks too, not just rank0 - the hardware result is not what
  the code says should happen.

Rather than keep reasoning about it, built the least-assumption-possible version: chord15_killswitch.s,
chord13.s with a single `bra .Lnormal` inserted as the very FIRST instruction after the register-save
prologue - literally nothing else in the hook can execute, for any track, on any step, unconditionally.
Verified in emulator (1500 iterations, varied inputs): every single call is a plain pass-through
(msg tagged with the calling track, default note, chord-flag bit16 never set, engine-params table
untouched), no register leaks, no crashes. Verified end-to-end the same way as chord14_forceblock: sha
of reassembled source == sha of bytes embedded in make_v2_chord15_killswitch.py == sha of the bytes
physically present in the shipped .syx's section 3 at 0x400b8e60 (c61d2ec0...), and eyeballed the first
bytes directly (4fefffe0 48d70cfc 6000025e = save regs, then unconditional bra to the pass-through).

Built: poly_v2/make_v2_chord15_killswitch.py -> poly_v2/section_3_MAIN_OS_v2_chord15_killswitch.bin
(1197 changed bytes vs official) -> poly_v2/DT_OS1.53_POLY_v2_chord15_killswitch.syx
(sha cc6285db..., see SHA256SUMS.txt). Confirmed section-3-only diff against
recovery/DT_OS1.53_OFFICIAL.syx - revertible the normal way like every prior build.

If this ALSO still produces an audible chord on hardware, that is very strong evidence the device isn't
actually running whatever .syx is being flashed (a transfer/flash pipeline issue, not a logic bug) -
worth double-checking the exact file/sha256 actually used to flash, and how it's being transferred to
the device.

## chord15_killswitch confirmed silent on hardware; adding a distinguishing version tag -> chord13v

The user flashed chord15_killswitch and confirmed the result matches the emulator prediction exactly:
completely silent, no chord fires from MIDI track 9 at all. This confirms two things at once: our hook
logic genuinely is reachable/controllable on real hardware (not just in emulation), and the flash/
transfer pipeline (the transfer app) does deliver a materially different file and the device does run
it. That leaves the earlier chord14_forceblock "still hear a chord despite the block" report looking
like a stale-file fluke rather than a real logic bug - most likely explanation given every byte of that
build was independently re-verified end to end (reassembled source, embedded hex in the build script,
and bytes physically present in the shipped .syx all matched) and the control-flow reasoning behind it
checked out on a second pass too.

The one gap that made that fluke hard to rule out with confidence: every one of these custom builds
reports itself as plain OS "1.53" (the ELE3 container's version field, untouched by any build script so
far), same as the official firmware and every other custom build. So the transfer app's own UI, and the
DT1's own System/About screen after flashing, show the identical "1.53" no matter which of our many
.syx files was actually sent - there was no way to visually confirm which specific custom build (if any)
made it onto the device.

Fixed going forward: container tool supports -V/--set-version to change that field (fixed 4-char
field, same width as "1.53" exactly - a too-long string is rejected outright, and mixing a letter into
the middle position renders "?" during parsing so only the last character was changed). Built
poly_v2/DT_OS1.53_POLY_v2_chord13v.syx = section_3_MAIN_OS_v2_chord13.bin (the already-validated
percentage-gate fix, unchanged) repackaged with version "1.5G" instead of "1.53" (sha 2ac66798..., see
SHA256SUMS.txt). Confirmed: version field reads back correctly as "1.5G", container/content checksums
still pass, and the section-3 diff against official is unchanged (1196 bytes, identical to the original
chord13.syx - only the version tag differs). This should show up distinctly in the transfer app before
sending and on the device's own OS version screen after flashing, so from here on every new diagnostic
build should get its own distinguishing version tag (single trailing letter is safest: K=killswitch,
G=gate/chord13, etc.) to eliminate any doubt about which file is actually running.

Next actual test (not a diagnostic - this is back to trying to get the real feature working): flash
chord13v.syx, confirm "1.5G" shows in the transfer app before sending and on the device after, then
re-test the percentage condition - probably worth using an extreme value (1%, should almost never fire,
or 99%, should almost always fire) rather than 4% for an unambiguous read, since chord13's percentage
logic was already proven correct against the real eaac8/eab10 firmware functions in emulation
(emu_real_percent2.py, 20000 trials matching the manufacturer's documented percentage curve closely).

## chord13v still "always" on hardware -> re-read the REAL callers -> chord16 (version tag 1.5H)

chord13v (tag 1.5G confirmed on device) still fired the chord every loop at 4%. Emulation of chord13
against the real eaac8/eab10 said 4%. The gap was the emulator's model of the CALLER, not the gate math.

Re-read with objdump -m 5407 (findings, all from section_3 of OS 1.53):
- The trig builder 0x4006f4be has exactly two callers:
  * 0x4006fcf0 inside 0x4006fb82 (the per-track sequencer build loop; many callers incl. UI):
    args (track, P=*0x4199dc38, Q=*0x4199dc44, step, arg5 = 0x421fa664 + track*0x4c, arg6 = &local).
    arg5 is a per-track 0x4c-byte "pending message" slot; the dispatcher (0x4006ecba / 0x4006f0f6)
    memcpy's pending slots into pool messages. The builder writes slot fields 0,4,8,c,14,18,24,28,30,
    34,38,3c,44 -- never +0x48.
  * 0x4007099c (play-start path, first step, tracks ascending): arg5 = 0 (clrl), arg6 = &local.
    With arg5 == 0 the builder allocates its own message from the pool (0x400ee036).
- The builder's own condition code (0x4006f538..0x4006f580, and the MIDI builder 0x4006f8c2..) computes
  eab10's 4th argument as: tst.l arg5 ; sne ; neg.l ; mvzb  ==  (arg5 != 0) ? 1 : 0.
  [C] corrects the earlier "ori.l #0xff ; neg.l" reading, which was wrong. eab10 only tests it for
  zero (flag==0 -> d0 = loop counter 0x421ed638[track], used by X:Y; result byte goes to 0x421ed604
  instead of 0x421ed5f4). So: percentages unaffected, but X:Y needs flag 0 on the path that has it.
- eab10 condition encoding, confirmed two ways (threshold table 0x401bc9c4 AND the UI string pointer
  table at 0x4018d220): 0..20 = 1,2,4,6,9,13,19,25,33,41,50,59,67,75,81,87,91,94,96,98,99 %;
  21 = 100% [C] (earlier notes called it "0%-like" - it is always-pass); 22-27 FILL/PRE/NEI (+NOT);
  28-29 1ST/NOT 1ST; 30-64 = 1:2 .. 8:8. Setter 0x400245b2 clamps stored byte to -1..64.
  4% = byte 2, as assumed.
- PRNG 0x4020db18/1c is .data, initial "pong"/"ping"; only eaac8/eab10 write it. Not the problem.

Defects in chord12/13/13v that emulation never exercised (emulator always passed a per-track arg5):
1. The "chord passed" flag was stored/read THROUGH arg5 (clr/set 0x48(arg5); voices read
   arg5 + (c-t)*0x4c + 0x48). On the arg5==0 path that writes absolute 0x48 and voices read from
   just below address 0 -- whatever is there decides whether they fire. Reproduced: chord13 in
   emu with arg5=0 faults writing 0x48.
2. eab10 flag wrong (see [C] above).

chord16.s (658 B, fits before ICON_BASE): 
- flag = (arg5 != 0) ? 1 : 0, as the firmware does.
- cache word at a FIXED address: 0x421fa664 + c*0x4c + 0x48 (control track's slot +0x48, a field no
  builder writes; the same RAM chord12/13 were already writing on the sequencer path).
- cache value is step-tagged: 0x80000000 | step<<1 | pass. Rank 0 writes it on both pass and block;
  voices fire only if it equals 0x80000001 | step<<1 for THEIR step. A stale/foreign value -> no
  voice (fails safe to "no chord" instead of "always chord").
Tests (poly_v2/emu_chord16.py, fake_orig.s models both callers incl. pool alloc when arg5==0):
- flag check: arg5=slot -> 1, arg5=null -> 0.
- functional model 5 seeds + register safety with a clobbering eab10 3 seeds, alternating arg5
  slot/null, with random junk pre-loaded in every cache word: all pass.
- real eaac8/eab10, 4 POLY tracks, both callers: 1% -> 0.95, 4% -> 4.08, 50% -> 49.0, 99% -> 99.1 %,
  never a partial chord.
- reversed call order (voices before control) degrades to root-only / voices-only mixes, never
  "always"; real loops call tracks ascending so control goes first.
Built: make_v2_chord16.py -> section_3_MAIN_OS_v2_chord16.bin (1220 changed bytes) ->
DT_OS1.53_POLY_v2_chord16.syx, version field "1.5H", sha c31b4dab... Section-3-only diff vs
official confirmed; hook bytes in shipped file == tested chord16.bin (be1b6e0e...).
Honest caveat: the arg5==0 caller as read is the play-start path; if the steady-state "always" had a
different cause, chord16 will show it differently: the step-tagged cache makes voices unable to fire
without a fresh PASS for that exact step, so "always" would then have to come from the gate decision
itself (cond byte / PRNG), and "root only, never voices" would point at call ordering.

## Crash-hardening audit (after chord16 confirmed working on hardware) -> chord17 (version tag 1.5J)

User confirmed chord16: POLY + trig conditions correct. Audit of every place our patches touch firmware:

1. Blanked SongTempoMenuView function 0x400b8cf8 (our code cave). It is vtable slot 4 (byte offset 16)
   of SongTempoMenuView (vtable fn ptrs from 0x401b5a74). The function drew ": ROW BPM"/": SONG BPM".
   The base-class default for that slot is 0x400c969a = bare rts, so our "moveq #0,d0; rts" is
   equivalent: the Song tempo page just draws nothing. No crash path. [V]
2. v2b round-robin counter RAM word 0x4208c8a8 was NOT free: 0x4208c898 is a function-local static
   std::map (guard byte 0x4208c8e0) inside Song-view method 0x400b7f28; 0x4208c89c = RB-tree header
   (color, root c8a0, leftmost c8a4, RIGHTMOST c8a8, count c8ac). Built once on first call from an
   initializer list; afterwards only find() via root. Our counter overwrote the rightmost pointer.
   Steady state harmless (rightmost never read after construction), but a race exists: map
   construction (range insert with end() hint) reads rightmost per insert; a POLY trig in that window
   -> deref of address 0..3. Fixed: counter moved.
3. BIGGER: slot +0x48 (where chord12..16 kept the "chord passed" cache) is the scheduler's message
   `next` link. Evidence: pool alloc 0x400ee036 uses +0x48 as free-list link and clears it on alloc;
   post-at-time 0x400ee1bc appends with tail->next(+0x48)=msg and never clears msg->next; consumers
   (0x4007767c..0x40077c6c, 0x400ee144, 0x400ee198, 0x400ee334, 0x40076f6e) walk `msg=msg->next`, one
   frees each msg; the consumer's own copy path clears +0x48 on the copy (0x40077920, 0x400779a8).
   The sequencer dispatcher 0x4006ecba memcpy's the whole 0x4c-byte pending slot into a pool message
   WITHOUT clearing +0x48 (stock never dirties it). So a control-track message carried our cache value
   as its `next`. Survived because voice/other-track messages appended after it in the same time
   bucket overwrite it. Crash path: control message last in its bucket (root-only chord with neutral
   NOT2-4, trig directly on the control track, micro-timing splitting buckets) -> consumer follows
   next=0x800000xx (chord16) / 1 (chord12/13), treats it as a message and frees it into the pool ->
   pool corruption -> delayed random crash. Fixed: cache moved.
4. Where to put our own state: boot code sets CACR=0xa50ce100, ACR0=0x4007e020 (SDRAM
   0x40000000-0x47ffffff, copyback, W=0 not write-protected); no MMU setup (only movec to cacr/acr0/
   vbr in the whole image). So the dead tail of our code cave (old SongTempoMenuView body, never
   executed, not referenced) is plain writable RAM. Chosen: 0x400b9100 = chord cache,
   0x400b9104 = round-robin counter (hook ends 0x400b90ea, icon data starts 0x400b9260).
5. Machine value 4 everywhere the real value is read: RAW getter sites 0x4002b754 (machine list
   cursor, list extended to 5), 0x4003bd3a (name getter, patched to 4), 0x4003b3fc (4-entry table
   0x4018470c behind stock bound check cmp#3/bcs -> 0). Direct readers of +0x7e: 0x4000f1f8/f3d0
   (-> patched param lookup), 0x4000f652 (compare only), 0x4002262a (setter, patched), 0x4007a314
   (sound/kit conversion: machine > 3 -> 0 = ONESHOT; this is why POLY resets after flashing, and
   why the OFFICIAL OS will load saved POLY tracks as ONESHOT instead of crashing), 0x4007a636
   (raw struct copy), 0x400d5e80 (unrelated struct). No unguarded table index by machine found.

chord17.s = chord16.s with the cache at 0x400b9100 (value 0x80000000 | c<<8 | step<<1 | pass),
no writes to any slot/message +0x48. HK_POLY bytes: both 0x4208c8a8 refs -> 0x400b9104 (the only
remaining 0x4208c8a8 in the image is the firmware's own map init at 0x400b8074). Build zeroes
0x400b9100..0x400b9107.
Tests: poly_v2/emu_chord17.py (both callers, stub + clobbering + real eaac8/eab10, new invariant:
+0x48 of all 16 slots and of every returned message stays 0 after every call; chord16 fails it on
the first call, chord17 passes everything; percentages 0.95/4.08/49.0/99.1 %).
poly_v2/emu_test_v2b_chord17.py: original exhaustive v2b round-robin test against the chord17
image with the counter at 0x400b9104, only the code cave mapped: 28672 runs, all good.
Built: make_v2_chord17.py -> section_3_MAIN_OS_v2_chord17.bin (1218 changed bytes) ->
DT_OS1.53_POLY_v2_chord17.syx, version "1.5J", sha 2ad6a988... Section-3-only diff vs
recovery/DT_OS1.53_OFFICIAL.syx; hook bytes in shipped file == tested chord17.bin (ae767023...).
Not changed (known, non-crash): chord hook briefly sets+restores the control track's trig bit in
pattern data during ORIG; a user edit of that exact step in that instant could be reverted.

## BUILD B trace: MIDI track -> POLY audio voices via channel ("internal MIDI cable") (2026-09-23)
Owner's design: external sequencer -> MIDI track (e.g. track 13 / E, its own receive channel) records
the chord as ONE MIDI trig (NOT1..4); track E's OUTPUT channel = the receive channel shared by the
POLY audio tracks (e.g. 5-8 on ch 5); those play the chord with voice rotation. Voice tracks never get
trigs. POLY machine = the enable switch. Disassembly: objdump -b binary -m m68k:5407
--adjust-vma=0x40000400 (brief-extension displacements print in HEX, e.g. "%fp@(14,%d0:l)" = +0x14).

### MIDI IN (DIN/USB) -> tracks  [read from code]
- Status-nibble dispatch table 0x401b8a54 (index = status>>4): 8 -> 0x400d5b86 note-off,
  9 -> 0x400d5baa note-on (vel 0 -> note-off), B -> 0x400d4a90 CC, C -> 0x400d4c0c PC. Gate: 0x4197b778.
- 0x400d59f4(chan, note, vel, x): receive-channel table 0x4197b700[16] (one long per track, compared
  with status&15), auto channel 0x4197b6fc, active track 0x4197b6b4. Builds a 16-bit MASK of every
  track whose channel matches, then calls liveNoteOn for EACH bit (loop 0x400d5b40). => stock already
  allows several tracks on one channel and plays them ALL (layered unison). 0x4219bcd8[note] = track
  (for note-off). Note-off twin: 0x400d58b8 -> liveNoteOff.
- liveNoteOn 0x400d53dc(track 0..15, note, vel, ...) builds a 0x30-byte event on its stack
  (+0 track, +4 note, +8 vel, +0xc 1=on/2=off, +0x10 flags, +0x24, +0x28 lock buf, +0x2c length) and:
    audio track (0..7)  -> 0x40076b3c  (live audio trig: pool msg, msg+8 = track = VOICE, msg+0xc = 2,
                                        msg+0x18 note, msg+0x14 vel<<8, msg+0x28 = 0 (voice's own params),
                                        immediate post 0x400ee296)
    MIDI track (8..15)  -> track -= 8 -> 0x400e1ce8 (MIDI event block, source +0x28 = 2 "live",
                                        posted to MIDI task queue 0x421b41f0)
  then posts a UI/Brain event (type 0xc, track/note/vel/time) through 0x400d4bc4 -> queue *0x4020c2a4.
  RECORDING happens downstream of that Brain event (Brain::processMidiEvent 0x40008c6e -> 0x4001c10a),
  NOT in 0x40076b3c. => calling 0x40076b3c directly plays a voice without recording anything. [inferred
  from the call structure; confirm on hardware]
- liveNoteOff 0x400d575e: same struct with +0xc = 2, vel -1, -> 0x40076b3c / 0x400e1ce8.
- Alloc 0x400ee036 and post 0x400ee296 mask interrupts (move #0x2700,sr) -> callable from any task.

### MIDI TRACK OUTPUT (sequenced)  [read from code]
- MIDI builder 0x4006f846 (called from step loop 0x4006fb82 for tracks 8..15) evaluates the trig
  condition itself (0x400eaac8 / 0x400eab10), collects up to 4 notes (NOT1 + 3 offsets; per-step bytes
  at +0x280+i*0x40, defaults 0x384+i, 0x40 = off), then fills a sequencer msg: type 3, msg+8 = track,
  msg+0x10 -> MIDI event block (pool 0x400e0a88, 0x30 B):
     +0x04 MIDI track 0..7, +0x08 1 = note trig, +0x0c flags (0x80 = send notes), +0x10 note count,
     +0x14..0x17 notes, +0x18 length (table 0x40191290), +0x1c velocity (byte +0x1f), +0x20 time,
     +0x24 CC/lock data, +0x28 source (1 = sequencer, 2 = live), +0x2c next.
- Audio ISR 0x40077420, type-3 case 0x4007771a: stamps block+0x20 with the sample time, chains blocks,
  and at the end of the ISR posts {type 1, list} to MIDI task queue 0x421b41f0 (0x40077cb4..0x40077ce6).

### MIDI TASK 0x400e0fbc (created 0x400e1cca, prio 8) - where every MIDI-track note becomes bytes
- Per block: channel = 0x400e07b0(track) (-1 = OFF -> nothing sent), mute check for source 1,
  note-on loop 0x400e1710: if the note is already sounding send 0x9c nn 00 first (0x400e175c), then
  0x9c nn vel (0x400e177e), schedule note-off node (list 0x421b7e30 sorted by time, or held list
  0x421b7e28 when length = 0/inf). Sounding table 0x439c8654[ch*128+note].
- Note-offs are all sent as 0x9c nn 00: live off 0x400e18cc, timed off 0x400e19c6, stop/flush
  0x400e1a58 / 0x400e1ae6.
- ALL of these go through ONE function: 0x400e0dda(len=3, bytes) = append to MIDI-out buffer
  0x421b5621 (len byte 0x421b5620). Its only callers are inside this task (0x400e12b8 lea,
  0x400e175c, 0x400e177e, 0x400e196e lea, 0x400e1a10 lea, 0x400e1a9e lea). CC/PC use other emitters.

### BUILD B PLAN (not built)
Hook 0x400e0dda entry = the internal MIDI cable. For len==3 and status 0x90..0x9F (and 0x80..0x8F):
  ch = status&15; group = audio tracks t in 0..7 with 0x4197b700[t]==ch AND machine byte (+0x7e)==4.
  If group non-empty:
    vel>0: pick voice (free, else oldest), remember (note, age) per voice, build a live audio msg like
           0x40076b3c (msg+8 = voice, msg+0x18 note, msg+0x14 vel<<8, msg+0xc = 2) but with
           msg+0x28 = CONTROL (lowest in group) param block and engine table 0x800019b4+4*voice cleared
           (same shared-sound trick as v2b), post 0x400ee296.
    vel==0 / 0x8n: find voice holding that note -> note-off msg (+0xc kind 2 path of 0x40076b3c).
  Always fall through to the original append (the note still goes out of MIDI OUT on that channel).
Covers sequenced playback, live passthrough while playing/recording into track E, retrigs, timed
note-offs, stop. Runs in one task -> the voice table needs no locking (unless Build A also edits it).
Replaces: chord hook (+8 pairing, condition gate, chord cache). Keeps: POLY machine/UI, param sharing.
Timing: hook fires when the MIDI task runs (after the ISR block that timed the note) and posts
"now" -> constant-ish latency of ~1-2 audio blocks behind audio tracks; micro-timing kept at block
resolution. Refinement if needed: post-at-time (0x400ee1bc) using block+0x20 + fixed offset.
Open: pitch mapping of MIDI note -> sample pitch (see note adjust in 0x400d5ad0..0x400d5afa for audio
tracks), velocity scaling, what 0x40076b3c's +0x10/+0x24/+0x2c should be for a live trig, audio block
size (latency), external MIDI sent directly on ch 5 still layers all POLY tracks (stock) unless Build A.

## POLY lost on reload -> chord18 (version tag 1.5K)

Question: does POLY survive pattern change / power cycle? No, up to chord17.
- Save path 0x4007a5a0 (live -> stored, format version 3) copies the machine byte raw
  (live +0x7e -> stored +0x7c), so POLY is written to storage correctly.
- Load path 0x4007a236 (stored v3 -> live) does machine = ((m+1)&0xff) < 5 ? m : 0, i.e. 0..3 kept,
  4 -> 0 (ONESHOT). [C] earlier note called 0x4007a314 "sound/kit conversion"; the clamp that matters
  for machine is at 0x4007a2ea..0x4007a2fe (0x4007a314 clamps a different field, stored +0x7e ->
  live +0x80).
- Callers: 0x4007a386 (references "KIT" - kit load), 0x4007a4ea, 0x4007efe8, 0x4007f708 (tail
  call), reached from project/pattern load paths (0x4005f1c0 references "DT1", 0x4001a8fc
  "ReloadAllSamples"). So every reload from storage turned POLY into ONESHOT (this is the
  "re-select POLY after flashing" behaviour).
Fix: 0x4007a2d0 moveq #5,d2 -> moveq #6,d2 (d2 is reloaded at 0x4007a2f8, used only for this
compare). Emulated the exact instructions 0x4007a2d0..0x4007a302 for all 256 stored values, original
vs patched: only stored 4 changes (0 -> 4). Official OS keeps its clamp, so reverting still loads
POLY tracks as ONESHOT (safe).
chord18 = chord17 + this 1-byte patch (only byte 0x4007a2d1 differs from chord17). Version "1.5K",
sha f8b672ee... Section-3-only diff vs official confirmed.

## v3_cable BUILT (Build B, version tag 1.5L) (2026-09-23)
- Hook source poly_v2/cable.s (592 B incl. 52 B state) at 0x400b8e60 (old chord-hook space, ends 0x400b90b0);
  entry patch 0x400e0dda: 73b9421b5620 -> jmp 0x400b8e60; hook re-executes "mvz.b 0x421b5620,d1" and jumps
  to 0x400e0de0. Saves/restores d0-d7/a0-a6. Chord hook removed: 0x4006f4be restored to original bytes.
  v2a UI/aliasing + v2b rotation (counter 0x400b9104) unchanged.
- Group: audio t in 0..7 with long 0x4197b700[t] == ch and byte Q+0x9e+t*0xa2 == 4 (Q = *0x4199dc44, as v2b).
  Control = lowest. State (in the hook image, SDRAM): vnote[8] (0xff free), vch[8], age[8], clock.
- Note on (vel>0, note 12..84): voice = min over group of key = age (free) / age+0x80000000 (busy).
  Message as 0x40076b3c: +0xc=2 (live id), +4=1, +8=voice, +0x14.w=vel<<8, +0x18=note, +0x28=0, +0x44=0,
  +0x30=0, +0x2c = sound lock = Q+0x20+c*0xa2 (ISR 0x40077b28: full param copy via 0x40077282 each note),
  +0x24 = mvs.w(0x409bac18 + pat*0x1ec68 + c*0x38f + 0x382) | 0x10001 (pat = *(*0x4199dc38+0x1ec64)),
  i.e. exactly what liveNoteOn builds for a keyboard-played audio track, with the control track's sound.
- Note off (vel 0 or 0x8n): the voice with vnote==note && vch==ch -> msg +4=2, +0x2c=0, +0x24=0.
  ISR 0x40077c06 releases only if last-id[voice]==2 and 0x4399dc80[voice]==note, so a stale off after a
  steal is ignored by the engine too. Live id 2 > sequencer id 1: while a routed note holds a voice,
  sequencer trigs on that voice are ignored (stock live-play priority, 0x4007784e).
- poly_v2/emu_cable.py: real image in unicorn CFV4E, stubbed alloc/post; compares every call against the
  ORIGINAL 0x400e0dda (identical registers and MIDI-out bytes) and a Python model (messages, state).
  Directed cases (rotation, steal, release, 0x8n, range, other channel, non-note, single-voice group,
  Q=0, alloc failure) + 40 random fuzz runs x 120 events: all pass, on cable.bin and on the shipped
  section 3. Mutation check: steal/lock/flags/free/range/machine/register-restore mutations all caught.
- Tool rebuilt on the Mac VM ($HOME/tools/container tool); repacking chord17.bin with -V 1.5J
  reproduces the shipped chord17.syx byte-for-byte. v3 syx: checksums ok, sections 2/4/5/8 identical to
  official, section 3 round-trips. sha256 514ba71c...
- Unverified on hardware: live-msg fields not exercised by stock MIDI-in (+0x2c sound lock from a live
  trig), latency, behaviour of the sound lock with sample slots / p-locks.

## v3b: POLY survives load (version tag 1.5M) (2026-09-23)
CORRECTION to the session-2 audit: 0x4007a314 is NOT the machine clamp. Sound (de)serialisation:
- save 0x4007a5a0(storage, runtime, x): header 0xbeefbace, version 3; storage+0x7c = runtime+0x7e (machine,
  raw), storage+0x7d = rt+0x7f, storage+0x7e = rt+0x80 (0x4007a636..). So POLY (4) IS written to disk.
- load 0x4007a236(runtime, storage) (requires version 3): runtime+0x7e = storage+0x7c if (byte)(v+1) < 5
  else 0 (0x4007a2d0 moveq #5,d2 .. 0x4007a2fe). 0x4007a312/14 clamps a DIFFERENT field (rt+0x80 <= 3).
  Callers: kit load loop 0x4007a3fe (kit+0x20+t*0xa2, fallback init 0x40084f8a on failure), 0x4007a50e,
  0x4007f252, 0x4007f968 (sound pool etc.) -> one patch covers them.
- Patch: 0x4007a2d0 7405 -> 7406. Verified with the real save+load functions in unicorn (emu_v3b_load.py):
  0..4 and -1 survive, 5 -> 0; stock drops 4 -> 0. The official OS keeps mapping saved POLY to ONESHOT.
- Other +0x7c readers: 0x4007b4ca (unreferenced fn 0x4007b2e8, clamps a +0x7c field of some other struct to
  <= 2; not the sound loader) and 0x40091014 (getter) - untouched.
- Built: make_v3b_cable.py (= make_v3_cable.py + this byte) -> section_3_MAIN_OS_v3b_cable.bin (1164 changed
  bytes vs official) -> DT_OS1.53_POLY_v3b_cable.syx, version 1.5M, sha 517e25bf...; checksums ok,
  sections 2/4/5/8 identical to official, section 3 round-trips; emu_cable.py passes on it too.

## v3c: live oscilloscope (version tag 1.5N) (2026-09-23)
Audio output path [read from code]:
- SSI at 0xfc0c8000 (TX0 +0x00, RX0 +0x08). eDMA TCD54 (0xfc0456c0): SADDR 0x4ba8f080 (uncached SDRAM; CACR
  default data mode = cache-inhibited outside ACR0), 32-bit, NBYTES 8 (L,R), CITER 64, SLAST -512, CSR 6
  (half + major IRQ) -> 64-frame ring, two 32-frame halves. TCD52: RX into 0x80001000 same shape.
- Audio block = 32 frames (0.67 ms @ 48 kHz). ISR 0x40077420: half = (TCD54.SADDR < 0x4ba8f180) ? 1 : 0;
  writes that half via 0x40071c20(out=0x4ba8f080+half*256, in=0x80001000+.., a2) at 0x4007814a; samples are
  EMAC accumulator >> 8 = 24-bit signed in 32-bit words, L then R (0x400721f8..0x4007221e).
- => internal cable latency is ~1 block (<1 ms) behind sequenced audio.
UI [read from code]:
- View vtable: slot 4 = drawView(this, Bitmap&) (base 0x400c969a rts), slot 11 = periodic tick (base rts),
  0x400c9812(view) = invalidate (sets +0x14, notifies controller). SongEditView vtable 0x401b3750, ctor
  0x400aa6e2, created via make_shared 0x401463c2 from MainScreenView's key handler (0x4002e8a2).
  SongEditView::drawView 0x400abe9c..0x400ac688 (2028 B), only ref = vtable 0x401b3760. Its tick 0x400aa8e2
  blinks every 8 ticks via invalidate.
- Bitmap: +4 width, +8 height, +0xc words per column, +0x10 data; 1 bpp, column-major, MSB = top.
  0x400c1040(bmp, x, y0, y1, color) vertical line (color >0 set, 0 clear, <0 xor); 0x400c178a line-ish,
  0x400c1ab8 rect, 0x400c257c / 0x400c25c0 text (bmp, font, x, y, ...).
Build (poly_v2/scope.s, 1464 B incl. 1 KB ring, at 0x400abe9c):
- DRAW = new drawView: latest rising zero crossing in the 256 samples before (idx-16-128), peak (min 512),
  y = 32 - s*30/peak, clear each column then vline(prev y .. y).
- TICK (vtable slot 11 -> 0x400abfb0): original tick then invalidate(this).
- TAP (0x4007814a -> jsr 0x400abfcc): re-pushes the 3 args, calls 0x40071c20, preserves its d0/d1/a0/a1,
  appends 8 samples: sum of 4 frames x (L+R) >> 11, clamped to int16, ring 512, IDX word.
- emu_scope.py: TAP identical registers/SP/output vs calling the writer directly + exact ring model
  (random, clipping extremes, wrap); DRAW through the REAL vline, pixel-exact vs model for sine/saw/square/
  silence/noise fed through TAP + 30 random rings/indices; TICK call order/args/d0. All pass on scope.bin and
  on the shipped section; cable + v3b load tests also pass on it.
- make_v3c_scope.py -> section_3_MAIN_OS_v3c_scope.bin (diff vs v3b only in the 3 regions) ->
  DT_OS1.53_POLY_v3c_scope.syx, 1.5N, sha 6ac17496..., checksums ok, other sections identical.
- Unknowns: whether the controller clears the bitmap/draws a header over the view, the tick rate (= scope
  frame rate), and song-edit key handlers still acting invisibly underneath.

## v3d (version tag 1.5P) (2026-09-23): direct scope key, read-only scope keys, CC cable
Key handling [read from code]:
- KeyEvent: +0x0c key id (0x400c317c), +0x10 flags (bit tests 0x400c31a4.. 0x400c3220; 0x400c3220 =
  bit0 && !bit3 = press edge). MainScreenView::consumeKeyEvent (vtable slot 2 = 0x4002dea6) key id 5:
  !bit2 or bit1 -> 0x4002e68c: (bit4&&bit1) -> 0x4002e91e (other menu), press edge && !bit1 -> make_shared
  SongModePopup 0x4014640c at 0x4002e914 -> push 0x400c9916; bit2 && !bit1 -> 0x4002e7a4 .. SongEditView
  0x401463c2 at 0x4002e8a2. Both opening sequences are identical after the make_shared call.
- SongEditView::consumeKeyEvent 0x400ac8f0: switch on id-1 (table 0x400ac936): 24..39 trig keys,
  19..23, 8..17, 1, 48 song-edit functions; 5: bit2 -> vtable slot 10 (close, base 0x400c98b6); 6: close
  path; 3,4,18: consumed on bit1; 2,7,40..47: base handler 0x400c96cc.
MIDI CC out [read from code]: MIDI task CC emitter 0x400e0bb4 (plain CC, 14-bit, NRPN) appends through
  0x400e0b84(len, bytes) to buffer 0x421b5a22 (len 0x421b5a21), flushed with the note buffer at 0x400e1bae
  via 0x400e076a (DIN 0x400028c6 / USB 0x40004990). Callers of 0x400e0b84 are all in the MIDI task
  (0x400e0cdc..0x400e0dc6, and CC120 per channel at 0x400e1b76 on stop/flush).
MIDI CC in: task 0x400d4642 (prio 7; MIDI out task is prio 8), status table 0x401b8a54, CC 0x400d4a90:
  gate 0x4197b77c, per track with rx channel match -> 0x400d6a58(track, cc, val, isAutoCh, 0) ->
  0x400d66f0 (CC map, NRPN state, param set). MIDI-in queues 0x421a8d7c/5c/3c (256 entries).
Build:
- 0x4002e914: jsr 0x4014640c -> jsr 0x401463c2 (plain press opens the scope).
- SongEditView vtable slot 2 (0x401b3758) -> KEY at 0x400ac050 (scope_v3d.s): id 5 press -> slot 10
  close, all id 5 events consumed; ids 1, 8..17, 19..39, 48 consumed; others tail-jump to 0x400ac8f0.
- CC hook poly_v2/cc.s (178 B) at 0x400b9110, entry patch 0x400e0b84 -> jmp; for 3-byte 0xBn, cc < 120,
  POLY tracks t (rx == ch, machine 4) ascending: 0x400d6a58(t, cc, val, 0, 0); then original
  "mvz.b 0x421b5a21,d1" + jmp 0x400e0b8a. Runs in the MIDI OUT task, the stock handler normally runs in
  the MIDI IN task (0x400d66f0 takes mutex 0x421b107c only for a one-time init) - concurrent external CC
  to the same POLY track at the same instant is the residual race.
- emu_v3d.py: CC hook transparent (regs + CC-out bytes vs original) and exact call list vs model
  (directed + 30 random runs x 40 messages); KEY: ids -2..59 x 9 flag patterns, close/swallow/tail-call
  behaviour and callee-saved registers. Mutations (cc<120 filter, track arg, POLY check, swallow range,
  press edge) all caught. emu_scope/emu_cable/v3b load also pass on the shipped section.
- make_v3d.py -> section_3_MAIN_OS_v3d.bin (diff vs v3c only in the 5 regions) -> 1.5P, sha 4acae455...
Open: whether a held POLY voice follows a CC live (engine update path of sound-locked voices unmapped).

## v3e (version tag 1.5Q) (2026-09-23): per-voice TUNE + LFO for POLY voices
Param block layout [confirmed from load table 0x401ac28c + descriptor array 0x401a9d9c]: runtime sound
block (0xa2 B, kit+0x20+t*0xa2) holds param SLOT s as a word at +0x14+2s, s = 0..0x34 (53 words = the 0x6a
bytes the engine copies), machine byte +0x7e. Slots: 1..8 LFO1 (SPD MULT FADE DEST WAVE PHAS MODE DEP),
9..0x10 LFO2, 0x11..0x18 machine params (0x11 = TUNE for all 4 sample machines), 0x19..0x25 filter,
0x26..0x2d amp. Descriptor entries: word0 = page/machine id, word1 = slot.
Engine load 0x40077282(ptr, v): S[0x131+v] = ptr; memcpy(0x80001502+v*0x6a, ptr+0x14, 0x6a);
0x4007725a machine byte; tail jmp 0x400749cc(v, ptr+0x14) -> 32-bit words (w<<16) at 0x80002b50+v*0xd4.
Callers: 0x40077b36 (msg+0x2c sound lock, S cleared after), 0x40077bb2 (msg+0x28 / default), kit load loop
0x4007730a (own blocks).
Build: poly_v2/lock.s (218 B) at 0x400ac4d4 (after scope_v3d in the old SongEditView::drawView body);
0x400772e0 jmp 0x400749cc -> jmp 0x400ac4d4: re-pushes (v, src), runs the expansion, then for v < 8, ptr in
[base+0x20, base+0x20+8*0xa2) for base = *0x4199dc44 then *0x800019ac, ptr != own, own machine == 4:
slots 1..0x11 of both per-voice copies = own block values.
emu_lock.py: real 0x40077282/memcpy/0x4007725a/0x400749cc with vs without the patch, 400 random cases
(49 patched): engine SRAM state = original + exactly the expected slot overwrites; callee-saved regs kept.
Mutations (slot range, POLY check, engine-base path) caught. make_v3e.py -> 1.5Q sha 03092c26...;
diff vs v3d only the two regions; all earlier emulator suites pass on the shipped section.
Open: live (non-trig) param changes to a sounding POLY voice (engine dirty-word path) unchanged.

## v3f (version tag 1.5R) (2026-09-23): scope as overlay on the main screen
- MainScreenView singleton: DynamicSingleton weak ref at 0x421f9b50 (object) / 0x421f9b54 (count block),
  filled by getter 0x40138cb0 (ctor 0x4002f088). vtable 0x40182f68: slot 2 consumeKeyEvent 0x4002dea6,
  slot 4 drawView 0x4002cc76.
- Main screen info line is at the bottom: pattern "%c%02d" box (1,0x37)-(0xd,0x3e) drawn at (7,0x38),
  tempo "%d.%d" near x=117-w y=0x37/0x38, pattern name via 0x400c2558 at x=0x12 y=64-h.
- scope_v3f.s (1616 B): DRAW calls mainscreen->drawView(bmp) first (if the singleton exists), then clears
  and plots rows 0..52 only (y = 26 - s*24/peak). KEY: id 5 press -> close; id 6 -> 0x400ac8f0; all other
  ids -> mainscreen->consumeKeyEvent(event), result returned (no main screen -> consumed).
  Offsets: TICK +0x138, TAP +0x154, KEY +0x1d8. lock.s moved to 0x400ac4ec (end of scope).
- Tests: emu_scope_v3f.py (fake main screen paints a pattern; rows 53..63 must keep it; rows 0..52 pixel-exact
  vs model; also with no main screen), emu_v3f.py (KEY routing incl. main-screen absent), emu_lock.py at
  0x400ac4ec, emu_cable.py: all pass on the shipped section. 1.5R sha 6ec4a8c0...
- Open: whether MainScreenView::drawView/consumeKeyEvent have side effects when it is not the top view.

## HARDWARE: v3f (1.5R) confirmed by owner (2026-09-23): POLY sequenced from a MIDI channel works, scope
responsive, mutes/changes work while the scope is open.

## v3g (version tag 1.5S): song mode blocked
- Project settings object: vtable slot 10 (+0x28) returns the data struct; data+0x28 = sequencer mode
  0 pattern / 1 song / 2 chain. Setter 0x4001d842(obj, mode) clamps 0..2, stores, notifies with
  ProjectSettingsSongModeChangedInfo (vtable 0x40180694) via obj vtable slot 4; getter 0x4001d8a8 clamps.
  Setter callers: PatternAndBankSelectView key handler 0x40095a54 (sets 0 and 2 = chains) and the
  SongModePopup lambda 0x400aebbc (dead since v3d). 24 getter callers (UI, 0x4002eab0 opens
  SongTempoMenuView only in song mode, 0x4000ba5c shows SONG MODE ON/OFF and opens the tempo page).
- songoff.s FIX at 0x400b91c4 (38 B): d1 -> clamp 0..2, 1 -> 0. Setter 0x4001d878 -> jsr FIX; nop.
  Getter 0x4001d8cc -> move.l 40(a0),d1; jsr FIX; move.l d1,d0; bra.s 0x4001d8de (0x4001d8dc clr kept).
- emu_songoff.py: real getter/setter, 15 values incl. extremes: stock clamp except 1 -> 0, notification
  unchanged, callee-saved regs kept. All other suites pass on the shipped section. 1.5S sha 7fbb9e0a...

## v3h (version tag 1.5T) (2026-09-23): stereo X-Y scope mode + POLY voice dots
- Free space: SongModePopup (vtable 0x401b3cd4, ctor 0x400ae26e, methods 0x400ae336..0x400af23c) only created by
  make_shared 0x4014640c whose only caller 0x4002e914 was redirected in v3d -> 0x400ae26e..0x400af23e (4048 B)
  unreachable (refs checked: only its vtables, the dead make_shared, an unreferenced EH pad 0x40162086).
  Ctor first word -> rts (defensive). Data at 0x400ae280: IDX, MODE, LASTV, pad, ring 512 x {mid, side} int16.
- scope_v3h.s (1148 B, padded to 1616 at 0x400abe9c; lock.s stays 0x400ac4ec). TICK +0x326, TAP +0x342, KEY +0x3e6.
  TAP: mid = sat(sum4(L+R)>>11), side = sat(sum4(L-R)>>11). DRAW: new `this` -> MODE 0; MODE 0 waveform (v3f on mid),
  MODE 1 goniometer: clear rows 0..52, last 256 points, peak = max(512,|mid|,|side|), y = 26 - mid*24/peak,
  x = 64 - side*24/peak, clamped (ring can move if the UI task is preempted > 21 ms). Voice dots: tracks with
  machine 4, x = 80 + 6t, rows 0..3, filled if cable STATE vnote[t] (0x400b907c) != 0xff, else outline; 1-px clear border.
  KEY: id 5 press MODE 0 -> 1, MODE 1 -> close + 0; id 6 -> MODE 0 + original; others -> main screen.
- emu_scope_v3h.py on the shipped section: TAP exact + transparent, wave/X-Y/dots pixel-exact via real vline, race
  clamp (ring overwritten mid-draw), KEY cycle; mutations (side sign, dot x, held test, LASTV, key 6 reset, clamps,
  point count) all caught. emu_cable, emu_lock 400ac4ec, emu_songoff, emu_v3f CC pass. Diff vs v3g: TAP call,
  scope body, vtable slots 2/11, cave. Rebuilt on the Mac byte-identical. 1.5T sha b5d9e8ee...

## v3i (version tag 1.5U) (2026-09-23): NO closes the scope
- NO = key id 12 [read from code]: SongEditView::consumeKeyEvent id 12 (0x400acbda): press edge; bit 1 set ->
  invalidate only; else clear selection flags +0x94/+0x95 if set, else vtable slot 10 close + 0x400c312c.
  Key 6 (0x400acd1c) closes on RELEASE when bit 1 clear - not NO. Since v3f id 12 went to the main screen (ignored).
- scope_v3i.s KEY: id 12 without bit 1 (0x400c3210): press -> MODE 0 + close, other events consumed; with bit 1 ->
  main screen. Diff vs v3h: 149 B in KEY. emu_scope_v3i.py adds id 12 cases; mutations caught; all suites pass.

## v3j (version tag 1.5V) (2026-09-23): scope keys fall through (pattern change fix)
- Key dispatch [read from code]: 0x400caf04.. builds functors (key invoker 0x400c9c54 -> view vtable slot 2)
  and calls 0x400cab06, which walks the view list from the end (top) via prev links and stops at the first view
  whose handler returns true. Unconsumed keys go to the next view down (no hidden check).
- Stock SongEditView returns false for PTN/BANK (ids 3/4 without bit 1 -> base handler) -> main screen handles
  them: id 4 -> 0x4002e732 / id 3 -> 0x4002e6ca push PatternAndBankSelectView (main+0xc4, no view groups, so
  nothing is closed) via 0x400ca776 (appended = top) + show pattern/bank select. Key 6 = SETTINGS (main+0xbc,
  "SETTINGS" view). PatternAndBankSelectView ctor 0x40094a10 (vtable 0x401af02c), built in MainScreen ctor.
- v3f..v3i KEY called mainscreen->consumeKeyEvent and returned its result: a false result made the controller
  deliver the key to the main screen again (double handling), views between scope and main screen skipped.
- scope_v3j.s KEY: ids 5/12/6 as v3i, everything else returns false (nothing called). Diff vs v3i 127 B.

## v3k (version tag 1.5W) (2026-09-23): activity dots for all 8 tracks
- Audio ISR [read from code]: per message, flags bit 7 (trigger) -> 0x40077a76 ORs (1<<voice) into d3; after the
  loop (0x40077d50) d3 &= ~a5 -> voices started this block; also posted to the UI as event 27 (0x40077dbe).
  0x40077d6c "clr.l 0x4199e130" (6 B, no branch targets inside 0x40077d50..d72) -> jsr TRIG (scope+0x452):
  clr, then TRIGCNT[v]++ for set bits (d0/d1/a0 saved). X flag clobbered: next X consumer is after lsl/addq
  that redefine it (0x40077d9c / 0x40077da6).
- Data after the ring: TRIGCNT 0x400aea90, LASTCNT +8, HOLD +16 (zeroed by make_v3k).
- DRAW dots: all 8 tracks, count change -> HOLD = 4 frames filled; POLY held (cable vnote) filled; POLY marker
  row 5. emu_scope_v3k.py: TRIG executed from 0x40077d6c, regs/SP/counts exact; flash timing; mutations caught.

## v3l (version tag 1.5X) (2026-09-23): scope survives pattern change, scope owns no LEDs
- Owner report (1.5W): first PTN from the scope shows green LEDs, pick works but the scope closes; after
  re-opening, PTN shows no green LEDs (picking still works).
- [read from code] PatternAndBankSelectView key handler after a pick (pattern 0x40095aa6.. / bank ..0x40095bee):
  seq mode -> 0 if not 0, then 0x4015ea5c(list of 0x400084f2(0x40139bac())) = find view with typeinfo
  0x401b36c4 (SongEditView) and call its slot 10 close. 3rd caller 0x400af05e is in the dead SongModePopup.
- LED dispatch 0x400ca40a: views top-down, dynamic_cast to LedHandler (typeinfo 0x401820f4), slot 2(free, claimed);
  claimed bits removed for lower views. SongEditView LedHandler at +104 (vtable 0x401b3804, slot 2 thunk 0x400ab128
  -> 0x400aaeca = primary slot 21) paints trig LEDs (pattern-select style when 0x40093708, song rows otherwise).
  PatternAndBankSelectView LedHandler slot 2 thunk 0x400958d2 -> 0x4009561c (colours 0x14/0x15/3 per pattern).
- Patches: 0x40095af2 / 0x40095bfc beq.s -> bra.s (no close); 0x401b380c and 0x401b3798 -> 0x400c96be (rts).

## v3m (version tag 1.5Y) (2026-09-23): YES fullscreen, NO closes; key id correction
- [read from code] ConfirmWindow::consumeKeyEvent 0x400bfc9c: id 12 -> close, result 1, callback(true) = YES;
  id 13 -> close, result 2, callback(false) = NO. => YES = 12, NO = 13. The v3i note calling id 12 "NO" was wrong
  (SongEditView id 12 = confirm/close; id 13 = cursor step). 1.5U-1.5X closed the scope on YES.
- scope_v3m.s: FULL flag DATA+12 (reset with MODE on a new view object, close, id 6). Geometry per frame in
  PYMAX/PYMID/PNAMP (0x400aeaa8..b4): normal 52/26/24, fullscreen 63/32/30; fullscreen skips main-screen draw
  and dots. KEY: 12 (no bit 1) press toggles FULL; 13 (no bit 1) press closes; bit 1 -> not consumed.

## v3n (version tag 1.5Z) (2026-09-23): voice-start hook moved to the ISR merge point
- [read from code] 0x40077cee: tst.l 0x4199e130; beq 0x40077d72 -> block 0x40077cf6..0x40077d71 (incl. the v3k
  hook site 0x40077d6c) runs only when that flag is set. Owner: ONESHOT tracks never flashed (POLY did, via vnote).
- New site 0x40077d72 (merge; only branch target in d72..d79 is d72 from 0x40077cf4): "move.l d3,d2; not.l d2;
  and.l -76(fp),d2" -> jsr TRIG; nop. TRIG counts d3 bits, then re-executes the three instructions. X flag:
  next X consumer after lsl/addq at 0x40077d9c/da6 (clr/lea/or/move/not/and/btst in between don't read X).
- emu_trig_v3n.py: real ISR 0x40077cee..d7a stock vs v3n, 600 runs both paths: regs/frame/engine memory identical,
  counts = stock mask at d72; the v3m image fails the same test.

## HARDWARE: v3n (1.5Z) confirmed by owner (2026-09-23): "everything is working really well".

## v3o (version tag 1.5a) (2026-09-23): tuner; screen orientation
- DISPLAY ORIENTATION [from code + owner]: the stock 5-px font (0x40200b0c, drawn by 0x400c257c(bmp, font, x, y,
  flags, fmt, ...) -> vsprintf 0x400005e0 -> 0x400c227c) renders upright only if bitmap row 0 is the physical
  BOTTOM; owner calls the main-screen info line (rows 53..63) the "top bar". => physical row = 63 - bitmap row.
  Waveform was upside down since v3c; X-Y diagonals swapped. v3o: y = mid + s*amp/peak; X-Y x unchanged.
- Space: old SongEditView::consumeKeyEvent 0x400ac8f0..0x400acfd6 (1766 B) freed by handling key 6 in the scope
  KEY (stock: bit1 -> false; release -> close, false; else true). Also dead since v3l: SongEditView LED fn
  0x400aaeca..0x400ab132 (616 B, unused). Cave: tuner data 0x400aeab4..cc, 3 kHz ring 0x400aead0..0x400aeed0.
- tuner.s (1374 B at 0x400ac8f0): TTAP (from TAP; 2 x (4 mids)>>2 per block), TUNE (YIN thr 0.25 on 12 kHz ring
  lags 4..200, else 3 kHz ring lags 45..250; parabolic + k*P refinement; integer note/cents), TDRAW (x 0..31,
  rows 0..6, "%s%d %c%d"). Work buffer 1 KB via operator new 0x400d4180 once. Bit-exact vs tuner_model.py.

## v3p (version tag 1.5b) (2026-09-23): knobs fall through the scope
- Encoder events (0x40008570: +4 byte, +8, +12 encoder id, +16 delta, +20 flag; getters 0x400c0274 id? /
  0x400c0256 scaled delta) -> 0x400cad60 -> 0x400cab06 top-down walk, interface +4 (invoker 0x400c9cc6).
  SongEditView +4 slot 2 = thunk 0x400aaec2 -> 0x400aaa86 (primary slot 20): song-row editing, consumed.
  Patched 0x401b37ac and 0x401b3794 -> 0x400c5104 (clr.b d0; rts). 0x400aaa86..0x400aaec6 now dead (~1 KB).
- Other SongEditView interfaces already stock "false": +8 0x400c5104, +12 0x400be830, +16 0x400c7380.
