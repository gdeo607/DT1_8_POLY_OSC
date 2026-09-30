| Digi Mono: the machine entries and the render hook. The logic is in digimono.c, the engine in mono.c.
| Firmware addresses are OS 1.53's.

        .section .run, "ax"

| ---------------- the machines (core 2.1's core_machines; elekloader docs/ADAPTING.md) --------------
| Descriptor: id, name, short name, icon, params, render. They take ONESHOT's eight parameters (their
| defaults on a switch, MIDI CC 16-23) and render as ONESHOT, so the voice runs the whole stock voice
| path (the amp envelope and VOL included, which an unknown render machine skips). digimono_rblock
| replaces the resampled block of a voice whose track plays one of them (core_track_machine).
        .balign 4
        .globl  digimono_m6, digimono_m7, digimono_m8, digimono_m9, digimono_m10
digimono_m6:    .long   6,  str_sin,  str_sin_s,  0, 0, 0
digimono_m7:    .long   7,  str_nois, str_nois_s, 0, 0, 0
digimono_m8:    .long   8,  str_saw,  str_saw_s,  0, 0, 0
digimono_m9:    .long   9,  str_puls, str_puls_s, 0, 0, 0
digimono_m10:   .long   10, str_ens,  str_ens_s,  0, 0, 0
str_sin:        .asciz  "MONO SIN"
str_sin_s:      .asciz  "MSIN"
str_nois:       .asciz  "MONO NOISE"
str_nois_s:     .asciz  "MNOI"
str_saw:        .asciz  "MONO SAW"
str_saw_s:      .asciz  "MSAW"
str_puls:       .asciz  "MONO PULSE"
str_puls_s:     .asciz  "MPLS"
str_ens:        .asciz  "MONO ENS"
str_ens_s:      .asciz  "MENS"

| ---------------- the render: every voice's block, before the amp/filter stage (0x40077fba) ----------
| After the voice loop (0x400757fe) each voice's 32 samples, Q31, are at 0x80001a18 + 128 v; the stages
| after it (0x40072478 onwards: the filter, the amp envelope, VOL, the mixer) work on them there. This
| replaces "lea 0x4199e444,a4" between the two; digimono_blocks() overwrites the block of every voice that
| plays a Digi Mono machine. Every register is kept; the EMAC is not touched (the C code has no MAC
| instructions). An earlier hook, right after the resampler (0x4007606e), came before those stages'
| input and so missed the filter and VOL (tests/digiemu_mono_fx.py).
        .balign 2
        .globl  digimono_rblock
digimono_rblock:
        lea     -60(%sp), %sp
        movem.l %d0-%d7/%a0-%a6, (%sp)
        jsr     digimono_blocks
        movem.l (%sp), %d0-%d7/%a0-%a6
        lea     60(%sp), %sp
        lea     0x4199e444, %a4                 | the instruction this replaced
        rts

| ---------------- the SRC page: names, ranges and values of a Digi Mono track's knobs ----------------
| Machines past the stock four get SLICE's SRC page (core 2.1): parameter ids 0x84..0x8b, knobs A..H.
| While the active track plays a Digi Mono machine, digimono.c gives B, C, E, F, G and H its own names,
| a 0..127 range and plain numbers (digimono_name, digimono_range, digimono_text return 0 otherwise, and
| the stock code runs as it was). A (TUNE) and D (SAMP) stay as they are.

| 0x4000fe8a (this, id) -> the parameter's short name (was: move.l 8(sp),d1 ; cmpi.l #164,d1)
        .globl  digimono_sname
digimono_sname:
        pea     1.w
        move.l  12(%sp), -(%sp)
        jsr     digimono_name
        addq.l  #8, %sp
        tst.l   %d0
        bne.s   1f
        move.l  8(%sp), %d1
        cmpi.l  #164, %d1
        jmp     0x4000fe94
1:      rts

| 0x4000feac (this, id) -> the parameter's long name (same stock bytes)
        .globl  digimono_lname
digimono_lname:
        clr.l   -(%sp)
        move.l  12(%sp), -(%sp)
        jsr     digimono_name
        addq.l  #8, %sp
        tst.l   %d0
        bne.s   1f
        move.l  8(%sp), %d1
        cmpi.l  #164, %d1
        jmp     0x4000feb6
1:      rts

| 0x40078f0c (id; a0 = out {min, max, default}) -> d0 = a0 (was: move.l d2,-(sp) ; move.l 8(sp),d0)
        .globl  digimono_prange
digimono_prange:
        move.l  %a0, -(%sp)
        move.l  8(%sp), -(%sp)
        jsr     digimono_range
        addq.l  #4, %sp
        movea.l (%sp)+, %a0
        tst.l   %d0
        beq.s   1f
        move.l  %a0, %d0
        rts
1:      move.l  %d2, -(%sp)
        move.l  8(%sp), %d0
        jmp     0x40078f12

| 0x400657ee (id, value) -> the value's text (was: move.l 4(sp),d1 ; cmpi.l #164,d1)
        .globl  digimono_vtext
digimono_vtext:
        move.l  8(%sp), -(%sp)
        move.l  8(%sp), -(%sp)
        jsr     digimono_text
        addq.l  #8, %sp
        tst.l   %d0
        bne.s   1f
        move.l  4(%sp), %d1
        cmpi.l  #164, %d1
        jmp     0x400657f8
1:      rts
