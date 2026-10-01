/* Digi Mono: the synth engine (see mono.h, DESIGN.md).
 *
 * Numbers: a phase is a 32-bit fraction of a cycle; an oscillator's output is Q15 (+-32768 = +-1); a level
 * is Q15 (32768 = 1). Aliasing is kept down with polyBLEP: each jump of a saw, square or pulse is smoothed
 * over one sample either side by a two-sample polynomial step. Every product fits in 32 bits.
 */
#include "mono.h"
#include "mono_tables.h"

#define CHO_MASK   (MONO_CHO_LEN - 1)
#define CHO_BASE   (336 << 8)               /* chorus centre delay, 7 ms, Q8 samples  */
#define CHO_DEPTH  120                      /* chorus swing at CHRW 127, samples      */
#define CHO_RATE   53687u                   /* chorus LFO, 0.6 Hz                     */

static uint32_t rnd(struct mono_voice *v)
{
    uint32_t r = v->rng;
    r ^= r << 13;
    r ^= r >> 17;
    r ^= r << 5;
    v->rng = r;
    return r;
}

/* inc * (1 + f/65536), f < 65536 */
static uint32_t scale_up(uint32_t inc, uint32_t f)
{
    return inc + (inc >> 16) * f + (((inc & 0xffff) * f) >> 16);
}

/* inc * (1 - f/65536), f < 65536 */
static uint32_t scale_down(uint32_t inc, uint32_t f)
{
    return inc - (inc >> 16) * f - (((inc & 0xffff) * f) >> 16);
}

static uint32_t pitch_inc_raw(int32_t pitch)
{
    int32_t semi, oct;
    uint32_t inc;
    if (pitch < 0)
        pitch = 0;
    semi = pitch >> 7;                              /* whole semitones above note 0 */
    oct = semi / 12;
    inc = MONO_SEMI_INC[semi - oct * 12];           /* notes 120..131 */
    inc = scale_up(inc, MONO_FINE[pitch & 127]);
    oct = 10 - oct;
    if (oct > 0)
        inc >>= oct < 31 ? oct : 31;
    else if (oct < 0)
        inc = 0xffffffffu;                          /* above note 131: no use to anyone */
    return inc;
}

uint32_t mono_pitch_inc(int32_t pitch)
{
    uint32_t inc = pitch_inc_raw(pitch);
    return inc > MONO_INC_MAX ? MONO_INC_MAX : inc;
}

/* inc moved by s semitones, -36..+36: inc * 2^(semi/12) * 2^(oct - 3), with s + 36 = 12 oct + semi */
static uint32_t interval(uint32_t inc, int32_t s)
{
    int32_t u = s + 36, oct = u / 12;
    inc = scale_up(inc, MONO_SEMI_UP[u - oct * 12]) >> 3;
    if (inc > (MONO_INC_MAX >> oct))
        return MONO_INC_MAX;
    return inc << oct;
}

/* The polyBLEP residual of a falling jump of 2 at t = 0, over a phase t and step dt in 1/65536 cycle. */
static inline int32_t blep(uint32_t t, uint32_t dt)
{
    int32_t x;
    if (t < dt) {
        x = (int32_t)((t << 15) / dt);
        return 2 * x - ((x * x) >> 15) - 32768;
    }
    if (t > 65535 - dt) {
        x = (int32_t)(((65536 - t) << 15) / dt);
        return ((x * x) >> 15) - 2 * x + 32768;
    }
    return 0;
}

static inline int32_t saw(uint32_t t, uint32_t dt)
{
    return (int32_t)t - 32768 - blep(t, dt);
}

static inline int32_t square(uint32_t t, uint32_t dt)
{
    return (t < 32768 ? 32767 : -32768) + blep(t, dt) - blep((t + 32768) & 0xffff, dt);
}

/* A pulse of duty o/65536 from two saws. Mean 0; peak (65536 - o) or o, halved. */
static inline int32_t pulse(uint32_t t, uint32_t o, uint32_t dt)
{
    return (saw(t, dt) - saw((t + o) & 0xffff, dt)) >> 1;
}

