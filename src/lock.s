| POLY v3e: per-voice SOURCE TUNE and LFO for POLY voices. Assemble: m68k-linux-gnu-as -mcpu=5475
| Engine param load 0x40077282(ptr, voice) copies 53 param words (slot s at ptr+0x14+2s) into the voice
| (16-bit copy at 0x80001502+v*0x6a, then tail-jumps to 0x400749cc(voice, ptr+0x14) which expands them
| to 32-bit at 0x80002b50+v*0xd4). Its tail "jmp 0x400749cc" (0x400772e0) now jumps here: we run the
| expansion unchanged, then, if the voice's own track is POLY and the loaded block is ANOTHER kit track's
| block (the control's sound given to a POLY voice), overwrite slots 0x01..0x11 (LFO1+LFO2 = 1..0x10,
| TUNE = 0x11) in both copies with the voice track's own values. Everything else (sample, filter, amp...)
| stays the control's. Stock sound locks (pool sounds) and non-POLY tracks are untouched.
| Runs in the audio interrupt, like 0x40077282 itself.

    .set EXPAND,   0x400749cc
    .set Q_PTR,    0x4199dc44      | sequencer kit params base
    .set E_PTR,    0x800019ac      | engine kit params base
    .set V16,      0x80001502
    .set V32,      0x80002b50
    .set SLOT_LO,  1
    .set SLOT_HI,  0x11

    .text
POST:
    move.l 8(%sp),-(%sp)            | src (ptr+0x14)
    move.l 8(%sp),-(%sp)            | voice
    jsr EXPAND
    addq.l #8,%sp
    lea -24(%sp),%sp
    movem.l %d2-%d5/%a2-%a3,(%sp)
    move.l 28(%sp),%d2              | voice
    move.l 32(%sp),%a2
    lea -0x14(%a2),%a2              | ptr (block)
    cmpi.l #8,%d2
    bcc .Lout                       | voices 0..7 only
    move.l Q_PTR,%d0
    bsr .Ltry
    beq .Lout                       | done (patched)
    move.l E_PTR,%d0
    bsr .Ltry
.Lout:
    movem.l (%sp),%d2-%d5/%a2-%a3
    lea 24(%sp),%sp
    rts

| try base d0: Z=1 if the block was recognised and patched, Z=0 otherwise
.Ltry:
    tst.l %d0
    beq .Lno
    addi.l #0x20,%d0                | first kit block
    move.l %a2,%d1
    sub.l %d0,%d1                   | ptr - lo
    bcs .Lno                        | below
    cmpi.l #8*0xa2,%d1
    bcc .Lno                        | above
    move.l #0xa2,%d3
    muls.l %d2,%d3
    add.l %d0,%d3                   | own block
    cmpa.l %d3,%a2
    beq .Lno                        | loading its own block: nothing to do
    move.l %d3,%a3
    move.b 0x7e(%a3),%d0
    cmpi.b #4,%d0
    bne .Lno                        | voice track is not POLY
    moveq #0x6a,%d4
    muls.l %d2,%d4
    addi.l #V16,%d4
    move.l %d4,%a0                  | 16-bit copy of voice
    move.l #0xd4,%d5
    muls.l %d2,%d5
    addi.l #V32,%d5
    move.l %d5,%a1                  | 32-bit copy of voice
    moveq #SLOT_LO,%d1
.Lcp:
    move.l %d1,%d0
    add.l %d0,%d0
    move.w 0x14(%a3,%d0.l),%d4      | own value
    move.w %d4,(%a0,%d0.l)
    swap %d4
    clr.w %d4
    add.l %d0,%d0
    move.l %d4,(%a1,%d0.l)
    addq.l #1,%d1
    cmpi.l #SLOT_HI,%d1
    ble .Lcp
    moveq #0,%d0                    | Z=1
    rts
.Lno:
    moveq #1,%d0                    | Z=0
    rts
