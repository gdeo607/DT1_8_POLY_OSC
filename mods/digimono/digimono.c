/* Digi Mono: synth machines for the audio tracks (DESIGN.md). The render side.
 *
 * digimono_blocks() runs once a render block, after the voice loop has left each voice's 32 Q31 samples at
 * 0x80001a18 + 128 v and before the filter, amp envelope and mixer stages work on them. For every voice
 * playing one of our machines (core_track_machine 20..25; they render as ONESHOT) it writes the engine's
 * block there, so the voice's filter, amp envelope, VOL, LFOs, sends and level follow as for a sample. Firmware addresses are OS 1.53's; how each was found: docs/TECHNICAL_NOTES.md.
 */
#include "mono.h"

#define MACH_FIRST   20                      /* digimono_m20..m25 in glue.s: SIN NOIS SAW PULS ENS VO */
extern volatile uint8_t core_track_machine[8];                  /* core 2.1: the machine each voice plays */
#define VOICE_MACH   core_track_machine
#define VOICE_START  (*(volatile const uint32_t *)0x80001228) /* bit v: voice v (re)started this block */
#define VOICE_NOTE   ((volatile const int32_t *)0x80001f28)   /* per voice: MIDI note << 16 */
#define VOICE_WORDS  0x80002772                /* smoothed parameter words, 106 bytes a voice */
#define BLOCK(v)     ((int32_t *)(0x80001a18 + 128 * (v)))   /* voice v's 32 samples, Q31 */
/* The amp envelope's phase (0: idle) and level, per track, as the AMP stage leaves them (digisophie reads
 * the same). Not the voice gain at 0x8000edc4 + 94 v + 16: that is LEV^2 x the track level, and LEV is
 * knob H, an engine parameter here. */
#define AMP_PHASE(v) (*(volatile const int32_t *)(0x4199df54 + 12 * (v)))
#define AMP_LEVEL(v) (*(volatile const int32_t *)(0x4199df58 + 12 * (v)))
#define QUIET_BLOCKS 32                      /* 21 ms of a silent envelope: the voice sleeps */

#define SLOT_TUNE    17                        /* SRC knob A */
#define KNOBS        7
static const uint8_t knob_slot[KNOBS] = {18, 19, 21, 22, 23, 24, 20};  /* SRC knobs B C E F G H, then D */

/* Which engine parameter each knob (B C E F G H D) sets, or -1: the knob is not on the machine's page. */
static const int8_t knob_p[MONO_MACHINES][KNOBS] = {
    {-1, -1, -1, -1, -1, -1, -1},       /* SIN                                            */
    { 0,  1,  2, -1, -1, -1, -1},       /* NOIS  ST RED STON                              */
    { 0,  1,  2,  4,  5,  6, -1},       /* SAW   UNIL UNIW UNIX SUBX SUB1 SUB2            */
    { 0,  1,  2,  4,  5,  6,  3},       /* PULS  UNIL UNIW SUB1 PW PWAD PWRS, D SUB2      */
    { 0,  1,  2,  3,  5,  6,  4},       /* ENS   PCH2 PCH3 PCH4 WAVE CHRL CHRW, D PW      */
    { 0,  1,  2,  4,  5,  6,  3},       /* VO    VOC1 VOC2 V-SW CONS CLEN CVOL, D VOIC    */
};

struct digimono_voice {
    struct mono_voice mv;
    uint8_t live;
    uint8_t quiet;                          /* blocks the amp envelope has been silent; QUIET_BLOCKS: asleep */
};
static struct digimono_voice voices[8];

static int16_t word(int v, int slot)
{
    return *(volatile const int16_t *)(VOICE_WORDS + 106 * v + 2 * slot);
}

