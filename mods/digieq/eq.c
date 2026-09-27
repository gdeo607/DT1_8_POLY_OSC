/* Digi EQ: the 4-band master EQ, its settings, its page and its drawing (model: tests/eq_model.py).
 *
 * The EQ is a page of the master pages (FUNC+LFO), between Compressor and Internal Mixer: "Master EQ (2/4)".
 * One page, one band per column:
 *   knobs A-D  band 1-4 level (-12 .. +12 dB);   pressed once: that band's Q (0.3 .. 8), pressed again: level
 *   knobs E-H  band 1-4 frequency (20 Hz .. 20 kHz); pressed once: that band's type, pressed again: frequency
 * Types: HP, low shelf, bell, notch, band pass, high shelf, LP (12 dB/oct state-variable filters). For shelves
 * and bells the level is the boost/cut; for HP/LP/BP/notch it is the band's output level.
 *
 * The audio part is eq_dsp.s, on the master mix before the render hands it to the analog outputs and to the
 * USB stream, so every output carries it. This file turns the settings into coefficients (32-bit integer
 * arithmetic only: the part has no FPU, and the 64-bit products and the one division are done here by hand).
 *
 * Where the settings live: in the pattern's kit, band b in track b + 1's sound, in bytes of the persistent
 * map in kitstore.h (frequency, level, type, Q; band 1 also carries the global bit). So each pattern has
 * its own EQ, it is saved with the project and it survives a power cycle. A kit that has never held EQ settings (every kit
 * made before this) reads as "no settings" and the EQ starts flat.
 *
 * SETTINGS > GLOBAL FX/MIX > MASTER EQ, like the other entries of that list: with it on, the EQ you can hear
 * now overrides every pattern's own - each pattern the unit reaches is given these settings (so they are kept
 * with the project when you save it). With it off, every pattern goes back to its own.
 *
 * The page: the master view (vtable 0x401845dc) shows a list of page kinds (+124 vector, +144 index; 11 COMP,
 * 12 internal mixer, 13 external mixer). digieq_mdraw inserts kind 0 (the firmware's unused "None" page, no
 * knobs) after 11; while it is shown, its draw, knobs and knob pushes are ours (sites on the view's vtable).
 */
typedef int int32;
typedef unsigned int uint32;

#include "eq_tables.h"

/* ---- firmware (OS 1.53) ---- */
typedef void (*fillrect_t)(void *bmp, int x0, int y0, int x1, int y1, int colour);
typedef void (*text_t)(void *bmp, const void *font, int x, int y, int flags, const char *fmt, ...);
#define FILLRECT ((fillrect_t)0x400c19a6)          /* colour 0 clear, 1 set, -1 invert */
#define FRAMERECT ((fillrect_t)0x400c178a)
#define TEXT     ((text_t)0x400c257c)
#define FONT5    ((const void *)0x40200b0c)
#define INVALIDATE ((void (*)(void *))0x400c9812)
#define OP_NEW(n) ((int32 *)((uint32 (*)(uint32))0x400d4180)(n))   /* the firmware returns pointers in d0 */
#define KEYID    ((int (*)(void *))0x400c317c)
#define KEYPRESS ((char (*)(void *))0x400c3220)
#define PAGEKINDS ((char **)0x4197cf88)             /* kind 0's short and long page names */
#define STOCK_DRAW ((void (*)(void *, void *))0x400395dc)
#define STOCK_ENC  ((int (*)(void *, void *))0x40038614)
#define STOCK_KEY  ((int (*)(void *, void *))0x40038b36)
#define BLIT     ((void (*)(void *, const void *, int, int, int))0x400c2960)
#define CHECKBOXES (*(const char **)0x421f7a3c)     /* two bitmaps, 0x1c bytes each: empty, ticked */
#define UI_KIT   (*(unsigned char *volatile *)0x4199dc44)
#include "kitstore.h"
/* band b in track b + 1's sound: a word (bit 15 stored, bit 14 global in band 1, level << 7 | frequency)
 * and the low 7 bits of a byte (type | Q << 3), whose top bit is Digi Poly's */
#define EQW(kit, b)     ((unsigned)(XB(kit, 6 * (b) + 4) << 8) | XB(kit, 6 * (b) + 5))
#define EQT(kit, b)     XB(kit, 6 * (b) + 3)
static struct kstore kst;
static unsigned char eqmask(int n)
{
    return n >= 24 ? 0 : n % 6 == 3 ? 0x7f : n % 6 >= 4 ? 0xff : 0;
}

