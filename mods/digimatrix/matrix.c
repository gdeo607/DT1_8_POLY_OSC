/* Digi Matrix: a modulation matrix that routes any track's LFO to any parameter of any track.
 *
 * Stock, each of a track's two LFOs modulates one parameter of its own track and nothing else. The
 * engine's LFO stage (0x400ed53e) walks the 8 voices, and for each of a voice's two LFOs reads the
 * LFO's DEST slot and DEP from the smoothed parameter words of that voice, works out the waveform's
 * current value and adds value * depth into the destination word -- always the same voice's.
 *
 * The matrix adds 8 routing slots on top of that. Each slot is
 *
 *      SRC: a track (1..8) and one of its two LFOs
 *      DST: a track (1..8) and one of its sound parameters
 *      DEP: its own depth, -64..+64, independent of the source LFO's own DEP
 *      OWN: whether the source LFO still modulates its own track as well
 *
 * so one LFO can drive several parameters across several tracks, each with its own amount. The LFO's
 * own DEP keeps controlling only its own track's modulation.
 *
 * How it hooks in (matrix_glue.s): the smoothing stage rewrites every voice's parameter words at the
 * start of every audio block, then the LFO stage adds its modulation on top. We run twice around that
 * LFO stage. Before it, a slot whose OWN is off has the source LFO's DEST word set to -1, which the
 * stage reads as "no destination" and skips (the word is put back afterwards; it is rewritten from
 * scratch next block anyway). After it, each slot reads its source LFO's value where the stage
 * left it and adds value * depth into the destination track's parameter word, with the same clamp the
 * stock stage uses. So the matrix is applied once per audio block, like the LFOs themselves.
 *
 * Storage: the matrix belongs to the pattern, in the kit: slot i in track i + 1's sound, three bytes of
 * the persistent map in kitstore.h (routing high byte, routing low byte, depth + 128). So every pattern
 * has its own matrix, it is saved with the project and it survives a power cycle. 0 -- what every existing kit
 * holds -- is an empty slot. The routing is two bytes, so it is written with the slot switched off in
 * between: the audio engine never reads half an old routing and half a new one as an active slot.
 *
 * UI: SETTINGS > MOD MATRIX opens a page with the 8 slots. UP/DOWN choose one, YES turns it on and
 * off, NO leaves. The knobs edit the slot under the cursor: A source track, B source LFO, C
 * destination track, D destination parameter, E depth, F whether the LFO keeps its own track.
 */
typedef unsigned int u32;
typedef unsigned short u16;

/* ---- firmware (OS 1.53) ---- */
#define ENGINE_KIT   (*(unsigned char *volatile *)0x800019ac)
#define UI_KIT       (*(unsigned char *volatile *)0x4199dc44)
#define INVALIDATE   ((void (*)(void *))0x400c9812)
#define FILLRECT     ((void (*)(void *, int, int, int, int, int))0x400c19a6)
#define TEXT         ((void (*)(void *, const void *, int, int, int, const char *, ...))0x400c257c)
#define FONT5        ((const void *)0x40200b0c)

/* The LFO stage's own state, 80 bytes a voice: the value it last worked out for LFO1 is at +0x00 of
 * the voice's block and LFO2's at +0x28, both as a signed 32-bit fraction of full scale. */
#define LFOVAL(v, n) (*(volatile int *)(0x421f3e14 + 80 * (v) + ((n) ? 0x28 : 0)))

/* The smoothed parameter words the engine plays from: 53 words a voice, slot s of voice v at
 * base + 18 + 106 * v + 2 * s (the LFO stage's own addressing). */
#define VOICE(p, v)  ((volatile short *)((char *)(p) + 18 + 106 * (v)))
#define PARAM_MAX    32512

/* the matrix's rows in the kit: three bytes a slot of the persistent map (kitstore.h) */
#include "kitstore.h"
#define MXB(i, k)      (6 * (i) + (k))
static struct kstore store;
static unsigned char mxmask(int n) { return n % 6 < 3 ? 0xff : 0; }
#define ROUTEW(kit, i) ((u16)((XB(kit, MXB(i, 0)) << 8) | XB(kit, MXB(i, 1))))
#define DEPTHW(kit, i) ((u16)XB(kit, MXB(i, 2)))

static void put_route(unsigned char *kit, int i, u16 r)
{
    XB(kit, MXB(i, 1)) = (unsigned char)(XB(kit, MXB(i, 1)) & ~0x80);   /* off while it changes */
    XB(kit, MXB(i, 0)) = (unsigned char)(r >> 8);
    XB(kit, MXB(i, 1)) = (unsigned char)r;
}

