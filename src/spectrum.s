| Spectrum page for the three-dots utility slot (DT1_8_POLY_OSC, page "spectrum"). GNU as -mcpu=5475.
| Linked at 0x400aaa86 (old song-edit knob handler + LED routine, 1708 B, unreachable since v3p).
| Integer model: tests/spec_model.py (bit-exact). Tables: bin/spec_tables.inc (tools/gen_spec_tables.py).
|  SCAP(out)  audio ISR, from the page TAP: while SREQ, append 32 frames of clamp((L+R)>>9) to the capture
|             buffer; at 1024 samples SREQ=0, SRDY=1. All registers preserved.
|  SPEC(bmp)  UI, from DRAW in waveform position: allocate 6 KB once; when SRDY: FFT 1024 of the capture
|             (columns >= CSPLIT) and FFT 512 of the tuner's 3 kHz ring (columns < CSPLIT), column heights
|             0..63 (60 dB log), falling peaks; then request the next capture. Draw 128 columns of bars.

    .set NEWOP,   0x400d4180
    .set VLINE,   0x400c1040
    .set TRING,   0x400aead0        | tuner 3 kHz ring, 512 x int16
    .set TIDX,    0x400aeab4
    .set FULLA,   0x400ae28c
    .set PYMAX,   0x400aeaa8
    .set SREQ,    0x400aeed0        | spectrum data (reclaimed song-popup space, after the tuner ring)
    .set SRDY,    SREQ+4
    .set SCNT,    SREQ+8
    .set SPTR,    SREQ+12           | capture buffer: 1024 x int16
    .set SWORK,   SREQ+16           | FFT: re[1024] int16, then im[1024] int16
    .set COLH,    0x400aeee8        | 128 x byte, 0..63
    .set PK,      COLH+128
    .set NCOL,    128
    .set L0,      48
    .set LRANGE,  160
    .set HMAX,    63

    .text
| ------------------------------------------------------------------ SCAP (ISR)
SCAP:
    tst.l SREQ
    beq .Lsc9
    tst.l SPTR
    beq .Lsc9
    lea -24(%sp),%sp
    movem.l %d0-%d3/%a0-%a1,(%sp)
    move.l 28(%sp),%a0              | out buffer: 32 frames x (L, R)
    move.l SPTR,%a1
    move.l SCNT,%d3
    moveq #32,%d2
.Lsc1:
    move.l (%a0)+,%d0
    add.l (%a0)+,%d0
    asr.l #8,%d0
    asr.l #1,%d0
    cmpi.l #32767,%d0
    ble .Lsc4
    move.l #32767,%d0
.Lsc4:
    cmpi.l #-32767,%d0
    bge .Lsc5
    move.l #-32767,%d0
.Lsc5:
    move.w %d0,(%a1,%d3.l*2)
    addq.l #1,%d3
    cmpi.l #1024,%d3
    bcs .Lsc2
    clr.l SREQ
    moveq #1,%d0
    move.l %d0,SRDY
    bra .Lsc3
.Lsc2:
    subq.l #1,%d2
    bne .Lsc1
.Lsc3:
    move.l %d3,SCNT
    movem.l (%sp),%d0-%d3/%a0-%a1
    lea 24(%sp),%sp
.Lsc9:
    rts

| ------------------------------------------------------------------ SPEC(bmp) (UI)
SPEC:
    lea -44(%sp),%sp
    movem.l %d2-%d7/%a2-%a6,(%sp)
    move.l 48(%sp),%a2              | bitmap
    move.l SPTR,%d0
    bne .Lsp1
    pea 6144.w
    jsr NEWOP
    addq.l #4,%sp
    tst.l %d0
    beq .Lspout
    move.l %d0,%d1
    addi.l #2048,%d1
    move.l %d1,SWORK
    clr.l SCNT
    clr.l SRDY
    move.l %d0,SPTR
    moveq #1,%d0
    move.l %d0,SREQ                 | start the first capture
.Lsp1:
    tst.l SRDY
    beq .Lsp2
    bsr .Lana
    move.l 48(%sp),%a2              | bitmap (the FFT used a2)
    clr.l SCNT
    clr.l SRDY
    moveq #1,%d0
    move.l %d0,SREQ                 | next capture
