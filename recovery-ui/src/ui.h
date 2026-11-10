#ifndef RUI_UI_H
#define RUI_UI_H

#include "lvgl.h"

/* Build fonts/theme and show the home screen */
void ui_init(lv_display_t *disp);

/* Headless review: walk through every screen (with simulated data from
 * the AD5X_RUI_* environment, see sim/run-sim.sh), calling shot(name)
 * after each one is rendered. Returns the number of failed checks made
 * on the way (logged as "shots: FAIL ..."). */
int ui_run_shots(void (*shot)(const char *name));

#endif