static void put_depth(unsigned char *kit, int i, u16 d)
{
    XB(kit, MXB(i, 2)) = (unsigned char)d;
}

/* the routing word */
#define R_STRK(r)  ((r) & 7)                    /* source track */
#define R_SLFO(r)  (((r) >> 3) & 1)             /* 0 = LFO1, 1 = LFO2 */
#define R_DTRK(r)  (((r) >> 4) & 7)             /* destination track */
#define R_ON(r)    ((r) & 0x80)                 /* the slot is on */
#define R_DEST(r)  ((int)(((r) >> 8) & 0x7f) - 1)   /* destination slot, -1 = none */
#define R_OWN(r)   ((r) & 0x8000)               /* the source LFO keeps its own track */
#define ROUTE(strk, slfo, dtrk, on, dest, own) \
    ((u16)(((strk) & 7) | (((slfo) & 1) << 3) | (((dtrk) & 7) << 4) | ((on) ? 0x80 : 0) \
           | ((((dest) + 1) & 0x7f) << 8) | ((own) ? 0x8000 : 0)))

#define DEPTH(w)   ((w) ? (int)((w) & 0x1ff) - 128 : 0)   /* the depth word: depth + 128, 0 = none */
#define DEPTHOF(d) ((u16)((d) + 128))
#define DEPTH_MIN  (-64)
#define DEPTH_MAX  64

/* LFO1's DEST is slot 4 of a sound, LFO2's slot 12 */
#define DESTSLOT(n) ((n) ? 12 : 4)

/* Where a destination slot's parameter is on the unit. The sound's 53 slots, measured: slot 0 unused,
 * 1..8 LFO1, 9..16 LFO2, 17..24 the SRC page, 25..32 the FLTR page, 33..37 its second page, 38..45 the
 * AMP page, 46..52 spare (46 and 47 are ours). A track set to a machine other than the sample ones
 * still takes 17..24 from its own SRC page, whatever that page calls them. */
static const char *const dnames[53] = {
    0,
    "L1.SPD", "L1.MUL", "L1.FADE", "L1.DEST", "L1.WAVE", "L1.PHAS", "L1.MODE", "L1.DEP",
    "L2.SPD", "L2.MUL", "L2.FADE", "L2.DEST", "L2.WAVE", "L2.PHAS", "L2.MODE", "L2.DEP",
    "SRC.A", "SRC.B", "SRC.C", "SRC.D", "SRC.E", "SRC.F", "SRC.G", "SRC.H",
    "FLT.TYPE", "FLT.FREQ", "FLT.RESO", "FLT.ENV", "FLT.ATK", "FLT.DEC", "FLT.SUS", "FLT.REL",
    "FLT2.A", "FLT2.B", "FLT2.C", "FLT2.D", "FLT2.E",
    "AMP.ATK", "AMP.HOLD", "AMP.DEC", "AMP.OVER", "AMP.DEL", "AMP.REV", "AMP.PAN", "AMP.VOL",
    0, 0, 0, 0, 0, 0, 0
};
#define DEST_FIRST 1
#define DEST_LAST  45

/* ---- the audio engine: around the LFO stage ---------------------------------------------------- */

static u16 snap_route[8], snap_depth[8];    /* the matrix as it was when this block's LFOs ran */
static short saved[16];                     /* the DEST words we took away from their own track */
static u16 savedmask;

void digimatrix_pre(void *words)            /* after the smoothing, before the LFO stage */
{
    unsigned char *kit = ENGINE_KIT;
    int i;
    savedmask = 0;
    if (!kit) {
        for (i = 0; i < 8; i++)
            snap_route[i] = 0;
        return;
    }
    for (i = 0; i < 8; i++) {
        snap_route[i] = ROUTEW(kit, i);
        snap_depth[i] = DEPTHW(kit, i);
    }
    for (i = 0; i < 8; i++) {
        u16 r = snap_route[i];
        int v, n, k;
        volatile short *w;
        if (!R_ON(r) || R_OWN(r) || R_DEST(r) < 0)
            continue;                       /* on, and its LFO is not to keep its own track */
        v = R_STRK(r);
        n = R_SLFO(r);
        k = v * 2 + n;
        if (savedmask & (1 << k))
            continue;                       /* two rows off the same LFO: once is enough */
        w = VOICE(words, v) + DESTSLOT(n);
        saved[k] = *w;
        *w = -1;                            /* the LFO stage reads -1 as "no destination" */
        savedmask |= 1 << k;
    }
}