.Lsp2:
    moveq #8,%d6                    | base row (normal: above tuner / boxes)
    moveq #44,%d7                   | bar height range
    tst.l FULLA
    beq .Lsp3
    moveq #0,%d6
    moveq #63,%d7
.Lsp3:
    lea COLH,%a3
    lea PK,%a4
    lea VLINE,%a5
    moveq #0,%d5                    | column
.Ldc:
    clr.l -(%sp)                    | clear rows 0..PYMAX
    move.l PYMAX,-(%sp)
    clr.l -(%sp)
    move.l %d5,-(%sp)
    move.l %a2,-(%sp)
    jsr (%a5)
    lea 20(%sp),%sp
    moveq #0,%d0
    move.b (%a3,%d5.l),%d0
    mulu.l %d7,%d0
    moveq #HMAX,%d1
    divu.l %d1,%d0
    move.l %d0,%d4                  | bar height
    ble .Ldn1
    pea 1.w
    move.l %d4,%d0
    add.l %d6,%d0
    move.l %d0,-(%sp)
    move.l %d6,-(%sp)
    move.l %d5,-(%sp)
    move.l %a2,-(%sp)
    jsr (%a5)
    lea 20(%sp),%sp
.Ldn1:
    moveq #0,%d0
    move.b (%a4,%d5.l),%d0
    mulu.l %d7,%d0
    moveq #HMAX,%d1
    divu.l %d1,%d0                  | peak height
    cmp.l %d4,%d0
    ble .Ldn2
    add.l %d6,%d0
    pea 1.w
    move.l %d0,-(%sp)
    move.l %d0,-(%sp)
    move.l %d5,-(%sp)
    move.l %a2,-(%sp)
    jsr (%a5)
    lea 20(%sp),%sp
.Ldn2:
    addq.l #1,%d5
    cmpi.l #NCOL,%d5
    blt .Ldc
    tst.l FULLA
    bne .Lspout
    lea MARKT,%a3                   | 100 Hz / 1 kHz / 10 kHz ticks on row 7
    moveq #3,%d5
.Ldm:
    moveq #0,%d0
    move.b (%a3)+,%d0
    pea 1.w
    pea 7.w
    pea 7.w
    move.l %d0,-(%sp)
    move.l %a2,-(%sp)
    jsr (%a5)
    lea 20(%sp),%sp
    subq.l #1,%d5
    bne .Ldm
.Lspout:
    movem.l (%sp),%d2-%d7/%a2-%a6
    lea 44(%sp),%sp
    rts

| .Lana: both bands -> COLH, then peaks. Uses d0-d7/a0-a6 freely (SPEC saved them).
.Lana:
    move.l SPTR,%a0
    move.l #1024,%d0
    moveq #10,%d1
    bsr .Lfft
    moveq #CSPLIT,%d0
    move.l #NCOL,%d1
    bsr .Lhts
    move.l SPTR,%a0                 | low band: latest 512 samples of the 3 kHz ring
    lea TRING,%a1
    move.l TIDX,%d2
    subi.l #512,%d2
    moveq #0,%d3
.La1:
    move.l %d2,%d0
    add.l %d3,%d0
    andi.l #511,%d0
    move.w (%a1,%d0.l*2),(%a0)+
    addq.l #1,%d3
    cmpi.l #512,%d3
    blt .La1
    move.l SPTR,%a0
    move.l #512,%d0
    moveq #9,%d1
    bsr .Lfft
    moveq #0,%d0
    moveq #CSPLIT,%d1
    bsr .Lhts
    lea COLH,%a0                    | peaks: pk = max(pk - 1, h)
    lea PK,%a1
    moveq #0,%d3
.La2:
    moveq #0,%d0
    move.b (%a1,%d3.l),%d0
    subq.l #1,%d0
    moveq #0,%d1
    move.b (%a0,%d3.l),%d1
    cmp.l %d0,%d1
    ble .La3
    move.l %d1,%d0