static inline int16_t sat16(int32_t x)
{
    return x > 32767 ? 32767 : x < -32768 ? -32768 : (int16_t)x;
}

static inline int32_t lin(int32_t v)                /* 0..127 -> 0..32766, straight */
{
    return v * 258;
}

static inline int32_t tri(uint32_t ph)              /* a triangle, 0..32767 */
{
    uint32_t u = ph >> 16;
    return u < 32768 ? (int32_t)u : (int32_t)(65535 - u);
}

/* Shrink levels whose sum is over 1 so that it is 1. g[0..n-1] Q15. */
static void normalise(int32_t *g, int n)
{
    int32_t i, sum = 0, k;
    for (i = 0; i < n; i++)
        sum += g[i];
    if (sum <= 32768)
        return;
    k = (1 << 30) / sum;
    for (i = 0; i < n; i++)
        g[i] = (g[i] * k) >> 15;
}

/* duty from a PW knob: 64 = 50 %, 0 / 127 = 1.2 % / 98.4 % */
static int32_t duty(int32_t pw)
{
    return 32768 + (pw - 64) * 500;
}

void mono_init(struct mono_voice *v)
{
    uint8_t *b = (uint8_t *)v;
    uint32_t i;
    for (i = 0; i < sizeof *v; i++)
        b[i] = 0;
    v->rng = 0x6d2b79f5u;
}

void mono_trig(struct mono_voice *v, int machine)
{
    int i;
    if (v->rng == 0)
        v->rng = 0x6d2b79f5u;
    v->ph[0] = 0;                                   /* every oscillator here reads 0 at phase 0 */
    for (i = 1; i < 4; i++)
        v->ph[i] = rnd(v);                          /* unison / ensemble: free, like analog ones */
    v->sub = 0;
    v->age = 0;
    v->c_lo = v->c_bp = 0;
    (void)machine;
}

static void render_sin(struct mono_voice *v, uint32_t inc, int16_t *out, int n)
{
    uint32_t p = v->ph[0];
    while (n--) {
        uint32_t i = p >> 23, f = (p >> 7) & 0xffff;
        int32_t a = MONO_SINE[i], b = MONO_SINE[i + 1];
        *out++ = (int16_t)(a + (((b - a) * (int32_t)f) >> 16));
        p += inc;
    }
    v->ph[0] = p;
}

static void render_nois(struct mono_voice *v, const uint8_t *p, uint32_t inc, int16_t *out, int n)
{
    int32_t st = p[0], red = p[1], gt = MONO_GAIN[p[2]];
    uint32_t shi = st ? pitch_inc_raw((135 * 128) - st * 99 * 128 / 127) : 0;
    uint32_t tinc = inc << 1;                       /* tuned: two new values a cycle */
    int32_t a = MONO_GAIN[127 - red] + 256;         /* the red filter, Q15 */
    int32_t mk = 32768 + red * 768;                 /* and its make-up gain, Q15 (x1 .. x4) */
    int32_t hold = v->hold, thold = v->thold, y = v->red;
    uint32_t sh = v->sh, tsh = v->tsh;
    while (n--) {
        int32_t x;
        if (shi == 0) {
            hold = (int32_t)rnd(v) >> 16;
        } else {
            uint32_t s = sh + shi;
            if (s < sh)
                hold = (int32_t)rnd(v) >> 16;
            sh = s;
        }
        if (gt) {
            uint32_t s = tsh + tinc;
            if (s < tsh)
                thold = (int32_t)rnd(v) >> 16;
            tsh = s;
            x = hold + (((thold - hold) * gt) >> 15);
        } else {
            x = hold;
        }
        if (red) {
            y += (((x - y) >> 1) * a) >> 14;
            x = (y * (mk >> 4)) >> 11;
        }
        *out++ = sat16(x);
    }
    v->hold = hold;
    v->thold = thold;
    v->red = y;
    v->sh = sh;
    v->tsh = tsh;
}

/* The oscillators run one at a time over a chunk of up to CHUNK samples, adding into an int32 buffer:
 * each loop then keeps its phase, step and level in registers. */
#define CHUNK 32

