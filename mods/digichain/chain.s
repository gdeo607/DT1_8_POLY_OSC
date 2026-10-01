| SPDX-License-Identifier: MIT
| digichain: one owner for the SRC-page and render sites that SOPHIE (digisophie), NEIGHBOR
| (digineighbor) and DIGISLICER (digislicer) each patch, so the three combine. Digi Mono (20..25) gets
| its page's layout, knob graphics, UI records and knob values through it too.
| ColdFire V4e, Digitakt mk1 OS 1.53.
|
| Each of those mods takes over the same firmware functions and acts only for its own machine
| (SOPHIE 7, NEIGHBOR 4, DIGISLICER 5): on any other machine its handler goes on to the stock code.
| So digichain owns each site once and sends the call to the handler of the machine it is for, or to
| the stock code. The handlers are the mods' own, unchanged; tools/chain_patch.py moves their sites
| here when tools/dev.sh builds them. Every handler is a weak import: a mod that is not in the build
| reads as core_zero, and its machine gets the stock code.
|
| Which machine a label, value or knob is for: the machine whose SRC page asked for its layout last
| (0x400657cc), as the mods themselves assume. Which machine a parameter range is for: the sound's,
| found from the object as the mods find it.

        .equ    M_NBR, 4                | NEIGHBOR
        .equ    M_DSL, 5                | DIGISLICER
        .equ    M_SOPH, 7               | SOPHIE
        .equ    M_MONO, 20              | Digi Mono: 20..25
        .equ    M_MONO_LAST, 25

        .section .bss
        .balign 4
        .globl  digichain_page_m
digichain_page_m:   .skip 4

        .section .run, "ax"

| jmp to \fn when the page's machine is \m and \fn is in the build; else on to the next line.
| Function entries only: d0, d1 and a1 are free there.
        .macro  ROUTE m, fn
        moveq   #\m, %d0
        cmp.l   digichain_page_m, %d0
        bne.s   1f
        move.l  #\fn, %d1
        cmpi.l  #core_zero, %d1
        beq.s   1f
        movea.l %d1, %a1
        jmp     (%a1)
1:
        .endm

| jmp to \fn when the page's machine is \lo..\hi and \fn is in the build; else on to the next line.
        .macro  ROUTE_IN lo, hi, fn
        move.l  digichain_page_m, %d0
        moveq   #\lo, %d1
        cmp.l   %d1, %d0
        bcs.s   1f
        moveq   #\hi, %d1
        cmp.l   %d1, %d0
        bhi.s   1f
        move.l  #\fn, %d1
        cmpi.l  #core_zero, %d1
        beq.s   1f
        movea.l %d1, %a1
        jmp     (%a1)
1:
        .endm

| d1 = the sound's machine: jmp to \soph on a SOPHIE sound, \dsl on a DIGISLICER one (when in the
| build), else the stock lookup.
        .macro  PRANGE soph, dsl, nbr
        moveq   #M_SOPH, %d0
        cmp.l   %d0, %d1
        bne.s   1f
        move.l  #\soph, %d0
        bra.s   2f
1:      moveq   #M_NBR, %d0
        cmp.l   %d0, %d1
        bne.s   4f
        move.l  #0x88, %d0              | NEIGHBOR's SLOT (SLICE's id), if NEIGHBOR is in the build
        cmp.l   4(%sp), %d0
        bne.s   3f
        move.l  #nb_layout, %d0
        cmpi.l  #core_zero, %d0
        beq.s   3f
        bra     \nbr
4:      moveq   #M_DSL, %d0
        cmp.l   %d0, %d1
        bne.s   3f
        move.l  #\dsl, %d0
2:      cmpi.l  #core_zero, %d0
        beq.s   3f
        movea.l %d0, %a1
        jmp     (%a1)
3:      jmp     0x40078f0c
        .endm

| 0x400657cc(machine): the SRC page's layout (was: moveq #3,d1 ; move.l 4(sp),d0), by jmp.
| The page asks for it, with its own track's machine, before it draws or turns a knob.
        .globl  digichain_layout
