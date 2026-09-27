| dt8poly (elekloader build): the POLY machine's small hooks, in the mod's RAM image instead of the
| fixed-address cave the stand-alone build uses (tools/patch_section3.py, same code).
| Firmware addresses are OS 1.53's. Nothing here is firmware code: the name table holds the addresses
| of the four stock name strings, which the SDK stores as a reference to the user's own image.

        .text

| ---------------- machine name table: 5 x {long name, short name} ----------------------------------
        .balign 4
        .globl  dt8poly_names, dt8poly_names4
dt8poly_names:
        .long   0x401cc672, 0x401c6b87          | ONESHOT, SAMP
        .long   0x401c65f5, 0x401c65f5          | WERP, WERP
        .long   0x401c6b8c, 0x401cc67a          | REPITCH, PTCH
        .long   0x401cc67f, 0x401c6b9f          | SLICE, SLIC
        .long   poly_str, poly_str              | POLY, POLY
        .set    dt8poly_names4, dt8poly_names+4
poly_str:
        .asciz  "POLY"
        .balign 4

| ---------------- param-id lookup (0x40078f72, in 0x40078f44 slot,machine -> param id) --------------
| replaces "moveq #3,d2; cmp.l d0,d2; bcs.b bad; lsl.l #3,d0": POLY (4) uses ONESHOT's parameter set
        .globl  dt8poly_lookup
dt8poly_lookup:
        cmpi.l  #4, %d0
        bhi.b   1f
        bne.b   0f
        moveq   #0, %d0
0:      lsl.l   #3, %d0
        rts
1:      addq.l  #4, %sp                         | drop the hook's return address
        jmp     0x40078f54                      | the stock "invalid machine" exit

| ---------------- machine byte -> audio engine (0x40077272, in 0x4007725a) --------------------------
| replaces "lea (0x7e,a0),a0; move.b (a0),(0,a1,d0.l)": the engine plays POLY as ONESHOT
        .globl  dt8poly_engine
dt8poly_engine:
        move.b  0x7e(%a0), %d1
        cmpi.b  #4, %d1
        bne.b   0f
        moveq   #0, %d1
0:      move.b  %d1, (0,%a1,%d0.l)
        rts

| ---------------- machine getter alias (0x4002202e, in 0x4002200a) ---------------------------------
| replaces "mvs.b (0x7e,a0),d0; bra.b end": every caller sees ONESHOT for POLY, then the getter's epilogue
        .balign 4
        .globl  dt8poly_getter
dt8poly_getter:
        mvs.b   0x7e(%a0), %d0
        cmpi.l  #4, %d0
        bne.b   0f
        moveq   #0, %d0
0:      addq.l  #4, %sp                         | drop the hook's return address
        movea.l (%sp)+, %a2                     | the getter's own epilogue
        rts

| ---------------- raw machine getter (3 UI call sites that must see POLY itself) --------------------
| int raw(Sound *s): the sound's machine byte (+0x7e of the object its virtual +0x28 returns), -1 if none
        .globl  dt8poly_rawget
dt8poly_rawget:
        move.l  4(%sp), %a0
        move.l  (%a0), %a1
        move.l  0x28(%a1), %a1
        move.l  %a0, -(%sp)
        jsr     (%a1)
        addq.l  #4, %sp
        tst.l   %d0
        beq.b   0f
        movea.l %d0, %a0
        mvs.b   0x7e(%a0), %d0
        rts
0:      moveq   #-1, %d0
        rts

| ---------------- sequencer voice rotation (0x4006f76a, in the trig-message builder) ----------------
| replaces "move.l d0,(12,a2); move.l d5,(8,a2)" (message id, message voice = track d5).
| The lowest POLY track is the control track; with 2 or more POLY tracks its trigs rotate over them
| (round robin), keeping the control track's sound. The chosen voice's stored params pointer
| (0x800019b4 + 4*voice) is cleared so the engine reloads the params at this trig.
        .balign 4
        .globl  dt8poly_rotate
