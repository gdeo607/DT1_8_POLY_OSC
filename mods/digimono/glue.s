| Digi Mono: the machine entries and the render hook. The logic is in digimono.c, the engine in mono.c.
| Firmware addresses are OS 1.53's.

        .section .run, "ax"

| ---------------- the machines (core 2.1's core_machines; elekloader docs/ADAPTING.md) --------------
| Descriptor: id, name, short name, icon, params, render. They take ONESHOT's eight parameters (their
| defaults on a switch, MIDI CC 16-23) and render as ONESHOT, so the voice runs the whole stock voice
| path (the amp envelope and VOL included, which an unknown render machine skips). digimono_rblock
| replaces the block of a voice whose track plays one of them (core_track_machine). Ids 20..25: clear of
| NEIGHBOR / POLY (4), DIGISLICER (5) and SOPHIE (7).
        .balign 4
        .globl  digimono_m20, digimono_m21, digimono_m22, digimono_m23, digimono_m24, digimono_m25
digimono_m20:   .long   20, str_sin,  str_sin_s,  0, 0, 0
digimono_m21:   .long   21, str_nois, str_nois_s, 0, 0, 0
digimono_m22:   .long   22, str_saw,  str_saw_s,  0, 0, 0
digimono_m23:   .long   23, str_puls, str_puls_s, 0, 0, 0
digimono_m24:   .long   24, str_ens,  str_ens_s,  0, 0, 0
digimono_m25:   .long   25, str_vo,   str_vo_s,   0, 0, 0
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
str_vo:         .asciz  "MONO VO"
str_vo_s:       .asciz  "MVO"

| ---------------- the render: every voice's block, before the amp/filter stage (0x40077fc2) ----------
| After the voice loop (0x400757fe) each voice's 32 samples, Q31, are at 0x80001a18 + 128 v; the stages
| from 0x40072478 on (the filter, the amp envelope, VOL, the mixer) work on them there. This replaces
| "pea 0x80001a18" (the first argument of 0x40072478), one instruction after the point digisophie hooks
| (0x40077fba), so both run; digimono_blocks() overwrites the block of every voice that plays a Digi
| Mono machine. The pea is done here: the return address goes one slot down and 0x80001a18 into its place.
| Every register is kept; the EMAC is not touched (the C code has no MAC instructions).
        .balign 2
        .globl  digimono_rblock
digimono_rblock:
        move.l  (%sp), -(%sp)                   | [ret][ret]
        lea     -60(%sp), %sp
        movem.l %d0-%d7/%a0-%a6, (%sp)
        move.l  #0x80001a18, %d0
        move.l  %d0, 64(%sp)                    | [ret][0x80001a18]: the pea this replaced
        jsr     digimono_blocks
        movem.l (%sp), %d0-%d7/%a0-%a6
        lea     60(%sp), %sp
        rts

| ---------------- the SRC page: names, ranges and values of a Digi Mono track's knobs ----------------
| Machines past the stock four get SLICE's SRC page (core 2.1): parameter ids 0x84..0x8b, knobs A..H.
| While the active track plays a Digi Mono machine, digimono.c gives B, C, E, F, G and H its own names,
| a 0..127 range and plain numbers (digimono_name, digimono_range, digimono_text return 0 otherwise, and
| the stock code runs as it was). A (TUNE) and D (SAMP) stay as they are.

| They are reached through their callers, not their entries, so that another mod (digisophie) can own
| the entries: a caller's jsr is pointed here, and anything not ours goes on to the function as before.

| jsr 0x4000fe8a (this, id) at 0x40030daa -> the parameter's short name
        .globl  digimono_sname
digimono_sname:
        pea     1.w
        move.l  12(%sp), -(%sp)
        jsr     digimono_name
        addq.l  #8, %sp
        tst.l   %d0
        bne.s   1f
        jmp     0x4000fe8a
1:      rts

| jsr 0x4000feac (this, id) at 0x40032d36 -> the parameter's long name
        .globl  digimono_lname
digimono_lname:
        clr.l   -(%sp)
        move.l  12(%sp), -(%sp)
        jsr     digimono_name
        addq.l  #8, %sp
        tst.l   %d0
        bne.s   1f
        jmp     0x4000feac
1:      rts

| 0x40078f0c (id; a0 = out {min, max, default}) -> d0 = a0 (was: move.l d2,-(sp) ; move.l 8(sp),d0).
| Its entry: digisophie and digislicer wrap its callers, so their wrappers reach this too.
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

| jsr 0x400657ee (id, value) at its five callers -> the value's text
        .globl  digimono_vtext
digimono_vtext:
        move.l  8(%sp), -(%sp)
        move.l  8(%sp), -(%sp)
        jsr     digimono_text
        addq.l  #8, %sp
        tst.l   %d0
        bne.s   1f
        jmp     0x400657ee
1:      rts