/* the main saw or pulse (o = 0: saw), written into acc; counts the wraps for the subs */
static void osc_main(int32_t *acc, uint32_t *ph, uint8_t *sub, uint32_t inc, uint32_t o, int32_t g, int n)
{
    uint32_t p = *ph, dt = inc >> 16;
    uint8_t w = *sub;
    while (n--) {
        uint32_t q = p + inc;
        int32_t s = o ? pulse(p >> 16, o, dt) : saw(p >> 16, dt);
        *acc++ = (s * g) >> 15;
        if (q < p)
            w++;
        p = q;
    }
    *ph = p;
    *sub = w;
}

/* a unison saw or pulse (o = 0: saw), added into acc */
static void osc_add(int32_t *acc, uint32_t *ph, uint32_t inc, uint32_t o, int32_t g, int n)
{
    uint32_t p = *ph, dt = inc >> 16;
    if (o) {
        while (n--) {
            *acc++ += (pulse(p >> 16, o, dt) * g) >> 15;
            p += inc;
        }
    } else {
        while (n--) {
            *acc++ += (saw(p >> 16, dt) * g) >> 15;
            p += inc;
        }
    }
    *ph = p;
}

/* The two subs, one and two octaves down, added into acc: square, faded to a falling saw by x (Q15).
 * p0 / w are the main oscillator's phase and wrap count at the chunk's start. The saw falls so that its
 * fundamental is in phase with the square's (a rising one would cancel most of it half-way). */
static void osc_subs(int32_t *acc, uint32_t p0, uint8_t w, uint32_t inc, int32_t g1, int32_t g2, int32_t x, int n)
{
    uint32_t dt = inc >> 16;
    while (n--) {
        uint32_t q = p0 + inc;
        if (g1) {
            uint32_t t = (((uint32_t)(w & 1) << 31) | (p0 >> 1)) >> 16;
            int32_t sq = square(t, dt >> 1);
            if (x)
                sq += ((-saw(t, dt >> 1) - sq) * x) >> 15;
            *acc += (sq * g1) >> 15;
        }
        if (g2) {
            uint32_t t = (((uint32_t)(w & 3) << 30) | (p0 >> 2)) >> 16;
            int32_t sq = square(t, dt >> 2);
            if (x)
                sq += ((-saw(t, dt >> 2) - sq) * x) >> 15;
            *acc += (sq * g2) >> 15;
        }
        acc++;
        if (q < p0)
            w++;
        p0 = q;
    }
}

static void put(int16_t *out, const int32_t *acc, int n)
{
    while (n--)
        *out++ = sat16(*acc++);
}

static void render_saw(struct mono_voice *v, const uint8_t *p, uint32_t inc, int16_t *out, int n)
{
    int32_t acc[CHUNK], g[6], nu, k, x = lin(p[4]);
    uint32_t iu[4], f = MONO_DETUNE[p[1]];
    nu = p[2] < 43 ? 1 : p[2] < 86 ? 2 : 3;         /* UNIX: how many unison saws */
    iu[1] = scale_up(inc, f);
    iu[2] = scale_down(inc, f);
    iu[3] = scale_up(inc, f >> 1);
    g[0] = 32767;
    g[1] = g[2] = g[3] = MONO_GAIN[p[0]];
    for (k = nu + 1; k < 4; k++)
        g[k] = 0;
    g[4] = MONO_GAIN[p[5]];
    g[5] = MONO_GAIN[p[6]];
    normalise(g, 6);
    while (n > 0) {
        int c = n < CHUNK ? n : CHUNK;
        uint32_t p0 = v->ph[0];
        uint8_t w = v->sub;
        osc_main(acc, &v->ph[0], &v->sub, inc, 0, g[0], c);
        for (k = 1; k < 4; k++)
            if (g[k])
                osc_add(acc, &v->ph[k], iu[k], 0, g[k], c);
        if (g[4] | g[5])
            osc_subs(acc, p0, w, inc, g[4], g[5], x, c);
        put(out, acc, c);
        out += c;
        n -= c;
    }
}

