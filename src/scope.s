| Live oscilloscope for OS 1.53 (POLY v3o = v3n + tuner, polarity fix, key 6 handled here).
| NOTE [v3o]: the physical LCD is vertically flipped relative to bitmap rows: row 0 = bottom, row 63 = top
| (the stock font renders upright only that way; the main-screen info line (rows 53..63) is the TOP bar). Assemble: m68k-linux-gnu-as -mcpu=5475
| Code in the body of SongEditView::drawView (0x400abe9c, padded to 1616 B so lock.s stays at 0x400ac4ec).
| Ring + state in the dead SongModePopup code (0x400ae26e..0x400af23e, never instantiated since v3d).
|  DRAW  (vtable slot 4): main screen underneath, then rows 0..52:
|        MODE 0 = waveform (as v3f), MODE 1 = stereo X-Y (goniometer: mono = vertical line,
|        left-only = "\" diagonal, right-only = "/", out of phase = horizontal), then POLY voice dots.
|  TICK  (vtable slot 11): original tick, then invalidate.
|  TAP   (audio ISR, 0x4007814a): original output writer, then appends 8 x {mid, side} per block.
|  KEY   (vtable slot 2): key 5 press: waveform -> X-Y -> close. key 6 -> original. Others -> main screen.

    .include "tuner_syms.inc"
.ifdef SPECTRUM
    .include "spec_syms.inc"
.endif
.ifdef ALLVIEWS
    .set USEWAVE, 1
.else
.ifndef SPECTRUM
    .set USEWAVE, 1
.endif
.endif
    .set KEYNOT0,  0x400c31f0      | event flags: !bit0 (release)
    .set VLINE,    0x400c1040      | vline(bmp, x, y0, y1, color): color>0 set, 0 clear
    .set OUTWRITE, 0x40071c20
    .set OLDTICK,  0x400aa8e2
    .set INVAL,    0x400c9812
    .set KEYID,    0x400c317c
    .set KEYPRESS, 0x400c3220
    .set KEYBIT1,  0x400c3210      | event flags bit 1 (stock NO handler: set -> do not close)
    .set MS_PTR,   0x421f9b50
    .set MS_CTL,   0x421f9b54
    .set Q_PTR,    0x4199dc44      | kit params base (machine of track t at Q+0x9e+t*0xa2)
    .set VSTATE,   0x400b907c      | cable.s STATE: vnote[8] (0xff = free)
    .set DATA,     0x400ae280
    .set IDXA,     DATA            | write index (samples)
    .set MODEA,    DATA+4          | 0 wave, 1 X-Y
    .set FULLA,    DATA+12         | 0 normal (info line + dots), 1 fullscreen (whole 128x64)
    .set LASTV,    DATA+8          | view object seen by the last DRAW (new view -> MODE 0)
    .set RING,     DATA+16         | 512 x {int16 mid, int16 side}
    .set TRIGCNT,  DATA+16+2048    | byte[8]: voices started by the audio ISR (TRIG hook), wraps
    .set LASTCNT,  TRIGCNT+8       | byte[8]: TRIGCNT seen by the last DRAW
    .set HOLD,     TRIGCNT+16      | byte[8]: frames left of the trig flash
    .set FLASHN,   4               | flash length in scope frames
    .set PYMAX,    TRIGCNT+24      | per-frame plot geometry (set at the top of DRAW)
    .set PYMID,    TRIGCNT+28
    .set PNAMP,    TRIGCNT+32      | amplitude (+: bigger row = physically up)
    .set RINGN,    512
    .set WIN,      128
    .set SEARCH,   256
    .set MARGIN,   16
    .set XYN,      256
    .set YMAX,     52              | normal: rows 0..52 (53..63 = main screen info line)
    .set YMID,     26
    .set YAMP,     24
    .set FYMAX,    63              | fullscreen: rows 0..63
    .set FYMID,    32
    .set FYAMP,    30
    .set XMID,     64
    .set DOTX,     80              | voice dot of track t at x = DOTX + 6t, rows 0..3

    .text
| ------------------------------------------------------------------ DRAW (must be first)
DRAW:
    lea -44(%sp),%sp
    movem.l %d2-%d7/%a2-%a6,(%sp)
    move.l 52(%sp),%a2              | bitmap
    move.l 48(%sp),%d0              | this
    cmp.l LASTV,%d0
    beq .Lsame
    move.l %d0,LASTV
    clr.l MODEA
    clr.l FULLA
.Lsame:
    tst.l FULLA
    bne .Lgfull
    moveq #YMAX,%d0
    move.l %d0,PYMAX
    moveq #YMID,%d0
    move.l %d0,PYMID
    moveq #YAMP,%d0
    move.l %d0,PNAMP
    bra .Lgdone
.Lgfull:
    moveq #FYMAX,%d0
    move.l %d0,PYMAX
    moveq #FYMID,%d0
    move.l %d0,PYMID
    moveq #FYAMP,%d0
    move.l %d0,PNAMP
    bra .Lnoms                      | fullscreen: no main screen underneath
.Lgdone:
    move.l MS_PTR,%d0
    beq .Lnoms
    tst.l MS_CTL
    beq .Lnoms
    move.l %d0,%a0
    move.l %a2,-(%sp)
    move.l %a0,-(%sp)
    move.l (%a0),%a0
    move.l 16(%a0),%a0              | vtable slot 4 = drawView
    jsr (%a0)
    addq.l #8,%sp
.Lnoms:
    lea RING,%a3
    lea VLINE,%a4
.ifdef ALLVIEWS
| all three views: MODE 0 waveform, 2 spectrum, 1 X-Y
    move.l MODEA,%d0
    beq .Lwav0
    cmpi.l #2,%d0
    bne .Lxy
| ================= spectrum (page "spectrum": src/spectrum.s) =================
    move.l %a2,-(%sp)
    jsr SPEC
    addq.l #4,%sp
    bra .Ldots
.Lwav0:
.else
    tst.l MODEA
    bne .Lxy
.endif
.ifdef USEWAVE
| ================= waveform =================
    move.l IDXA,%d7
    subi.l #MARGIN+WIN,%d7
    move.l %d7,%d6
    move.l #SEARCH,%d5
.Ltrg:
    move.l %d6,%d0
    andi.l #RINGN-1,%d0
    lsl.l #2,%d0
    move.w (%a3,%d0.l),%d1          | s[i]
    ext.l %d1
    move.l %d6,%d0
    subq.l #1,%d0
    andi.l #RINGN-1,%d0
    lsl.l #2,%d0
    move.w (%a3,%d0.l),%d2          | s[i-1]
    ext.l %d2
    tst.l %d2
    bpl .Lnt
    tst.l %d1
    bmi .Lnt
    move.l %d6,%d7
    bra .Ltdone
.Lnt:
    subq.l #1,%d6
    subq.l #1,%d5
    bne .Ltrg
.Ltdone:
    move.l #512,%d4
    moveq #0,%d5
.Lpk:
    move.l %d7,%d0
    add.l %d5,%d0
    andi.l #RINGN-1,%d0
    lsl.l #2,%d0
    move.w (%a3,%d0.l),%d1
    ext.l %d1
    bpl .Lpos
    neg.l %d1
.Lpos:
    cmp.l %d4,%d1
    ble .Lpn
    move.l %d1,%d4
.Lpn:
    addq.l #1,%d5
    cmpi.l #WIN,%d5
    blt .Lpk
    moveq #-1,%d6
    moveq #0,%d5
.Lpl:
    clr.l -(%sp)
    move.l PYMAX,-(%sp)
    clr.l -(%sp)
    move.l %d5,-(%sp)
    move.l %a2,-(%sp)
    jsr (%a4)
    lea 20(%sp),%sp
    move.l %d7,%d0
    add.l %d5,%d0
    andi.l #RINGN-1,%d0
    lsl.l #2,%d0
    move.w (%a3,%d0.l),%d1
    ext.l %d1
    move.l PNAMP,%d0
    muls.l %d0,%d1
    divs.l %d4,%d1
    add.l PYMID,%d1
    bpl .Lc0
    moveq #0,%d1
.Lc0:
    cmp.l PYMAX,%d1
    ble .Lc1
    move.l PYMAX,%d1
.Lc1:
    move.l %d6,%d2
    bpl .Lhp
    move.l %d1,%d2
.Lhp:
    move.l %d1,%d6
    pea 1.w
    move.l %d1,-(%sp)
    move.l %d2,-(%sp)
    move.l %d5,-(%sp)
    move.l %a2,-(%sp)
    jsr (%a4)
    lea 20(%sp),%sp
    addq.l #1,%d5
    cmpi.l #WIN,%d5
    blt .Lpl
.else
| ================= spectrum (page "spectrum": src/spectrum.s) =================
    move.l %a2,-(%sp)
    jsr SPEC
    addq.l #4,%sp
.endif
    bra .Ldots
| ================= X-Y (goniometer) =================
.Lxy:
    moveq #0,%d5
.Lxc:
    move.l %d5,%d0
    moveq #0,%d1
    move.l PYMAX,%d2
    moveq #0,%d3
    bsr .Lvl                        | clear column
    addq.l #1,%d5
    cmpi.l #128,%d5
    blt .Lxc
    move.l IDXA,%d7
    subi.l #XYN,%d7                 | last XYN samples
    move.l #512,%d4                 | peak over |mid|, |side| (min 512)
    moveq #0,%d5
.Lxp:
    move.l %d7,%d0
    add.l %d5,%d0
    andi.l #RINGN-1,%d0
    lsl.l #2,%d0
    move.w (%a3,%d0.l),%d1
    ext.l %d1
    bpl .Lxp1
    neg.l %d1
.Lxp1:
    cmp.l %d4,%d1
    ble .Lxp2
    move.l %d1,%d4
.Lxp2:
    move.w 2(%a3,%d0.l),%d1
    ext.l %d1
    bpl .Lxp3
    neg.l %d1
.Lxp3:
    cmp.l %d4,%d1
    ble .Lxp4
    move.l %d1,%d4
.Lxp4:
    addq.l #1,%d5
    cmpi.l #XYN,%d5
    blt .Lxp
    moveq #0,%d5
.Lxl:
    move.l %d7,%d0
    add.l %d5,%d0
    andi.l #RINGN-1,%d0
    lsl.l #2,%d0
    move.w (%a3,%d0.l),%d1          | mid
    ext.l %d1
    move.w 2(%a3,%d0.l),%d6         | side = L-R
    ext.l %d6
    move.l PNAMP,%d0
    muls.l %d0,%d1
    divs.l %d4,%d1
    add.l PYMID,%d1                 | y = YMID + mid*YAMP/peak (physically up)
    move.l PNAMP,%d0
    neg.l %d0
    muls.l %d0,%d6
    divs.l %d4,%d6
    addi.l #XMID,%d6                | x = XMID - side*YAMP/peak (left-only = physical "\")
| clamp (the ring may move under us if this task is preempted for > 21 ms)
    tst.l %d1
    bpl .Lxc0
    moveq #0,%d1
.Lxc0:
    cmp.l PYMAX,%d1
    ble .Lxc1
    move.l PYMAX,%d1
.Lxc1:
    tst.l %d6
    bpl .Lxc2
    moveq #0,%d6
.Lxc2:
    cmpi.l #127,%d6
    ble .Lxc3
    moveq #127,%d6
.Lxc3:
    move.l %d6,%d0
    move.l %d1,%d2
    moveq #1,%d3
    bsr .Lvl                        | dot
    addq.l #1,%d5
    cmpi.l #XYN,%d5
    blt .Lxl
| ================= track activity dots (all 8 audio tracks) =================
| Box of track t: 4x4 at x = DOTX+6t, rows 0..3 (1-px cleared border, rows 0..6 cleared).
| Filled = the track's voice was triggered in the last FLASHN frames (any machine, sequencer, live, POLY cable),
|          or (POLY track) a note is held on it (cable.s vnote[t] != 0xff). Outline = idle.
| POLY tracks get a 2-px marker under the box (row 5).
.Ldots:
    tst.l FULLA
    bne .Ldone                      | fullscreen: wave only
    jsr TUNE                        | tuner estimate (every 4th frame)
    move.l %a2,-(%sp)
    jsr TDRAW                       | tuner readout, physical lower left
    addq.l #4,%sp
    move.l Q_PTR,%d0
    beq .Ldq
    addi.l #0x9e,%d0                | machine byte of track 0
.Ldq:
    move.l %d0,%a3                  | 0 = no kit (no POLY info)
    lea VSTATE,%a5
    lea TRIGCNT,%a6
    moveq #0,%d7
.Ld:
    move.l %d7,%d6
    add.l %d6,%d6
    move.l %d6,%d0
    add.l %d6,%d6
    add.l %d0,%d6
    addi.l #DOTX,%d6                | x0
    moveq #-1,%d5
.Ldc:
    move.l %d6,%d0
    add.l %d5,%d0
    moveq #0,%d1
    moveq #6,%d2
    moveq #0,%d3
    bsr .Lvl                        | clear x0-1 .. x0+4, rows 0..6
    addq.l #1,%d5
    cmpi.l #5,%d5
    blt .Ldc
| d4 bit0 = active, bit1 = POLY
    moveq #0,%d4
    move.b (%a6,%d7.l),%d0          | trig count
    move.b 8(%a6,%d7.l),%d1         | last seen
    cmp.b %d1,%d0
    beq .Ldh
    move.b %d0,8(%a6,%d7.l)
    moveq #FLASHN,%d0
    move.b %d0,16(%a6,%d7.l)        | new trig -> flash
.Ldh:
    moveq #0,%d0
    move.b 16(%a6,%d7.l),%d0
    beq .Ldp
    subq.l #1,%d0
    move.b %d0,16(%a6,%d7.l)
    moveq #1,%d4
.Ldp:
    move.l %a3,%d0
    beq .Ldraw
    move.l %d7,%d0
    mulu.w #0xa2,%d0
    move.b (%a3,%d0.l),%d0
    cmpi.b #4,%d0
    bne .Ldraw
    addq.l #2,%d4                   | POLY
    moveq #0,%d0
    move.b (%a5,%d7.l),%d0
    cmpi.l #0xff,%d0
    beq .Ldraw
    moveq #3,%d4                    | POLY + held
.Ldraw:
    moveq #1,%d3
    btst #0,%d4
    beq .Lidle
    moveq #0,%d5
.Ldf:
    move.l %d6,%d0
    add.l %d5,%d0
    moveq #0,%d1
    moveq #3,%d2
    bsr .Lvl                        | filled
    addq.l #1,%d5
    cmpi.l #4,%d5
    blt .Ldf
    bra .Ldm
.Lidle:
    move.l %d6,%d0
    moveq #0,%d1
    moveq #3,%d2
    bsr .Lvl
    move.l %d6,%d0
    addq.l #3,%d0
    moveq #0,%d1
    moveq #3,%d2
    bsr .Lvl
    moveq #1,%d5
.Ldi:
    move.l %d6,%d0
    add.l %d5,%d0
    moveq #0,%d1
    moveq #0,%d2
    bsr .Lvl
    move.l %d6,%d0
    add.l %d5,%d0
    moveq #3,%d1
    moveq #3,%d2
    bsr .Lvl
    addq.l #1,%d5
    cmpi.l #3,%d5
    blt .Ldi
.Ldm:
    btst #1,%d4
    beq .Ldn
    moveq #1,%d5
.Ldk:
    move.l %d6,%d0
    add.l %d5,%d0
    moveq #5,%d1
    moveq #5,%d2
    bsr .Lvl                        | POLY marker
    addq.l #1,%d5
    cmpi.l #3,%d5
    blt .Ldk
.Ldn:
    addq.l #1,%d7
    cmpi.l #8,%d7
    blt .Ld
.Ldone:
    movem.l (%sp),%d2-%d7/%a2-%a6
    lea 44(%sp),%sp
    rts

| vline(a2 = bitmap, d0 = x, d1 = y0, d2 = y1, d3 = color) via a4; clobbers d0/d1/a0/a1
.Lvl:
    move.l %d3,-(%sp)
    move.l %d2,-(%sp)
    move.l %d1,-(%sp)
    move.l %d0,-(%sp)
    move.l %a2,-(%sp)
    jsr (%a4)
    lea 20(%sp),%sp
    rts

| ------------------------------------------------------------------ TICK (vtable slot 11)
TICK:
    move.l 4(%sp),-(%sp)
    jsr OLDTICK
    move.l %d0,(%sp)
    move.l 8(%sp),-(%sp)
    jsr INVAL
    addq.l #4,%sp
    move.l (%sp)+,%d0
    rts

| ------------------------------------------------------------------ TAP (audio ISR)
TAP:
    move.l 12(%sp),-(%sp)
    move.l 12(%sp),-(%sp)
    move.l 12(%sp),-(%sp)
    jsr OUTWRITE
    lea 12(%sp),%sp
    lea -36(%sp),%sp
    movem.l %d0-%d6/%a0-%a1,(%sp)   | preserve everything OUTWRITE returned
    move.l 40(%sp),%a0              | out buffer (32 frames x L,R)
    lea RING,%a1
    move.l IDXA,%d3
    moveq #8,%d4
.Ltp:
    moveq #0,%d2                    | mid  = sum(L+R)
    moveq #0,%d6                    | side = sum(L-R)
    moveq #4,%d1
.Ltf:
    move.l (%a0)+,%d0               | L
    move.l (%a0)+,%d5               | R
    add.l %d0,%d2
    add.l %d5,%d2
    add.l %d0,%d6
    sub.l %d5,%d6
    subq.l #1,%d1
    bne .Ltf
    move.l %d3,%d0
    andi.l #RINGN-1,%d0
    lsl.l #2,%d0
    move.l %d2,%d1
    bsr .Lsat
    move.w %d1,(%a1,%d0.l)
    move.l %d6,%d1
    bsr .Lsat
    move.w %d1,2(%a1,%d0.l)
    addq.l #1,%d3
    subq.l #1,%d4
    bne .Ltp
    move.l %d3,IDXA
    jsr TTAP                        | tuner: 3 kHz history (registers preserved)
.ifdef SPECTRUM
    move.l 40(%sp),-(%sp)           | out buffer
    jsr SCAP                        | spectrum capture (registers preserved)
    addq.l #4,%sp
.endif
    movem.l (%sp),%d0-%d6/%a0-%a1
    lea 36(%sp),%sp
    rts
| d1 = (d1 >> 11) clamped to int16
.Lsat:
    asr.l #8,%d1
    asr.l #3,%d1
    cmpi.l #32767,%d1
    ble .Ls1
    move.l #32767,%d1
.Ls1:
    cmpi.l #-32768,%d1
    bge .Ls2
    move.l #-32768,%d1
.Ls2:
    rts

.ifdef ALLVIEWS
| all-views build: TRIG lives in its own section, placed after the spectrum code (0x400ab072)
    .section .trigtext,"ax"
.endif
| ------------------------------------------------------------------ TRIG (audio ISR)
| Replaces "move.l d3,d2; not.l d2; and.l -76(fp),d2" at 0x40077d72 (8 bytes -> jsr TRIG + nop). 0x40077d72 is the
| merge point after the optional block 0x40077cf6..0x40077d71 (run only when 0x4199e130 != 0; v3k hooked inside it
| and so missed most sequencer trigs). Here d3 = final mask of voices 0..7 started in this block, on every pass.
| Counts starts per voice, then executes the three replaced instructions (same d2 and condition codes as stock;
| fp is the ISR frame, unchanged by jsr). d0/d1/a0 are saved; everything else untouched.
TRIG:
    tst.l %d3
    beq .Ltr9
    lea -12(%sp),%sp
    movem.l %d0-%d1/%a0,(%sp)
    lea TRIGCNT,%a0
    moveq #0,%d0
.Ltr1:
    btst %d0,%d3
    beq .Ltr2
    moveq #0,%d1
    move.b (%a0,%d0.l),%d1
    addq.l #1,%d1
    move.b %d1,(%a0,%d0.l)
.Ltr2:
    addq.l #1,%d0
    cmpi.l #8,%d0
    blt .Ltr1
    movem.l (%sp),%d0-%d1/%a0
    lea 12(%sp),%sp
.Ltr9:
    move.l %d3,%d2
    not.l %d2
    and.l -76(%fp),%d2
    rts

.ifdef ALLVIEWS
    .text
.endif
| ------------------------------------------------------------------ KEY (vtable slot 2 = consumeKeyEvent)
| Key ids [ConfirmWindow 0x400bfc9c: 12 = YES (confirm), 13 = NO (cancel)]. The view controller offers keys
| top-down and stops at the first view that returns true; false passes the key to the main screen.
|  id 5 (three dots) press: waveform -> X-Y; X-Y -> close. All id 5 events consumed.
|  id 12 (YES) without flag bit 1: press toggles fullscreen; other YES events consumed.
|  id 13 (NO)  without flag bit 1: press closes the scope; other NO events consumed.
|  YES/NO with flag bit 1: not consumed (main screen).
|  id 6 (SETTINGS): as stock (close on release), see below.
|  every other id: not consumed.
KEY:
    move.l 8(%sp),-(%sp)
    jsr KEYID
    addq.l #4,%sp
    cmpi.l #5,%d0
    beq .Lk5
    cmpi.l #12,%d0
    beq .Lkyes
    cmpi.l #13,%d0
    beq .Lkno
    cmpi.l #6,%d0
    bne .Lpass
| id 6 (SETTINGS), as the stock SongEditView handler did: flag bit 1 -> not consumed; release (!bit0) -> close,
| not consumed; otherwise consumed. (Old handler 0x400ac8f0 is now the tuner.)
    move.l 8(%sp),-(%sp)
    jsr KEYBIT1
    addq.l #4,%sp
    tst.b %d0
    bne .Lpass
    move.l 8(%sp),-(%sp)
    jsr KEYNOT0
    addq.l #4,%sp
    tst.b %d0
    beq .Lswal
    clr.l MODEA
    clr.l FULLA
    move.l 4(%sp),%a0
    move.l %a0,-(%sp)
    move.l (%a0),%a0
    move.l 40(%a0),%a0              | vtable slot 10 = close
    jsr (%a0)
    addq.l #4,%sp
    bra .Lpass
.Lkyes:
    bsr .Lkchk                      | d0: 0 = pass, 1 = press, 2 = swallow
    tst.l %d0
    beq .Lpass
    subq.l #1,%d0
    bne .Lswal
    moveq #1,%d0
    eor.l %d0,FULLA                 | toggle fullscreen
    bra .Lswal
.Lkno:
    bsr .Lkchk
    tst.l %d0
    beq .Lpass
    subq.l #1,%d0
    beq .Lclose
    bra .Lswal
| .Lkchk: event at 12(sp) (after bsr). d0 = 0 if flag bit 1 set, 1 on press edge, else 2
.Lkchk:
    move.l 12(%sp),-(%sp)
    jsr KEYBIT1
    addq.l #4,%sp
    tst.b %d0
    beq .Lkc1
    moveq #0,%d0
    rts
.Lkc1:
    move.l 12(%sp),-(%sp)
    jsr KEYPRESS
    addq.l #4,%sp
    tst.b %d0
    beq .Lkc2
    moveq #1,%d0
    rts
.Lkc2:
    moveq #2,%d0
    rts
.Lk5:
    move.l 8(%sp),-(%sp)
    jsr KEYPRESS
    addq.l #4,%sp
    tst.b %d0
    beq .Lswal
.ifdef ALLVIEWS
    move.l MODEA,%d0                | waveform (0) -> spectrum (2) -> X-Y (1) -> close
    beq .Lk5w
    cmpi.l #2,%d0
    bne .Lclose
    moveq #1,%d0
    move.l %d0,MODEA
    bra .Lswal
.Lk5w:
    moveq #2,%d0
    move.l %d0,MODEA
    bra .Lswal
.else
    tst.l MODEA
    bne .Lclose
    moveq #1,%d0
    move.l %d0,MODEA                | waveform -> X-Y
    bra .Lswal
.endif
.Lclose:
    clr.l MODEA
    clr.l FULLA
    move.l 4(%sp),%a0
    move.l %a0,-(%sp)
    move.l (%a0),%a0
    move.l 40(%a0),%a0              | vtable slot 10 = close
    jsr (%a0)
    addq.l #4,%sp
.Lswal:
    moveq #1,%d0
    rts
.Lpass:
    moveq #0,%d0                    | not consumed -> next view down (main screen)
    rts
