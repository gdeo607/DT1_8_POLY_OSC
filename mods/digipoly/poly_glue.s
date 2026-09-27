| Digi Poly: the hooks into the sequencer, the audio engine, the TRIG page and SETTINGS.
| The logic is in poly.c; these are the entry shims (registers as each site has them).
| Firmware addresses are OS 1.53's.

        .text

| ---------------- trig message builder, end (0x4006f7ea, in 0x4006f4be) ----------------------------
| replaces "move.l a5,(68,a2); move.l a2,d0". a2 = the message, a3 = track data + step, d4 = step,
| 64(sp) = the builder's arguments (track, pattern, kit, step, ...) + 4 for this call.
| A trig of a POLY track carries its chord in msg+28: 0xC4, then NOT2, NOT3, NOT4 as stored (0x40 = off,
| else a semitone offset + 0x40), the step's own values or the track's defaults. Any other message gets 0
| there (messages are recycled).
        .balign 2
        .globl  digipoly_tag
digipoly_tag:
        move.l  %a5, 68(%a2)
        clr.l   28(%a2)
        move.l  8(%a2), %d0                     | track
        moveq   #7, %d1
        cmp.l   %d1, %d0
        bhi.b   9f
        movea.l 76(%sp), %a0                    | kit (sound t at +0x20 + t*0xa2, machine at +0x7e)
        move.l  %a0, %d1
        beq.b   9f
        mulu.w  #0xa2, %d0
        lea     0x9e(%a0), %a0
        move.b  (%a0,%d0.l), %d1
        cmpi.b  #4, %d1
        bne.b   9f
        movea.l %a3, %a1
        suba.l  %d4, %a1                        | the track's data (defaults at +0x384..)
        move.b  #0xc4, 28(%a2)
        move.b  0x2c0(%a3), %d1                 | NOT2 of the step
        cmpi.b  #-1, %d1
        bne.b   1f
        move.b  0x385(%a1), %d1                 | its default
1:      move.b  %d1, 29(%a2)
        move.b  0x300(%a3), %d1                 | NOT3
        cmpi.b  #-1, %d1
        bne.b   2f
        move.b  0x386(%a1), %d1
2:      move.b  %d1, 30(%a2)
        move.b  0x340(%a3), %d1                 | NOT4
        cmpi.b  #-1, %d1
        bne.b   3f
        move.b  0x387(%a1), %d1
3:      move.b  %d1, 31(%a2)
9:      move.l  %a2, %d0
        rts

