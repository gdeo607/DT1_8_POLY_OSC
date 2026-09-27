/* Digi Poly: chords and polyphony for audio tracks set to the POLY machine, by voice stealing.
 *
 * The unit has one voice per audio track. A POLY track borrows the voices of other tracks:
 *
 *  - Sequencer: a POLY track's trig carries its chord (NOT2..NOT4 of the step, else of the track; tagged
 *    by the builder hook, poly_glue.s). When the audio engine takes that trig, digipoly_route_c plays
 *    NOTE on the track's own voice and each extra note on a stolen voice: a copy of the message with the
 *    other voice, the note and the POLY track's sound (the message's sound pointer), inserted right after
 *    it, so the engine starts them all in the same block.
 *  - Live notes (MIDI in on the POLY track's own channel): each note-on takes the
 *    track's own voice if it is free, else a stolen one; the note-off goes to the voice that holds it.
 *  - The unit's own keys (the track's trig key, the FUNC+TRK keyboard) play the chord: the key's note goes
 *    through the firmware as always (so recording records one note), and the chord's other notes are added
 *    as live notes of their own (poly_glue.s hooks the two panel call sites).
 *
 * Which voice is stolen: never the POLY track's own (it plays NOTE), a track kept out of the pool in
 * SETTINGS > POLY, a muted track's voice, a voice holding a live note, or one whose own track has a trig
 * in the same block; of the others, the one whose last note started longest ago. With no voice left the
 * extra note is dropped. A stolen voice plays the POLY track's whole sound and gets its own back at its
 * own track's next trig (the engine reloads a voice's sound when a message brings another one).
 *
 * Which tracks lend their voice is kept in the pattern's kit, one bit in each track's sound (the
 * persistent map in kitstore.h): the kit belongs to the pattern, so every pattern has its own voice
 * allocation, and it is saved with the project and survives a power cycle. 0 (what every existing kit
 * holds) means the track lends its voice.
 *
 * TRIG page: while the active track is a POLY audio track, its TRIG page is the MIDI tracks' one
 * (NOT1..NOT4, VEL, LEN, PROB, LFO.T). Both are the same view class; only the page kind differs.
 */
typedef unsigned int u32;

/* ---- firmware (OS 1.53) ---- */
#define M(m, o)      (*(volatile int *)((char *)(m) + (o)))
#define MSG_ALLOC()  ((char *)((u32 (*)(void))0x400ee036)())   /* pointers come back in d0 */
#define MSG_COPY     ((void (*)(char *, char *))0x400ee0a0)   /* dst, src: 0x4c bytes, lock block ref counted */
#define ENGINE_KIT   (*(unsigned char *volatile *)0x800019ac)
#define UI_KIT       (*(unsigned char *volatile *)0x4199dc44)
#define MUTES        (*(volatile unsigned short *)0x4199e47c)  /* bit t: track t muted */
#define OWNER        ((volatile int *)0x4399db54)             /* voice -> id of the message holding it (2 = live) */
#define ACTIVE_TRACK (*(volatile int *)0x4197b6b4)
#define INVALIDATE   ((void (*)(void *))0x400c9812)
#define FILLRECT     ((void (*)(void *, int, int, int, int, int))0x400c19a6)
#define TEXT         ((void (*)(void *, const void *, int, int, int, const char *, ...))0x400c257c)
#define FONT5        ((const void *)0x40200b0c)
#define BLIT         ((void (*)(void *, const void *, int, int, int))0x400c2960)
#define CHECKBOXES   (*(const char **)0x421f7a3c)   /* two bitmaps, 0x1c bytes each: empty, ticked */

#define POLY     4
#define TAG      0xc4
#define NOTE_OFF 0x40                     /* NOT2..4: 0x40 = no note, else offset + 0x40 */

/* message fields */
#define M_TYPE   0
#define M_ON     4                        /* 1 note on, 2 note off (live) */
#define M_VOICE  8
#define M_ID     12                       /* 1 sequencer, 2 live, -1 ignored */
#define M_NOTE   24
#define M_CHORD  28                       /* ours: 0xC4, NOT2, NOT3, NOT4 */
#define M_FLAGS  36                       /* bit 7 trig, bit 0 on, bit 18: the engine's own note-off copy */
#define M_SOUND  40
#define M_SLOCK  44
#define M_NEXT   72

