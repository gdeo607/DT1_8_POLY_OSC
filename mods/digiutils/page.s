| Digi utilities: opening the page by HOLDING "..." while Song mode stays as stock.
|
| Stock (OS 1.53): "..." press = the SONG MODE popup (MainScreenView); the popup then gets the key's later
| events. Key event flags (+16): bit 0 down, 1 FUNC, 2 double press, 3 repeat, 4 up, 5 long press (sent once,
| after about half a second of holding), 6 longer press. Stock: a double press with song mode on opens the
| Song edit screen (SongEditView). Here a long press (bit 5) opens a SongEditView, and that one instance becomes
| the utility page:
| digiutils_adopt (page.c) points its vtables at copies whose draw/key/tick/knob/LED entries are ours. The Song
| edit screen opened any other way (the popup's EDIT) keeps the stock vtables and works as stock.

        .text
| 0x400aee4a, the SONG MODE popup's "..." handling (the popup is on top from the press on, so it gets the hold):
| stock "lea 0x400eb218,a3", then: song mode on and a double press -> 0x400af042 (open / close the Song edit
| screen), else 0x400af0d8. Here a long press (bit 5, without FUNC) goes to 0x400af042 too, marked as the page.
        .globl  digiutils_popkey
digiutils_popkey:
        lea     0x400eb218, %a3                 | displaced
        move.l  %d0, -(%sp)
        movea.l %d2, %a0                        | the key event (fp@(12), kept in d2)
        move.l  16(%a0), %d0                    | flags: bit 5 long press, bit 1 FUNC
        btst    #5, %d0
        beq.b   3f
        btst    #1, %d0
        bne.b   3f
        moveq   #1, %d0
        move.b  %d0, page_next
        move.l  (%sp)+, %d0
        movea.l %a3, %a5                        | as the stock code has them at 0x400af042
        lea     0x400c31f0, %a4
        lea     0x400af042, %a0
        move.l  %a0, (%sp)
        rts
3:      move.l  (%sp)+, %d0
        rts

| 0x400af086, after make_shared<SongEditView> (0x40161ffe) on the popup's path (object at -24(fp)):
| displaced "clr.l -(sp); movea.l -20(fp),a0".
        .globl  digiutils_made2
digiutils_made2:
        tst.b   page_next
        beq.b   4f
        clr.b   page_next
        lea     -16(%sp), %sp
        movem.l %d0-%d1/%a0-%a1, (%sp)
        move.l  -24(%fp), -(%sp)
        jsr     digiutils_adopt
        addq.l  #4, %sp
        movem.l (%sp), %d0-%d1/%a0-%a1
        lea     16(%sp), %sp
4:      subq.l  #4, %sp
        move.l  4(%sp), (%sp)
        clr.l   4(%sp)
        movea.l -20(%fp), %a0
        rts

| 0x40095aec and 0x40095bf6 (pattern / bank picked): "movea.l -32(fp),a0; tst.l a0; beq.s +12" then the
| found SongEditView is closed. Stock closes the Song edit screen there; the page stays open.
        .globl  digiutils_patchk
digiutils_patchk:
        movea.l -32(%fp), %a0
        tst.l   %a0
        beq.b   2f
        movea.l (%a0), %a1
        cmpa.l  digiutils_vtprim, %a1
        beq.b   2f
        rts                                     | another SongEditView: closed as stock
2:      movea.l (%sp), %a1                      | none, or the page: skip the close (site + 20)
        lea     14(%a1), %a1
        move.l  %a1, (%sp)
        rts

        .section .bss
page_next:
        .skip   4