/* The engine's seven parameters from the SRC knobs B..H (DESIGN.md, "The SRC page"). */
static void params(int v, int model, uint8_t *p)
{
    int i;
    for (i = 0; i < MONO_PARAMS; i++)
        p[i] = 0;
    for (i = 0; i < KNOBS; i++) {
        int w, j = knob_p[model][i];
        if (j < 0)
            continue;
        w = word(v, knob_slot[i]) >> 8;
        p[j] = w < 0 ? 0 : w > 127 ? 127 : (uint8_t)w;
    }
    if (model == MONO_ENS)                  /* PW on D: 0 = square (the engine's 64) .. 127 = thinnest */
        p[4] = (uint8_t)(64 + (p[4] >> 1));
}

static void digimono_block(int v)
{
    struct digimono_voice *d;
    int model, i;
    int32_t pitch;
    uint8_t p[MONO_PARAMS];
    int16_t out[32];
    if ((unsigned)v > 7)
        return;
    model = VOICE_MACH[v] - MACH_FIRST;
    if ((unsigned)model >= MONO_MACHINES)
        return;
    d = &voices[v];
    if (!d->live) {
        mono_init(&d->mv);
        d->mv.rng ^= (uint32_t)v * 0x9e3779b9u;
        d->live = 1;
        d->quiet = QUIET_BLOCKS;
    }
    if ((VOICE_START >> v) & 1) {
        mono_trig(&d->mv, model);
        d->quiet = 0;
    } else {
        int32_t l = AMP_LEVEL(v);
        if (AMP_PHASE(v) != 0 || (l < 0 ? -l : l) > (1 << 19))
            d->quiet = 0;
        else if (d->quiet < QUIET_BLOCKS)
            d->quiet++;
        if (d->quiet >= QUIET_BLOCKS)
            return;                         /* asleep: the stock block is silence already */
    }
    /* the pitch as the render computes a sample's: the note plus TUNE (after the LFOs), in Q16 semitones */
    pitch = VOICE_NOTE[v] + ((int32_t)(word(v, SLOT_TUNE) - 16384) << 8);
    params(v, model, p);
    mono_render(&d->mv, model, p, mono_pitch_inc(pitch >> 9), out, 32);
    for (i = 0; i < 32; i++)
        BLOCK(v)[i] = (int32_t)out[i] << 16;
}

void digimono_blocks(void)
{
    int v;
    for (v = 0; v < 8; v++)
        digimono_block(v);
}

/* ---- the SRC page ------------------------------------------------------------------------------- */

#define ACTIVE_TRACK (*(volatile const uint32_t *)0x4197b6b4)
#define UI_KIT       (*(uint8_t *volatile const *)0x4199dc44)   /* its sounds: + 0x20 + 0xa2 t */
#define SLICE_ID_B   0x85                      /* SLICE's SRC page: ids 0x84..0x8b = knobs A..H */
#define FMT_INT      ((void *)0x4197c7fc)      /* the firmware's plain-number formatter (BR's) */
#define FMT_BUF      ((char *)0x4197ce98)      /* where 0x400657ee writes a value's text */
typedef void (*fmt_t)(void *fmt, int32_t value, char *buf);
#define FORMAT       ((fmt_t)0x40151cc2)

/* the knobs: B C E F G H D ("-": not on the page) */
static const char *const sname[MONO_MACHINES][KNOBS] = {
    {"-",    "-",    "-",    "-",    "-",    "-",    "-"},
    {"ST",   "RED",  "STON", "-",    "-",    "-",    "-"},
    {"UNIL", "UNIW", "UNIX", "SUBX", "SUB1", "SUB2", "-"},
    {"UNIL", "UNIW", "SUB1", "PW",   "PWAD", "PWRS", "SUB2"},
    {"PCH2", "PCH3", "PCH4", "WAVE", "CHRL", "CHRW", "PW"},
    {"VOC1", "VOC2", "V-SW", "CONS", "CLEN", "CVOL", "VOIC"},
};
static const char *const lname[MONO_MACHINES][KNOBS] = {
    {"-", "-", "-", "-", "-", "-", "-"},
    {"Sample Hold Rate", "Red Noise", "Tuned Noise", "-", "-", "-", "-"},
    {"Unison Level", "Unison Detune", "Unison Voices", "Sub Shape", "Sub 1 Oct Lev", "Sub 2 Oct Lev", "-"},
    {"Unison Level", "Unison Detune", "Sub 1 Oct Lev", "Pulse Width", "PWM Depth", "PWM Rate", "Sub 2 Oct Lev"},
    {"Pitch Osc 2", "Pitch Osc 3", "Pitch Osc 4", "Saw-Pulse", "Chorus Level", "Chorus Width", "Pulse Width"},
    {"Vowel 1", "Vowel 2", "Vowel Glide", "Consonant", "Cons. Length", "Cons. Level", "Breath"},
};

