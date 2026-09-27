| digiutils (elekloader build): the page's state, same layout as the stand-alone build's fixed data area
| (0x400ae280.. in the reclaimed Song-popup code there). Offsets used by src/scope.s, tuner.s, spectrum.s.

        .section .bss
        .balign 4
        .globl  digiutils_data, digiutils_tring, digiutils_sreq
digiutils_data:                    | IDX, MODE, LASTV, FULL, ring 512 x {mid, side}, TRIGCNT[8], LASTCNT[8],
        .skip   0x834           | HOLD[8], PYMAX, PYMID, PNAMP
digiutils_tring:                   | tuner 3 kHz ring, 512 x int16
        .skip   1024
digiutils_sreq:                    | spectrum: SREQ, SRDY, SCNT, SPTR, SWORK, pad, COLH[128], PK[128]
        .skip   0x118

        .text
        .balign 4
        .globl  digiutils_tdata, digiutils_sint
digiutils_tdata:                   | tuner: TIDX, TNOTE (-1 = none), TCENT, TCNT, TBUF, pad
        .long   0, -1, 0, 0, 0, 0, 0
digiutils_sint:                    | 257 x int16 quarter sine (tools/gen_spec_tables.py, from tests/spec_model.py)
        .incbin "spec_sin.bin"
        .balign 4