digichain_layout:
        move.l  4(%sp), %d0
        move.l  %d0, digichain_page_m
        ROUTE   M_SOPH, ds_layout
        ROUTE   M_NBR, nb_layout
        ROUTE_IN M_MONO, M_MONO_LAST, digimono_layout
        move.l  4(%sp), %d0
        moveq   #3, %d1
        jmp     0x400657d2

| 0x4000fe8a(obj, id), a knob's label, and 0x4000feac(obj, id), its long name
| (was: move.l 8(sp),d1 ; cmpi.l #164,d1), by jmp.
        .globl  digichain_lab_short, digichain_lab_long
digichain_lab_short:
        ROUTE   M_SOPH, ds_lab_short
        ROUTE   M_NBR, nb_lab_short
        move.l  8(%sp), %d1
        cmpi.l  #164, %d1
        jmp     0x4000fe94

digichain_lab_long:
        ROUTE   M_SOPH, ds_lab_long
        ROUTE   M_NBR, nb_lab_long
        move.l  8(%sp), %d1
        cmpi.l  #164, %d1
        jmp     0x4000feb6

| 0x4000f324(obj, id, value, buf), a knob's value text
| (was: lea -20(sp),sp ; movem.l d2-d4/a2-a3,(sp)), by jmp.
        .globl  digichain_val_text
digichain_val_text:
        ROUTE   M_SOPH, ds_val_text
        ROUTE   M_NBR, nb_val_text
        ROUTE_IN M_MONO, M_MONO_LAST, digimono_val_text
        lea     -20(%sp), %sp
        movem.l %d2-%d4/%a2-%a3, (%sp)
        jmp     0x4000f32c

| 0x4000f2bc(obj, id, value, ...), a knob's graphic
| (was: lea -20(sp),sp ; movem.l d2-d6,(sp)), by jmp.
        .globl  digichain_knob_gfx
digichain_knob_gfx:
        ROUTE   M_SOPH, ds_knob_gfx
        ROUTE   M_NBR, nb_knob_gfx
        ROUTE_IN M_MONO, M_MONO_LAST, digimono_knob_gfx
        lea     -20(%sp), %sp
        movem.l %d2-%d6, (%sp)
        jmp     0x4000f2c4

| 0x40065794(id), a parameter's UI record (was: move.l 4(sp),d1 ; cmpi.l #164,d1), by jmp.
        .globl  digichain_ui_rec
digichain_ui_rec:
        ROUTE   M_SOPH, ds_ui_rec
        ROUTE   M_NBR, nb_ui_rec
        ROUTE_IN M_MONO, M_MONO_LAST, digimono_ui_rec
        move.l  4(%sp), %d1
        cmpi.l  #164, %d1
        jmp     0x4006579e

| 0x400657ee(id, value), the value pop-up's text (was: move.l 4(sp),d1 ; cmpi.l #164,d1), by jmp.
        .globl  digichain_pop_text
digichain_pop_text:
        ROUTE   M_SOPH, ds_pop_text
        ROUTE   M_NBR, nb_pop_text
        move.l  4(%sp), %d1
        cmpi.l  #164, %d1
        jmp     0x400657f8

| At 0x40077fba in the render handler, after playback has written every track's block and before
| the overdrive stage (was: lea 0x4199e444,a4), by jsr: SOPHIE's voices, then NEIGHBOR's (so a
| NEIGHBOR track can take a SOPHIE track's sound). Each mod's wrapper keeps every register and ends
| with the replaced instruction; so does this one.
        .globl  digichain_inject
digichain_inject:
        move.l  %a0, -(%sp)
        move.l  %d0, -(%sp)
        move.l  #ds_inject_s, %d0
        cmpi.l  #core_zero, %d0
        beq.s   1f
        movea.l %d0, %a0
        jsr     (%a0)
1:      move.l  #nb_inject_s, %d0
        cmpi.l  #core_zero, %d0
        beq.s   2f
        movea.l %d0, %a0
        jsr     (%a0)
2:      move.l  (%sp)+, %d0
        movea.l (%sp)+, %a0
        lea     0x4199e444, %a4
        rts

| The parameter range lookup 0x40078f0c, from four callers: 0x4000ff20, 0x400100c4 and 0x4000f534
| (jsr, the object in a2) and 0x4000f5fc (lea into a2, called later; the object is its caller's
| first argument, 36(sp) on entry), each now going here instead (keep2). SOPHIE changes the ranges
| of ids 0x85-0x8b but BR (0x86) on its sounds, DIGISLICER those of PLAY (0x85) and GRID (0x8a)
| on its own: the sound's machine picks the handler, which is entered exactly as from the caller.
| a0 (where the range goes) and a2 are the caller's: kept.
        .globl  digichain_prange, digichain_prange_f
digichain_prange:
        movea.l %a2, %a1
        bsr.w   digichain_rmach
        PRANGE  ds_prange, dsl_prange, digichain_nb_range

digichain_prange_f:
        movea.l 36(%sp), %a1
        bsr.w   digichain_rmach
        PRANGE  ds_prange_f, dsl_prange_f, digichain_nb_range_f

| NEIGHBOR's SLOT is SLICE's parameter underneath, 0..64 (slices), but only 1-8 pick a track: the range is
| 0..8 (0, off). Entered as the range lookup would be (as digislicer's dsl_prange): the object in a2, or
| its caller's first argument (36(sp)); a0 where the range goes.
digichain_nb_range:
        movea.l %a2, %a1
        bra.s   1f
digichain_nb_range_f:
        movea.l 36(%sp), %a1
1:      move.l  %a1, -(%sp)             | the object
        move.l  %a0, -(%sp)             | the result's place
        move.l  12(%sp), -(%sp)         | the id
        jsr     0x40078f0c
        addq.l  #4, %sp
        movea.l (%sp)+, %a0
        movea.l (%sp)+, %a1
        move.l  #8 << 8, %d0
        move.l  %d0, 4(%a0)             | the max: track 8
        move.l  %a0, %d0
        rts

| a1 = the object, the id at 8(sp) (past this call's return address) -> d1 = the machine of the
| object's sound when the id is one SOPHIE or DIGISLICER changes, else 0. Uses d0, d1, a1.
digichain_rmach:
        moveq   #0, %d1
        move.l  8(%sp), %d0             | the id
        cmpi.l  #0x85, %d0
        bcs.s   9f
        cmpi.l  #0x8b, %d0
        bhi.s   9f
        cmpi.l  #0x86, %d0
        beq.s   9f
        move.l  (%a1), %d0              | the object -> its sound, as the mods find it
        cmpi.l  #0x4017eb58, %d0
        bne.s   9f
        movea.l 16(%a1), %a1
        move.l  (%a1), %d0
        cmpi.l  #0x40181330, %d0
        bne.s   9f
        movea.l 16(%a1), %a1
        move.b  126(%a1), %d1           | its machine
9:      rts

| The machine menu's icons. Its row loop (0x4002a37c..) asks 0x40029e80(machine) for a row's icon type
| (1-4 for the stock four, 0 past them) and draws the row's icon only when the type differs from the row
| above's (0 above the first). So with core 2.1 an added machine got its icon only right under SLICE, and
| none past the first: SOPHIE, DIGISLICER and Digi Mono's never showed. At 0x4002a382 (was: jsr
| 0x40029e80), by keep2: an added machine's type is its own (5 + its number), so every row draws its icon
| (core's icon callback draws the machine's own, or none). The stock four are as they were.
        .globl  digichain_mtype
digichain_mtype:
        move.l  4(%sp), %d0
        moveq   #3, %d1
        cmp.l   %d0, %d1
        bcs.s   1f
        jmp     0x40029e80              | 0-3: the stock types
1:      addq.l  #5, %d0
        rts