/* ---- the coefficient sets read by eq_dsp.s ---- */
struct eqset {
    int32 run, lvl, act[4];
    int32 c[4][6];                                  /* a1 a2 a3 (Q31), c0 c1 c2 (mix/16, Q31) */
};
static struct eqset sets[2];
static int cur;
struct eqset *digieq_live;

/* ---- settings ---- */
enum { HP, LSH, BELL, NOTCH, BP, HSH, LP, NTYPES };
static const char *const TNAME[NTYPES] = {"HP", "LSHF", "BELL", "NTCH", "BP", "HSHF", "LP"};
static unsigned char fi[4] = {25, 55, 89, 114};     /* 80 Hz, 400 Hz, 2.5 kHz, 10 kHz */
static unsigned char gi[4] = {24, 24, 24, 24};      /* 0 dB */
static unsigned char qi[4] = {4, 5, 5, 4};          /* Q 0.72 (shelves), 0.9 (bells) */
static unsigned char ty[4] = {LSH, BELL, BELL, HSH};
static unsigned char alt[8];                        /* knob pressed: A-D set Q, E-H set the type */
static signed char last = -1;                       /* the knob turned last (0..7) */
static signed char curve[128];                      /* drawn response, half-dB, per frequency step */

#define ONE27 (1 << 27)

/* floor(a * b / 2^sh) for 16 <= sh <= 31, when the result fits 32 bits */
static int32 mulsh(int32 a, int32 b, int sh)
{
    uint32 ua = a < 0 ? -(uint32)a : (uint32)a, ub = b < 0 ? -(uint32)b : (uint32)b;
    uint32 al = ua & 0xffff, ah = ua >> 16, bl = ub & 0xffff, bh = ub >> 16;
    uint32 ll = al * bl, lh = al * bh, hl = ah * bl, hh = ah * bh;
    uint32 mid = (ll >> 16) + (lh & 0xffff) + (hl & 0xffff);
    uint32 lo = (ll & 0xffff) | (mid << 16);
    uint32 hi = hh + (lh >> 16) + (hl >> 16) + (mid >> 16);
    if ((a < 0) != (b < 0)) {                       /* negate the 64-bit product */
        lo = ~lo + 1;
        hi = ~hi + (lo == 0);
    }
    return (int32)((hi << (32 - sh)) | (lo >> sh));
}

/* floor(2^55 / d), d > 2^24 */
static int32 div55(uint32 d)
{
    uint32 rem = 1u << 23, q = 0;
    int i;
    for (i = 0; i < 32; i++) {
        uint32 carry = rem >> 31;
        rem <<= 1;
        q <<= 1;
        if (carry || rem >= d) {
            rem -= d;
            q |= 1;
        }
    }
    return (int32)q;
}

static int clampi(int v, int lo, int hi)
{
    return v < lo ? lo : v > hi ? hi : v;
}

static int is_filter(int t)
{
    return t == HP || t == NOTCH || t == BP || t == LP;
}

/* the band's g, k (Q27) and its coefficients (as eq_model.coef) */
static void band_coef(int b, int32 *c, int32 *gp, int32 *kp)
{
    int32 A = A27[gi[b]], A2 = AA27[gi[b]], g = G27[fi[b]], k = K27[qi[b]], d24;
    switch (ty[b]) {
    case BELL:
        k = mulsh(k, A27[48 - gi[b]], 27);
        c[3] = 0; c[4] = mulsh(k, A2 - ONE27, 27); c[5] = 0;
        break;
    case LSH:
        g = mulsh(g, SQA27[48 - gi[b]], 27);
        c[3] = 0; c[4] = mulsh(k, A - ONE27, 27); c[5] = A2 - ONE27;
        break;
    case HSH:
        g = mulsh(g, SQA27[gi[b]], 27);
        c[3] = A2 - ONE27; c[4] = mulsh(mulsh(k, ONE27 - A, 27), A, 27); c[5] = ONE27 - A2;
        break;
    case LP:
        c[3] = -ONE27; c[4] = 0; c[5] = A2;
        break;
    case HP:
        c[3] = A2 - ONE27; c[4] = -mulsh(k, A2, 27); c[5] = -A2;
        break;
    case BP:
        c[3] = -ONE27; c[4] = mulsh(k, A2, 27); c[5] = 0;
        break;
    default:                                        /* NOTCH */
        c[3] = A2 - ONE27; c[4] = -mulsh(k, A2, 27); c[5] = 0;
        break;
    }
    d24 = (1 << 24) + mulsh(g, g + k, 30);
    c[0] = div55((uint32)d24);
    c[1] = mulsh(g, c[0], 27);
    c[2] = mulsh(g, c[1], 27);
    *gp = g;
    *kp = k;
}