dt8poly_rotate:
        move.l  %d0, 12(%a2)
        movea.l 76(%sp), %a0                    | the builder's kit params (block t at +0x20 + t*0xa2)
        move.l  %a0, %d0
        beq.w   9f
        adda.l  #0x9e, %a0                      | machine byte of track 0
        moveq   #0, %d1
        moveq   #-1, %d6                        | control track
        moveq   #0, %d7                         | number of POLY tracks
1:      move.b  (%a0), %d0
        cmpi.b  #4, %d0
        bne.w   2f
        tst.l   %d6
        bge.w   3f
        move.l  %d1, %d6
3:      addq.l  #1, %d7
2:      adda.l  #0xa2, %a0
        addq.l  #1, %d1
        cmpi.l  #8, %d1
        bne.w   1b
        cmp.l   %d6, %d5
        bne.w   9f                              | not the control track: as stock
        moveq   #2, %d0
        cmp.l   %d0, %d7
        bcs.w   9f                              | fewer than 2 POLY tracks
        move.l  poly_rr, %d1                    | round-robin counter, validated modulo n
        cmp.l   %d7, %d1
        bcs.w   4f
        moveq   #0, %d1
4:      move.l  %d1, %d3
        addq.l  #1, %d3
        cmp.l   %d7, %d3
        bcs.w   5f
        moveq   #0, %d3
5:      move.l  %d3, poly_rr
        movea.l 76(%sp), %a0
        adda.l  #0x9e, %a0
        moveq   #0, %d3
6:      move.b  (%a0), %d0                      | d3 = the d1-th POLY track
        cmpi.b  #4, %d0
        bne.w   7f
        tst.l   %d1
        beq.w   8f
        subq.l  #1, %d1
7:      adda.l  #0xa2, %a0
        addq.l  #1, %d3
        cmpi.l  #8, %d3
        bne.w   6b
        move.l  %d5, %d3
8:      cmp.l   %d3, %d5
        beq.w   10f
        move.l  %d3, %d1
        asl.l   #2, %d1
        lea     0x800019b4, %a0
        clr.l   (0,%a0,%d1.l)
10:     move.l  %d3, 8(%a2)
        rts
9:      move.l  %d5, 8(%a2)
        rts

| ---------------- POLY row icon in the FUNC+SRC machine list ----------------------------------------
| Row icons are drawn by 0x40029e9c: the group id (0x40029e80, table by machine id) selects one of four
| static bitmap objects {vtable 0x401b73b4, h 11, w 7, words 1, glyph, mask, flag}. Group 5 = POLY.
        .balign 4
        .globl  dt8poly_icon_tab
dt8poly_icon_tab:
        .byte   1, 2, 3, 4, 5, 0, 0, 0
icon_obj:
        .long   0x401b73b4, 11, 7, 1, icon_glyph, icon_mask, 0
icon_mask:
        .rept   11
        .long   0xfe000000
        .endr
icon_glyph:                                     | 7x11 capital P
        .long   0xfc000000, 0xc6000000, 0xc6000000, 0xc6000000, 0xc6000000, 0xfc000000
        .long   0xc0000000, 0xc0000000, 0xc0000000, 0xc0000000, 0xc0000000

| replaces the icon draw's default exit (group not 1..4) at 0x40029f60:
| "movem.l (sp),d2-d4; lea 12(sp),sp; rts"
        .globl  dt8poly_icon
dt8poly_icon:
        cmpi.l  #5, %d0
        bne.w   1f
        subq.l  #1, %d4
        addq.l  #2, %d3
        clr.l   0x20(%sp)
        move.l  #icon_obj, %d0
        move.l  %d0, 0x14(%sp)
        move.l  %d4, 0x1c(%sp)
        move.l  %d3, 0x18(%sp)
        move.l  %d2, 0x10(%sp)
        movem.l (%sp), %d2-%d4
        lea     12(%sp), %sp
        jmp     0x400c2960                      | draw the bitmap
1:      movem.l (%sp), %d2-%d4
        lea     12(%sp), %sp
        rts

        .section .bss
        .balign 4
poly_rr:
        .skip   4
