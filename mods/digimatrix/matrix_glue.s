| Digi Matrix: the two hooks around the engine's LFO stage, and the SETTINGS row.
| The logic is in matrix.c. Firmware addresses are OS 1.53's.

        .text

| ---------------- render: between the smoothing and the LFO stage (0x40077ea2) ---------------------
| Replaces "move.l 0x4020db60,-(sp)", one of the LFO stage call's argument pushes: the smoothing has
| just run and left the parameter words in d0. digimatrix_pre takes the DEST word away from any LFO a
| matrix row has told to leave its own track alone; then the push happens as it did, under our return
| address. d0 is kept.
        .balign 2
        .globl  digimatrix_prehook
digimatrix_prehook:
        move.l  %d0, -(%sp)
        move.l  %d0, -(%sp)                     | the smoothed words
        jsr     digimatrix_pre
        addq.l  #4, %sp
        move.l  (%sp)+, %d0
        movea.l (%sp)+, %a1                     | our return address
        move.l  0x4020db60, -(%sp)              | the push this replaced
        jmp     (%a1)

| ---------------- render: after the LFO stage (0x40077eb2) ---------------------------------------
| Replaces "lea (16,sp),sp; clr.l d0", the two instructions after the LFO stage's call, while its
| arguments are still on the stack: (sp) = the smoothed parameter words after our return address.
| digimatrix_post puts the borrowed DEST words back and applies the matrix's own routings.
        .balign 2
        .globl  digimatrix_posthook
digimatrix_posthook:
        move.l  4(%sp), -(%sp)                  | the smoothed words
        jsr     digimatrix_post
        addq.l  #4, %sp
        move.l  (%sp), %d0                      | our return address
        lea     20(%sp), %sp                    | it, and the 16 bytes the lea dropped
        move.l  %d0, -(%sp)
        clr.l   %d0                             | the clr.l this replaced
        rts

| ---------------- SETTINGS: the MOD MATRIX row --------------------------------------------------
        .globl  digimatrix_settings
digimatrix_settings:
        pea     row_matrix
        move.l  8(%sp), -(%sp)                  | the menu
        jsr     core_additem
        addq.l  #8, %sp
        rts

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
row_matrix:
        .long   row_label, digimatrix_select, digimatrix_rowdraw, digimatrix_change
str_row:
        .asciz  "MOD MATRIX"
        .balign 2
