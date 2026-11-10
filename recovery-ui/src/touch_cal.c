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