.La3:
    move.b %d0,(%a1,%d3.l)
    addq.l #1,%d3
    cmpi.l #NCOL,%d3
    blt .La2
    rts

| .Lfft: a0 = int16 source, d0 = n (512/1024), d1 = log2 n. Result in SWORK re/im.
    .set FC,   0                    | locals
    .set FS,   2
    .set FJ,   4
    .set FN,   8
.Lfft:
    lea -12(%sp),%sp
    move.l %d0,FN(%sp)
    move.l SWORK,%a3                | re
    lea 2048(%a3),%a4               | im
    moveq #10,%d7
    sub.l %d1,%d7                   | tsh = 10 - lg
    move.l %d1,%a5                  | lg
    moveq #0,%d2                    | i
.Lw1:                               | window + bit reversal
    move.l %d2,%d0
    lsl.l %d7,%d0
    bsr .Lcos
    move.l #32767,%d3
    sub.l %d0,%d3
    asr.l #1,%d3                    | Hann, Q15
    move.w (%a0)+,%d4
    ext.l %d4
    muls.w %d3,%d4
    asr.l #8,%d4
    asr.l #7,%d4                    | windowed sample
    moveq #0,%d5                    | r = bitrev(i)
    move.l %d2,%d6
    move.l %a5,%d1
.Lw2:
    lsl.l #1,%d5
    move.l %d6,%d0
    andi.l #1,%d0
    or.l %d0,%d5
    lsr.l #1,%d6
    subq.l #1,%d1
    bne .Lw2
    move.w %d4,(%a3,%d5.l*2)
    clr.w (%a4,%d5.l*2)
    addq.l #1,%d2
    cmp.l FN(%sp),%d2
    blt .Lw1
    move.l FN(%sp),%d0
    add.l %d0,%d0
    move.l %a3,%a6
    adda.l %d0,%a6                  | end of re[]
    moveq #2,%d3                    | size (elements) = byte offset of the partner (half*2)
.Lst:
    move.l %d3,%d2
    add.l %d2,%d2                   | stride in bytes (size*2)
    clr.l FJ(%sp)                   | j
.Lj:
    move.l FJ(%sp),%d0
    move.l #1024,%d1
    divu.l %d3,%d1                  | step = 1024 / size
    mulu.l %d1,%d0                  | j * step
    move.l %d0,-(%sp)
    bsr .Lcos
    move.w %d0,FC+4(%sp)
    move.l (%sp)+,%d0
    bsr .Lsin
    move.w %d0,FS(%sp)
    move.l FJ(%sp),%d0
    add.l %d0,%d0
    lea (%a3,%d0.l),%a1             | &re[j]
    lea (%a4,%d0.l),%a2             | &im[j]
.Lbk:
    move.w (%a1,%d3.l),%d0          | xr = re[k + half]
    ext.l %d0
    move.w (%a2,%d3.l),%d1          | xi
    ext.l %d1
    move.l %d0,%d4
    muls.w FC(%sp),%d4
    move.l %d1,%d5
    muls.w FS(%sp),%d5
    add.l %d5,%d4
    asr.l #8,%d4
    asr.l #7,%d4                    | tr = (c*xr + s*xi) >> 15
    muls.w FC(%sp),%d1
    muls.w FS(%sp),%d0
    sub.l %d0,%d1
    asr.l #8,%d1
    asr.l #7,%d1                    | ti = (c*xi - s*xr) >> 15
    move.w (%a1),%d0
    ext.l %d0
    move.l %d0,%d5
    add.l %d4,%d0
    asr.l #1,%d0
    move.w %d0,(%a1)
    sub.l %d4,%d5
    asr.l #1,%d5
    move.w %d5,(%a1,%d3.l)
    move.w (%a2),%d0
    ext.l %d0
    move.l %d0,%d5
    add.l %d1,%d0
    asr.l #1,%d0
    move.w %d0,(%a2)
    sub.l %d1,%d5
    asr.l #1,%d5
    move.w %d5,(%a2,%d3.l)
    adda.l %d2,%a1
    adda.l %d2,%a2
    cmpa.l %a6,%a1
    bcs .Lbk
    move.l FJ(%sp),%d0
    addq.l #1,%d0
    move.l %d0,FJ(%sp)
    move.l %d3,%d1
    lsr.l #1,%d1                    | half (elements)
    cmp.l %d1,%d0
    blt .Lj
    move.l %d2,%d3                  | next size
    cmp.l FN(%sp),%d3
    ble .Lst
    lea 12(%sp),%sp
    rts

