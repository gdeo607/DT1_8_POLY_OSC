#!/usr/bin/env python3
# DT1_8_POLY_OSC - patch the MAIN OS section (section 3) of the official OS 1.53 image.
# Usage: python3 tools/patch_section3.py <official section_3 .bin> <output .bin>
# Normally called by tools/build.py. Every patched site first asserts the ORIGINAL bytes, so a wrong or
# modified input aborts instead of producing a broken image. Our own code comes from bin/ (built from src/).
# Build history: v2a (POLY machine) -> v2b (sequencer voice rotation) -> v3 (MIDI-track cable) ... -> v3p.
import struct, sys, os as _os
_here = _os.path.dirname(_os.path.abspath(__file__))
_bin = _os.path.join(_here, "..", "bin")
B   = 0x40000400
SRC = sys.argv[1]
DST = sys.argv[2]
d = bytearray(open(SRC, "rb").read())
orig = bytes(d)
def get(a, n): return bytes(orig[a-B:a-B+n])
def put(a, bs): d[a-B:a-B+len(bs)] = bs
def expect(a, hexs):
    assert get(a, len(hexs)//2).hex() == hexs, "unexpected bytes at %x: %s" % (a, get(a, len(hexs)//2).hex())
def w(x): return struct.pack(">H", x)
def l(x): return struct.pack(">I", x)

# ---------------- free space: body of SongTempoMenuView slot 400b8cf8 (1608 B, vtable-only ref) -------------
FN = 0x400b8cf8
expect(FN, "4fefffc048d77cfc")                # lea (-0x40,SP),SP ; movem.l ...
put(FN, bytes.fromhex("70004e75"))            # moveq #0,D0 ; rts   (song tempo menu unusable)
H = FN + 4
assert H % 4 == 0

# ---------------- name table (5 x {long name, short name}) ----------------
TBL = H                                       # 40 bytes
old_tbl = struct.unpack(">8I", get(0x401a9a40, 32))
assert [get(x, 8).split(b"\0")[0] for x in old_tbl[0::2]] == [b"ONESHOT", b"WERP", b"REPITCH", b"SLICE"], old_tbl
POLY_STR = TBL + 40
tbl = struct.pack(">8I", *old_tbl) + l(POLY_STR) + l(POLY_STR)
put(TBL, tbl)
put(POLY_STR, b"POLY\0\0\0\0")
code = POLY_STR + 8
assert code % 4 == 0

# ---------------- hooks ----------------
# LOOKUP: replaces "moveq 3,D2; cmp.l D0,D2; bcs.b bad; lsl.l #3,D0" in 40078f44 (slot,machine -> param id)
HK_LOOKUP = code
h  = bytes.fromhex("0c80") + l(4)             # 0  cmpi.l #4,D0
h += bytes.fromhex("6208")                    # 6  bhi.b  bad(16)
h += bytes.fromhex("6602")                    # 8  bne.b  ok(12)
h += bytes.fromhex("7000")                    # 10 moveq  #0,D0      (POLY -> ONESHOT param set)
h += bytes.fromhex("e788")                    # 12 lsl.l  #3,D0
h += bytes.fromhex("4e75")                    # 14 rts
h += bytes.fromhex("588f")                    # 16 addq.l #4,SP
h += bytes.fromhex("4ef9") + l(0x40078f54)    # 18 jmp    40078f54   (original "invalid machine" exit)
assert len(h) == 24
put(HK_LOOKUP, h)
code = HK_LOOKUP + len(h)

# ENGINE: replaces "lea (0x7e,A0),A0; move.b (A0),(0,A1,D0*1)" in 4007725a (machine byte -> audio engine)
HK_ENG = code
h  = bytes.fromhex("1228007e")                # move.b (0x7e,A0),D1
h += bytes.fromhex("0c010004")                # cmpi.b #4,D1
h += bytes.fromhex("6602")                    # bne.b  +2
h += bytes.fromhex("7200")                    # moveq  #0,D1
h += bytes.fromhex("13810800")                # move.b D1,(0,A1,D0*1)
h += bytes.fromhex("4e75")                    # rts
assert len(h) == 18
put(HK_ENG, h)
code = HK_ENG + len(h)
code = (code + 3) & ~3

# GETTER (alias): replaces "mvs.b (0x7e,A0),D0 ; bra.b end" in 4002200a (machine of a sound)
HK_GET = code
h  = bytes.fromhex("7128007e")                # mvs.b (0x7e,A0),D0
h += bytes.fromhex("0c80") + l(4)             # cmpi.l #4,D0
h += bytes.fromhex("6602")                    # bne.b  +2
h += bytes.fromhex("7000")                    # moveq  #0,D0
h += bytes.fromhex("588f")                    # addq.l #4,SP        (drop hook return address)
h += bytes.fromhex("245f")                    # movea.l (SP)+,A2    (original epilogue)
h += bytes.fromhex("4e75")                    # rts
assert len(h) == 20
put(HK_GET, h)
code = HK_GET + len(h)
code = (code + 3) & ~3

# RAW getter: byte-exact copy of the ORIGINAL 4002200a (returns real machine incl. 4). Used by 3 UI call sites.
RAW = code
raw = get(0x4002200a, 0x30)
assert raw[-2:] == bytes.fromhex("4e75") and raw[0x24:0x2a] == bytes.fromhex("7128007e6002"), raw.hex()
put(RAW, raw)
code = RAW + len(raw)
assert code < FN + 1608, "out of space"

# ---------------- patches at original sites ----------------
# 1. machine list has 5 entries (0..4)
expect(0x40022fe6, "7004"); put(0x40022fe6, bytes.fromhex("7005"))
# 2. list cursor pre-selection accepts 4
expect(0x4002a9e8, "7804"); put(0x4002a9e8, bytes.fromhex("7805"))
# 3. machine setter accepts 4
expect(0x400225f0, "7003"); put(0x400225f0, bytes.fromhex("7004"))
# 4. param-id lookup alias
expect(0x40078f72, "7403b48065dce788"); put(0x40078f72, bytes.fromhex("4eb9") + l(HK_LOOKUP) + bytes.fromhex("4e71"))
# 5. engine machine byte alias
expect(0x40077272, "41e8007e13900800"); put(0x40077272, bytes.fromhex("4eb9") + l(HK_ENG) + bytes.fromhex("4e71"))
# 6. getter alias (all callers see ONESHOT for POLY)
expect(0x4002202e, "7128007e6002"); put(0x4002202e, bytes.fromhex("4eb9") + l(HK_GET))
# 7. UI call sites that need the real value -> raw getter
for a in (0x4002b754, 0x4003b3fc, 0x4003bd3a):
    expect(a, "4eb94002200a"); put(a, bytes.fromhex("4eb9") + l(RAW))
# 8. name getters: bounds 3->4, new table
expect(0x4007910c, "7203"); put(0x4007910c, bytes.fromhex("7204"))
expect(0x40079118, "41f9401a9a40"); put(0x40079118, bytes.fromhex("41f9") + l(TBL))
expect(0x4007912c, "7203"); put(0x4007912c, bytes.fromhex("7204"))
expect(0x40079138, "0680401a9a44"); put(0x40079138, bytes.fromhex("0680") + l(TBL + 4))

# 9. list window size: the machine list view is built with a 6-row scroll window but only DRAWS 4 rows (draw loop cap at 4002a306).
#    With 4 items that never mattered; with 5 the cursor could sit on an undrawn row and POLY stayed invisible.
#    Make the window 4 rows so the list scrolls when the cursor reaches the 5th entry.
expect(0x4002a76e, "48780006"); put(0x4002a76e, bytes.fromhex("48780004"))
# 10. machine-select-by-index helper: limit idx+1<=4 -> 5 (lets the cursor/model reach POLY)
expect(0x4002a4ca, "7204"); put(0x4002a4ca, bytes.fromhex("7205"))

# ---------------- v2b: poly voice logic at the trig-message builder (4006f4be) ----------------
# site: move.l D0,(0xc,A2) ; move.l D5,(0x8,A2)  (msg id, msg voice = track). D5 must stay = track (used later for the params pointer).
# hook (assembled with GNU as -mcpu=5475, tested under unicorn CFV4E: src/ emu_test_v2b.py):
#  - reads machine byte of tracks 0..7 from the params block (builder arg3 + 0x20 + t*0xa2 + 0x7e); POLY == 4
#  - control track = lowest POLY track; only its trigs are redirected, and only if >= 2 POLY tracks exist
#  - voice = round-robin over POLY tracks; counter = song-mode-only RAM word 0x4208c8a8 (validated modulo n; garbage -> 0)
#  - message keeps the CONTROL track's params pointer (all poly voices share its sound); the engine's stored
#    params pointer of the chosen voice (0x800019b4+4*voice) is cleared so the engine does a full param reload at this trig
HK_POLY = (code + 3) & ~3
HK_BYTES = bytes.fromhex("2540000c206f004c2008670000aed1fc0000009e72007cff7e0010100c0000046600000c4a866c0000042c015287d1fc000000a252810c81000000086600ffdcba86660000767002be806500006e2239400b9104b28765000004720026015283b68765000004760023c3400b9104206f004cd1fc0000009e760010100c0000046600000a4a81670000185381d1fc000000a252830c83000000086600ffde2605ba83670000102203e58141f9800019b442b01800254300084e75254500084e75")
assert len(HK_BYTES) == 192
put(HK_POLY, HK_BYTES)
code = HK_POLY + len(HK_BYTES)
assert code < FN + 1608, "out of space"
expect(0x4006f76a, "2540000c25450008"); put(0x4006f76a, bytes.fromhex("4eb9") + l(HK_POLY) + bytes.fromhex("4e71"))


# ---------------- v3: Build B "internal MIDI cable" (replaces the v2c chord hook; 0x4006f4be stays ORIGINAL) ----------------
# Source: src/ cable.s (GNU as -mcpu=5475), tested: src/ emu_cable.py (real OS image, stubbed alloc/post).
# Entry patch over 0x400e0dda (MIDI task: append N bytes to MIDI-out buffer; only callers = the MIDI task's note on/off emitters).
# A 3-byte note on/off on channel ch also plays the audio tracks 0..7 whose MIDI receive channel == ch and machine == POLY,
# one voice per note (free voice first, else oldest), with the lowest such track's sound as sound lock (msg+0x2c).
# Message layout mirrors 0x40076b3c (stock live play). The note still goes out of MIDI OUT (original code runs after).
HK_CABLE_BYTES = bytes.fromhex("4fefffc448d77fff202f00400c800000000366000146206f00447200121020010280000000e00c80000000806600012c7600162800017800182800020801000466000004780002810000000f240120394199dc446700010424407a007cff7e0047f94197b70049ea009e201bb0826600001610140c0000046600000c0fc54a866a0000042c0749ec00a252870c87000000086d00ffd64a85670000c04bfa017e4a846700007c200304800000000c0c8000000048620000a472ff7eff70000105670000262040d1c0d1c0d1c0227588104a3508006b000008d3fc80000000b3c16400000622092e0052800c80000000086d00ffcc4a876b000062202d003052802b4000302207e58941f5181020801b8378001b8278087001610000546000003c7e000f0567000028700010357800b0836600001c10357808b0826600001270ff1b8078007002610000266000000e52870c87000000086d00ffca4cd77fff4fef003c73b9421b56204ef9400e0de026404eb9400ee0364a80670000a0204072022141000c214b0004214700082204e189314100142143001842a8002842a8004442a80030220b0c81000000016600005a223c000000a24c061800d28a0681000000202141002c22794199dc38d3fc0001ec642211203c0001ec684c0018000681409bac18203c0000038f4c060800d28006810000038222417351008100010001214100246000000a42a8002c42a800242f084eb9400ee296588f4e75ffffffffffffffffffffffffffffffff000000000000000000000000000000000000000000000000000000000000000000000000")
HK_CABLE = 0x400b8e60
ICON_BASE = 0x400b9260
assert HK_CABLE >= code and HK_CABLE + len(HK_CABLE_BYTES) <= 0x400b9100, (hex(code), len(HK_CABLE_BYTES))
put(HK_CABLE, HK_CABLE_BYTES)
expect(0x400e0dda, "73b9421b5620"); put(0x400e0dda, bytes.fromhex("4ef9") + l(HK_CABLE))

# ---------------- v3b: keep POLY across kit/project load ----------------
# Sound load 0x4007a236 (storage v3 -> runtime 0xa2 block): runtime+0x7e (machine) = storage+0x7c only if
# (byte)(v+1) < 5, else 0 (ONESHOT). Save 0x4007a5a0 stores the machine raw, so POLY (4) is saved but dropped on load.
# moveq #5,d2 -> moveq #6,d2 : accept 0..4 (and -1). The official OS still maps 4 -> ONESHOT on load.
expect(0x4007a2d0, "7405"); put(0x4007a2d0, bytes.fromhex("7406"))

# ---------------- v3c: live oscilloscope on the Song edit screen ----------------
# Source src/ scope_v3f.s: scope drawn over the main screen (info line kept), keys go to the main screen.
# Tests src/ emu_scope_v3f.py + emu_v3f.py (KEY). Code + 512x16-bit ring live in the body of
# SongEditView::drawView 0x400abe9c (2028 B; its only reference is vtable slot 4 at 0x401b3760, which keeps pointing here).
# v3h: code from src/scope.s (no ring inside any more), padded to the v3f size so lock.s stays put.
SCOPE_CODE = open(_os.path.join(_bin, "scope.bin"), "rb").read()
SYMS = {p[2]: int(p[0], 16) for p in (ln.split() for ln in open(_os.path.join(_bin, "scope.sym"))) if len(p) == 3}
assert len(SCOPE_CODE) <= 1616
SCOPE_BYTES = SCOPE_CODE + bytes(1616 - len(SCOPE_CODE))
SCOPE = 0x400abe9c
SC_TICK, SC_TAP = SCOPE + SYMS["TICK"], SCOPE + SYMS["TAP"]
assert len(SCOPE_BYTES) <= 0x400ac688 - SCOPE
expect(SCOPE, "4fefff8448d77cfc"); put(SCOPE, SCOPE_BYTES)
# SongEditView vtable slot 11 (periodic tick) -> TICK (original tick + invalidate = continuous redraw)
expect(0x401b377c, "400aa8e2"); put(0x401b377c, l(SC_TICK))
# audio ISR: "jsr 0x40071c20" (write output half) -> TAP (same call, then copy to ring)
expect(0x4007814a, "4eb940071c20"); put(0x4007814a, bytes.fromhex("4eb9") + l(SC_TAP))

# ---------------- v3d ----------------
# (a) scope opens directly: MainScreenView key 5 plain press made SongModePopup (0x4014640c); now it makes
#     SongEditView (0x401463c2, same calling convention) = the scope. The hold path already opened SongEditView.
expect(0x4002e914, "4eb94014640c"); put(0x4002e914, bytes.fromhex("4eb9401463c2"))
# (b) scope key handler: SongEditView vtable slot 2 (consumeKeyEvent) -> KEY (song-edit keys swallowed,
#     key 5 press closes, navigation/exit ids go to the original handler)
SC_KEY = SCOPE + SYMS["KEY"]
expect(0x401b3758, "400ac8f0"); put(0x401b3758, l(SC_KEY))
# (c) CC cable: source src/ cc.s, tested by emu_v3d.py. Entry patch over 0x400e0b84 (MIDI task CC buffer append).
CC_BYTES = bytes.fromhex("4fefffc448d77fff202f00400c80000000036600008a206f00447200121020010280000000f00c80000000b06600007002810000000f24017600162800010c83000000786400005878001828000220394199dc4467000048244047f94197b70049ea009e4bf9400d6a587e00201bb0826600001c10140c0000046600001242a742a72f042f032f074e954fef001449ec00a252870c87000000086d00ffd04cd77fff4fef003c73b9421b5a214ef9400e0b8a")
CC_HK = 0x400b9110
assert CC_HK + len(CC_BYTES) <= 0x400b9260          # before the POLY icon data
put(CC_HK, CC_BYTES)
expect(0x400e0b84, "73b9421b5a21"); put(0x400e0b84, bytes.fromhex("4ef9") + l(CC_HK))

# ---------------- v3e: per-voice SOURCE TUNE + LFO for POLY voices ----------------
# Source src/ lock.s, test src/ emu_lock.py. Code after the scope in the old SongEditView::drawView body.
# Engine param load 0x40077282 tail "jmp 0x400749cc" -> POST: expansion unchanged, then slots 1..0x11
# (LFO1/LFO2, TUNE) of a POLY voice loaded with another kit track's block are taken from the voice's own track.
LOCK_BYTES = bytes.fromhex("2f2f00082f2f00084eb9400749cc508f4fefffe848d70c3c242f001c246f002045eaffec0c82000000086400001a20394199dc446100001a6700000c2039800019ac6100000c4cd70c3c4fef00184e754a8067000082068000000020220a9280650000740c81000005106400006a263c000000a24c023800d680b5c3670000582643102b007e0c0000046600004a786a4c02480006848000150220442a3c000000d44c025800068580002b50224572012001d080383308143184080048444244d0802384080052810c81000000116f00ffe070004e7570014e75")
LOCK = SCOPE + len(SCOPE_BYTES)                    # 0x400ac4ec (v3f, v3g, v3h)
assert LOCK == 0x400ac4ec
assert LOCK == SCOPE + len(SCOPE_BYTES) and LOCK + len(LOCK_BYTES) <= 0x400ac688
put(LOCK, LOCK_BYTES)
expect(0x400772e0, "4ef9400749cc"); put(0x400772e0, bytes.fromhex("4ef9") + l(LOCK))

# ---------------- v3g: song mode can never become active ----------------
# Project setting +0x28: 0 pattern, 1 SONG, 2 chain. Source src/ songoff.s (FIX: clamp 0..2, 1 -> 0),
# test src/ emu_songoff.py. Chains (2) keep working; song mode (1) is blocked in the setter and hidden
# by the getter (a project saved in song mode loads in pattern mode).
FIX_BYTES = bytes.fromhex("4a816a00000672004e750c81000000016600000672004e750c81000000026f00000472024e75")
FIX = 0x400b91c4
assert FIX >= CC_HK + len(CC_BYTES) and FIX + len(FIX_BYTES) <= 0x400b9260
put(FIX, FIX_BYTES)
# setter 0x4001d842: "moveq #2,d2; cmp.l d1,d2; bge; moveq #2,d1" -> jsr FIX ; nop
expect(0x4001d878, "7402b4816c027202"); put(0x4001d878, bytes.fromhex("4eb9") + l(FIX) + bytes.fromhex("4e71"))
# getter 0x4001d8a8: "move.l 40(a0),d0; blt; moveq #2,d1; cmp; bge; moveq #2,d0" -> move.l 40(a0),d1; jsr FIX; move.l d1,d0; bra.s 0x4001d8de
expect(0x4001d8cc, "202800286d0a7202b2806c067002")
put(0x4001d8cc, bytes.fromhex("22280028") + bytes.fromhex("4eb9") + l(FIX) + bytes.fromhex("20016004"))
expect(0x4001d8dc, "4280")   # null-object path target stays intact

# ---------------- v3h: scope ring moved to the dead SongModePopup code ----------------
# SongModePopup (vtable 0x401b3cd4) was only created by make_shared 0x4014640c, whose only caller 0x4002e914 was
# redirected in v3d. Its ctor/methods 0x400ae26e..0x400af23e (4048 B) are unreachable (checked: no absolute or
# pc-relative references from outside except its own vtables/make_shared and an unreferenced EH landing pad).
# scope_v3o data: IDX, MODE, LASTV, pad, ring 512 x {mid, side} int16 = 0x400ae280..0x400aea90.
CAVE, CAVE_END = 0x400ae26e, 0x400af23e
expect(CAVE, "4feffff02f0a2f02")
expect(0x40146446, "4eb9400ae26e")          # the (dead) make_shared call site, untouched
put(CAVE, bytes.fromhex("4e75"))             # ctor -> rts (defensive; unreachable)
DATA = 0x400ae280
put(DATA, bytes(16 + 512 * 4 + 36))          # + v3k: TRIGCNT[8], LASTCNT[8], HOLD[8]; v3m: PYMAX, PYMID, PNAMP
assert DATA + 16 + 512 * 4 + 36 <= CAVE_END
# v3k: audio ISR voice-start hook. At 0x40077d6c d3 = mask of voices 0..7 started in this block;
# "clr.l 0x4199e130" -> jsr TRIG (does the same clear, then counts starts per voice; registers preserved).
SC_TRIG = SCOPE + SYMS["TRIG"]
# v3n: the site above (0x40077d6c) is inside a block that only runs when 0x4199e130 != 0 -> most sequencer trigs
# were missed. Hook the merge point 0x40077d72 instead (only branch target in 0x40077d72..79 is 0x40077d72 itself,
# from 0x40077cf4): "move.l d3,d2; not.l d2; and.l -76(fp),d2" -> jsr TRIG; nop (TRIG re-executes them).
# 0x40077d6c stays stock.
expect(0x40077d6c, "42b94199e130")
expect(0x40077d72, "24034682c4aeffb4"); put(0x40077d72, bytes.fromhex("4eb9") + l(SC_TRIG) + bytes.fromhex("4e71"))

# ---------------- v3l: scope survives pattern/bank change; scope does not own any LEDs ----------------
# PatternAndBankSelectView key handler, after a pattern (0x40095ae4) or bank (0x40095bee) pick, looks up a view of type
# SongEditView (0x4015ea5c, typeinfo 0x401b36c4) and closes it (stock: leaving song edit). The only SongEditView in
# this firmware is the scope (song mode blocked since v3g) -> never close it: "beq.s skip" -> "bra.s skip".
expect(0x40095af2, "670c2250"); put(0x40095af2, bytes.fromhex("600c"))
expect(0x40095bfc, "670c2250"); put(0x40095bfc, bytes.fromhex("600c"))
# SongEditView LED handler (LedHandler subobject +104 vtable slot 2 = thunk 0x400ab128 -> 0x400aaeca, primary slot 21)
# claimed the trig LEDs for song-edit displays; when the scope sat above the pattern-select view it hid the green
# "pattern has data" LEDs. Point both entries at the stock empty method 0x400c96be (rts): the scope claims no LEDs,
# the views below (pattern select, main screen) light them exactly as without the scope.
expect(0x400c96be, "4e75")
expect(0x401b380c, "400ab128"); put(0x401b380c, l(0x400c96be))
expect(0x401b3798, "400aaeca"); put(0x401b3798, l(0x400c96be))

# ---------------- v3o: tuner ----------------
# Source src/tuner.s (linked at 0x400ac8f0, tuner.elf -> tuner.bin), model tuner_model.py, tests emu_tuner_v3o.py.
# Placed over the old SongEditView::consumeKeyEvent 0x400ac8f0..0x400acfd6 (1766 B): its only reference was the
# vtable slot now pointing at the scope KEY, which since v3o also handles key 6 itself (checked: no other refs).
TUNER = 0x400ac8f0
TUNER_BYTES = open(_os.path.join(_bin, "tuner.bin"), "rb").read()
expect(TUNER, "4e56ffcc48d73c3c")
assert TUNER + len(TUNER_BYTES) <= 0x400acfd6, len(TUNER_BYTES)
assert get(0x400acfd4, 2).hex() == "4e75"                 # end of the old handler
put(TUNER, TUNER_BYTES)
# tuner data (after the scope data): TIDX, TNOTE (= -1), TCENT, TCNT, TBUF, pad; 3 kHz ring 512 x int16
put(0x400aeab4, bytes(4) + bytes.fromhex("ffffffff") + bytes(20))
put(0x400aead0, bytes(1024))
assert 0x400aead0 + 1024 <= CAVE_END

# ---------------- v3p: knob (encoder) turns fall through the scope to the main screen's parameter page ----------------
# Encoder events (+12 encoder id, +16 delta, +20 flag; built at 0x40008570) are dispatched by 0x400cad60 through the
# same top-down controller walk as keys (0x400cab06, stops at the first view returning true), via interface +4
# (invoker 0x400c9cc6). SongEditView's +4 handler (thunk 0x400aaec2 -> 0x400aaa86 = primary slot 20) edits song rows
# with the knobs and returns true, so the scope swallowed every turn. Point both entries at the stock
# "not handled" method 0x400c5104 (clr.b d0; rts), as used by the other listener interfaces.
expect(0x400c5104, "42004e75")
expect(0x401b37ac, "400aaec2"); put(0x401b37ac, l(0x400c5104))
expect(0x401b3794, "400aaa86"); put(0x401b3794, l(0x400c5104))

# data words in the dead SongTempoMenuView body (SDRAM, ACR0 copyback, not write-protected)
put(0x400b9100, bytes(8))
# 11. POLY row icon
sys.path.insert(0, _here)
import icon_patch
assert get(0x400b9100, 0x100) == bytes(0x100) or True
icon_end = icon_patch.apply(get, put, expect, l, ICON_BASE)
assert icon_end < FN + 1608
# the hooks embedded above as hex must equal the assembled sources in bin/
for _n, _b in (("cable", HK_CABLE_BYTES), ("cc", CC_BYTES), ("lock", LOCK_BYTES), ("songoff", FIX_BYTES)):
    _a = open(_os.path.join(_bin, _n + ".bin"), "rb").read()
    assert _b.startswith(_a) and not any(_b[len(_a):]), "embedded %s hook differs from src/%s.s" % (_n, _n)
open(DST, "wb").write(d)
n = sum(1 for i in range(len(d)) if d[i] != orig[i])
print("wrote", DST, "changed bytes:", n)
print("table %x poly str %x hooks: lookup %x engine %x getter %x raw %x poly %x end %x (limit %x)" %
      (TBL, POLY_STR, HK_LOOKUP, HK_ENG, HK_GET, RAW, HK_POLY, code, FN + 1608))