#include "kitstore.h"
#define POOLOUT(kit, t) XB(kit, 6 * (t) + 3)   /* bit 7: track t is kept out of the POLY pool */
static struct kstore store;
static unsigned char poolmask(int n) { return n % 6 == 3 ? 0x80 : 0; }
unsigned char dt8poly_vstate[8] = {       /* voice -> live POLY note it holds, 0xff = none (Digi utilities */
    0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff  /* reads it for the activity dots) */
};
static unsigned char held_by[8];          /* voice -> the POLY track whose live note it holds */
static u32 started[8], clock;             /* voice -> clock at its last note start */

static int is_poly(const unsigned char *kit, int t)
{
    return kit && (unsigned)t < 8 && kit[0x9e + t * 0xa2] == POLY;
}

static int locked(const unsigned char *kit, int t)
{
    return kit && (unsigned)t < 8 && (POOLOUT(kit, t) & 0x80);
}

static int muted(int v, const char *fp)
{
    return ((MUTES >> v) & 1) || ((*(const int *)(fp - 80) >> v) & 1);
}

static int trig_on(const char *m)          /* a note message that starts a voice */
{
    int ty = M(m, M_TYPE), f = M(m, M_FLAGS);
    return (ty < 2 || ty > 5) && M(m, M_ON) == 1 && (f & 0x81) == 0x81 && !(f & 0x40000);
}

static int own_trig_pending(const char *m, int v)   /* the voice's own track trigs later in this block */
{
    for (; m; m = (const char *)M(m, M_NEXT))
        if (M(m, M_VOICE) == v && M(m, M_ID) == 1 && trig_on(m))
            return 1;
    return 0;
}

static int steal(u32 used, const char *fp, const char *rest)
{
    const unsigned char *kit = ENGINE_KIT;
    int v, best = -1;
    u32 age, oldest = 0;
    for (v = 0; v < 8; v++) {
        if ((used >> v) & 1 || locked(kit, v))
            continue;
        if (muted(v, fp) || OWNER[v] >= 2 || own_trig_pending(rest, v))
            continue;
        age = clock - started[v];
        if (best < 0 || age > oldest) {
            best = v;
            oldest = age;
        }
    }
    return best;
}

static int holder(int p, int note)          /* the voice holding POLY track p's live note */
{
    int v;
    for (v = 0; v < 8; v++)
        if (dt8poly_vstate[v] == note && held_by[v] == p && OWNER[v] == 2)
            return v;
    return -1;
}

void digipoly_route_c(char *m, u32 busy, const char *fp)
{
    int v = M(m, M_VOICE), id = M(m, M_ID), i, w, n;
    const unsigned char *kit = ENGINE_KIT;

    for (w = 0; w < 8; w++)                 /* forget live notes the engine has let go */
        if (dt8poly_vstate[w] != 0xff && OWNER[w] != 2)
            dt8poly_vstate[w] = 0xff;
    if ((unsigned)v > 7)
        return;

    if (id == 1) {                          /* sequencer */
        u32 tag = M(m, M_CHORD), used;
        int base;
        if (M(m, M_FLAGS) & 0x40000)        /* the engine's own note-off copy */
            return;
        M(m, M_CHORD) = 0;
        if (!trig_on(m))
            return;
        started[v] = ++clock;
        if ((tag >> 24) != TAG || !is_poly(kit, v) || muted(v, fp))
            return;
        used = (1u << v) | busy;
        base = M(m, M_NOTE);
        for (i = 16; i >= 0; i -= 8) {
            char *c;
            int b = (tag >> i) & 0xff;
            if (b == NOTE_OFF || b == 0xff)
                continue;
            n = base + b - NOTE_OFF;
            if (n < 0 || n > 127)
                continue;
            w = steal(used, fp, (const char *)M(m, M_NEXT));
            if (w < 0)
                break;
            c = MSG_ALLOC();
            if (!c)
                break;
            MSG_COPY(c, m);
            M(c, M_VOICE) = w;
            M(c, M_NOTE) = n;
            M(c, M_CHORD) = 0;
            M(c, M_FLAGS) |= 0x10000;       /* the pitch is the message's note */
            M(c, M_NEXT) = M(m, M_NEXT);
            M(m, M_NEXT) = (int)c;
            used |= 1u << w;
        }
        return;
    }

    if (id != 2)
        return;
    n = M(m, M_NOTE);                       /* live */
    if (!is_poly(kit, v)) {
        if (M(m, M_ON) == 1)
            started[v] = ++clock;
        return;
    }
    if (M(m, M_ON) == 1) {
        w = holder(v, n);                   /* the same note again: the same voice */
        if (w < 0)
            w = OWNER[v] < 2 ? v : steal(1u << v, fp, 0);
        if (w < 0) {
            M(m, M_ID) = -1;                /* no voice: dropped */
            return;
        }
        M(m, M_VOICE) = w;
        if (w != v && !M(m, M_SLOCK))
            M(m, M_SOUND) = (int)(kit + 0x20 + v * 0xa2);   /* the POLY track's sound */
        held_by[w] = v;
        dt8poly_vstate[w] = n;
        started[w] = ++clock;
    } else {
        w = holder(v, n);
        if (w >= 0) {
            M(m, M_VOICE) = w;
            dt8poly_vstate[w] = 0xff;
        }
    }
}

