| Scope tuner for OS 1.53 (POLY v3o). Assemble: m68k-linux-gnu-as -mcpu=5475
| Placed at 0x400ac8f0 over the old SongEditView::consumeKeyEvent (1766 B; dead since v3o, where the scope's
| KEY handles the one key (6) it still forwarded there). Integer model: tuner_model.py (bit-exact).
|  TTAP  (audio ISR, called by the scope TAP after each block): 2 samples at 3 kHz = (sum of 4 new 12 kHz mids)>>2
|         into a 512-entry ring (170 ms, for bass notes).
|  TUNE  (UI, every DRAW): every 4th call estimates the pitch (YIN, threshold 0.25, parabolic interpolation,
|         refined at the largest multiple of the period) on the 12 kHz ring (lags 4..200 = 3000..60 Hz), else on
|         the 3 kHz ring (lags 45..250 = 67..12 Hz); result in TNOTE (MIDI note, -1 = none) and TCENT (-50..49).
|  TDRAW (UI, DRAW(bmp)): clears x 0..31, rows 0..6 (= lower left on the physical screen) and prints
|         "A#4 +12" / "--" with the stock 5-px font 0x40200b0c via 0x400c257c.

    .set RING,     0x400ae290      | scope ring: 512 x {int16 mid, int16 side}
    .set IDXA,     0x400ae280
    .set TDATA,    0x400aeab4      | after the scope data (PNAMP ends at 0x400aeab4)
    .set TIDX,     TDATA           | 3 kHz ring write index
    .set TNOTE,    TDATA+4         | MIDI note or -1
    .set TCENT,    TDATA+8
    .set TCNT,     TDATA+12        | TUNE call counter
    .set TBUF,     TDATA+16        | work buffer (heap, 1024 B, allocated once)
    .set TRING,    0x400aead0      | 512 x int16 (3 kHz)
    .set RN,       512
    .set W,        256
    .set NEWOP,    0x400d4180      | operator new(size)
    .set TEXT,     0x400c257c      | printf text(bmp, font, x, y, flags, fmt, ...)
    .set FONT,     0x40200b0c      | stock 5-px font
    .set VLINE,    0x400c1040
    .set PA4,      6982            | A4 period at 12 kHz in 1/256 sample
    .set MINPK,    256

    .text
| ------------------------------------------------------------------ TTAP (ISR; all registers preserved)
TTAP:
    lea -16(%sp),%sp
    movem.l %d0-%d2/%a0,(%sp)
    move.l IDXA,%d2
    subq.l #8,%d2                   | first of the 8 new mids
    bsr .Ltt1
    bsr .Ltt1
    movem.l (%sp),%d0-%d2/%a0
    lea 16(%sp),%sp
    rts
.Ltt1:                              | one 3 kHz sample from mids d2..d2+3; d2 += 4
    moveq #0,%d1
    moveq #4,%d0
    lea RING,%a0
.Ltt2:
    move.l %d2,-(%sp)
    andi.l #RN-1,%d2
    move.w (%a0,%d2.l*4),%d2
    ext.l %d2
    add.l %d2,%d1
    move.l (%sp)+,%d2
    addq.l #1,%d2
    subq.l #1,%d0
    bne .Ltt2
    asr.l #2,%d1
    move.l TIDX,%d0
    move.l %d0,-(%sp)
    andi.l #RN-1,%d0
    lea TRING,%a0
    move.w %d1,(%a0,%d0.l*2)
    move.l (%sp)+,%d0
    addq.l #1,%d0
    move.l %d0,TIDX
    rts

| ------------------------------------------------------------------ TUNE (UI; all registers preserved)
TUNE:
    lea -44(%sp),%sp
    movem.l %d2-%d7/%a2-%a6,(%sp)
    move.l TCNT,%d0
    addq.l #1,%d0
    move.l %d0,TCNT
    andi.l #3,%d0
    bne .Luout                      | estimate on every 4th frame
    move.l TBUF,%d0
    bne .Lubuf
    pea 1024.w
    jsr NEWOP
    addq.l #4,%sp
    move.l %d0,TBUF
    beq .Luout
.Lubuf:
    move.l %d0,%a2                  | a2 = work buffer
| ---- 12 kHz: 457 mids ending 16 behind the write index
    move.l IDXA,%d7
    subi.l #16+W+201,%d7
    lea RING,%a3
    moveq #4,%d6                    | stride shift: *4
    move.l #W+201,%d5
    bsr .Lucopy
    bne .Lunone                     | too quiet
    moveq #4,%d0                    | lmin
    move.l #200,%d1                 | lmax
    bsr .Lyin
    tst.l %d0
    bpl .Lunote
