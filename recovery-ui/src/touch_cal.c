#include "touch_cal.h"

#include <stdio.h>

bool touch_cal_from_env(const char *env, int v[4])
{
	int a, b, c, d;
	char end;
	if (env && sscanf(env, "%d %d %d %d %c", &a, &b, &c, &d, &end) == 4 &&
	    a != c && b != d &&
	    a >= -10000 && a <= 10000 && b >= -10000 && b <= 10000 &&
	    c >= -10000 && c <= 10000 && d >= -10000 && d <= 10000) {
		v[0] = a, v[1] = b, v[2] = c, v[3] = d;
		return true;
	}
	v[0] = TOUCH_CAL_DEFAULT_MIN_X;
	v[1] = TOUCH_CAL_DEFAULT_MIN_Y;
	v[2] = TOUCH_CAL_DEFAULT_MAX_X;
	v[3] = TOUCH_CAL_DEFAULT_MAX_Y;
	return false;
}

#define TOUCH_W 800
#define TOUCH_H 480
#define TOUCH_RAW 4096

/* n / d rounded to the nearest, halves away from zero (d > 0) */
static int div_round(long n, long d)
{
	return (int)(n >= 0 ? (n + d / 2) / d : -((-n + d / 2) / d));
}

void touch_cal_to_raw(int v[4])
{
	int min_y = v[1], max_y = v[3];
	v[0] = div_round((long)v[0] * TOUCH_RAW, TOUCH_W);
	v[2] = div_round((long)v[2] * TOUCH_RAW, TOUCH_W);
	v[1] = div_round((long)(TOUCH_H - min_y) * TOUCH_RAW, TOUCH_H);
	v[3] = div_round((long)(TOUCH_H - max_y) * TOUCH_RAW, TOUCH_H);
}