/* ---- the POLY track's sound on stolen voices follows its knobs ----
 * A voice plays the sound its engine slot has loaded (LOADED[v]); a stolen voice has the POLY track's.
 * Knob turns reach the engine through 0x400771e8 (value -> voice's parameter copy), for the track's own voice
 * only; the track level is a separate word per voice in the mixer's smoothed parameter block. */
#define LOADED   ((volatile u32 *)(0x800014f0 + 0x131 * 4))  /* voice -> sound loaded */
#define PARAMS   ((volatile short *)0x800014f2)             /* the engine's 16-bit parameter block */

static int owner_of(int w, const unsigned char *kit)       /* the track whose sound voice w has, if another */
{
    u32 d = LOADED[w] - (u32)(kit + 0x20);
    int p;
    if (!kit || d % 0xa2)
        return -1;
    p = d / 0xa2;
    return p < 8 && p != w ? p : -1;
}

/* replaces 0x400771e8 (value, voice, slot): the stock write, then the same value on every voice that is
 * playing that track's sound */
void digipoly_setparam(int value, int voice, int slot)
{
    const unsigned char *kit = ENGINE_KIT;
    u32 own;
    int w;
    if (voice == 16) {
        PARAMS[432 + slot] = value;
        return;
    }
    PARAMS[53 * voice + 8 + slot] = value;
    own = (u32)(kit + 0x20 + voice * 0xa2);
    if (LOADED[voice] != own)
        LOADED[voice] = 0;
    if ((unsigned)voice > 7 || !kit)
        return;
    for (w = 0; w < 8; w++)
        if (w != voice && LOADED[w] == own)
            PARAMS[53 * w + 8 + slot] = value;
}

/* each render block, after the parameter smoothing (words: the smoothed block, word t = track t's level):
 * a stolen voice takes the level of the track whose sound it plays */
void digipoly_levels(short *words)
{
    const unsigned char *kit = ENGINE_KIT;
    int w, p;
    for (w = 0; w < 8; w++)
        if ((p = owner_of(w, kit)) >= 0)
            words[w] = words[p];
}

/* ---- TRIG page ---- */
static void *audio_views[4];                /* views seen with the audio TRIG page kind */

static int cur_kind(char *view)             /* the page kind the view is showing */
{
    int *b = *(int **)(view + 124), *e = *(int **)(view + 128), i = *(int *)(view + 144);
    if (!b || i < 0 || i >= e - b)
        return -1;
    return b[i];
}

void digipoly_trigkind(char *view)
{
    int *b = *(int **)(view + 124), *e = *(int **)(view + 128), i, t;
    if (e - b != 1)
        return;
    for (i = 0; i < 4 && audio_views[i] != view; i++)
        ;
    if (i == 4) {
        if (*b != 1)
            return;                         /* a MIDI track's TRIG page */
        for (i = 0; i < 4 && audio_views[i]; i++)
            ;
        if (i == 4)
            return;
        audio_views[i] = view;
    }
    t = ACTIVE_TRACK;
    *b = is_poly(UI_KIT, t) ? 15 : 1;
}

/* ---- SETTINGS > POLY: the tracks 1..8 that lend their voice ----
 * LEFT/RIGHT choose a track, YES takes it out of the pool or puts it back. The checkbox shows the chosen
 * track's state: ticked = its voice is in the POLY pool. A track in the pool is shown inverted. */
static int cursor;

void digipoly_select(void **payload)
{
    unsigned char *kit = UI_KIT;
    if (kit)
        POOLOUT(kit, cursor) = (unsigned char)(POOLOUT(kit, cursor) ^ 0x80);
    INVALIDATE((char *)*payload + 0x38);
}

void digipoly_change(void **payload, int unused, int delta)
{
    if (delta > 0 && cursor < 7)
        cursor++;
    else if (delta < 0 && cursor > 0)
        cursor--;
    else
        return;
    INVALIDATE((char *)*payload + 0x38);
}