/* how each knob's value reads */
enum { F_NUM, F_VOICES, F_SEMI, F_PW, F_PWENS, F_VOWEL, F_CONS, F_MS, F_SHAPE };
static const uint8_t knob_fmt[MONO_MACHINES][KNOBS] = {
    {F_NUM, F_NUM, F_NUM, F_NUM, F_NUM, F_NUM, F_NUM},
    {F_NUM, F_NUM, F_NUM, F_NUM, F_NUM, F_NUM, F_NUM},
    {F_NUM, F_NUM, F_VOICES, F_SHAPE, F_NUM, F_NUM, F_NUM},
    {F_NUM, F_NUM, F_NUM, F_PW, F_NUM, F_NUM, F_NUM},
    {F_SEMI, F_SEMI, F_SEMI, F_SHAPE, F_NUM, F_NUM, F_PWENS},
    {F_VOWEL, F_VOWEL, F_NUM, F_CONS, F_MS, F_NUM, F_NUM},
};

/* The active track's Digi Mono model, or -1. */
static int active_model(void)
{
    uint32_t t = ACTIVE_TRACK;
    const uint8_t *kit = UI_KIT;
    int m;
    if (t > 7 || !kit)
        return -1;
    m = kit[0x9e + 0xa2 * t] - MACH_FIRST;
    return (unsigned)m < MONO_MACHINES ? m : -1;
}

/* A SLICE page id -> our knob 0..6 (B C E F G H D), or -1 (A = TUNE, anything else). */
static int knob_of(uint32_t id)
{
    static const int8_t k[7] = {0, 1, 6, 2, 3, 4, 5};      /* ids 0x85..0x8b: B C D E F G H */
    return id >= SLICE_ID_B && id < SLICE_ID_B + 7 ? k[id - SLICE_ID_B] : -1;
}

/* The knob of id on the active Digi Mono page, if the machine has it there; else -1. */
static int our_knob(uint32_t id, int *model)
{
    int m = active_model(), k = knob_of(id);
    if (m < 0 || k < 0 || knob_p[m][k] < 0)
        return -1;
    *model = m;
    return k;
}

int digimono_ours(uint32_t id)
{
    int m;
    return our_knob(id, &m) >= 0;
}

const char *digimono_name(uint32_t id, int shortname)
{
    int m, k = our_knob(id, &m);
    if (k < 0)
        return 0;
    return shortname ? sname[m][k] : lname[m][k];
}

int digimono_range(uint32_t id, int32_t *out)
{
    int m;
    if (our_knob(id, &m) < 0)
        return 0;
    out[0] = 0;
    out[1] = 127 << 8;
    out[2] = 0;
    return 1;
}

/* VO's vowels (VOC1, VOC2: the continuum of mono.c's VOWEL, nearest) and consonants (CONS: 8 zones) */
static const char *const vowel_name[10] = {"OO", "U", "AW", "AH", "UH", "AE", "EH", "IH", "EE", "ER"};
static const char *const cons_name[8] = {"-", "S", "SH", "F", "H", "T", "K", "P"};

static char *put_s(char *o, const char *t)
{
    while ((*o = *t++))
        o++;
    return o;
}

static char *put_u(char *o, uint32_t n)
{
    char d[10];
    int i = 0;
    do {
        d[i++] = (char)('0' + n % 10);
        n /= 10;
    } while (n);
    while (i)
        *o++ = d[--i];
    *o = 0;
    return o;
}