/* ---- the drawn response: |H|^2 = N / D of the band's filter at each frequency step (eq_model.resp_db2) ---- */
static uint32 udivq16(uint32 x, uint32 y)           /* floor(x * 65536 / y), x <= y < 2^30 */
{
    uint32 rem = x, q = 0;
    int i;
    for (i = 0; i < 16; i++) {
        rem <<= 1;
        q <<= 1;
        if (rem >= y) {
            rem -= y;
            q |= 1;
        }
    }
    return q;
}

static int log2q8(uint32 v)                         /* log2(v) x 256, v > 0 */
{
    int p = 31;
    uint32 m;
    while (!(v >> p))
        p--;
    m = p >= 8 ? v >> (p - 8) : v << (8 - p);
    return p * 256 + LOG2Q8[m & 255];
}

static int resp_db2(const int32 *c, int32 g, int32 k, int x)
{
    int32 m0 = (c[3] + ONE27) >> 11, m1 = c[4] >> 11, m2 = c[5] >> 11, kk = k >> 11;
    int32 a = m0 + m2, b = mulsh(m0, kk, 16) + m1, G = G27[x], t, t2, n1, d1, bt, kt, n, d;
    if (G <= g) {
        t = udivq16(G, g);
        t2 = mulsh(t, t, 16);
        n1 = a - mulsh(m0, t2, 16);
        d1 = 65536 - t2;
    } else {
        t = udivq16(g, G);
        t2 = mulsh(t, t, 16);
        n1 = mulsh(a, t2, 16) - m0;
        d1 = t2 - 65536;
    }
    bt = mulsh(b, t, 16);
    kt = mulsh(kk, t, 16);
    n = mulsh(n1, n1, 16) + mulsh(bt, bt, 16);
    d = mulsh(d1, d1, 16) + mulsh(kt, kt, 16);
    if (n <= 0)
        return -200;
    if (d <= 0)
        return 200;
    return ((log2q8(n) - log2q8(d)) * 1541 + 32768) >> 16;
}

static void commit(void)
{
    struct eqset *s = &sets[cur ^ 1];
    int32 g[4], k[4];
    int b, x, any = 0;
    for (b = 0; b < 4; b++) {
        s->act[b] = is_filter(ty[b]) || gi[b] != 24;
        any |= s->act[b];
        band_coef(b, s->c[b], &g[b], &k[b]);
    }
    s->lvl = 0;
    s->run = any;
    cur ^= 1;
    digieq_live = s;                           /* one 32-bit store: the audio side switches here */
    for (x = 0; x < 128; x++) {
        int sum = 0;
        for (b = 0; b < 4; b++)
            if (s->act[b])
                sum += resp_db2(s->c[b], g[b], k[b], x);
        curve[x] = clampi(sum, -100, 100);
    }
}

/* ---- the pattern's own EQ, in the kit ---------------------------------------------------------- */

int digieq_global;                                  /* SETTINGS > GLOBAL FX/MIX > MASTER EQ */
static void defaults(void)
{
    static const unsigned char F[4] = {25, 55, 89, 114}, Q[4] = {4, 5, 5, 4};
    static const unsigned char T[4] = {LSH, BELL, BELL, HSH};
    int b;
    for (b = 0; b < 4; b++) {
        fi[b] = F[b];
        gi[b] = 24;
        qi[b] = Q[b];
        ty[b] = T[b];
    }
}

