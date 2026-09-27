| Digi Poly: the POLY machine itself (the machine list entry, its name and icon, and the aliases that
| make the firmware treat a POLY track's sound as ONESHOT). Same code as in the earlier dt8poly mod.
| Firmware addresses are OS 1.53's. Nothing here is firmware code: the name table holds the addresses
| of the four stock name strings, which the SDK stores as a reference to the user's own image.

        .text

| ---------------- machine name table: 5 x {long name, short name} ----------------------------------
        .balign 4
        .globl  digipoly_names, digipoly_names4
digipoly_names:
        .long   0x401cc672, 0x401c6b87          | ONESHOT, SAMP
        .long   0x401c65f5, 0x401c65f5          | WERP, WERP
        .long   0x401c6b8c, 0x401cc67a          | REPITCH, PTCH
        .long   0x401cc67f, 0x401c6b9f          | SLICE, SLIC
        .long   poly_str, poly_str              | POLY, POLY
        .set    digipoly_names4, digipoly_names+4
poly_str:
        .asciz  "POLY"
        .balign 4

| ---------------- param-id lookup (0x40078f72, in 0x40078f44 slot,machine -> param id) --------------
| replaces "moveq #3,d2; cmp.l d0,d2; bcs.b bad; lsl.l #3,d0": POLY (4) uses ONESHOT's parameter set
        .globl  digipoly_lookup
digipoly_lookup:
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
        .globl  digipoly_engine
digipoly_engine:
        move.b  0x7e(%a0), %d1
        cmpi.b  #4, %d1
        bne.b   0f
        moveq   #0, %d1
0:      move.b  %d1, (0,%a1,%d0.l)
        rts

| ---------------- machine getter alias (0x4002202e, in 0x4002200a) ---------------------------------
| replaces "mvs.b (0x7e,a0),d0; bra.b end": every caller sees ONESHOT for POLY, then the getter's epilogue
        .balign 4
        .globl  digipoly_getter
digipoly_getter:
        mvs.b   0x7e(%a0), %d0
        cmpi.l  #4, %d0
        bne.b   0f
        moveq   #0, %d0
0:      addq.l  #4, %sp                         | drop the hook's return address
        movea.l (%sp)+, %a2                     | the getter's own epilogue
        rts

| ---------------- raw machine getter (3 UI call sites that must see POLY itself) --------------------
| int raw(Sound *s): the sound's machine byte (+0x7e of the object its virtual +0x28 returns), -1 if none
        .globl  digipoly_rawget
digipoly_rawget:
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

| ---------------- POLY row icon in the FUNC+SRC machine list ----------------------------------------
| Row icons are drawn by 0x40029e9c: the group id (0x40029e80, table by machine id) selects one of four
| static bitmap objects {vtable 0x401b73b4, h 11, w 7, words 1, glyph, mask, flag}. Group 5 = POLY.
        .balign 4
        .globl  digipoly_icon_tab
digipoly_icon_tab:
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
        .globl  digipoly_icon
digipoly_icon:
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