/* A knob's value v (0..127) as text: units where it has them. */
static void text_into(int m, int k, int v, char *buf)
{
    char *o = buf;
    switch (knob_fmt[m][k]) {
    case F_VOICES:                          /* mono.c render_saw: 1 to 3 unison saws */
        o = put_u(o, v < 43 ? 1 : v < 86 ? 2 : 3);
        put_s(o, v < 43 ? " SAW" : " SAWS");
        break;
    case F_SEMI: {                          /* render_ens: 63 = the main oscillator's pitch */
        int s = v - 63;
        s = s < -36 ? -36 : s > 36 ? 36 : s;
        if (s > 0)
            *o++ = '+';
        if (s < 0) {
            *o++ = '-';
            s = -s;
        }
        o = put_u(o, (uint32_t)s);
        put_s(o, "st");
        break;
    }
    case F_PW:                              /* duty(): 50 % at 64, 0.763 % a step */
        o = put_u(o, (uint32_t)((50 * 131 + (v - 64) * 100 + 65) / 131));
        put_s(o, "%");
        break;
    case F_PWENS:                           /* D 0..127 -> the engine's 64..127 */
        v = 64 + (v >> 1);
        o = put_u(o, (uint32_t)((50 * 131 + (v - 64) * 100 + 65) / 131));
        put_s(o, "%");
        break;
    case F_VOWEL:
        put_s(o, vowel_name[(v * 9 * 2 + 127) / 254]);
        break;
    case F_CONS:
        put_s(o, cons_name[v >> 4]);
        break;
    case F_MS:                              /* render_vo: CLEN 96 + v^2 x 1188 / 1024 samples */
        o = put_u(o, (uint32_t)((96 + ((v * v * 1188) >> 10)) / 48));
        put_s(o, "ms");
        break;
    case F_SHAPE:                           /* SUBX square..saw, WAVE saw..pulse: a mix, in % */
        o = put_u(o, (uint32_t)((v * 100 + 63) / 127));
        put_s(o, "%");
        break;
    default:
        put_u(o, (uint32_t)v);
    }
}

/* The value pop-up's text (0x400657ee's callers): FMT_BUF, as the firmware's own. */
char *digimono_text(uint32_t id, int32_t value)
{
    int m, k = our_knob(id, &m);
    if (k < 0)
        return 0;
    text_into(m, k, (value >> 8) & 0x7f, FMT_BUF);
    return FMT_BUF;
}

/* A knob's value under it while it turns (0x4000f324, through digichain): into buf; 0 if not ours. */
int digimono_knob_text(uint32_t id, int32_t value, char *buf)
{
    int m, k = our_knob(id, &m);
    if (k < 0)
        return 0;
    text_into(m, k, (value >> 8) & 0x7f, buf);
    return 1;
}

/* The SRC page's layout for a Digi Mono machine (0x400657cc, through digichain): SLICE's, with the
 * knobs the machine does not have emptied (id 0), so they show nothing and turn nothing. 0: not ours. */
#define LAY_SLICE    ((const uint32_t *)0x4197cf5c)    /* 44 bytes; the knobs' ids at +8 (A..H) */
static uint32_t lay[MONO_MACHINES][11];
static uint8_t lay_ok[MONO_MACHINES];

uint32_t *digimono_layout_for(uint32_t machine)
{
    static const uint8_t at[KNOBS] = {3, 4, 6, 7, 8, 9, 5};   /* B C E F G H D: longs at +12 .. +36 */
    int m = (int)machine - MACH_FIRST, i;
    if ((unsigned)m >= MONO_MACHINES)
        return 0;
    if (!lay_ok[m]) {
        for (i = 0; i < 11; i++)
            lay[m][i] = LAY_SLICE[i];
        for (i = 0; i < KNOBS; i++)
            if (knob_p[m][i] < 0)
                lay[m][at[i]] = 0;
        lay_ok[m] = 1;
    }
    return lay[m];
}