| .Lsin / .Lcos: d0 = index (mod 1024) -> d0 = Q15 value. Preserves all other registers.
.Lcos:
    addi.l #256,%d0
.Lsin:
    move.l %d1,-(%sp)
    move.l %a0,-(%sp)
    andi.l #1023,%d0
    move.l %d0,%d1
    lsr.l #8,%d1                    | quadrant
    andi.l #255,%d0
    btst #0,%d1
    beq .Ls1
    neg.l %d0
    addi.l #256,%d0                 | 256 - r
.Ls1:
    lea SINT,%a0
    move.w (%a0,%d0.l*2),%d0
    ext.l %d0
    btst #1,%d1
    beq .Ls2
    neg.l %d0
.Ls2:
    move.l (%sp)+,%a0
    move.l (%sp)+,%d1
    rts

| .Lhts: columns d0 .. d1-1 from the current re/im -> COLH
.Lhts:
    move.l %d0,%d6
    move.l %d1,%d7
    move.l SWORK,%a3
    lea 2048(%a3),%a4
.Lh1:
    lea COLT,%a0
    move.l %d6,%d0
    moveq #0,%d2
    move.w (%a0,%d0.l*2),%d2
    move.l %d2,%d3
    andi.l #1023,%d2                | lo
    moveq #10,%d0
    lsr.l %d0,%d3                   | count
    moveq #0,%d4                    | max magnitude
.Lh2:
    move.w (%a3,%d2.l*2),%d0
    ext.l %d0
    bpl .Lh3
    neg.l %d0
.Lh3:
    move.w (%a4,%d2.l*2),%d1
    ext.l %d1
    bpl .Lh4
    neg.l %d1
.Lh4:
    cmp.l %d1,%d0
    bge .Lh5
    move.l %d0,%d5
    move.l %d1,%d0
    move.l %d5,%d1
.Lh5:                               | d0 = max, d1 = min
    asr.l #1,%d1
    add.l %d1,%d0
    cmp.l %d4,%d0
    ble .Lh6
    move.l %d0,%d4
.Lh6:
    addq.l #1,%d2
    subq.l #1,%d3
    bne .Lh2
    moveq #0,%d0                    | log2 * 16
    tst.l %d4
    beq .Lh9
    move.l %d4,%d5
    moveq #31,%d1                   | p = msb position
.Lhm:
    tst.l %d5
    bmi .Lhn
    lsl.l #1,%d5
    subq.l #1,%d1
    bra .Lhm
.Lhn:
    cmpi.l #4,%d1
    blt .Lh7
    move.l %d4,%d0
    move.l %d1,%d5
    subq.l #4,%d5
    lsr.l %d5,%d0
    bra .Lh8
.Lh7:
    move.l %d4,%d0
    moveq #4,%d5
    sub.l %d1,%d5
    lsl.l %d5,%d0
.Lh8:
    andi.l #15,%d0
    lea LTT,%a0
    moveq #0,%d5
    move.b (%a0,%d0.l),%d5
    move.l %d1,%d0
    lsl.l #4,%d0
    add.l %d5,%d0
.Lh9:
    subi.l #L0,%d0
    moveq #HMAX,%d1
    muls.l %d1,%d0
    move.l #LRANGE,%d1
    divs.l %d1,%d0
    tst.l %d0
    bpl .Lh10
    moveq #0,%d0
.Lh10:
    cmpi.l #HMAX,%d0
    ble .Lh11
    moveq #HMAX,%d0
.Lh11:
    lea COLH,%a0
    move.b %d0,(%a0,%d6.l)
    addq.l #1,%d6
    cmp.l %d7,%d6
    blt .Lh1
    rts

    .include "spec_tables.inc"