static void store(unsigned char *kit)               /* the live settings into this pattern's kit */
{
    int b;
    if (!kit)
        return;
    for (b = 0; b < 4; b++) {
        unsigned w = 0x8000u | ((unsigned)gi[b] << 7) | fi[b] | (b == 0 && digieq_global ? 0x4000u : 0);
        XB(kit, 6 * b + 4) = (unsigned char)(w >> 8);
        XB(kit, 6 * b + 5) = (unsigned char)w;
        EQT(kit, b) = (unsigned char)((EQT(kit, b) & 0x80) | ty[b] | (qi[b] << 3));
    }
}

static int load(const unsigned char *kit)           /* -> the kit had settings */
{
    int b;
    if (!kit || !(EQW(kit, 0) & 0x8000))
        return 0;
    for (b = 0; b < 4; b++) {
        unsigned int w = EQW(kit, b), x = EQT(kit, b);
        fi[b] = (unsigned char)(w & 0x7f);
        gi[b] = (unsigned char)clampi((int)((w >> 7) & 0x3f), 0, 48);
        ty[b] = (unsigned char)clampi((int)(x & 7), 0, NTYPES - 1);
        qi[b] = (unsigned char)((x >> 3) & 0xf);
    }
    digieq_global = (EQW(kit, 0) >> 14) & 1;
    return 1;
}

/* Every UI frame. Another pattern: global on, the live EQ is written into its kit (it overrides that
 * pattern's own, and is kept with the project); global off, its own settings come back. The same kit
 * loaded again in place (a project loaded, the kit reloaded) brings its own settings back, global bit
 * included; if it has none, it is treated like another pattern. A sound loaded onto one track changes
 * nothing (kitstore.h puts the EQ's bytes back). */
void digieq_tick(void *ctrl)
{
    unsigned char *kit = UI_KIT;
    int r = kstore_tick(&kst, kit, KS_SLOT_EQ, eqmask);
    (void)ctrl;
    if (!kit || r == KS_SAME)
        return;
    if (digieq_global && (r == KS_OTHER || !(EQW(kit, 0) & 0x8000))) {
        store(kit);
    } else {
        if (!load(kit))
            defaults();
        commit();
    }
    kstore_tick(&kst, kit, KS_SLOT_EQ, eqmask);          /* the copy now holds what was just written */
}

/* ---- SETTINGS > GLOBAL FX/MIX > MASTER EQ ------------------------------------------------------- */

void digieq_gselect(void **payload)
{
    digieq_global = !digieq_global;
    store(UI_KIT);
    INVALIDATE((char *)*payload + 0x38);
}

void digieq_gchange(void **payload, int unused, int delta)
{
    (void)unused;
    (void)delta;
    INVALIDATE((char *)*payload + 0x38);
}

void digieq_gdraw(void *a, void *b, void *bmp, int x, int y)
{
    (void)a;
    (void)b;
    BLIT(bmp, CHECKBOXES + (digieq_global ? 0x1c : 0), x, y, 0);
}

/* the page's knob events carry 16 per notch (the firmware's own pages step once per 16): one step per notch */
#define PER_STEP 16
static int32 eacc[9];

static int steps(int id, int d)
{
    int st;
    if ((d > 0 && eacc[id] < 0) || (d < 0 && eacc[id] > 0))
        eacc[id] = 0;                               /* a change of direction starts afresh */
    eacc[id] += d;
    st = eacc[id] / PER_STEP;
    eacc[id] -= st * PER_STEP;
    return st;
}

/* the knobs on the EQ page: id 1..8 = A..H, d = counts (4 a notch) */
static void eq_knob(int id, int d)
{
    int b = (id - 1) & 3;
    d = steps(id, d);
    if (!d)
        return;
    if (id <= 4) {
        if (alt[id - 1])
            qi[b] = clampi(qi[b] + d, 0, 15);
        else
            gi[b] = clampi(gi[b] + d, 0, 48);
    } else {
        if (alt[id - 1])
            ty[b] = clampi(ty[b] + d, 0, NTYPES - 1);
        else
            fi[b] = clampi(fi[b] + d, 0, 127);
    }
    last = id - 1;
    commit();
    store(UI_KIT);
}

/* ---------------- the master page ---------------- */
static const char name_short[] = "EQ", name_long[] = "Master EQ";

static int cur_kind(char *view)
{
    int32 *v = *(int32 **)(view + 124), *e = *(int32 **)(view + 128), i = *(int32 *)(view + 144);
    if (!v || i < 0 || i >= e - v)
        return -1;
    return v[i];
}