void digipoly_draw(void *a, void *b, void *bmp, int x, int y)
{
    const unsigned char *kit = UI_KIT;
    int t, cx;
    BLIT(bmp, CHECKBOXES + (locked(kit, cursor) ? 0 : 0x1c), x, y, 0);   /* the chosen track: in the pool? */
    for (t = 0; t < 8; t++) {               /* after the label: 1..8, the pool's tracks inverted */
        cx = x + 34 + t * 5;
        TEXT(bmp, FONT5, cx, y, -1, "%d", t + 1);
        if (!locked(kit, t))
            FILLRECT(bmp, cx - 1, y - 1, cx + 3, y + 5, -1);
        if (t == cursor)
            FILLRECT(bmp, cx - 1, y + 7, cx + 3, y + 7, -1);   /* a bar over it (y grows upwards) */
    }
}

/* ---- the unit's own keys: a POLY track's key plays its chord ----
 * The panel calls liveNoteOn/liveNoteOff for the key (recorded as usual, one note); we add the chord's
 * other notes straight to the audio engine (0x40076b3c), so they sound without being recorded. */
#define LIVE_BUILD ((void (*)(int *))0x40076b3c)
#define LIVE_ON    ((void (*)(int, int, int, int, int, int, int))0x400d53dc)
#define LIVE_OFF   ((void (*)(int, int, int))0x400d575e)
#define PAT_TRACK(t) ((const unsigned char *)(0x409bac18 + (t) * 0x38f))

static int chord_notes(int track, int note, int *out)    /* -> how many extra notes the track's chord has */
{
    const unsigned char *d = PAT_TRACK(track) + 0x385;   /* NOT2, NOT3, NOT4 defaults */
    int i, n = 0;
    for (i = 0; i < 3; i++) {
        int b = d[i], v;
        if (b == NOTE_OFF || b == 0xff)
            continue;
        v = note + b - NOTE_OFF;
        if (v >= 0 && v <= 127)
            out[n++] = v;
    }
    return n;
}

static void live_note(int track, int note, int vel, int on)
{
    int src[12];
    int i;
    for (i = 0; i < 12; i++)
        src[i] = 0;
    src[0] = track;
    src[1] = note;
    src[2] = on ? vel : 0;
    src[3] = on ? 1 : 2;
    src[4] = on ? 0x10281 : 0;
    src[5] = -1;
    src[8] = 0x40;
    LIVE_BUILD(src);
}

void digipoly_prevon(int track, int note, int vel, int a3, int a4, int a5, int a6)
{
    int extra[3], n, i;
    LIVE_ON(track, note, vel, a3, a4, a5, a6);
    if (!is_poly(UI_KIT, track))
        return;
    n = chord_notes(track, note, extra);
    for (i = 0; i < n; i++)
        live_note(track, extra[i], vel, 1);
}

void digipoly_prevoff(int track, int note, int a2)
{
    int extra[3], n, i;
    LIVE_OFF(track, note, a2);
    if (!is_poly(UI_KIT, track))
        return;
    n = chord_notes(track, note, extra);
    for (i = 0; i < n; i++)
        live_note(track, extra[i], 0, 0);
}

/* ---- the POLY track's TRIG page keeps the track level in view ----
 * The MIDI tracks' page (which a POLY track borrows) has no LEV cell; the audio page has one under the
 * sample box. Drawn after the stock page, in the same place and at the same size as the stock one
 * (measured off the audio TRIG page): the frame x 4..10, the scale marks at x 0..1 and 13..14 every four
 * rows, the filled part three pixels wide, and "LEV" under it - replaced by the value for a moment after
 * the knob moves, as the stock pages do. The track levels are the high bytes of the words at
 * kit + 0x10 + 2 * track (0..127); the low bytes are the persistent map's bytes 0..7 (kitstore.h). */
#define TRACK_LEVEL(kit, t) ((kit)[0x10 + 2 * (t)])
#define FRAMERECT ((void (*)(void *, int, int, int, int, int))0x400c178a)

static int lev_shown = -1;                          /* the level at the last draw */
static int lev_hold;                                /* frames left showing the value instead of "LEV" */