static void render_puls(struct mono_voice *v, const uint8_t *p, uint32_t inc, int16_t *out, int n)
{
    int32_t acc[CHUNK], g[5], o;
    uint32_t iu[3], f = MONO_DETUNE[p[1]];
    /* the pulse width for this block: PW, swung by the PWM LFO (triangle, PWRS) by PWAD */
    o = duty(p[4]) + ((((tri(v->lfo) << 1) - 32767) * ((MONO_GAIN[p[5]] * 30000) >> 15)) >> 15);
    if (o < 1024)
        o = 1024;
    if (o > 64511)
        o = 64511;
    v->lfo += MONO_RATE[p[6]] * (uint32_t)n;
    iu[1] = scale_up(inc, f);
    iu[2] = scale_down(inc, f);
    g[0] = 32767;
    g[1] = g[2] = MONO_GAIN[p[0]];
    g[3] = MONO_GAIN[p[2]];
    g[4] = MONO_GAIN[p[3]];
    normalise(g, 5);
    while (n > 0) {
        int c = n < CHUNK ? n : CHUNK;
        uint32_t p0 = v->ph[0];
        uint8_t w = v->sub;
        osc_main(acc, &v->ph[0], &v->sub, inc, (uint32_t)o, g[0], c);
        if (g[1]) {
            osc_add(acc, &v->ph[1], iu[1], (uint32_t)o, g[1], c);
            osc_add(acc, &v->ph[2], iu[2], (uint32_t)o, g[2], c);
        }
        if (g[3] | g[4])
            osc_subs(acc, p0, w, inc, g[3], g[4], 0, c);
        put(out, acc, c);
        out += c;
        n -= c;
    }
}

/* one ENS oscillator, saw - k * (saw a duty later), added into acc */
static void osc_ens(int32_t *acc, uint32_t *ph, uint32_t inc, uint32_t o, int32_t k, int n)
{
    uint32_t p = *ph, dt = inc >> 16;
    if (k) {
        while (n--) {
            uint32_t t = p >> 16;
            *acc++ += saw(t, dt) - ((saw((t + o) & 0xffff, dt) * k) >> 15);
            p += inc;
        }
    } else {
        while (n--) {
            *acc++ += saw(p >> 16, dt);
            p += inc;
        }
    }
    *ph = p;
}

static void render_ens(struct mono_voice *v, const uint8_t *p, uint32_t inc, int16_t *out, int n)
{
    uint32_t io[4], o = (uint32_t)duty(p[4]);
    int32_t acc[CHUNK], k = lin(p[3]), gc = MONO_GAIN[p[5]], i;
    int32_t nw = (1 << 30) / (32768 + k);           /* keeps saw - k * saw' within +-1 */
    int32_t nc = (1 << 30) / (32768 + gc);          /* and dry + chorus */
    int32_t sw = (lin(p[6]) * CHO_DEPTH) >> 7;      /* chorus swing, Q8 samples */
    int32_t d0, d1, dd;
    uint16_t wr = v->wr;
    io[0] = inc > MONO_INC_MAX ? MONO_INC_MAX : inc;
    for (i = 1; i < 4; i++) {
        int32_t s = (int32_t)p[i - 1] - 63;        /* PCH: 63 = the same pitch */
        io[i] = interval(inc, s < -36 ? -36 : s > 36 ? 36 : s);
    }
    /* A fixed ensemble spread, +4, -4 and +7 cents: oscillators at one pitch beat slowly instead of
     * locking into a comb whose timbre would depend on the phases they started at. */
    io[1] = scale_up(io[1], 152);
    io[2] = scale_down(io[2], 152);
    io[3] = scale_up(io[3], 265);
    /* the chorus delay at the start and the end of the block; the samples between glide */
    d0 = CHO_BASE + ((((tri(v->lfo) << 1) - 32767) * sw) >> 15);
    v->lfo += CHO_RATE * (uint32_t)n;
    d1 = CHO_BASE + ((((tri(v->lfo) << 1) - 32767) * sw) >> 15);
    dd = (d1 - d0) / n;
    while (n > 0) {
        int c = n < CHUNK ? n : CHUNK, j;
        for (j = 0; j < c; j++)
            acc[j] = 0;
        for (i = 0; i < 4; i++)
            osc_ens(acc, &v->ph[i], io[i], o, k, c);
        for (j = 0; j < c; j++) {
            int32_t dry = ((acc[j] >> 2) * (nw >> 1)) >> 14;
            v->dl[wr] = sat16(dry);
            if (gc) {
                int32_t di = d0 >> 8, fr = d0 & 255;
                int32_t a = v->dl[(wr - di) & CHO_MASK], b = v->dl[(wr - di - 1) & CHO_MASK];
                int32_t wet = a + (((b - a) * fr) >> 8);
                dry = ((dry + ((wet * gc) >> 15)) * (nc >> 1)) >> 14;
            }
            *out++ = sat16(dry);
            wr = (wr + 1) & CHO_MASK;
            d0 += dd;
        }
        n -= c;
    }
    v->wr = wr;
}