void digimatrix_post(void *words)           /* after the LFO stage: the matrix's own routings */
{
    int i;
    for (i = 0; i < 16; i++)                /* the borrowed DEST words go back */
        if (savedmask & (1 << i))
            *(VOICE(words, i >> 1) + DESTSLOT(i & 1)) = saved[i];
    savedmask = 0;
    for (i = 0; i < 8; i++) {
        u16 r = snap_route[i];
        int ds = R_DEST(r), d, x;
        volatile short *w;
        if (!R_ON(r) || ds < 0 || ds > 52)
            continue;
        d = DEPTH(snap_depth[i]);
        if (!d)
            continue;
        if (d < DEPTH_MIN)
            d = DEPTH_MIN;
        else if (d > DEPTH_MAX)
            d = DEPTH_MAX;
        /* value * depth, the way the stock stage scales it: a full-scale LFO at +-64 covers the whole
         * parameter range. 32 bits are enough either side of the shift. */
        x = ((LFOVAL(R_STRK(r), R_SLFO(r)) >> 15) * (d * 508)) >> 16;
        w = VOICE(words, R_DTRK(r)) + ds;
        x += *w;
        if (x < 0)
            x = 0;
        else if (x > PARAM_MAX)
            x = PARAM_MAX;
        *w = (short)x;
    }
}

/* ---- SETTINGS > MOD MATRIX ---------------------------------------------------------------------- */

int digimatrix_open;                        /* the page is up (also read by the tests) */
static int cursor;                          /* the slot under the cursor, 0..7 */

static u16 route(void)
{
    unsigned char *kit = UI_KIT;
    return kit ? ROUTEW(kit, cursor) : 0;
}

static void setroute(u16 r)
{
    unsigned char *kit = UI_KIT;
    if (kit)
        put_route(kit, cursor, r);
}

static int active(const unsigned char *kit)
{
    int i, n = 0;
    if (kit)
        for (i = 0; i < 8; i++)
            if (R_ON(ROUTEW(kit, i)))
                n++;
    return n;
}

void digimatrix_select(void **payload)      /* YES on the SETTINGS row */
{
    digimatrix_open = 1;
    cursor = 0;
    INVALIDATE((char *)*payload + 0x38);
}

void digimatrix_change(void **payload, int unused, int delta)
{
    (void)unused;
    (void)delta;
    INVALIDATE((char *)*payload + 0x38);
}

void digimatrix_rowdraw(void *a, void *b, void *bmp, int x, int y)
{
    (void)a;
    (void)b;
    TEXT(bmp, FONT5, x + 58, y, -1, "%d/8", active(UI_KIT));
}

/* ---- the page ----------------------------------------------------------------------------------- */

#define ROWY(i) (49 - (i) * 7)              /* y grows upwards: row 0 at the top */

static void rowtext(void *bmp, int i, u16 r, int d)
{
    int y = ROWY(i);
    const char *name;
    TEXT(bmp, FONT5, 1, y, -1, "%d", i + 1);
    if (!R_ON(r)) {
        TEXT(bmp, FONT5, 10, y, -1, "- - -");
        return;
    }
    TEXT(bmp, FONT5, 10, y, -1, "T%d", R_STRK(r) + 1);
    TEXT(bmp, FONT5, 23, y, -1, "L%d", R_SLFO(r) + 1);
    TEXT(bmp, FONT5, 36, y, -1, ">");
    TEXT(bmp, FONT5, 43, y, -1, "T%d", R_DTRK(r) + 1);
    name = (R_DEST(r) >= 0 && R_DEST(r) < 53) ? dnames[R_DEST(r)] : 0;
    TEXT(bmp, FONT5, 56, y, -1, "%s", name ? name : "--");
    if (d < 0)
        TEXT(bmp, FONT5, 92, y, -1, "-%d", -d);
    else
        TEXT(bmp, FONT5, 92, y, -1, "%d", d);
    if (!R_OWN(r))
        TEXT(bmp, FONT5, 116, y, -1, "X");
}