/* kinds {11, ...} without 0 -> {11, 0, ...} (once per view) */
static void add_page(char *view)
{
    int32 *v = *(int32 **)(view + 124), *e = *(int32 **)(view + 128), *nv, n = e - v, i, j;
    if (!v || n < 1 || n > 15 || v[0] != 11)
        return;
    for (i = 0; i < n; i++)
        if (v[i] == 0)
            return;
    nv = OP_NEW(4 * (n + 1));
    if (!nv)
        return;
    for (i = j = 0; i < n; i++) {
        nv[j++] = v[i];
        if (i == 0)
            nv[j++] = 0;
    }
    i = *(int32 *)(view + 144);
    *(int32 **)(view + 124) = nv;
    *(int32 **)(view + 128) = nv + n + 1;
    *(int32 **)(view + 132) = nv + n + 1;
    if (i >= 1)
        *(int32 *)(view + 144) = i + 1;             /* stay on the same page */
    /* the old 12 bytes are left alone: they do not come from the heap operator delete checks */
    PAGEKINDS[0] = (char *)name_short;              /* kind 0's names ("NONE", "None", unused): the title bar */
    PAGEKINDS[1] = (char *)name_long;
}

static void put_db(char *p, int db2)                /* "+3.5", "-10.5", " 0.0" */
{
    int a = db2 < 0 ? -db2 : db2;
    *p++ = db2 < 0 ? '-' : db2 ? '+' : ' ';
    if (a >= 20)
        *p++ = '0' + a / 20;
    *p++ = '0' + (a / 2) % 10;
    *p++ = '.';
    *p++ = a & 1 ? '5' : '0';
    *p = 0;
}

static void put_hz(char *p, int hz)                 /* "82", "420", "2.5K", "12K" */
{
    char t[8];
    int n = 0, i;
    if (hz >= 10000) {
        int k = (hz + 500) / 1000;
        while (k) { t[n++] = '0' + k % 10; k /= 10; }
        for (i = 0; i < n; i++) p[i] = t[n - 1 - i];
        p[n++] = 'K';
    } else if (hz >= 1000) {
        int h = (hz + 50) / 100;
        p[0] = '0' + h / 10;
        p[1] = '.';
        p[2] = '0' + h % 10;
        p[3] = 'K';
        n = 4;
    } else {
        while (hz) { t[n++] = '0' + hz % 10; hz /= 10; }
        for (i = 0; i < n; i++) p[i] = t[n - 1 - i];
    }
    p[n] = 0;
}

static void put_q(char *p, int q10)                 /* "Q.3", "Q.9", "Q1.5", "Q8.0", "Q27" */
{
    *p++ = 'Q';
    if (q10 >= 100) {
        *p++ = '0' + q10 / 100;
        *p++ = '0' + (q10 / 10) % 10;
    } else {
        if (q10 >= 10)
            *p++ = '0' + q10 / 10;
        *p++ = '.';
        *p++ = '0' + q10 % 10;
    }
    *p = 0;
}

/* screen: 128 x 64, bitmap row 0 = the bottom. The firmware draws the title bar ("Master EQ (2/4)").
 *   x 1..17      a box with "EQ" (as the other master pages' icons)
 *   rows 21..51  the graph: 0 dB dotted, +-12 dB, 20 Hz .. 20 kHz, the response, band points 1-4
 *   rows 11..19  knobs A-D: level (or Q, inverted while the knob is switched to it)
 *   rows 1..9    knobs E-H: frequency (or type, inverted while switched); the knob turned last underlined */
#define GX0  21
#define GX1  127
#define GY0  21
#define GY1  51
#define GMID 36

static int db2y(int db2)                            /* half-dB -> row: +-12 dB = +-14 rows */
{
    int r = db2 * 7;
    r = r >= 0 ? (r + 6) / 12 : -((-r + 6) / 12);
    return clampi(GMID + r, GY0 + 1, GY1 - 1);
}

static int col2step(int x)                          /* graph column -> frequency step 0..127 */
{
    return (x - GX0 - 1) * 127 / (GX1 - GX0 - 2);
}

static int step2col(int s)
{
    return GX0 + 1 + s * (GX1 - GX0 - 2) / 127;
}

