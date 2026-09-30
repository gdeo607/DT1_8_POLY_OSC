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
#define VOICE_GAIN(v) (*(volatile const int32_t *)(0x8000edc4 + 94 * (v) + 16))   /* 0: not playing */

#define SLOT_TUNE    17                        /* SRC knob A */
static const uint8_t knob_slot[6] = {18, 19, 21, 22, 23, 24};  /* SRC knobs B, C, E, F, G, H */

struct digimono_voice {
    struct mono_voice mv;
    uint8_t live;
};
static struct digimono_voice voices[8];

static int16_t word(int v, int slot)
{
    return *(volatile const int16_t *)(VOICE_WORDS + 106 * v + 2 * slot);
}

/* The engine's seven parameters from the six free SRC knobs (DESIGN.md, "The SRC page"). */
static void params(int v, int model, uint8_t *p)
{
    uint8_t k[6];
    int i;
    for (i = 0; i < 6; i++) {
        int w = word(v, knob_slot[i]) >> 8;
        k[i] = w < 0 ? 0 : w > 127 ? 127 : (uint8_t)w;
    }
    for (i = 0; i < MONO_PARAMS; i++)
        p[i] = 0;
    switch (model) {
    case MONO_NOIS:
        p[0] = k[0]; p[1] = k[1]; p[2] = k[2];
        break;
    case MONO_SAW:                              /* UNIL UNIW UNIX - SUBX SUB1 SUB2 */
        p[0] = k[0]; p[1] = k[1]; p[2] = k[2]; p[4] = k[3]; p[5] = k[4]; p[6] = k[5];
        break;
    case MONO_PULS:                             /* UNIL UNIW SUB1 (SUB2) PW PWAD PWRS */
        p[0] = k[0]; p[1] = k[1]; p[2] = k[2]; p[4] = k[3]; p[5] = k[4]; p[6] = k[5];
        break;
    case MONO_ENS:                              /* PCH2 PCH3 PCH4 WAVE (PW) CHRL CHRW */
        p[0] = k[0]; p[1] = k[1]; p[2] = k[2]; p[3] = k[3]; p[4] = 64; p[5] = k[4]; p[6] = k[5];
        break;
    case MONO_VO:                               /* VOC1 VOC2 V-SW (VOIC) CONS CLEN CVOL */
        p[0] = k[0]; p[1] = k[1]; p[2] = k[2]; p[3] = 0; p[4] = k[3]; p[5] = k[4]; p[6] = k[5];
        break;
    }
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
    }
    if ((VOICE_START >> v) & 1)
        mono_trig(&d->mv, model);
    else if (VOICE_GAIN(v) == 0)
        return;                             /* not started, or stopped: the stock block is silence already */
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

/* the knobs: B C E F G H */
static const char *const sname[MONO_MACHINES][6] = {
    {"-",    "-",    "-",    "-",    "-",    "-"},
    {"ST",   "RED",  "STON", "-",    "-",    "-"},
    {"UNIL", "UNIW", "UNIX", "SUBX", "SUB1", "SUB2"},
    {"UNIL", "UNIW", "SUB",  "PW",   "PWAD", "PWRS"},
    {"PCH2", "PCH3", "PCH4", "WAVE", "CHRL", "CHRW"},
    {"VOC1", "VOC2", "V-SW", "CONS", "CLEN", "CVOL"},
};
static const char *const lname[MONO_MACHINES][6] = {
    {"-", "-", "-", "-", "-", "-"},
    {"Sample Hold", "Red Noise", "Tuned Noise", "-", "-", "-"},
    {"Unison Level", "Unison Width", "Unison Voices", "Sub Shape", "Sub 1 Oct", "Sub 2 Oct"},
    {"Unison Level", "Unison Width", "Sub 1 Oct", "Pulse Width", "PWM Depth", "PWM Rate"},
    {"Pitch 2", "Pitch 3", "Pitch 4", "Saw-Pulse", "Chorus Level", "Chorus Width"},
    {"Vowel 1", "Vowel 2", "Vowel Glide", "Consonant", "Cons. Length", "Cons. Level"},
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

/* A SLICE page id -> our knob 0..5 (B C E F G H), or -1 (A = TUNE, D = SAMP, anything else). */
static int knob_of(uint32_t id)
{
    static const int8_t k[7] = {0, 1, -1, 2, 3, 4, 5};
    return id >= SLICE_ID_B && id < SLICE_ID_B + 7 ? k[id - SLICE_ID_B] : -1;
}

const char *digimono_name(uint32_t id, int shortname)
{
    int m = active_model(), k = knob_of(id);
    if (m < 0 || k < 0)
        return 0;
    return shortname ? sname[m][k] : lname[m][k];
}

int digimono_range(uint32_t id, int32_t *out)
{
    if (active_model() < 0 || knob_of(id) < 0)
        return 0;
    out[0] = 0;
    out[1] = 127 << 8;
    out[2] = 0;
    return 1;
}

/* VO's vowels (VOC1, VOC2: the continuum of mono.c's VOWEL, nearest) and consonants (CONS: 8 zones) */
static const char *const vowel_name[10] = {"OO", "U", "AW", "AH", "UH", "AE", "EH", "IH", "EE", "ER"};
static const char *const cons_name[8] = {"-", "S", "SH", "F", "H", "T", "K", "P"};

char *digimono_text(uint32_t id, int32_t value)
{
    int m = active_model(), k = knob_of(id), v = (value >> 8) & 0x7f;
    const char *t = 0;
    if (m < 0 || k < 0)
        return 0;
    if (m == MONO_VO && k <= 1)
        t = vowel_name[(v * 9 * 2 + 127) / 254];
    else if (m == MONO_VO && k == 3)
        t = cons_name[v >> 4];
    if (t) {
        char *o = FMT_BUF;
        while ((*o++ = *t++))
            ;
        return FMT_BUF;
    }
    FORMAT(FMT_INT, value, FMT_BUF);
    return FMT_BUF;
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
static const uint8_t mono_def[MONO_MACHINES][6] = {
    {0, 0, 0, 0, 0, 0},                 /* SIN                                   */
    {0, 0, 0, 0, 0, 0},                 /* NOIS  ST RED STON                     */
    {0, 40, 0, 0, 0, 0},                /* SAW   UNIL UNIW UNIX SUBX SUB1 SUB2   */
    {0, 40, 0, 64, 0, 40},              /* PULS  UNIL UNIW SUB PW PWAD PWRS      */
    {63, 63, 63, 0, 0, 127},            /* ENS   PCH2 PCH3 PCH4 WAVE CHRL CHRW   */
    {43, 113, 64, 0, 40, 100},          /* VO    VOC1 (AH) VOC2 (EE) V-SW CONS CLEN CVOL */
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
        for (i = 0; i < 6; i++)
            if (knobw(snd, i) != (uint16_t)(mono_def[pm][i] << 8))
                break;
        if (i == 6)
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
        for (i = 0; i < 6; i++) {
            int32_t w = (int32_t)mono_def[m][i] << 8;
            *(uint16_t *)(snd + 0x14 + 2 * knob_slot[i]) = (uint16_t)w;
            SETPARAM(w, t, knob_slot[i]);
        }
    }
}