void digimatrix_draw(void *bmp, void *ctrl)
{
    const unsigned char *kit = UI_KIT;
    int i;
    (void)ctrl;
    if (!digimatrix_open)
        return;
    FILLRECT(bmp, 0, 0, 127, 63, 0);
    TEXT(bmp, FONT5, 1, 57, -1, "MOD MATRIX");
    TEXT(bmp, FONT5, 92, 57, -1, "DEP");
    TEXT(bmp, FONT5, 112, 57, -1, "OWN");
    for (i = 0; i < 8; i++) {
        rowtext(bmp, i, kit ? ROUTEW(kit, i) : 0, kit ? DEPTH(DEPTHW(kit, i)) : 0);
        if (i == cursor)
            FILLRECT(bmp, 0, ROWY(i) - 1, 127, ROWY(i) + 5, -1);   /* the cursor's row, inverted */
    }
}

void digimatrix_tick(void *ctrl)             /* keep the frame coming while the page is up */
{
    kstore_tick(&store, UI_KIT, KS_SLOT_MATRIX, mxmask);   /* a sound load keeps the matrix */
    if (digimatrix_open)
        *((volatile char *)ctrl + 0x20) = 1;
}

#define KEYID(ev)    (*(int *)((char *)(ev) + 12))
#define KEYDOWN(ev)  (*(int *)((char *)(ev) + 16) & 1)

int digimatrix_key(void *brain, void *ev)
{
    int id = KEYID(ev);
    (void)brain;
    if (!digimatrix_open)
        return 0;
    if (id == 9 || id == 10 || id == 11)     /* REC, PLAY, STOP still work */
        return 0;
    if (!KEYDOWN(ev))
        return 1;
    switch (id) {
    case 13:                                 /* NO: leave */
        digimatrix_open = 0;
        break;
    case 14:                                 /* UP */
        if (cursor > 0)
            cursor--;
        break;
    case 15:                                 /* DOWN */
        if (cursor < 7)
            cursor++;
        break;
    case 12: {                               /* YES: the slot on or off */
        u16 r = route();
        if (R_ON(r))
            r &= (u16)~0x80;
        else {
            unsigned char *kit = UI_KIT;
            if (R_DEST(r) < 0)               /* a slot switched on for the first time */
                r = ROUTE(cursor, 0, cursor, 1, DEST_FIRST, 1);
            else
                r |= 0x80;
            if (kit && !DEPTHW(kit, cursor))
                put_depth(kit, cursor, DEPTHOF(0));
        }
        setroute(r);
        break;
    }
    default:
        break;
    }
    return 1;
}

int digimatrix_enc(void *brain, void *ev)
{
    int id = *(int *)((char *)ev + 12);
    int delta = *(int *)((char *)ev + 16);
    unsigned char *kit;
    u16 r;
    int s;
    (void)brain;
    if (!digimatrix_open)
        return 0;
    kit = UI_KIT;
    if (!kit || !delta)
        return 1;
    s = delta > 0 ? 1 : -1;
    if (id == 9) {                           /* LEVEL: the cursor */
        if (s > 0 && cursor < 7)
            cursor++;
        else if (s < 0 && cursor > 0)
            cursor--;
        return 1;
    }
    r = ROUTEW(kit, cursor);
    if (!R_ON(r))
        return 1;                            /* an empty slot: YES turns it on first */
    switch (id) {
    case 1: {                                /* source track */
        int v = R_STRK(r) + s;
        if (v >= 0 && v <= 7)
            r = (u16)((r & ~7) | v);
        break;
    }
    case 2:                                  /* source LFO */
        r = (u16)((r & ~8) | (s > 0 ? 8 : 0));
        break;
    case 3: {                                /* destination track */
        int v = R_DTRK(r) + s;
        if (v >= 0 && v <= 7)
            r = (u16)((r & ~0x70) | (v << 4));
        break;
    }
    case 4: {                                /* destination parameter */
        int v = R_DEST(r) + s;
        while (v >= DEST_FIRST && v <= DEST_LAST && !dnames[v])
            v += s;
        if (v >= DEST_FIRST && v <= DEST_LAST)
            r = (u16)((r & ~0x7f00) | (((v + 1) & 0x7f) << 8));
        break;
    }
    case 5: {                                /* depth */
        int d = DEPTH(DEPTHW(kit, cursor)) + s * 2;
        if (d < DEPTH_MIN)
            d = DEPTH_MIN;
        else if (d > DEPTH_MAX)
            d = DEPTH_MAX;
        put_depth(kit, cursor, DEPTHOF(d));
        break;
    }
    case 6:                                  /* the LFO keeps its own track, or not */
        r = (u16)((r & ~0x8000) | (s > 0 ? 0x8000 : 0));
        break;
    default:
        break;
    }
    put_route(kit, cursor, r);
    return 1;
}
