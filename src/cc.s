| POLY v3d: internal MIDI cable for CC. Entry-patched over 0x400e0b84 (MIDI task: append N bytes to the
| CC output buffer 0x421b5a22; only callers are the MIDI task's CC emitters, incl. the stop-time CC120).
| For a 3-byte control change on channel ch, every audio track 0..7 whose MIDI receive channel == ch and
| machine == POLY gets the CC exactly as if it had arrived on MIDI IN for that track
| (0x400d6a58(track, cc, value, 0, 0), the per-track call of the stock MIDI-in CC handler 0x400d4a90).
| CC 120-127 (channel mode, incl. the CC120 sent on stop) are not forwarded, so a stop can't loop back.
| The original function then runs unchanged, so the CC still goes out of MIDI OUT.
| Assemble: m68k-linux-gnu-as -mcpu=5475

    .set Q_PTR,     0x4199dc44
    .set RXCHAN,    0x4197b700
    .set TRACKCC,   0x400d6a58
    .set ORIG_CONT, 0x400e0b8a
    .set OUTLEN,    0x421b5a21

    .text
CCHOOK:
    lea -60(%sp),%sp
    movem.l %d0-%d7/%a0-%a6,(%sp)
    move.l 64(%sp),%d0              | len
    cmpi.l #3,%d0
    bne .Lout
    move.l 68(%sp),%a0              | bytes
    moveq #0,%d1
    move.b (%a0),%d1
    move.l %d1,%d0
    andi.l #0xf0,%d0
    cmpi.l #0xb0,%d0
    bne .Lout
    andi.l #0x0f,%d1
    move.l %d1,%d2                  | channel
    moveq #0,%d3
    move.b 1(%a0),%d3               | cc number
    cmpi.l #120,%d3                 | channel-mode messages (120-127, e.g. CC120 sent on STOP) are not forwarded
    bcc .Lout
    moveq #0,%d4
    move.b 2(%a0),%d4               | value
    move.l Q_PTR,%d0
    beq .Lout
    move.l %d0,%a2
    lea RXCHAN,%a3
    lea 0x9e(%a2),%a4               | machine byte of track 0
    lea TRACKCC,%a5
    moveq #0,%d7
.Lscan:
    move.l (%a3)+,%d0
    cmp.l %d2,%d0
    bne .Lnx
    move.b (%a4),%d0
    cmpi.b #4,%d0
    bne .Lnx
    clr.l -(%sp)
    clr.l -(%sp)
    move.l %d4,-(%sp)
    move.l %d3,-(%sp)
    move.l %d7,-(%sp)
    jsr (%a5)
    lea 20(%sp),%sp
.Lnx:
    lea 0xa2(%a4),%a4
    addq.l #1,%d7
    cmpi.l #8,%d7
    blt .Lscan
.Lout:
    movem.l (%sp),%d0-%d7/%a0-%a6
    lea 60(%sp),%sp
    mvz.b OUTLEN,%d1                | original first instruction of 0x400e0b84
    jmp ORIG_CONT
