| digiutils (elekloader build): the audio tap. The stand-alone build hooks the render's output-write call
| (0x4007814a); FAST AUDIO (digihealth) routes that same call to its SRAM copy, so here the tap sits on
| the next two instructions instead, "move.l d0,d4; jsr 0x40006e04" at 0x40078150, after the output is
| written. The stack is as the stock code left it: the out buffer (32 frames x L,R) at 4(sp).

        .text
        .globl  digiutils_tap
digiutils_tap:
        move.l  %d0, %d4                | displaced
        jsr     0x40006e04              | displaced: d0 = a status word (no arguments; touches d0 only)
        jmp     digiutils_tapc          | src/scope.s: capture (all registers kept), then rts to the site