/* ---- defaults on a switch ------------------------------------------------------------------------ */
/* Switching a track's machine gives it the parameters' machine's defaults (ONESHOT's: core 2.1), which
 * mean nothing here (ENS would start 36 semitones down). digimono_tick (ev_tick, 30 Hz) watches the UI
 * kit: when a track of the same kit turns into a Digi Mono machine while its knobs still hold switch
 * defaults (ONESHOT's for E F G H, which a stock switch resets, or the Digi Mono machine it was before: the machine
 * list switches as its cursor moves), it sets the new machine's own, through the firmware's knob path
 * (0x400771e8, the engine's copy) and in the kit (what is saved and shown). A kit or sound load that
 * brings its own values matches neither, or comes with a new kit, and is left alone. */
typedef void (*setparam_t)(int32_t value, int32_t voice, int32_t slot);
#define SETPARAM     ((setparam_t)0x400771e8)

static const uint16_t oneshot_def[6] = {0x0300, 0x0000, 0x0000, 0x7800, 0x0000, 0x6400};  /* B C E F G H */
static const uint8_t mono_def[MONO_MACHINES][KNOBS] = {   /* B C E F G H D */
    {0, 0, 0, 0, 0, 0, 0},              /* SIN                                         */
    {0, 0, 0, 0, 0, 0, 0},              /* NOIS  ST RED STON                           */
    {0, 40, 0, 0, 0, 0, 0},             /* SAW   UNIL UNIW UNIX SUBX SUB1 SUB2         */
    {0, 40, 0, 64, 0, 40, 0},           /* PULS  UNIL UNIW SUB1 PW PWAD PWRS, SUB2     */
    {63, 63, 63, 0, 0, 127, 0},         /* ENS   PCH2 PCH3 PCH4 WAVE CHRL CHRW, PW (square) */
    {43, 113, 64, 0, 40, 100, 0},       /* VO    VOC1 (AH) VOC2 (EE) V-SW CONS CLEN CVOL, VOIC */
};

static const uint8_t *seen_kit;
static uint8_t seen_mach[8];

static uint16_t knobw(const uint8_t *snd, int i)
{
    return *(const uint16_t *)(snd + 0x14 + 2 * knob_slot[i]);
}

/* Do knobs B..H hold what a machine switch leaves there? prev: the machine before (id). */
static int switch_defaults(const uint8_t *snd, int prev)
{
    int i, pm = prev - MACH_FIRST;
    if ((unsigned)pm < MONO_MACHINES) {
        for (i = 0; i < KNOBS; i++)
            if (knobw(snd, i) != (uint16_t)(mono_def[pm][i] << 8))
                break;
        if (i == KNOBS)
            return 1;
    }
    for (i = 2; i < 6; i++)                 /* a stock switch resets E..H; B and C it leaves or clears */
        if (knobw(snd, i) != oneshot_def[i])
            return 0;
    return 1;
}

void digimono_tick(void *ctrl)
{
    uint8_t *kit = UI_KIT;
    int t, i;
    (void)ctrl;
    if (!kit)
        return;
    if (kit != seen_kit) {                  /* another pattern's kit: take it as it is */
        for (t = 0; t < 8; t++)
            seen_mach[t] = kit[0x9e + 0xa2 * t];
        seen_kit = kit;
        return;
    }
    for (t = 0; t < 8; t++) {
        uint8_t *snd = kit + 0x20 + 0xa2 * t;
        int m = snd[0x7e], prev = seen_mach[t];
        if (m == prev)
            continue;
        seen_mach[t] = m;
        m -= MACH_FIRST;
        if ((unsigned)m >= MONO_MACHINES || !switch_defaults(snd, prev))
            continue;
        for (i = 0; i < KNOBS; i++) {
            int32_t w = (int32_t)mono_def[m][i] << 8;
            *(uint16_t *)(snd + 0x14 + 2 * knob_slot[i]) = (uint16_t)w;
            SETPARAM(w, t, knob_slot[i]);
        }
    }
}