/* ---- VO: a formant voice ------------------------------------------------------------------------ *
 * A glottal source (a band-limited saw through a one-pole low-pass, with breath noise mixed in by VOIC)
 * through three parallel resonators at a vowel's first three formants. VOC1 and VOC2 pick vowels along
 * a continuum; V-SW glides from VOC1 to VOC2 after the note starts (0: VOC1 only). CONS picks a
 * consonant, a band of noise with its own decay (CLEN) and level (CVOL) at the note's start, the
 * vowel fading in under it. The vowel formants are published averages of measured male vowels
 * (Peterson and Barney, 1952); nothing here comes from the Monomachine. */

/* F1, F2, F3 in Hz, along a continuum: u  U  aw  ah  uh  ae  eh  ih  ee  er */
static const uint16_t VOWEL[10][3] = {
    {300, 870, 2240}, {440, 1020, 2240}, {570, 840, 2410}, {730, 1090, 2440}, {640, 1190, 2390},
    {660, 1720, 2410}, {530, 1840, 2480}, {390, 1990, 2550}, {270, 2290, 3010}, {490, 1350, 1690},
};
static const uint16_t VBW[3] = {80, 100, 140};             /* formant bandwidths, Hz */
static const int16_t VAMP[3] = {16384, 8192, 4096};        /* formant levels, Q14: 1, -6, -12 dB */
/* consonants: none, S, SH, F, H, T, K, P: centre (Hz), q (Q14: bandwidth / centre), longest (ms) */
static const uint16_t CONS[8][3] = {
    {0, 0, 0}, {6000, 4900, 400}, {2800, 8200, 400}, {7000, 16384, 400}, {1200, 16384, 400},
    {4000, 6500, 30}, {1800, 6500, 40}, {700, 9800, 30},
};

/* 2 sin(pi f / 48000) in Q14, f < 12 kHz: the state-variable filter's frequency coefficient */
static int32_t svf_f(int32_t hz)
{
    int32_t pos = (hz * 1398) >> 10;                        /* Q8 index into MONO_SINE: hz * 512 / 96000 */
    int32_t i = pos >> 8, fr = pos & 255;
    int32_t a = MONO_SINE[i], b = MONO_SINE[i + 1];
    return a + (((b - a) * fr) >> 8);                      /* sin in Q15 = 2 sin in Q14 */
}

/* The same at 24 kHz, where VO's vowel runs: hz * 512 / 48000 */
static int32_t svf_f24(int32_t hz)
{
    int32_t pos = (hz * 2796) >> 10;
    int32_t i = pos >> 8, fr = pos & 255;
    int32_t a = MONO_SINE[i], b = MONO_SINE[i + 1];
    return a + (((b - a) * fr) >> 8);
}

