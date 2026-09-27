| Digi utilities: the master EQ's audio part (model: tests/eq_model.py, EQ.block).
| digieq_run(int32 *buf): in place on one render block, 32 frames x {L, R}, of the master mix - 32-bit
| samples, 8 bits hotter than the words the codec takes. Called from eq_glue.s on the master pair before the
| render hands it to the analog outputs and to the USB stream, so every output carries the EQ and the scope,
| spectrum and tuner still see what you hear. All registers kept; the EMAC state (MACSR, ACC0, ACCEXT01) is
| saved and restored.
| Inside, the arithmetic is the same as on a 24-bit sample with 2 bits of headroom: the block comes down by 8
| bits on the way in (asr 6 = >>8 then the x4 working range) and goes back up by 8 on the way out.
| The coefficient set (eq.c, struct eqset) is read through digieq_live, which the UI only switches
| between two sets, so a block never sees a half-written one:
|   +0 run (0 = pass the block untouched)   +4 output level (Q27, 0 = 0 dB)   +8 act[4]
|   +24 + 24*band: a1, a2, a3 (Q31), c0, c1, c2 (mix/16 in Q31)
| Per band and channel, the trapezoidal SVF: v3 = v0 - ic2; v1 = a1*ic1 + a2*v3; v2 = ic2 + a2*ic1 + a3*v3;
| ic1 = 2*v1 - ic1; ic2 = 2*v2 - ic2; out = v0 + 16*(c0*v0 + c1*v1 + c2*v2). Working range: samples x4.

        .set    RUN, 0
        .set    LVL, 4
        .set    ACT, 8
        .set    CO,  24
        .set    FR,  32                         | frames per block

        .text
        .globl  digieq_run
digieq_run:
        lea     -76(%sp), %sp
        movem.l %d0-%d7/%a0-%a6, (%sp)          | 0..59
        move.l  digieq_live, %d0
        beq.w   .Loff
        movea.l %d0, %a5
        tst.l   RUN(%a5)
        beq.w   .Loff
        move.l  %a5, 72(%sp)
        move.l  %macsr, %d0
        move.l  %d0, 60(%sp)
        move.l  %acc0, %d0
        move.l  %d0, 64(%sp)
        move.l  %accext01, %d0
        move.l  %d0, 68(%sp)
        move.l  #0x20, %macsr                   | signed, fractional, truncating, no saturation
        moveq   #0, %d0
        move.l  %d0, %acc0                      | start from an empty accumulator
        move.l  %d0, %accext01
        movea.l 80(%sp), %a0                    | 32-bit master -> 24-bit x4, the working range
        moveq   #2*FR, %d7
.Lpre:  move.l  (%a0), %d0
        asr.l   #6, %d0
        move.l  %d0, (%a0)+
        subq.l  #1, %d7
        bne.b   .Lpre

        moveq   #0, %d6                         | band
.Lband: movea.l 72(%sp), %a5
        lea     eq_was, %a1
        move.l  %d6, %d0
        asl.l   #2, %d0
        tst.l   ACT(%a5,%d0.l)
        bne.b   .Lact
        clr.l   (%a1,%d0.l)                     | off: its states restart when it comes back
        bra.w   .Lnext
.Lact:  tst.l   (%a1,%d0.l)
        bne.b   .Lrun
        moveq   #1, %d1
        move.l  %d1, (%a1,%d0.l)
        lea     eq_st, %a1                      | first block after switching on: states 0
        move.l  %d6, %d0
        asl.l   #4, %d0
        clr.l   0(%a1,%d0.l)
        clr.l   4(%a1,%d0.l)
        clr.l   8(%a1,%d0.l)
        clr.l   12(%a1,%d0.l)
.Lrun:  move.l  %d6, %d0                        | a1 = coefficients of this band
        mulu.w  #24, %d0
        lea     CO(%a5,%d0.l), %a1
        move.l  %d6, -(%sp)                     | band (the loop needs d6)
        moveq   #0, %d0                         | channel
