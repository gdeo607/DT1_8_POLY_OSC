| Build B "internal MIDI cable" hook for OS 1.53 (POLY v3).
| Entry-patched over 0x400e0dda (MIDI task: append N bytes to MIDI-out buffer; only callers are the
| MIDI task's note-on/note-off emitters). Args: 4(sp)=len, 8(sp)=byte ptr.
| For a 3-byte note-on/note-off on channel ch, if audio tracks 0..7 exist whose MIDI receive channel
| (0x4197b700[t]) == ch AND machine == POLY (4), the note is also played internally on one of those
| tracks (voice rotation), with the CONTROL (lowest) track's sound as a sound lock. Then the original
| function runs unchanged, so the note still goes out of MIDI OUT.
| Live audio message layout mirrors 0x40076b3c (stock live play of an audio track).
| Assemble: m68k-linux-gnu-as -mcpu=5475

    .set Q_PTR,     0x4199dc44      | current kit params base (sequencer arg3; block(t) = Q+0x20+t*0xa2)
    .set P_PTR,     0x4199dc38      | sequencer/pattern object
    .set RXCHAN,    0x4197b700      | long[16] MIDI receive channel per track (0..15)
    .set PAT_BASE,  0x409bac18      | pattern array (as used by liveNoteOn 0x400d53dc)
    .set MSG_ALLOC, 0x400ee036
    .set MSG_POST,  0x400ee296
    .set ORIG_CONT, 0x400e0de0
    .set OUTLEN,    0x421b5620

    .text
CABLE:
    lea -60(%sp),%sp
    movem.l %d0-%d7/%a0-%a6,(%sp)
    move.l 64(%sp),%d0              | len
    cmpi.l #3,%d0
    bne .Lout
    move.l 68(%sp),%a0              | bytes
    moveq #0,%d1
    move.b (%a0),%d1                | status
    move.l %d1,%d0
    andi.l #0xe0,%d0
    cmpi.l #0x80,%d0                | 0x80..0x9f
    bne .Lout
    moveq #0,%d3
    move.b 1(%a0),%d3               | note
    moveq #0,%d4
    move.b 2(%a0),%d4               | velocity
    btst #4,%d1
    bne .Lison
    moveq #0,%d4                    | 0x8n = note off
.Lison:
    andi.l #0x0f,%d1
    move.l %d1,%d2                  | d2 = channel
    move.l Q_PTR,%d0
    beq .Lout
    move.l %d0,%a2                  | a2 = Q
| ---- POLY group on this channel: d5 = mask, d6 = control (lowest) ----
    moveq #0,%d5
    moveq #-1,%d6
    moveq #0,%d7
    lea RXCHAN,%a3
    lea 0x9e(%a2),%a4               | machine byte of track 0
.Lscan:
    move.l (%a3)+,%d0
    cmp.l %d2,%d0
    bne .Lsnx
    move.b (%a4),%d0
    cmpi.b #4,%d0
    bne .Lsnx
    bset %d7,%d5
    tst.l %d6
    bpl .Lsnx
    move.l %d7,%d6
.Lsnx:
    lea 0xa2(%a4),%a4
    addq.l #1,%d7
    cmpi.l #8,%d7
    blt .Lscan
    tst.l %d5
    beq .Lout
    lea STATE(%pc),%a5                   | vnote[8] @0, vch[8] @8, age[8] @16, clock @48
    tst.l %d4
    beq .Loff
| ---- note on ----
    move.l %d3,%d0
    subi.l #12,%d0
    cmpi.l #72,%d0                  | stock plays audio tracks only for notes 12..84
    bhi .Lout
    moveq #-1,%d1                   | best key (unsigned)
    moveq #-1,%d7                   | best voice
    moveq #0,%d0
.Lvl:
    btst %d0,%d5
    beq .Lvn
    move.l %d0,%a0
    add.l %d0,%a0
    add.l %d0,%a0
    add.l %d0,%a0                   | a0 = 4*t
    move.l 16(%a5,%a0.l),%a1        | key = age
    tst.b (%a5,%d0.l)
    bmi .Lfree                      | 0xff = free
    adda.l #0x80000000,%a1          | busy voices only when nothing is free
.Lfree:
    cmpa.l %d1,%a1
    bcc .Lvn
    move.l %a1,%d1
    move.l %d0,%d7
.Lvn:
    addq.l #1,%d0
    cmpi.l #8,%d0
    blt .Lvl
    tst.l %d7
    bmi .Lout
    move.l 48(%a5),%d0
    addq.l #1,%d0
    move.l %d0,48(%a5)
    move.l %d7,%d1
    lsl.l #2,%d1
    lea 16(%a5,%d1.l),%a0
    move.l %d0,(%a0)                | age[v] = ++clock
    move.b %d3,(%a5,%d7.l)          | vnote[v] = note
    move.b %d2,8(%a5,%d7.l)         | vch[v] = channel
    moveq #1,%d0
    bsr .Lsend
    bra .Lout
| ---- note off: release the voice holding (channel, note) ----
.Loff:
    moveq #0,%d7
.Lol:
    btst %d7,%d5
    beq .Lon
    moveq #0,%d0
    move.b (%a5,%d7.l),%d0
    cmp.l %d3,%d0
    bne .Lon
    move.b 8(%a5,%d7.l),%d0
    cmp.l %d2,%d0
    bne .Lon
    moveq #-1,%d0
    move.b %d0,(%a5,%d7.l)          | free
    moveq #2,%d0
    bsr .Lsend
    bra .Lout
.Lon:
    addq.l #1,%d7
    cmpi.l #8,%d7
    blt .Lol
.Lout:
    movem.l (%sp),%d0-%d7/%a0-%a6
    lea 60(%sp),%sp
    mvz.b OUTLEN,%d1                | original first instruction of 0x400e0dda
    jmp ORIG_CONT

| send: d0 = kind (1 on, 2 off), d7 = voice, d3 = note, d4 = velocity, d6 = control, a2 = Q
.Lsend:
    move.l %d0,%a3
    jsr MSG_ALLOC
    tst.l %d0
    beq .Lsret
    move.l %d0,%a0
    moveq #2,%d1
    move.l %d1,12(%a0)              | source id 2 = live
    move.l %a3,4(%a0)               | 1 = note on, 2 = note off
    move.l %d7,8(%a0)               | voice
    move.l %d4,%d1
    lsl.l #8,%d1
    move.w %d1,20(%a0)              | velocity 8.8
    move.l %d3,24(%a0)              | note
    clr.l 40(%a0)                   | +0x28 params ptr (none)
    clr.l 68(%a0)                   | +0x44 p-locks (none)
    clr.l 48(%a0)                   | +0x30 length (0 = until note off)
    move.l %a3,%d1
    cmpi.l #1,%d1
    bne .Lsoff
    move.l #0xa2,%d1
    muls.l %d6,%d1
    add.l %a2,%d1
    addi.l #0x20,%d1
    move.l %d1,44(%a0)              | +0x2c sound lock = control track's params block
    move.l P_PTR,%a1
    adda.l #0x1ec64,%a1
    move.l (%a1),%d1                | current pattern index (as 0x4006f40c)
    move.l #0x1ec68,%d0
    muls.l %d0,%d1
    addi.l #PAT_BASE,%d1
    move.l #0x38f,%d0
    muls.l %d6,%d0
    add.l %d0,%d1
    addi.l #0x382,%d1
    move.l %d1,%a1
    mvs.w (%a1),%d1                 | control track's trig-flag word (as liveNoteOn)
    ori.l #0x10001,%d1
    move.l %d1,36(%a0)              | +0x24 flags
    bra .Lpost
.Lsoff:
    clr.l 44(%a0)
    clr.l 36(%a0)
.Lpost:
    move.l %a0,-(%sp)
    jsr MSG_POST
    addq.l #4,%sp
.Lsret:
    rts

    .balign 4
STATE:
    .byte 0xff,0xff,0xff,0xff,0xff,0xff,0xff,0xff   | vnote
    .byte 0xff,0xff,0xff,0xff,0xff,0xff,0xff,0xff   | vch
    .long 0,0,0,0,0,0,0,0                           | age
    .long 0                                         | clock