static void render_vo(struct mono_voice *v, const uint8_t *p, uint32_t inc, int16_t *out, int n)
{
    int32_t fk[3], qk[3], gk[3], k, cf = 0, cq = 0, cg, lenc, age0, pos1, pos2, pos, m, breath;
    uint32_t dt = inc >> 16, ph = v->ph[0], morph;
    int ct = p[4] >> 4;                                     /* CONS: 8 zones */
    /* the vowel: VOC1 -> VOC2 by V-SW, per block */
    pos1 = p[0] * 9 * 256 / 127;                            /* Q8 along the continuum 0..9 */
    pos2 = p[1] * 9 * 256 / 127;
    if (p[2] == 0) {
        m = 0;
    } else {
        uint32_t mi = MONO_RATE[127 - p[2]] * 10;           /* 5 ms .. 2 s from VOC1 to VOC2 */
        uint32_t a = v->age > 0x7fffff ? 0x7fffff : v->age;
        morph = (a >= 0xffffffffu / (mi ? mi : 1)) ? 0xffffffffu : a * mi;
        m = (int32_t)(morph >> 17);                         /* Q15 */
    }
    pos = pos1 + (((pos2 - pos1) * m) >> 15);
    for (k = 0; k < 3; k++) {
        int32_t i = pos >> 8, fr = pos & 255, hz;
        if (i >= 9) {
            i = 8;
            fr = 256;
        }
        hz = VOWEL[i][k] + (((VOWEL[i + 1][k] - VOWEL[i][k]) * fr) >> 8);
        fk[k] = svf_f24(hz);                                /* the vowel runs at 24 kHz */
        qk[k] = (VBW[k] << 14) / hz;                        /* 1 / Q, Q14 */
        gk[k] = VAMP[k];
    }
    /* the consonant */
    lenc = 96 + ((p[5] * p[5] * 1188) >> 10);               /* CLEN: 2 ms .. 400 ms */
    if (ct && lenc > CONS[ct][2] * 48)
        lenc = CONS[ct][2] * 48;
    if (ct) {
        cf = svf_f(CONS[ct][0]);
        cq = CONS[ct][1];
    }
    cg = MONO_GAIN[p[6]];
    breath = MONO_GAIN[p[3]];
    age0 = (int32_t)(v->age > 0x7fffffff ? 0x7fffffff : v->age);
    {
        /* The vowel (source, breath, three formants) runs at 24 kHz, every other output sample: everything
         * it makes is under 4 kHz. Between, the output is the line from the last 24 kHz sample to the new
         * one (ph[1] holds the last; bit 0 of pad, which sample of the pair is next: VO uses neither
         * otherwise). The consonant, up to 6 kHz, runs at 48 kHz while it lasts. The loop keeps the state
         * in locals; the consonant's fade-in and decay are ramps with a step worked out once a block; the
         * formant levels (VAMP: 1, 1/2, 1/4) are shifts. */
        int32_t lo0 = v->f_lo[0], lo1 = v->f_lo[1], lo2 = v->f_lo[2];
        int32_t bp0 = v->f_bp[0], bp1 = v->f_bp[1], bp2 = v->f_bp[2];
        int32_t glp = v->glp;
        const int32_t f0 = fk[0], f1 = fk[1], f2 = fk[2], q0 = qk[0], q1 = qk[1], q2 = qk[2];
        int32_t half = lenc >> 1, vstep = 0, einv = 0, yh, last;
        uint32_t r = v->rng, inc2 = inc > 0x3fffffffu ? 0x7fffffffu : inc << 1, dt2 = inc2 >> 16;
        int par;
        (void)gk;
        (void)dt;
        if (v->age == 0) {                                  /* a new note: the pair starts afresh */
            v->ph[1] = 0;
            v->pad = 0;
        }
        last = (int32_t)v->ph[1];
        par = v->pad & 1;
        yh = last;
        if (ct) {
            vstep = (32767 << 8) / (half + 1);              /* venv = age0 x 32767 / (half + 1), Q8 */
            einv = (1 << 23) / lenc;                        /* e = (lenc - age0) << 15 / lenc, Q8 */
        }
/* one output sample of the vowel into y: a new 24 kHz sample on the first of a pair, else the held one */
#define VO_VOWEL(y) do {                                                                \
            if (!par) {                                                                 \
                int32_t s_, hp_;                                                        \
                s_ = saw(ph >> 16, dt2);                                                \
                ph += inc2;                                                             \
                glp += ((s_ - glp) * 7) >> 4;               /* about 2 kHz, one pole */ \
                s_ = glp;                                                               \
                if (breath) {                                                           \
                    r ^= r << 13; r ^= r >> 17; r ^= r << 5;                            \
                    s_ += (((((int32_t)r >> 16) - s_) >> 1) * breath) >> 14;            \
                }                                                                       \
                lo0 += (f0 * bp0) >> 14;                                                \
                hp_ = ((s_ * q0) >> 14) - lo0 - ((q0 * bp0) >> 14);                     \
                bp0 += (f0 * hp_) >> 14;                                                \
                lo1 += (f1 * bp1) >> 14;                                                \
                hp_ = ((s_ * q1) >> 14) - lo1 - ((q1 * bp1) >> 14);                     \
                bp1 += (f1 * hp_) >> 14;                                                \
                lo2 += (f2 * bp2) >> 14;                                                \
                hp_ = ((s_ * q2) >> 14) - lo2 - ((q2 * bp2) >> 14);                     \
                bp2 += (f2 * hp_) >> 14;                                                \
                yh = bp0 + (bp1 >> 1) + (bp2 >> 2);                                     \
                y = (last + yh) >> 1;                       /* halfway from the last */ \
                last = yh;                                                              \
            } else {                                                                    \
                y = yh;                                                                 \
            }                                                                           \
            par ^= 1;                                                                   \
        } while (0)
        if (ct && age0 < lenc) {
            /* while the consonant lasts: the vowel fades in over its first half under a noise band at
             * 48 kHz that decays; both ramps are running sums, Q8 */
            int32_t clo = v->c_lo, cbp = v->c_bp;
            int32_t va = age0 * vstep, ea = (lenc - age0) * einv;
            while (n && age0 < lenc) {
                int32_t y, x, nz, hp, venv = age0 < half ? va >> 8 : 32767;
                VO_VOWEL(y);
                x = (y * (venv >> 1)) >> 13;                /* x2 make-up with the fade */
                r ^= r << 13; r ^= r >> 17; r ^= r << 5;
                nz = (int32_t)r >> 17;
                clo += (cf * cbp) >> 14;
                hp = ((nz * cq) >> 14) - clo - ((cq * cbp) >> 14);
                cbp += (cf * hp) >> 14;
                x += (((cbp * (ea >> 8)) >> 15) * cg) >> 14;    /* x2: the band's level is its q's */
                *out++ = sat16(x);
                va += vstep;
                ea -= einv;
                age0++;
                n--;
            }
            v->c_lo = clo;
            v->c_bp = cbp;
        }
        if (n > 0) {                                        /* the vowel alone */
            int32_t rest = n;
            while (n--) {
                int32_t y;
                VO_VOWEL(y);
                *out++ = sat16((y * 16383) >> 13);
            }
            age0 = age0 > 0x7fffffff - rest ? 0x7fffffff : age0 + rest;
        }
#undef VO_VOWEL
        v->f_lo[0] = lo0; v->f_lo[1] = lo1; v->f_lo[2] = lo2;
        v->f_bp[0] = bp0; v->f_bp[1] = bp1; v->f_bp[2] = bp2;
        v->glp = glp; v->rng = r;
        v->ph[1] = (uint32_t)last;
        v->pad = (uint8_t)par;
    }
    v->ph[0] = ph;
    v->age = (uint32_t)age0;
}

void mono_render(struct mono_voice *v, int machine, const uint8_t *p, uint32_t inc, int16_t *out, int n)
{
    if (inc > MONO_INC_MAX)
        inc = MONO_INC_MAX;
    switch (machine) {
    case MONO_SIN:  render_sin(v, inc, out, n); break;
    case MONO_NOIS: render_nois(v, p, inc, out, n); break;
    case MONO_SAW:  render_saw(v, p, inc, out, n); break;
    case MONO_PULS: render_puls(v, p, inc, out, n); break;
    case MONO_ENS:  render_ens(v, p, inc, out, n); break;
    case MONO_VO:   render_vo(v, p, inc, out, n); break;
    default:
        while (n--)
            *out++ = 0;
    }
}
