| Digi EQ: where the EQ meets the render, the master pages and the GLOBAL FX/MIX list.
| The logic is in eq.c and eq_dsp.s. Firmware addresses are OS 1.53's.

        .text

| ---------------- the render: the master mix, before it is handed out (0x400721e6) ------------------
| Replaces "move.l #0x8000ea70,d4", the first instruction of the stage that spreads the master pair over
| the outputs: from here it goes to the analog conversion for the main outputs and the headphones, and
| into the 12-channel bus the USB stream is built from. 0x8000ea70 holds this block's master, 32 frames
| of {L, R} 32-bit samples; the EQ runs on it in place, so every output carries it - and the scope,
| spectrum and tuner, which read the block further on, still show what you hear.
| digieq_run keeps every register; d4 is set afterwards anyway.
        .balign 2
        .globl  digieq_master
digieq_master:
        pea     0x8000ea70
        jsr     digieq_run
        addq.l  #4, %sp
        move.l  #0x8000ea70, %d4                | the instruction this replaced
        rts

| ---------------- the master view's knob listener (its +4 subobject's vtable entry 0x401846bc) --------
| this -= 4, then eq.c's handler for the whole view.
        .balign 2
        .globl  digieq_menc_thunk
digieq_menc_thunk:
        subq.l  #4, 4(%sp)
        jmp     digieq_menc

| ---------------- SETTINGS > GLOBAL FX/MIX: the MASTER EQ row ---------------------------------------
| At 0x40044acc, the end of that menu's item builder (was: "movea.l (a4),a0; pea 2.w"), where a4 is the
| menu and d7 the selection it is about to restore - the same shape as the SETTINGS builder core hooks.
| We add our row, then do what the two instructions did and carry on at 0x40044ad2.
        .balign 2
        .globl  digieq_gfx
digieq_gfx:
        move.l  (%sp)+, %d0                     | our return address: we go back by hand
        pea     row_eq
        move.l  %a4, -(%sp)                     | the menu
        jsr     core_additem
        addq.l  #8, %sp
        movea.l (%a4), %a0                      | the instructions this replaced
        pea     2.w
        jmp     0x40044ad2

| label: builds the std::string in a0
row_label:
        link    %a6, #-4
        move.l  %d2, -(%sp)
        pea     -1(%a6)
        pea     str_row
        move.l  %a0, %d2
        move.l  %a0, -(%sp)
        jsr     0x4017ac20                      | std::string(this, const char*, alloc&)
        lea     12(%sp), %sp
        move.l  %d2, %d0
        move.l  -8(%a6), %d2
        unlk    %a6
        rts

        .balign 4
row_eq:
        .long   row_label, digieq_gselect, digieq_gdraw, digieq_gchange
str_row:
        .asciz  "MASTER EQ"
        .balign 2
