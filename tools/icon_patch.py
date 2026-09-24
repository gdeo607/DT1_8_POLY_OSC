# POLY row icon (7x11 capital "P") for the FUNC+SRC machine list. Shared by make_v2a.py / make_v2b.py.
# Row icons are drawn by 0x40029e9c: group id (0x40029e80: table 01 02 03 04 by machine id) selects one of 4
# static bitmap objects {vtable 401b73b4, h=0xb, w=7, words=1, glyph ptr, mask ptr, flag}.
# We add group 5 with a static bitmap object placed in free space (0x400b9100..), plus a tiny hook.
import struct
def apply(get, put, expect, l, base=0x400b9100):
    OBJ, MASK, GLYPH, TAB, CODE = base, base+0x20, base+0x50, base+0x80, base+0x90
    # the free area must be unused (zero or code we don't own): it is inside the SongTempoMenuView body
    P = [0xfc,0xc6,0xc6,0xc6,0xc6,0xfc,0xc0,0xc0,0xc0,0xc0,0xc0]
    put(MASK, b"".join(l(0xfe000000) for _ in range(11)))
    put(GLYPH, b"".join(l(v << 24) for v in P))
    put(OBJ, l(0x401b73b4) + l(11) + l(7) + l(1) + l(GLYPH) + l(MASK) + l(0))
    put(TAB, bytes([1,2,3,4,5,0,0,0]))
    # group getter 0x40029e80: accept machine ids 0..4, table moved
    expect(0x40029e80, "7203"); put(0x40029e80, bytes.fromhex("7204"))
    expect(0x40029e8a, "41f9401c2e0c"); put(0x40029e8a, bytes.fromhex("41f9") + l(TAB))
    # icon draw 0x40029e9c default exit (group not 1..4) -> our hook
    expect(0x40029f60, "4cd7001c4fef000c4e75")
    put(0x40029f60, bytes.fromhex("4ef9") + l(CODE) + bytes.fromhex("4e714e71"))
    c  = bytes.fromhex("0c80") + l(5)                 # cmpi.l #5,D0      (group id, zero extended)
    c += bytes.fromhex("6600") + b"\0\0"              # bne.w default (patched below)
    c += bytes.fromhex("5384")                        # subq.l #1,D4
    c += bytes.fromhex("5483")                        # addq.l #2,D3
    c += bytes.fromhex("42af0020")                    # clr.l (0x20,SP)
    c += bytes.fromhex("203c") + l(OBJ)               # move.l #OBJ,D0  (ColdFire: no 4-word insns)
    c += bytes.fromhex("2f400014")                    # move.l D0,(0x14,SP)
    c += bytes.fromhex("2f44001c")                    # move.l D4,(0x1c,SP)
    c += bytes.fromhex("2f430018")                    # move.l D3,(0x18,SP)
    c += bytes.fromhex("2f420010")                    # move.l D2,(0x10,SP)
    c += bytes.fromhex("4cd7001c4fef000c")            # movem.l (SP),D2-D4 ; lea 12(SP),SP
    c += bytes.fromhex("4ef9400c2960")                # jmp 400c2960 (draw bitmap)
    dflt = len(c)
    c += bytes.fromhex("4cd7001c4fef000c4e75")        # original default exit
    c = bytearray(c); c[8:10] = struct.pack(">h", dflt - 8) ; c[6:8] = bytes.fromhex("6600")
    # bne.w: opcode 6600 + 16-bit disp relative to (opcode addr+2)
    c[6:8] = bytes.fromhex("6600"); c[8:10] = struct.pack(">h", dflt - 8)
    put(CODE, bytes(c))
    return CODE + len(c)