.Lch:   move.l  %d0, -(%sp)
        movea.l 88(%sp), %a0                    | buf (2 words pushed)
        asl.l   #2, %d0
        adda.l  %d0, %a0                        | first sample of the channel
        move.l  4(%sp), %d6                     | band
        asl.l   #4, %d6
        add.l   %d0, %d0                        | channel * 8
        add.l   %d0, %d6                        | band*16 + channel*8
        lea     eq_st, %a6
        adda.l  %d6, %a6                        | a6 = &st[band][channel] {ic1, ic2}
        move.l  (%a6), %d4                      | ic1
        move.l  4(%a6), %d5                     | ic2
        move.l  %a6, -(%sp)
        movea.l 0(%a1), %a2                     | a1
        movea.l 4(%a1), %a3                     | a2
        movea.l 8(%a1), %a4                     | a3
        movea.l 12(%a1), %a5                    | c0
        movea.l 16(%a1), %a6                    | c1
        move.l  20(%a1), %d6                    | c2
        moveq   #FR, %d7
.Ls:    move.l  (%a0), %d0                      | v0
        move.l  %d0, %d1
        sub.l   %d5, %d1                        | v3 = v0 - ic2
        mac.l   %a2, %d4, %acc0                 | a1*ic1
        mac.l   %a3, %d1, %acc0                 | a2*v3
        movclr.l %acc0, %d2                     | v1
        mac.l   %a3, %d4, %acc0                 | a2*ic1
        mac.l   %a4, %d1, %acc0                 | a3*v3
        movclr.l %acc0, %d3
        add.l   %d5, %d3                        | v2 = ic2 + ...
        move.l  %d2, %d1
        add.l   %d1, %d1
        sub.l   %d4, %d1
        move.l  %d1, %d4                        | ic1 = 2*v1 - ic1
        move.l  %d3, %d1
        add.l   %d1, %d1
        sub.l   %d5, %d1
        move.l  %d1, %d5                        | ic2 = 2*v2 - ic2
        mac.l   %a5, %d0, %acc0                 | c0*v0
        mac.l   %a6, %d2, %acc0                 | c1*v1
        mac.l   %d6, %d3, %acc0                 | c2*v2
        movclr.l %acc0, %d1
        asl.l   #4, %d1
        add.l   %d1, %d0
        move.l  %d0, (%a0)
        addq.l  #8, %a0
        subq.l  #1, %d7
        bne.b   .Ls
        movea.l (%sp)+, %a6
        move.l  %d4, (%a6)
        move.l  %d5, 4(%a6)
        move.l  (%sp)+, %d0
        addq.l  #1, %d0
        moveq   #2, %d1
        cmp.l   %d1, %d0
        bne.w   .Lch
        move.l  (%sp)+, %d6
.Lnext: addq.l  #1, %d6
        moveq   #4, %d0
        cmp.l   %d0, %d6
        bne.w   .Lband

        movea.l 72(%sp), %a5                    | output level, back to the master's scale, clamp
        move.l  LVL(%a5), %d6
        movea.l 80(%sp), %a0
        moveq   #2*FR, %d7
        move.l  #0x7fffff, %d2
        move.l  #-0x7fffff, %d3
.Lpost: move.l  (%a0), %d0
        tst.l   %d6
        beq.b   .Lp1
        mac.l   %d6, %d0, %acc0
        movclr.l %acc0, %d0
        asl.l   #4, %d0
.Lp1:   addq.l  #2, %d0
        asr.l   #2, %d0
        cmp.l   %d2, %d0
        ble.b   .Lp2
        move.l  %d2, %d0
.Lp2:   cmp.l   %d3, %d0
        bge.b   .Lp3
        move.l  %d3, %d0
.Lp3:   asl.l   #8, %d0                         | back to the master's own scale
        move.l  %d0, (%a0)+
        subq.l  #1, %d7
        bne.b   .Lpost

        move.l  64(%sp), %d0
        move.l  %d0, %acc0
        move.l  68(%sp), %d0
        move.l  %d0, %accext01
        move.l  60(%sp), %d0
        move.l  %d0, %macsr
        bra.b   .Lret
.Loff:  lea     eq_was, %a1
        clr.l   (%a1)
        clr.l   4(%a1)
        clr.l   8(%a1)
        clr.l   12(%a1)
.Lret:  movem.l (%sp), %d0-%d7/%a0-%a6
        lea     76(%sp), %sp
        rts

        .section .bss
        .balign 4
eq_st:  .skip   64                              | [band][channel] {ic1, ic2}
eq_was: .skip   16                              | band ran in the last block