static void knobcell(void *bmp, int i, const char *val)
{
    int x = 21 + (i & 3) * 27, y = i < 4 ? 12 : 2;
    TEXT(bmp, FONT5, x + 1, y, -1, "%s", val);
    if (alt[i])
        FILLRECT(bmp, x, y - 1, x + 25, y + 5, -1);
    if (i == last)
        FILLRECT(bmp, x, y - 2, x + 25, y - 2, 1);
}

static void eq_body(void *bmp)
{
    int x, b, prev = -1;
    char v[12];
    FILLRECT(bmp, 0, 0, 127, 52, 0);
    FRAMERECT(bmp, 1, 27, 17, 50, 1);               /* the page's box */
    TEXT(bmp, FONT5, 5, 36, -1, "EQ");
    FRAMERECT(bmp, GX0, GY0, GX1, GY1, 1);
    for (x = GX0 + 2; x < GX1; x += 3)
        FILLRECT(bmp, x, GMID, x, GMID, 1);         /* 0 dB */
    for (b = 0; b < 3; b++) {                       /* ticks at 100 Hz, 1 kHz, 10 kHz */
        static const unsigned char TS[3] = {30, 72, 114};
        x = step2col(TS[b]);
        FILLRECT(bmp, x, GY0 + 1, x, GY0 + 2, 1);
    }
    for (x = GX0 + 1; x < GX1; x++) {               /* the response */
        int y = db2y(curve[col2step(x)]);
        if (prev < 0)
            prev = y;
        FILLRECT(bmp, x, prev < y ? prev : y, x, prev < y ? y : prev, 1);
        prev = y;
    }
    for (b = 0; b < 4; b++) {                       /* band points and numbers */
        int px = clampi(step2col(fi[b]), GX0 + 3, GX1 - 3), py = db2y(curve[fi[b]]), tyr;
        FILLRECT(bmp, px - 2, py - 2, px + 2, py + 2, 0);
        FRAMERECT(bmp, px - 2, py - 2, px + 2, py + 2, 1);
        if (last >= 0 && (last & 3) == b)
            FILLRECT(bmp, px - 1, py - 1, px + 1, py + 1, 1);
        tyr = py + 4 <= GY1 - 7 ? py + 4 : py - 9;
        TEXT(bmp, FONT5, clampi(px - 1, GX0 + 1, GX1 - 5), tyr, -1, "%d", b + 1);
    }
    for (b = 0; b < 4; b++) {                       /* the knobs */
        if (alt[b])
            put_q(v, QX10[qi[b]]);
        else
            put_db(v, gi[b] - 24);
        knobcell(bmp, b, v);
        if (alt[4 + b]) {
            const char *s = TNAME[ty[b]];
            int n = 0;
            while ((v[n] = s[n]))
                n++;
        } else
            put_hz(v, HZ[fi[b]]);
        knobcell(bmp, 4 + b, v);
    }
}

/* vtable slot 4 of the master view: draw */
void digieq_mdraw(char *view, void *bmp)
{
    add_page(view);
    if (cur_kind(view) != 0) {
        STOCK_DRAW(view, bmp);
        return;
    }
    if (!digieq_live)
        commit();
    STOCK_DRAW(view, bmp);
    eq_body(bmp);
}

/* the view's knob listener (reached through its +4 subobject, see osc_glue.s): event +12 knob 1..8 = A..H,
 * 9 = LEVEL; +16 the turn; +20 set while the knob is held down */
int32 digieq_mlast[2];                           /* the last event's knob and turn (for tests) */
int digieq_menc(char *view, void *ev)
{
    int id = *(int32 *)((char *)ev + 12);
    digieq_mlast[0] = id;
    digieq_mlast[1] = *(int32 *)((char *)ev + 16);
    if (cur_kind(view) != 0 || id < 1 || id > 8)
        return STOCK_ENC(view, ev);
    eq_knob(id, *(int32 *)((char *)ev + 16));
    INVALIDATE(view);
    return 1;
}

/* vtable slot 2: keys. Knob pushes (40..47 = A..H) switch that knob between its two settings. */
int digieq_mkey(char *view, void *ev)
{
    int id = KEYID(ev);
    if (cur_kind(view) != 0 || id < 40 || id > 47)
        return STOCK_KEY(view, ev);
    if (KEYPRESS(ev)) {
        alt[id - 40] ^= 1;
        last = id - 40;
        INVALIDATE(view);
    }
    return 1;
}