| ---- 3 kHz: 507 samples ending 2 behind
    move.l TIDX,%d7
    subi.l #2+W+251,%d7
    lea TRING,%a3
    moveq #2,%d6
    move.l #W+251,%d5
    bsr .Lucopy
    bne .Lunone
    moveq #45,%d0
    move.l #250,%d1
    bsr .Lyin
    tst.l %d0
    bmi .Lunone
    lsl.l #2,%d0                    | 3 kHz period -> 12 kHz
.Lunote:
    bsr .Lnote                      | d0 = P12 -> d0 = midi, d1 = cents
    cmpi.l #12,%d0
    blt .Lunone
    cmpi.l #127,%d0
    bgt .Lunone
    move.l %d0,TNOTE
    move.l %d1,TCENT
    bra .Luout
.Lunone:
    moveq #-1,%d0
    move.l %d0,TNOTE
.Luout:
    movem.l (%sp),%d2-%d7/%a2-%a6
    lea 44(%sp),%sp
    rts

| .Lucopy: copy d5 samples from ring a3 (stride d6 = 4 or 2 bytes, 512 entries) starting at index d7 into a2
| (int16), then shift right so |x| <= 1023. Z=0 (bne) if the peak < MINPK.
.Lucopy:
    move.l %a2,%a0
    moveq #0,%d4                    | peak
    moveq #0,%d3                    | k
.Luc1:
    move.l %d7,%d0
    add.l %d3,%d0
    andi.l #RN-1,%d0
    cmpi.l #4,%d6
    bne .Luc2
    move.w (%a3,%d0.l*4),%d1
    bra .Luc3
.Luc2:
    move.w (%a3,%d0.l*2),%d1
.Luc3:
    move.w %d1,(%a0)+
    ext.l %d1
    bpl .Luc4
    neg.l %d1
.Luc4:
    cmp.l %d4,%d1
    ble .Luc5
    move.l %d1,%d4
.Luc5:
    addq.l #1,%d3
    cmp.l %d5,%d3
    blt .Luc1
    cmpi.l #MINPK,%d4
    blt .Lucq
    moveq #0,%d2                    | shift
.Luc6:
    move.l %d4,%d0
    asr.l %d2,%d0
    cmpi.l #1023,%d0
    ble .Luc7
    addq.l #1,%d2
    bra .Luc6
.Luc7:
    move.l %a2,%a0
    move.l %d5,%d3
.Luc8:
    move.w (%a0),%d1
    ext.l %d1
    asr.l %d2,%d1
    move.w %d1,(%a0)+
    subq.l #1,%d3
    bne .Luc8
    moveq #0,%d0                    | Z=1: ok
    rts
.Lucq:
    moveq #1,%d0                    | Z=0: quiet
    rts

| .Ldf: d0 = sum_{i<W} (x[i]-x[i+L])^2 over a2, L = d1. Clobbers d0 only (and scratch saved inside).
.Ldf:
    lea -20(%sp),%sp
    movem.l %d1-%d3/%a0-%a1,(%sp)
    move.l %a2,%a0
    lea (%a2,%d1.l*2),%a1
    moveq #0,%d0
    move.l #W,%d3
.Ldf1:
    move.w (%a0)+,%d2
    ext.l %d2
    move.w (%a1)+,%d1
    ext.l %d1
    sub.l %d1,%d2
    muls.w %d2,%d2
    add.l %d2,%d0
    subq.l #1,%d3
    bne .Ldf1
    movem.l (%sp),%d1-%d3/%a0-%a1
    lea 20(%sp),%sp
    rts

| .Lyin: buffer a2, lmin d0, lmax d1 -> d0 = period * 256 or -1. Uses d2-d7, a4-a5.
.Lyin:
    move.l %d0,%a4                  | lmin
    move.l %d1,%a5                  | lmax
    moveq #0,%d4                    | cum
    moveq #1,%d5                    | L
.Ly1:
    move.l %d5,%d1
    bsr .Ldf
    lsr.l #8,%d0
    move.l %d0,%d6                  | d8(L)
    add.l %d0,%d4
    cmp.l %a4,%d5
    blt .Ly2
    move.l %d6,%d2
    mulu.l %d5,%d2                  | d8*L
    move.l %d4,%d3
    moveq #100,%d0
    divu.l %d0,%d3
    moveq #25,%d0
    mulu.l %d0,%d3                  | (cum/100)*25
    cmp.l %d3,%d2
    bcs .Ly3                        | found
