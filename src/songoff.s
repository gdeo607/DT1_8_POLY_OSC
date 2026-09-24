| POLY v3g: song mode can never become active (value 1). Chain mode (2) and pattern mode (0) unchanged.
| Project settings field +0x28 = mode 0 pattern, 1 SONG, 2 chain (setter 0x4001d842, getter 0x4001d8a8;
| PatternAndBankSelectView sets 0/2, SongModePopup set 1).
| FIX: d1 -> clamp to 0..2, and 1 -> 0. Only d1 and flags change. Assemble: m68k-linux-gnu-as -mcpu=5475
    .text
FIX:
    tst.l %d1
    bpl 1f
    moveq #0,%d1
    rts
1:  cmpi.l #1,%d1
    bne 2f
    moveq #0,%d1
    rts
2:  cmpi.l #2,%d1
    ble 3f
    moveq #2,%d1
3:  rts
