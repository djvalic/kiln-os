/* The touch calibration of the recovery UI (issue #47): the range of the
 * stock tsc2007 driver's units (0-800 x 0-480, Y already flipped) that
 * maps to the 800x480 screen. S80ad5x-recovery-ui passes the main OS's
 * calibration as AD5X_RUI_TOUCH_CAL="min_x min_y max_x max_y" (a pair the
 * other way round inverts that axis); without it, or with one that can't
 * be used, the panel's usual range from the seed settings of HelixScreen
 * (helixscreen-settings.json). The driver's full range is never used: the
 * panel never reports its edges, so Back in the top left corner could not
 * be reached.
 * Our 6.6 kernel's tsc2007 reports raw 0-4095 instead, with Y not flipped.
 * The calibration stays in stock units (the file, the variable and the
 * default); with AD5X_RUI_TOUCH_UNITS=raw (S80ad5x-recovery-ui, from
 * kernel.sh) touch_cal_to_raw converts it at use. */
#ifndef RUI_TOUCH_CAL_H
#define RUI_TOUCH_CAL_H

#include <stdbool.h>

#define TOUCH_CAL_DEFAULT_MIN_X 60
#define TOUCH_CAL_DEFAULT_MIN_Y 72
#define TOUCH_CAL_DEFAULT_MAX_X 723
#define TOUCH_CAL_DEFAULT_MAX_Y 404

/* v = {min_x, min_y, max_x, max_y} from ENV (may be NULL); true when ENV
 * was used, false for the default. ENV must be four whole numbers within
 * -10000..10000 with min != max on each axis. */
bool touch_cal_from_env(const char *env, int v[4]);

/* v (stock units, as touch_cal_from_env gives it) -> the raw tsc2007 units
 * of our 6.6 kernel, edge for edge: x * 4096 / 800 and (480 - y) * 4096 /
 * 480, rounded, the inverse of the main OS's ad5x-touch-units
 * --recovery-cal. Y comes out the other way round (min above max), which
 * LVGL's calibration takes as an inverted axis. */
void touch_cal_to_raw(int v[4]);

#endif