.Ly2:
    addq.l #1,%d5
    cmp.l %a5,%d5
    ble .Ly1
    moveq #-1,%d0
    rts
.Ly3:                               | descend to the local minimum
    move.l %d5,%d1
    addq.l #1,%d1
    cmp.l %a5,%d1
    bgt .Ly4
    bsr .Ldf
    lsr.l #8,%d0
    cmp.l %d6,%d0
    bcc .Ly4
    move.l %d0,%d6
    addq.l #1,%d5
    bra .Ly3
.Ly4:
    cmp.l %a5,%d5
    blt .Ly5
    moveq #-1,%d0                   | minimum at the edge: out of range
    rts
.Ly5:
    move.l %d5,%d7
    bsr .Lpat                       | d0 = L*256 + parab around d7
    move.l %d0,%d6                  | P
| refine at k*P
    move.l %a5,%d2
    lsl.l #8,%d2
    divu.l %d6,%d2                  | k
    cmpi.l #2,%d2
    blt .Ly9
    move.l %d2,%d3
    mulu.l %d6,%d3
    addi.l #128,%d3
    lsr.l #8,%d3                    | Lk
    move.l %d3,%d7                  | best
    move.l %d3,%d1
    bsr .Ldf
    move.l %d0,%d4                  | bv
    moveq #-2,%d5
.Ly6:
    tst.l %d5
    beq .Ly8
    move.l %d3,%d1
    add.l %d5,%d1
    cmpi.l #2,%d1
    blt .Ly8
    cmp.l %a5,%d1
    bgt .Ly8
    move.l %d1,-(%sp)
    bsr .Ldf
    move.l (%sp)+,%d1
    cmp.l %d4,%d0
    bcc .Ly8
    move.l %d0,%d4
    move.l %d1,%d7
.Ly8:
    addq.l #1,%d5
    cmpi.l #2,%d5
    ble .Ly6
    bsr .Lpat                       | around best (d7)
    move.l %d2,%d1
    lsr.l #1,%d1
    add.l %d1,%d0
    divu.l %d2,%d0                  | (Pk + k/2) / k
    rts
.Ly9:
    move.l %d6,%d0
    rts

| .Lpat: d0 = d7*256 + parab(D(d7-1), D(d7), D(d7+1)). Uses d0-d1 and saves d2-d5.
.Lpat:
    lea -16(%sp),%sp
    movem.l %d2-%d5,(%sp)
    move.l %d7,%d1
    subq.l #1,%d1
    bsr .Ldf
    move.l %d0,%d2                  | a
    move.l %d7,%d1
    bsr .Ldf
    move.l %d0,%d3                  | b
    move.l %d7,%d1
    addq.l #1,%d1
    bsr .Ldf
    move.l %d0,%d4                  | c
    move.l %d2,%d0
    cmp.l %d3,%d0
    bcc .Lp1
    move.l %d3,%d0
.Lp1:
    cmp.l %d4,%d0
    bcc .Lp2
    move.l %d4,%d0
.Lp2:                               | d0 = max
    moveq #0,%d5
.Lp3:
    move.l %d0,%d1
    lsr.l %d5,%d1
    cmpi.l #0x800000,%d1
    bcs .Lp4
    addq.l #1,%d5
    bra .Lp3
.Lp4:
    lsr.l %d5,%d2
    lsr.l %d5,%d3
    lsr.l %d5,%d4
    move.l %d2,%d0
    sub.l %d3,%d0
    sub.l %d3,%d0
    add.l %d4,%d0                   | den
    ble .Lp6
    move.l %d2,%d1
    sub.l %d4,%d1
    asl.l #7,%d1
    divs.l %d0,%d1                  | off
    cmpi.l #128,%d1
    ble .Lp5
    move.l #128,%d1
.Lp5:
    cmpi.l #-128,%d1
    bge .Lp7
    move.l #-128,%d1
    bra .Lp7
.Lp6:
    moveq #0,%d1
.Lp7:
    move.l %d7,%d0
    lsl.l #8,%d0
    add.l %d1,%d0
    movem.l (%sp),%d2-%d5
    lea 16(%sp),%sp
    rts

| .Lnote: d0 = P12 (period at 12 kHz, 1/256 sample) -> d0 = MIDI note, d1 = cents (-50..49)
.Lnote:
    move.l #PA4<<16,%d2
    divu.l %d0,%d2                  | q
    moveq #0,%d3                    | octave
