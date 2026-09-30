/* Digi Mono: a synth engine for the Digitakt's audio tracks, after the Monomachine's machines.
 *
 * A clean-room engine: written from the Monomachine's public manual (machine names, parameter names and
 * what each is described to do), not from its firmware. It contains no Elektron code or data and does not
 * try to be sample-exact; see mods/digimono/DESIGN.md.
 *
 * It renders one voice's oscillator into a block of 16-bit mono samples, the form a sample voice's data
 * has, so the Digitakt's own filter, amp envelope, LFOs and effects follow it unchanged. Plain C with 32-bit
 * integer arithmetic only (no 64-bit maths, no floating point, no library calls): it builds for the
 * MCF54455 with elekloader's flags and for a PC with any C compiler, bit for bit the same.
 */
#ifndef MONO_H
#define MONO_H

#include <stdint.h>

/* The machines. Numbered for this engine only; the SRC machine list maps onto them. */
enum {
    MONO_SIN  = 0,      /* GND-SIN     a sine                                                     */
    MONO_NOIS = 1,      /* GND-NOIS    noise: sample and hold, red, tuned                         */
    MONO_SAW  = 2,      /* SWAVE-SAW   band-limited saw, unison, two sub-oscillators              */
    MONO_PULS = 3,      /* SWAVE-PULS  band-limited pulse, PWM, unison, two sub-oscillators       */
    MONO_ENS  = 4,      /* SWAVE-ENS   four oscillators at set intervals, saw..pulse, chorus      */
    MONO_VO   = 5,      /* VO-6        a formant voice: vowel 1 -> vowel 2, consonants              */
    MONO_MACHINES
};

/* The seven parameters of a machine: the Monomachine SYN page's first seven knobs, 0..127. Its eighth,
 * TUNE, is the Digitakt's own SRC TUNE, which reaches the engine through the phase increment.
 *
 *            p[0]  p[1]  p[2]  p[3]  p[4]  p[5]  p[6]
 *   SIN      -     -     -     -     -     -     -
 *   NOIS     ST    RED   STON  -     -     -     -
 *   SAW      UNIL  UNIW  UNIX  -     SUBX  SUB1  SUB2
 *   PULS     UNIL  UNIW  SUB1  SUB2  PW    PWAD  PWRS
 *   ENS      PCH2  PCH3  PCH4  WAVE  PW    CHRL  CHRW
 *   VO       VOC1  VOC2  V-SW  VOIC  CONS  CLEN  CVOL
 */
#define MONO_PARAMS 7

#define MONO_CHO_LEN 512            /* the ENS chorus delay line, samples (10.7 ms); a power of two */
#define MONO_INC_MAX 0x40000000u    /* 12 kHz: the highest fundamental the oscillators play         */

/* One voice's state. Zero it once (or call mono_init); mono_trig starts a note. 1,112 bytes: 48 of
 * 32-bit words and bytes, the chorus line (16-bit), then the VO's state (32-bit words only). */
struct mono_voice {
    uint32_t ph[4];                 /* oscillator phases: main + unison (SAW, PULS), osc 1..4 (ENS)  */
    uint32_t lfo;                   /* PULS: the PWM LFO; ENS: the chorus LFO                         */
    uint32_t rng;                   /* noise generator state, never 0                                */
    uint32_t sh;                    /* NOIS: the sample-and-hold clock                               */
    uint32_t tsh;                   /* NOIS: the tuned sample-and-hold clock                         */
    int32_t  hold, thold, red;      /* NOIS: held values, the red (low-pass) filter's state          */
    uint16_t wr;                    /* ENS: chorus write position                                    */
    uint8_t  sub;                   /* SAW, PULS: main-oscillator wraps, bit 0 / bits 0-1 = sub 1 / 2 */
    uint8_t  pad;
    int16_t  dl[MONO_CHO_LEN];      /* ENS: chorus delay line                                        */
    int32_t  f_lo[3], f_bp[3];      /* VO: the three formant resonators                              */
    int32_t  c_lo, c_bp;            /* VO: the consonant's noise band                                */
    int32_t  glp;                   /* VO: the glottal source's low-pass                             */
    uint32_t age;                   /* VO: samples since the note started, saturating                */
};

/* Clear a voice. */
void mono_init(struct mono_voice *v);

/* Start a note: the oscillators restart at a known phase (the unison ones at spread phases), the
 * sub-oscillators in step with the main one. Noise and LFO state carry on. */
void mono_trig(struct mono_voice *v, int machine);

/* Render n samples (n > 0) of machine `machine` with parameters p[0..6] at phase increment inc
 * (a 32-bit phase step per 48 kHz sample; mono_pitch_inc makes one from a note) into out.
 * Parameters and inc are taken as constant over the block. Out-of-range machines render silence. */
void mono_render(struct mono_voice *v, int machine, const uint8_t *p, uint32_t inc, int16_t *out, int n);

/* The phase increment of a pitch in 1/128 semitone, MIDI note 0 = 0 (note 60 = 7680 = middle C),
 * clamped to MONO_INC_MAX. */
uint32_t mono_pitch_inc(int32_t pitch);

#endif