void digipoly_levdraw(char *view, void *bmp)
{
    const unsigned char *kit = UI_KIT;
    int t = ACTIVE_TRACK, lev, h, i;
    if (!bmp || !is_poly(kit, t) || cur_kind(view) != 15) {
        lev_shown = -1;
        return;
    }
    lev = TRACK_LEVEL(kit, t) & 0x7f;
    if (lev_shown >= 0 && lev != lev_shown)
        lev_hold = 24;                              /* the knob just moved: show the number */
    else if (lev_hold > 0)
        lev_hold--;
    lev_shown = lev;
    h = (lev * 13) / 127;                           /* the filled part, 0..13 rows */
    FILLRECT(bmp, 0, 0, 15, 24, 0);                 /* our part of the left column (y grows upwards) */
    FRAMERECT(bmp, 4, 7, 10, 23, 1);
    if (h)
        FILLRECT(bmp, 6, 9, 8, 8 + h, 1);
    for (i = 0; i < 5; i++) {                       /* the scale marks either side */
        int y = 7 + 4 * i;
        FILLRECT(bmp, 0, y, 1, y, 1);
        FILLRECT(bmp, 13, y, 14, y, 1);
    }
    if (lev_hold > 0)
        TEXT(bmp, FONT5, lev >= 100 ? 1 : lev >= 10 ? 3 : 6, 0, -1, "%d", lev);
    else
        TEXT(bmp, FONT5, 1, 0, -1, "LEV");
}

/* ---- the LEVEL knob on a POLY track's TRIG page ----
 * The knob's event goes to the view, which asks itself which parameter the knob is on this page; the
 * MIDI page has none for LEVEL, so the turn is dropped. For the LEVEL knob on a POLY track we put the
 * page kind back to the audio one for the length of the stock call, so it answers "the track level". */
#define STOCK_TRIGENC ((int (*)(void *, void *))0x40032a78)

int digipoly_trigenc(char *view, void *ev)
{
    int id = *(int *)((char *)ev + 12);
    int *b = *(int **)(view + 124);
    int r;
    if (id != 9 || !b || cur_kind(view) != 15 || !is_poly(UI_KIT, ACTIVE_TRACK))
        return STOCK_TRIGENC(view, ev);
    *b = 1;
    r = STOCK_TRIGENC(view, ev);
    *b = 15;
    return r;
}

/* ---- recording notes onto a POLY track ----
 * The firmware records a live note on an audio track as a bare trig: it clears the step's NOT1..NOT4 to
 * "no value" and stores nothing, because an audio track has no notes. A POLY track does, so after the
 * trig is recorded (poly_glue.s hooks the tail of that path, where the track's pattern data, the track
 * and the note are all in hand) we write the notes in: the chord's notes are gathered as they arrive -
 * MIDI in sends one note-on each - and the whole chord is written again every time, lowest note in NOT1
 * and the others as their offsets from it, so a chord of up to four notes ends up in the piano roll.
 * The sequencer's record step is 0x4020c29c, 0..63 only while a note is being recorded. */
#define REC_STEP (*(volatile int *)0x4020c29c)
#define NOT1     0x280                              /* the step arrays, 0x40 apart */

static int rec_step[8], rec_n[8], rec_age[8];
static unsigned char rec_note[8][4];

/* The record step is -1 whenever a note is not being recorded, so it cannot say whether two notes belong
 * together: the chord is held for a few frames after its last note instead (a keyboard's notes arrive
 * within a few milliseconds of each other, the UI runs at 30 Hz), and anything later starts a new one. */
void digipoly_rectick(void *ctrl)
{
    int t;
    (void)ctrl;
    kstore_tick(&store, UI_KIT, KS_SLOT_POLY, poolmask);   /* a sound loaded onto a track keeps its pool flag */
    for (t = 0; t < 8; t++)
        if (rec_age[t] > 0 && --rec_age[t] == 0)
            rec_n[t] = 0;
}

void digipoly_recnote(unsigned char *d, int track, int note)
{
    int step = REC_STEP, i, j, base, n;
    if ((unsigned)track > 7 || (unsigned)step > 63 || note < 0 || note > 127)
        return;
    if (!is_poly(UI_KIT, track))
        return;
    if (rec_step[track] != step) {
        rec_step[track] = step;
        rec_n[track] = 0;
    }
    n = rec_n[track];
    for (i = 0; i < n; i++)
        if (rec_note[track][i] == note)
            return;                                 /* already in this chord */
    if (n >= 4)
        return;
    for (i = 0; i < n && rec_note[track][i] < note; i++)
        ;
    for (j = n; j > i; j--)                         /* keep them in order: NOT1 is the lowest */
        rec_note[track][j] = rec_note[track][j - 1];
    rec_note[track][i] = (unsigned char)note;
    rec_n[track] = ++n;
    rec_age[track] = 5;
    base = rec_note[track][0];
    d[NOT1 + step] = (unsigned char)base;
    for (i = 0; i < 3; i++) {
        int k = i + 1, v = NOTE_OFF;
        if (k < n) {
            int off = rec_note[track][k] - base;
            if (off >= -63 && off <= 63)
                v = NOTE_OFF + off;
        }
        d[NOT1 + 0x40 * (i + 1) + step] = (unsigned char)v;
    }
}