.Ln1:
    cmpi.l #65536,%d2
    bcc .Ln2
    lsl.l #1,%d2
    subq.l #1,%d3
    bra .Ln1
.Ln2:
    cmpi.l #131072,%d2
    bcs .Ln3
    lsr.l #1,%d2
    addq.l #1,%d3
    bra .Ln2
.Ln3:
    lea TRT(%pc),%a0
    moveq #11,%d4                   | j
.Ln4:
    move.l (%a0,%d4.l*4),%d5
    cmp.l %d2,%d5
    bls .Ln5
    subq.l #1,%d4
    bra .Ln4
.Ln5:
    move.l %d2,%d0
    sub.l %d5,%d0
    lsl.l #8,%d0
    lsl.l #8,%d0
    divu.l %d5,%d0                  | y (16.16)
    move.l %d0,%d1
    mulu.l %d0,%d1
    lsr.l #8,%d1
    lsr.l #8,%d1
    move.l #865,%d5
    mulu.l %d5,%d1
    move.l #1731,%d5
    mulu.l %d5,%d0
    sub.l %d1,%d0
    lsr.l #8,%d0
    lsr.l #8,%d0                    | cents 0..99
    move.l %d0,%d1
    moveq #12,%d0
    muls.l %d3,%d0
    add.l %d4,%d0                   | semis
    cmpi.l #50,%d1
    blt .Ln6
    addq.l #1,%d0
    subi.l #100,%d1
.Ln6:
    addi.l #69,%d0
    rts

| ------------------------------------------------------------------ TDRAW(bmp)  (UI)
TDRAW:
    lea -12(%sp),%sp
    movem.l %d2-%d3/%a2,(%sp)
    move.l 16(%sp),%a2              | bitmap
    moveq #0,%d2
.Ltd1:                              | clear x 0..31, rows 0..6
    clr.l -(%sp)
    pea 6.w
    clr.l -(%sp)
    move.l %d2,-(%sp)
    move.l %a2,-(%sp)
    jsr VLINE
    lea 20(%sp),%sp
    addq.l #1,%d2
    cmpi.l #32,%d2
    blt .Ltd1
    move.l TNOTE,%d0
    bpl .Ltd2
    pea STRNONE(%pc)
    bra .Ltd3
.Ltd2:
    move.l TCENT,%d1
    moveq #'+',%d3
    tst.l %d1
    bpl .Ltd4
    moveq #'-',%d3
    neg.l %d1
.Ltd4:
    move.l %d1,-(%sp)               | |cents|
    move.l %d3,-(%sp)               | sign
    move.l %d0,%d2
    moveq #12,%d1
    divu.l %d1,%d2                  | d2 = note / 12
    moveq #12,%d1
    muls.l %d2,%d1
    neg.l %d1
    add.l %d0,%d1                   | d1 = note % 12
    subq.l #1,%d2
    move.l %d2,-(%sp)               | octave
    lea NAMES(%pc),%a0
    add.l %d1,%d1
    add.l %d1,%d1
    move.l (%a0,%d1.l),-(%sp)       | name
    pea STRFMT(%pc)
.Ltd3:
    pea -1.w                        | flags (as stock callers)
    pea 1.w                         | y: rows 1..5
    pea 1.w                         | x
    pea FONT
    move.l %a2,-(%sp)
    jsr TEXT
    move.l TNOTE,%d0
    bpl .Ltd5
    lea 24(%sp),%sp
    bra .Ltd6
.Ltd5:
    lea 40(%sp),%sp
.Ltd6:
    movem.l (%sp),%d2-%d3/%a2
    lea 12(%sp),%sp
    rts

    .balign 4
TRT:
    .long 65536, 69433, 73562, 77936, 82570, 87480, 92682, 98193, 104032, 110218, 116772, 123715
NAMES:
    .long NC, NCS, ND, NDS, NE, NF, NFS, NG, NGS, NA, NAS, NB
STRFMT:
    .asciz "%s%d %c%d"
STRNONE:
    .asciz "--"
NC:  .asciz "C"
NCS: .asciz "C#"
ND:  .asciz "D"
NDS: .asciz "D#"
NE:  .asciz "E"
NF:  .asciz "F"
NFS: .asciz "F#"
NG:  .asciz "G"
NGS: .asciz "G#"
NA:  .asciz "A"
NAS: .asciz "A#"
NB:  .asciz "B"
