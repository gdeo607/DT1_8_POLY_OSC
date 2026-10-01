/* SPDX-License-Identifier: MIT
 * digichain: NEIGHBOR's source on a machine switch (ev_tick).
 *
 * NEIGHBOR's SLOT (knob E, sound slot 21, its source track: 1-8, 0 off) is 0 after a switch, so a new
 * NEIGHBOR track is silent until it is set. When a track of the UI kit has been NEIGHBOR for half a second
 * (the machine menu switches as its cursor moves: passing over NEIGHBOR is not a switch to it) with SLOT
 * still 0, SLOT becomes the track on its left (track 2 for track 1). If the track then leaves NEIGHBOR with
 * SLOT still as set here, SLOT goes back to 0, so the next machine sees the value a switch leaves (Digi
 * Mono's defaults look for it). Only with NEIGHBOR in the build (its nb_layout is a weak import). */
#include <stdint.h>

extern char core_zero[];
extern char nb_layout[];

#define UI_KIT      (*(uint8_t *volatile const *)0x4199dc44)   /* the UI kit: sounds at + 0x20 + 0xa2 t */
#define M_NBR       4
#define SLOT_SRC    21                         /* knob E */
#define SETTLE      15                         /* ticks (30 Hz): half a second */
typedef void (*setparam_t)(int32_t value, int32_t voice, int32_t slot);
#define SETPARAM    ((setparam_t)0x400771e8)   /* the firmware's knob path: the engine's copy */

static const uint8_t *seen_kit;
static uint8_t seen_mach[8], wait_t[8], set_by_us[8];

static uint16_t *src_word(uint8_t *kit, int t)
{
    return (uint16_t *)(kit + 0x20 + 0xa2 * t + 0x14 + 2 * SLOT_SRC);
}

static void set_src(uint8_t *kit, int t, int v)
{
    *src_word(kit, t) = (uint16_t)(v << 8);
    SETPARAM((int32_t)v << 8, t, SLOT_SRC);
}

void digichain_tick(void *ctrl)
{
    uint8_t *kit = UI_KIT;
    int t;
    (void)ctrl;
    if (!kit || nb_layout == core_zero)
        return;
    if (kit != seen_kit) {                  /* another pattern's kit: take it as it is */
        for (t = 0; t < 8; t++) {
            seen_mach[t] = kit[0x9e + 0xa2 * t];
            wait_t[t] = set_by_us[t] = 0;
        }
        seen_kit = kit;
        return;
    }
    for (t = 0; t < 8; t++) {
        int m = kit[0x9e + 0xa2 * t];
        if (m != seen_mach[t]) {
            if (seen_mach[t] == M_NBR && set_by_us[t] && (*src_word(kit, t) >> 8) == set_by_us[t])
                set_src(kit, t, 0);         /* left NEIGHBOR untouched: back to what a switch leaves */
            seen_mach[t] = (uint8_t)m;
            set_by_us[t] = 0;
            wait_t[t] = m == M_NBR ? SETTLE : 0;
            continue;
        }
        if (wait_t[t] && --wait_t[t] == 0 && (*src_word(kit, t) >> 8) == 0) {
            int src = t ? t : 2;            /* 1-based: the track on its left (t), track 2 for track 1 */
            set_src(kit, t, src);
            set_by_us[t] = (uint8_t)src;
        }
    }
}