| ---------------- audio engine, note message (0x400777a2, in the render's message loop) -------------
| replaces "move.l (8,a2),d2; move.l d2,d0" (the message's voice). a2 = the message, d3 = voices started
| so far in this render call, a6 = the render's frame. digipoly_route_c may change the voice (and add
| messages after this one); every register but d0/d2 is kept.
        .balign 2
        .globl  digipoly_route
digipoly_route:
        lea     -16(%sp), %sp
        movem.l %d0-%d1/%a0-%a1, (%sp)
        move.l  %a6, -(%sp)
        move.l  %d3, -(%sp)
        move.l  %a2, -(%sp)
        jsr     digipoly_route_c
        lea     12(%sp), %sp
        movem.l (%sp), %d0-%d1/%a0-%a1
        lea     16(%sp), %sp
        move.l  8(%a2), %d2
        move.l  %d2, %d0
        rts

| ---------------- render, after the parameter smoothing (0x40077eaa) -----------------------------
| replaces "movea.l d0,a2; jsr 0x400ed53e" (d0 = the smoothed parameter words; the call's arguments are on
| the stack). digipoly_levels gives stolen voices the level of the POLY track; then the stock call, returning
| to the nop after this site.
        .balign 2
        .globl  digipoly_lvlhook
digipoly_lvlhook:
        lea     -16(%sp), %sp
        movem.l %d0-%d1/%a0-%a1, (%sp)
        move.l  %d0, -(%sp)
        jsr     digipoly_levels
        addq.l  #4, %sp
        movem.l (%sp), %d0-%d1/%a0-%a1
        lea     16(%sp), %sp
        movea.l %d0, %a2
        jmp     0x400ed53e

| ---------------- TRIG page draw (vtable 0x40184004 slot 5, was 0x400368ba) ------------------------
| The same view class shows the audio TRIG page (page kind 1) and the MIDI one (kind 15); poly.c sets
| the audio view's kind to 15 while the active track is POLY, the stock draw runs, and poly.c adds the
| track's LEV fader in the left column, which the MIDI page leaves empty.
| f(view, bmp).
        .balign 2
        .globl  digipoly_trigdraw
digipoly_trigdraw:
        move.l  4(%sp), -(%sp)
        jsr     digipoly_trigkind
        addq.l  #4, %sp
        move.l  8(%sp), -(%sp)                  | bmp
        move.l  8(%sp), -(%sp)                  | view
        jsr     0x400368ba
        addq.l  #8, %sp
        move.l  8(%sp), -(%sp)                  | bmp
        move.l  8(%sp), -(%sp)                  | view
        jsr     digipoly_levdraw
        addq.l  #8, %sp
        rts

| ---------------- the unit's keys: chord preview (0x40028bae, 0x40028c60) -------------------------
| Both sites are a jsr to the firmware's live note on/off for a key press on a track. The shims pass the
| same arguments to poly.c, which makes the stock call and adds the chord's other notes.
        .balign 2
        .globl  digipoly_prevon_hook
digipoly_prevon_hook:                           | 7 arguments (track, note, vel, 0x40, x, -1, -1)
        .rept   7
        move.l  28(%sp), -(%sp)
        .endr
        jsr     digipoly_prevon
        lea     28(%sp), %sp
        rts

        .globl  digipoly_prevoff_hook
digipoly_prevoff_hook:                          | 3 arguments (track, note, 0x40)
        .rept   3
        move.l  12(%sp), -(%sp)
        .endr
        jsr     digipoly_prevoff
        lea     12(%sp), %sp
        rts

| ---------------- SETTINGS: the POLY row (which tracks lend their voice) --------------------------------------------------
        .globl  digipoly_settings
digipoly_settings:
        pea     row_poly
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
row_poly:
        .long   row_label, digipoly_select, digipoly_draw, digipoly_change
str_row:
        .asciz  "POLY"
        .balign 2

| ---------------- recording a live note: the tail of the record path (0x400d55c6) -----------------
| In liveNoteOn, right after the trig has been recorded (jsr 0x4006f46e). Replaces
| "lea (24,sp),sp; adda.l a5,a2": a2 is the pattern's data, a5 = 911 * track, so after the adda a2 is
| the track's own block; d2 = the track, d3 = the note. poly.c writes the chord into the step's
| NOT1..NOT4. Our return address is dropped: the two instructions are done here and the function carries
| on at 0x400d55cc.
        .balign 2
        .globl  digipoly_rechook
digipoly_rechook:
        movea.l (%sp)+, %a1                     | our return address
        lea     24(%sp), %sp                    | the lea it replaced
        adda.l  %a5, %a2                        | the adda it replaced
        lea     -16(%sp), %sp
        movem.l %d0-%d1/%a0-%a1, (%sp)
        move.l  %d3, -(%sp)                     | note
        move.l  %d2, -(%sp)                     | track
        move.l  %a2, -(%sp)                     | the track's pattern data
        jsr     digipoly_recnote
        lea     12(%sp), %sp
        movem.l (%sp), %d0-%d1/%a0-%a1
        lea     16(%sp), %sp
        jmp     (%a1)

| ---------------- the TRIG view's knob listener, through its +4 subobject (0x401840e8) -------------
| The stock entry is a thunk (0x40032d8c: "subq.l #4,(4,sp); bra 0x40032a78"), so a knob event that comes
| this way never looks at the primary vtable. Same shape, ours instead.
        .balign 2
        .globl  digipoly_trigenc_thunk
digipoly_trigenc_thunk:
        subq.l  #4, 4(%sp)
        jmp     digipoly_trigenc
