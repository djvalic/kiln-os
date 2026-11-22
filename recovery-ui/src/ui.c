/* ad5x-recovery-ui screens (LVGL v9, 800x480, touch) */
#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include "ui.h"
#include "commands.h"
#include "job.h"
#include "swu.h"
#include "sys.h"
#include "i18n.h"
#include "lang.h"
#include "progress.h"
#include <stdarg.h>

#include <errno.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

/* ------------------------------------------------------------------ style */

/* The brand's Nord colours, as the boot logos and install screens
 * (tools/make_logo.py, docs/brand) and HelixScreen's Nord theme tokens in
 * brackets. Flat ground. Contrast: C_TEXT on the fills 3.5:1 (their labels
 * are 20 px bold), C_ACCENT text 5.0:1 and C_DANGER icons 3.7:1 on C_CARD. */
#define C_BG_TOP   lv_color_hex(0x2E3440)	/* [screen_bg] */
#define C_BG_BOT   lv_color_hex(0x2E3440)
#define C_CARD     lv_color_hex(0x3B4252)	/* [overlay_bg] */
#define C_CARD_HI  lv_color_hex(0x434C5E)	/* [card_bg] */
#define C_BORDER   lv_color_hex(0x4C566A)	/* [elevated_bg] */
#define C_TEXT     lv_color_hex(0xECEFF4)	/* [text] */
#define C_MUTED    lv_color_hex(0xD8DEE9)	/* [text_muted] */
#define C_ACCENT   lv_color_hex(0x88C0D0)	/* [primary]: text, icons, lines */
#define C_ACCENT_FILL lv_color_hex(0x5E81AC)	/* [tertiary]: under C_TEXT */
#define C_DANGER   lv_color_hex(0xCC8C93)	/* [danger] + 30% text: text, icons */
#define C_DANGER_FILL lv_color_hex(0xBF616A)	/* [danger]: under C_TEXT */
#define C_WARN     lv_color_hex(0xEBCB8B)	/* [warning] */
#define C_OK       lv_color_hex(0xA3BE8C)	/* [success] */

#define W 800
#define H 480
#define PAD 14
#define HEADER_H 64

extern const unsigned char noto_sans_regular_ttf[], noto_sans_bold_ttf[], noto_sans_mono_ttf[];
extern const size_t noto_sans_regular_ttf_len, noto_sans_bold_ttf_len, noto_sans_mono_ttf_len;

static lv_font_t *F16, *F20, *F20B, *F24B, *F28B, *F40, *FMONO;

static lv_font_t *mkfont(const unsigned char *data, size_t len, int px, const lv_font_t *fb)
{
	lv_font_t *f = lv_tiny_ttf_create_data_ex(data, len, px, LV_FONT_KERNING_NORMAL, 256);
	if (!f)
		return (lv_font_t *)fb;
	f->fallback = fb;	/* LV_SYMBOL_* icons */
	return f;
}

static void fonts_init(void)
{
	F16 = mkfont(noto_sans_regular_ttf, noto_sans_regular_ttf_len, 16, &lv_font_montserrat_16);
	F20 = mkfont(noto_sans_regular_ttf, noto_sans_regular_ttf_len, 20, &lv_font_montserrat_20);
	F20B = mkfont(noto_sans_bold_ttf, noto_sans_bold_ttf_len, 20, &lv_font_montserrat_20);
	F24B = mkfont(noto_sans_bold_ttf, noto_sans_bold_ttf_len, 24, &lv_font_montserrat_24);
	F28B = mkfont(noto_sans_bold_ttf, noto_sans_bold_ttf_len, 28, &lv_font_montserrat_28);
	F40 = mkfont(noto_sans_regular_ttf, noto_sans_regular_ttf_len, 40, &lv_font_montserrat_40);
	FMONO = mkfont(noto_sans_mono_ttf, noto_sans_mono_ttf_len, 15, &lv_font_montserrat_14);
}

static lv_obj_t *label(lv_obj_t *parent, const char *text, const lv_font_t *f, lv_color_t c)
{
	lv_obj_t *l = lv_label_create(parent);
	lv_label_set_text(l, text);
	lv_obj_set_style_text_font(l, f, 0);
	lv_obj_set_style_text_color(l, c, 0);
	return l;
}

static lv_obj_t *wrap_label(lv_obj_t *parent, const char *text, const lv_font_t *f, lv_color_t c)
{
	lv_obj_t *l = label(parent, text, f, c);
	lv_label_set_long_mode(l, LV_LABEL_LONG_MODE_WRAP);
	lv_obj_set_width(l, lv_pct(100));
	return l;
}

/* Text with an icon in front: icon, sep, then fmt (a translated text, with
 * its arguments) formatted into t. The icon is never translated. */
static char *iconed_v(char *t, size_t cap, const char *icon, const char *sep,
	const char *fmt, va_list ap)
{
	size_t k = (size_t)snprintf(t, cap, "%s%s", icon ? icon : "", icon ? sep : "");
	if (k < cap)
		vsnprintf(t + k, cap - k, fmt, ap);
	return t;
}

static char *iconed(char *t, size_t cap, const char *icon, const char *sep, const char *fmt, ...)
{
	va_list ap;
	va_start(ap, fmt);
	iconed_v(t, cap, icon, sep, fmt, ap);
	va_end(ap);
	return t;
}

static void set_iconed(lv_obj_t *l, const char *icon, const char *sep, const char *fmt, ...)
{
	char t[480];
	va_list ap;
	va_start(ap, fmt);
	iconed_v(t, sizeof(t), icon, sep, fmt, ap);
	va_end(ap);
	lv_label_set_text(l, t);
}

/* ad5x-status words for slot B, translated; other values as they are */
static const char *slot_word(const char *s)
{
	if (!strcmp(s, "installed"))
		return tr(RS_SLOT_INSTALLED);
	if (!strcmp(s, "not found"))
		return tr(RS_SLOT_NOT_FOUND);
	if (!strcmp(s, "empty"))
		return tr(RS_SLOT_EMPTY);
	if (!strcmp(s, "unknown"))
		return tr(RS_SLOT_UNKNOWN);
	return s;
}

/* SWUpdate's status, translated (the order is swu_status's) */
static const char *swu_status_tr(swu_status s)
{
	static const enum rui_str ids[] = {
		RS_SWU_IDLE, RS_SWU_STARTING, RS_SWU_INSTALLING, RS_SWU_SUCCESS, RS_SWU_FAILED,
		RS_SWU_RECEIVING, RS_SWU_DONE, RS_SWU_SUBPROCESS, RS_SWU_PROGRESS,
	};
	return (unsigned)s < sizeof(ids) / sizeof(ids[0]) ? tr(ids[s]) : swu_status_name(s);
}

static void plain(lv_obj_t *o)
{
	lv_obj_set_style_bg_opa(o, LV_OPA_TRANSP, 0);
	lv_obj_set_style_border_width(o, 0, 0);
	lv_obj_set_style_pad_all(o, 0, 0);
	lv_obj_set_style_radius(o, 0, 0);
}

static lv_obj_t *box(lv_obj_t *parent, lv_flex_flow_t flow)
{
	lv_obj_t *o = lv_obj_create(parent);
	plain(o);
	lv_obj_set_flex_flow(o, flow);
	lv_obj_remove_flag(o, LV_OBJ_FLAG_SCROLLABLE);
	return o;
}

static lv_obj_t *card(lv_obj_t *parent)
{
	lv_obj_t *o = lv_obj_create(parent);
	lv_obj_set_style_bg_color(o, C_CARD, 0);
	lv_obj_set_style_bg_opa(o, LV_OPA_COVER, 0);
	lv_obj_set_style_border_color(o, C_BORDER, 0);
	lv_obj_set_style_border_width(o, 1, 0);
	lv_obj_set_style_radius(o, 14, 0);
	lv_obj_set_style_pad_all(o, 12, 0);
	lv_obj_remove_flag(o, LV_OBJ_FLAG_SCROLLABLE);
	return o;
}

/* Big touch button: icon + text. kind: 0 normal, 1 accent, 2 danger, 3 warn */
static lv_obj_t *button(lv_obj_t *parent, const char *icon, const char *text, int kind,
			lv_event_cb_t cb, void *ud)
{
	lv_obj_t *b = lv_button_create(parent);
	lv_color_t bg = kind == 1 ? C_ACCENT_FILL : kind == 2 ? C_DANGER_FILL : kind == 3 ? C_WARN : C_CARD_HI;
	lv_obj_set_style_bg_color(b, bg, 0);
	lv_obj_set_style_bg_opa(b, LV_OPA_COVER, 0);
	lv_obj_set_style_radius(b, 12, 0);
	lv_obj_set_style_shadow_width(b, 0, 0);
	lv_obj_set_style_border_width(b, kind ? 0 : 1, 0);
	lv_obj_set_style_border_color(b, C_BORDER, 0);
	lv_obj_set_style_bg_color(b, C_CARD, LV_STATE_DISABLED);
	lv_obj_set_style_text_color(b, lv_color_hex(0x7B8394), LV_STATE_DISABLED);
	lv_obj_set_style_pad_hor(b, 18, 0);
	lv_obj_set_style_text_color(b, C_TEXT, 0);
	lv_obj_set_height(b, 60);
	lv_obj_t *l = lv_label_create(b);
	char t[160];
	snprintf(t, sizeof(t), "%s%s%s", icon ? icon : "", icon && text ? "  " : "", text ? text : "");
	lv_label_set_text(l, t);
	lv_obj_set_style_text_font(l, F20B, 0);
	lv_obj_center(l);
	if (cb)
		lv_obj_add_event_cb(b, cb, LV_EVENT_CLICKED, ud);
	return b;
}

static void enable(lv_obj_t *o, bool on)
{
	if (!o)
		return;
	if (on)
		lv_obj_remove_state(o, LV_STATE_DISABLED);
	else
		lv_obj_add_state(o, LV_STATE_DISABLED);
}

static void show(lv_obj_t *o, bool on)
{
	if (!o)
		return;
	if (on)
		lv_obj_remove_flag(o, LV_OBJ_FLAG_HIDDEN);
	else
		lv_obj_add_flag(o, LV_OBJ_FLAG_HIDDEN);
}

/* -------------------------------------------------------------- navigation */

typedef void (*page_fn)(void);
static page_fn cur_page;
static void (*cur_refresh)(void);	/* called every 250 ms */
static lv_obj_t *scr;			/* current screen */

static void page_home(void);
static void page_update(void);
static void page_backup(void);
static void page_restore(void);
static void page_return(void);
static void page_bootloader(void);
static void page_bootloader_upgrade(void);
static void page_network(void);
static void page_logs(void);
static void page_power(void);
static void page_job(void);
static void page_auto(void);

static void dlg_close(void);

static void go(page_fn f)
{
	/* any dialog, with its arm timer and the top layer's CLICKABLE flag:
	 * left behind, the next page lost its taps to the empty top layer and
	 * the timer touched the deleted OK button (a web update opens the job
	 * page over a dialog, issue #47) */
	dlg_close();
	cur_refresh = NULL;
	lv_obj_t *old = scr;
	scr = lv_obj_create(NULL);
	lv_obj_set_style_bg_color(scr, C_BG_TOP, 0);
	lv_obj_set_style_bg_grad_color(scr, C_BG_BOT, 0);
	lv_obj_set_style_bg_grad_dir(scr, LV_GRAD_DIR_VER, 0);
	lv_obj_set_style_bg_opa(scr, LV_OPA_COVER, 0);
	lv_obj_set_style_text_color(scr, C_TEXT, 0);
	lv_obj_set_style_text_font(scr, F20, 0);
	lv_obj_remove_flag(scr, LV_OBJ_FLAG_SCROLLABLE);
	cur_page = f;
	f();
	lv_screen_load(scr);
	if (old)
		lv_obj_delete(old);
	if (cur_refresh)
		cur_refresh();
}

static void on_go(lv_event_t *e)
{
	go((page_fn)lv_event_get_user_data(e));
}

static void on_home(lv_event_t *e)
{
	(void)e;
	go(page_home);
}

/* Header with Back (unless back == false) and title; returns the body:
 * a flex column filling the rest of the screen. */
static lv_obj_t *back_btn;

static lv_obj_t *page_frame(const char *title, bool back)
{
	lv_obj_t *hdr = box(scr, LV_FLEX_FLOW_ROW);
	lv_obj_set_size(hdr, W, HEADER_H);
	lv_obj_set_pos(hdr, 0, 0);
	lv_obj_set_style_pad_hor(hdr, PAD, 0);
	lv_obj_set_style_pad_column(hdr, 16, 0);
	lv_obj_set_flex_align(hdr, LV_FLEX_ALIGN_START, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);
	back_btn = NULL;
	if (back) {
		back_btn = button(hdr, LV_SYMBOL_LEFT, tr(RS_BACK), 0, on_home, NULL);
		lv_obj_set_size(back_btn, 130, 50);
	}
	label(hdr, title, F28B, C_TEXT);
	lv_obj_t *line = lv_obj_create(scr);
	plain(line);
	lv_obj_set_style_bg_color(line, C_ACCENT, 0);
	lv_obj_set_style_bg_opa(line, LV_OPA_COVER, 0);
	lv_obj_set_size(line, W, 2);
	lv_obj_set_pos(line, 0, HEADER_H);

	lv_obj_t *body = box(scr, LV_FLEX_FLOW_COLUMN);
	lv_obj_set_pos(body, PAD, HEADER_H + 2 + 10);
	lv_obj_set_size(body, W - 2 * PAD, H - HEADER_H - 2 - 10 - PAD);
	lv_obj_set_style_pad_row(body, 10, 0);
	return body;
}

/* ------------------------------------------------------- confirm dialogs */

typedef void (*action_fn)(void);

static struct {
	char title[96], text[1024], text2[1024], ok[96];
	bool danger, twice;
	action_fn fn;
	lv_obj_t *ok_btn;
	lv_timer_t *arm;
	int arm_left;
} dlg;

static void dlg_close(void)
{
	if (dlg.arm) {
		lv_timer_delete(dlg.arm);
		dlg.arm = NULL;
	}
	lv_obj_clean(lv_layer_top());
	lv_obj_remove_flag(lv_layer_top(), LV_OBJ_FLAG_CLICKABLE);
	dlg.ok_btn = NULL;
}

static void dlg_show(int stage);

static void on_dlg_cancel(lv_event_t *e)
{
	(void)e;
	slog("cancelled: %s", dlg.title);
	dlg_close();
}

static void on_dlg_ok(lv_event_t *e)
{
	int stage = (int)(intptr_t)lv_event_get_user_data(e);
	if (dlg.twice && stage == 1) {
		dlg_show(2);
		return;
	}
	dlg_close();
	if (dlg.fn)
		dlg.fn();
}

static void arm_tick(lv_timer_t *t)
{
	(void)t;
	if (!dlg.ok_btn)
		return;
	lv_obj_t *l = lv_obj_get_child(dlg.ok_btn, 0);
	if (--dlg.arm_left > 0) {
		lv_label_set_text_fmt(l, tr(RS_WAIT_N_S), dlg.arm_left);
		return;
	}
	lv_label_set_text(l, dlg.ok);
	enable(dlg.ok_btn, true);
	lv_timer_delete(dlg.arm);
	dlg.arm = NULL;
}

/* Stage 1: question, Cancel left / OK right. Stage 2 (destructive): the
 * last word, buttons swapped (a double tap can't hit both) and OK armed
 * only after 2 s. */
static void dlg_show(int stage)
{
	dlg_close();
	lv_obj_t *top = lv_layer_top();
	lv_obj_add_flag(top, LV_OBJ_FLAG_CLICKABLE);	/* modal */
	lv_obj_t *scrim = lv_obj_create(top);
	plain(scrim);
	lv_obj_set_size(scrim, W, H);
	lv_obj_set_style_bg_color(scrim, lv_color_black(), 0);
	lv_obj_set_style_bg_opa(scrim, LV_OPA_70, 0);
	lv_obj_remove_flag(scrim, LV_OBJ_FLAG_SCROLLABLE);

	lv_obj_t *c = card(scrim);
	lv_obj_set_size(c, 640, LV_SIZE_CONTENT);
	lv_obj_center(c);
	lv_obj_set_style_pad_all(c, 22, 0);
	lv_obj_set_style_border_color(c, dlg.danger ? C_DANGER : C_ACCENT, 0);
	lv_obj_set_style_border_width(c, 2, 0);
	lv_obj_set_flex_flow(c, LV_FLEX_FLOW_COLUMN);
	lv_obj_set_style_pad_row(c, 14, 0);

	char t[160];
	if (stage == 2)
		snprintf(t, sizeof(t), "%s", tr_sym(LV_SYMBOL_WARNING, RS_ARE_YOU_SURE));
	else
		snprintf(t, sizeof(t), "%s%s", dlg.danger ? LV_SYMBOL_WARNING "  " : "", dlg.title);
	label(c, t, F28B, dlg.danger ? C_DANGER : C_TEXT);
	wrap_label(c, stage == 2 ? dlg.text2 : dlg.text, F20, C_TEXT);
	if (dlg.twice)
		label(c, tr(stage == 1 ? RS_STEP_1_OF_2 : RS_STEP_2_OF_2),
		      F16, C_MUTED);

	lv_obj_t *row = box(c, LV_FLEX_FLOW_ROW);
	lv_obj_set_size(row, lv_pct(100), LV_SIZE_CONTENT);
	lv_obj_set_flex_align(row, LV_FLEX_ALIGN_SPACE_BETWEEN, LV_FLEX_ALIGN_CENTER,
			      LV_FLEX_ALIGN_CENTER);
	lv_obj_set_style_pad_top(row, 6, 0);
	lv_obj_t *cancel = NULL, *ok = NULL;
	if (stage == 2) {
		ok = button(row, NULL, dlg.ok, dlg.danger ? 2 : 1, on_dlg_ok, (void *)(intptr_t)2);
		cancel = button(row, LV_SYMBOL_CLOSE, tr(RS_CANCEL), 0, on_dlg_cancel, NULL);
	} else {
		cancel = button(row, LV_SYMBOL_CLOSE, tr(RS_CANCEL), 0, on_dlg_cancel, NULL);
		ok = button(row, NULL, dlg.twice ? tr(RS_CONTINUE) : dlg.ok, dlg.danger ? 2 : 1,
			    on_dlg_ok, (void *)(intptr_t)1);
	}
	lv_obj_set_size(cancel, 240, 64);
	lv_obj_set_size(ok, 280, 64);
	dlg.ok_btn = ok;
	if (stage == 2) {
		enable(ok, false);
		dlg.arm_left = 3;
		lv_label_set_text_fmt(lv_obj_get_child(ok, 0), tr(RS_WAIT_N_S), dlg.arm_left);
		dlg.arm = lv_timer_create(arm_tick, 700, NULL);
	}
}

static void confirm(const char *title, const char *text, const char *ok, bool danger,
		    const char *text2, action_fn fn)
{
	snprintf(dlg.title, sizeof(dlg.title), "%s", title);
	snprintf(dlg.text, sizeof(dlg.text), "%s", text);
	snprintf(dlg.text2, sizeof(dlg.text2), "%s", text2 ? text2 : "");
	snprintf(dlg.ok, sizeof(dlg.ok), "%s", ok);
	dlg.danger = danger;
	dlg.twice = text2 != NULL;
	dlg.fn = fn;
	dlg_show(1);
}

/* ------------------------------------------------------------ job launch */

typedef enum { JK_CMD, JK_INSTALL, JK_WEB } job_kind;
typedef enum { AFTER_NONE, AFTER_BOOT_MAIN, AFTER_REBOOT, AFTER_POWEROFF } job_after;

static struct {
	job_kind kind;
	char title[96];
	char what[160];		/* subtitle: file, destination... */
	bool cancelable;
	bool reboots;		/* the command reboots the printer */
	bool critical;		/* writes the eMMC: "don't switch off" */
	job_after after;	/* button offered after success */
	bool started;
	bool failed_start;
	unsigned last_seq, last_swu;
	unsigned swu_seq_at_start, swu_result_at_start;
	char *pending;		/* command waiting for a status query to end */
	const char *done_text;	/* shown for a last line "result: done..." (set
				 * right after start_job_x; read when it ends) */
} jb;

static void status_kick(bool slots);
static bool status_busy(void);

/* text has the whole line LINE */
static bool text_has_line(const char *text, const char *line)
{
	size_t n = strlen(line);
	for (const char *l = text; l && *l; l = strchr(l, '\n') ? strchr(l, '\n') + 1 : NULL)
		if (!strncmp(l, line, n) && (l[n] == '\n' || l[n] == 0 || l[n] == '\r'))
			return true;
	return false;
}

static void start_job_x(job_kind kind, const char *title, const char *what, const char *cmd,
			bool cancelable, bool reboots, bool critical, job_after after)
{
	free(jb.pending);
	memset(&jb, 0, sizeof(jb));
	jb.kind = kind;
	snprintf(jb.title, sizeof(jb.title), "%s", title);
	snprintf(jb.what, sizeof(jb.what), "%s", what ? what : "");
	jb.cancelable = cancelable;
	jb.reboots = reboots;
	jb.critical = critical;
	jb.after = after;
	swu_state s;
	swu_get(&s);
	jb.swu_seq_at_start = s.seq;
	jb.swu_result_at_start = s.result_seq;
	/* `ad5x-status --slots` mounts the slots for a moment: a restore or
	 * install must not start meanwhile (it would find rootfs2 mounted) */
	if (cmd && status_busy()) {
		jb.pending = strdup(cmd);
	} else if (cmd) {
		jb.started = job_start(title, cmd);
		jb.failed_start = !jb.started;
	}
	go(page_job);
}

static void start_job(job_kind kind, const char *title, const char *what, const char *cmd,
		      bool cancelable, bool reboots)
{
	start_job_x(kind, title, what, cmd, cancelable, reboots, false, AFTER_NONE);
}

/* ---------------------------------------------------------- system state */

/* `ad5x-status` (key=value lines), refreshed in the background every 5 s;
 * `--slots` (mounts both slots, slower) at start and after every job. */
static struct {
	capture *cap;
	bool cap_slots, want_slots;
	char text[4096];
	char slots[1024];	/* slot_a=, slot_b=, bootloader= lines from the last --slots */
	/* a --slots run has finished (the power page's boot loader line says
	 * "reading" before), and the last one ran during the start-up
	 * actions (auto=running): one more once they are done */
	bool slots_read, slots_auto;
	unsigned seq;
	time_t last;
} stc;

static bool kv_in(const char *text, const char *key, char *out, size_t cap);

static bool status_busy(void)
{
	return stc.cap != NULL;
}

static void status_kick(bool slots)
{
	stc.want_slots |= slots;
	stc.last = 0;
}

static void status_poll(void)
{
	if (stc.cap) {
		if (!capture_done(stc.cap))
			return;
		const char *t = capture_text(stc.cap);
		snprintf(stc.text, sizeof(stc.text), "%s", t ? t : "");
		char au[16];
		bool auto_run = kv_in(stc.text, "auto", au, sizeof(au)) && !strcmp(au, "running");
		if (stc.cap_slots) {
			stc.slots[0] = 0;
			for (const char *l = stc.text; l && *l; l = strchr(l, '\n') ? strchr(l, '\n') + 1 : NULL)
				if (!strncmp(l, "slot_", 5) || !strncmp(l, "bootloader", 10)) {
					size_t n = strlen(stc.slots);
					snprintf(stc.slots + n, sizeof(stc.slots) - n, "%.*s\n",
						 (int)strcspn(l, "\n"), l);
				}
			stc.slots_read = true;
			stc.slots_auto = auto_run;
		} else if (stc.slots_auto && !auto_run) {
			/* the start-up actions are done (they may have installed
			 * the main OS or mounted a stick): the slots and the boot
			 * loader once more, as they are now */
			stc.slots_auto = false;
			stc.want_slots = true;
			stc.last = 0;
		}
		capture_free(stc.cap);
		stc.cap = NULL;
		stc.seq++;
		return;
	}
	time_t now = time(NULL);
	if (job_running() || jb.pending || (stc.last && now - stc.last < 5))
		return;
	stc.last = now;
	stc.cap_slots = stc.want_slots;
	stc.want_slots = false;
	char *c = cmd_expand(stc.cap_slots ? CMD_STATUS_SLOTS : CMD_STATUS, NULL);
	stc.cap = capture_start(c, sizeof(stc.text));
	free(c);
}

static bool kv_in(const char *text, const char *key, char *out, size_t cap)
{
	size_t kl = strlen(key);
	for (const char *l = text; l && *l; l = strchr(l, '\n') ? strchr(l, '\n') + 1 : NULL) {
		if (!strncmp(l, key, kl) && l[kl] == '=') {
			const char *v = l + kl + 1;
			snprintf(out, cap, "%.*s", (int)strcspn(v, "\n"), v);
			return out[0] != 0;
		}
	}
	return false;
}

/* A status value; false when unknown or empty */
static bool kv(const char *key, char *out, size_t cap)
{
	out[0] = 0;
	return kv_in(stc.text, key, out, cap) || kv_in(stc.slots, key, out, cap);
}

/* Kiln's boot loader: the install record is an upgrade's (ad5x-status
 * bootloader_kind=upgrade) and still current (started, or installed and
 * its first start recorded or not), not one left from before a Return to
 * Flashforge firmware */
static bool bl_record_upgrade(void)
{
	char k[16], st[24];
	if (!kv("bootloader_kind", k, sizeof(k)) || strcmp(k, "upgrade") ||
	    !kv("bootloader_install", st, sizeof(st)))
		return false;
	return !strcmp(st, "started") || !strcmp(st, "installed") ||
	       !strcmp(st, "verified") || !strcmp(st, "unverified");
}

/* Kiln's boot loader's page opened by itself this start (home_refresh) */
static bool bl_shown;

/* The start-up actions (ad5x-recovery-auto) still running: ad5x-status
 * auto=running (done, or off with /data/ad5x/recovery/noauto: not
 * waited for). Jobs that check for them (ad5x-bootloader-install's "no
 * other job") wait instead of running into "busy: start-up-actions" */
static bool auto_running(void)
{
	char v[16];
	return kv("auto", v, sizeof(v)) && !strcmp(v, "running");
}

/* The printer's IPv4 (no /prefix) and interface */
static bool cur_ip(char *ip, size_t cap, char *ifc, size_t icap)
{
	if (kv("net_ip", ip, cap)) {
		ip[strcspn(ip, "/")] = 0;
		if (!kv("net_if", ifc, icap))
			snprintf(ifc, icap, "net");
		return true;
	}
	return sys_main_ip(ip, cap, ifc, icap);
}

/* ------------------------------------------------------------------- home */

static struct {
	lv_obj_t *ip, *slot, *trace, *last, *chip;
	unsigned seen;
} hm;

static void boot_main_now(void)
{
	char *c = cmd_expand(CMD_BOOT_MAIN, NULL);
	start_job(JK_CMD, tr(RS_BOOT_MAIN_OS), tr(RS_BOOT_MAIN_WHAT),
		  c, false, true);
	free(c);
}

/* What slot B holds: ad5x-status --slots, else a look at its first bytes */
static const char *main_os_text(char *buf, size_t cap)
{
	if (kv("slot_b", buf, cap))
		return buf;
	snprintf(buf, cap, "%s", sys_main_installed() ? "installed" : "not found");
	return buf;
}

/* A Return to Flashforge firmware started and not finished (ad5x-status
 * return_stock=unfinished): slot B may hold part of a system, so Boot main
 * OS and Install are locked; the dialog leads to the return page */
static bool return_unfinished(void)
{
	char v[24];
	return kv("return_stock", v, sizeof(v)) && !strcmp(v, "unfinished");
}

static void open_return(void)
{
	go(page_return);
}

static bool return_lock(void)
{
	if (!return_unfinished())
		return false;
	confirm(tr(RS_RS_LOCKED_Q), tr(RS_RS_LOCKED_TEXT), tr_sym(LV_SYMBOL_WARNING, RS_RS_OPEN),
		true, NULL, open_return);
	return true;
}

static void on_boot_main(lv_event_t *e)
{
	(void)e;
	if (return_lock())
		return;
	char what[96];
	main_os_text(what, sizeof(what));
	if (strcmp(what, "empty") && strcmp(what, "not found") && strcmp(what, "unknown"))
		confirm(tr(RS_BOOT_MAIN_Q),
			tr(RS_BOOT_MAIN_TEXT), tr_sym(LV_SYMBOL_PLAY, RS_BOOT_MAIN_OS), false, NULL,
			boot_main_now);
	else
		confirm(tr(RS_NO_MAIN_Q),
			tr(RS_NO_MAIN_TEXT), tr_sym(LV_SYMBOL_PLAY, RS_TRY), true, NULL, boot_main_now);
}

static void home_refresh(void)
{
	if (hm.seen == stc.seq + 1)
		return;
	hm.seen = stc.seq + 1;
	/* Once per start: Return to Flashforge firmware asked for (main OS,
	 * USB stick marker) or left unfinished opens its page; it writes
	 * nothing without a tap there */
	static bool return_shown;
	char ro[24];
	if (!return_shown && stc.seq > 0 && !job_running() &&
	    ((kv("return_stock_open", ro, sizeof(ro)) && ro[0]) || return_unfinished())) {
		return_shown = true;
		slog("opening Return to Flashforge firmware (%s)", ro[0] ? ro : "unfinished");
		go(page_return);
		return;
	}
	/* Once per start: the first start after Kiln's boot loader was
	 * installed (its result) or an unfinished install opens its page
	 * (ad5x-bootloader-install --verify-start). It opens at once, while
	 * the start-up actions may still run: the page shows the result and
	 * waits for them before its check (bl_start_check) */
	char bo[16];
	if (!bl_shown && stc.seq > 0 && !job_running() && kv("bootloader_open", bo, sizeof(bo))) {
		bl_shown = true;
		slog("opening Kiln's boot loader (%s%s)", bo, bl_record_upgrade() ? ", an update" : "");
		go(bl_record_upgrade() ? page_bootloader_upgrade : page_bootloader);
		return;
	}
	char ip[64], ifc[16], mode[16], ssh[16], buf[300], flag[32], slotb[96], v[64];

	if (cur_ip(ip, sizeof(ip), ifc, sizeof(ifc))) {
		bool have_mode = kv("net_mode", mode, sizeof(mode));
		bool ssh_up = !kv("ssh", ssh, sizeof(ssh)) || !strcmp(ssh, "running");
		const char *ssh_txt = ssh_up ? "ssh root@" : tr(RS_SSH_NOT_RUNNING);
		set_iconed(hm.ip, LV_SYMBOL_WIFI, "   ", "%s  (%s%s%s)    %s%s", ip, ifc,
			have_mode ? ", " : "", have_mode ? mode : "", ssh_txt, ssh_up ? ip : "");
	} else {
		set_iconed(hm.ip, LV_SYMBOL_WIFI, "   ", "%s", tr(RS_NO_NETWORK_HOME));
	}

	bool have_flag = kv("flag", flag, sizeof(flag)) || sys_ota_flag(flag, sizeof(flag));
	const char *boots = !have_flag ? tr(RS_BOOT_FLAG_UNREADABLE)
		: !strcmp(flag, "ota:kernel2") ? tr(RS_NEXT_MAIN)
		: tr(RS_NEXT_RECOVERY);
	set_iconed(hm.slot, LV_SYMBOL_DRIVE, "   ", tr(RS_HOME_SLOT),
		slot_word(main_os_text(slotb, sizeof(slotb))), boots);

	if (kv("main_trace", buf, sizeof(buf)))
		set_iconed(hm.trace, LV_SYMBOL_EYE_OPEN, "   ", tr(RS_HOME_TRACE), buf);
	else
		set_iconed(hm.trace, LV_SYMBOL_EYE_OPEN, "   ", "%s", tr(RS_HOME_NO_TRACE));

	if (kv("update_last", buf, sizeof(buf)) || sys_last_update(buf, sizeof(buf))) {
		char u[400];
		set_iconed(hm.last, LV_SYMBOL_DOWNLOAD, "   ", tr(RS_HOME_LAST_UPDATE),
			   update_text(buf, u, sizeof(u)));
	}
	else
		set_iconed(hm.last, LV_SYMBOL_DOWNLOAD, "   ", "%s", tr(RS_HOME_NO_UPDATE));

	swu_state s;
	swu_get(&s);
	bool swu_up = s.connected || (kv("swupdate", v, sizeof(v)) && !strcmp(v, "running"));
	lv_label_set_text(hm.chip, job_running() ? tr(RS_BUSY) : swu_up ? tr(RS_SWU_READY)
					       : tr(RS_SWU_NOT_RUNNING));
	lv_obj_set_style_bg_color(hm.chip, swu_up ? lv_color_hex(0x45504F)
						  : lv_color_hex(0x5D5A53), 0);
}

static lv_obj_t *tile(lv_obj_t *parent, const char *icon, const char *text, lv_color_t ic,
		      bool accent, lv_event_cb_t cb, void *ud)
{
	lv_obj_t *b = lv_button_create(parent);
	lv_obj_set_size(b, (W - 2 * PAD - 3 * 12) / 4, 116);
	lv_obj_set_style_radius(b, 16, 0);
	lv_obj_set_style_shadow_width(b, 0, 0);
	lv_obj_set_style_bg_color(b, accent ? C_ACCENT_FILL : C_CARD, 0);
	lv_obj_set_style_bg_opa(b, LV_OPA_COVER, 0);
	lv_obj_set_style_border_color(b, accent ? C_ACCENT_FILL : C_BORDER, 0);
	lv_obj_set_style_border_width(b, 1, 0);
	lv_obj_set_style_bg_color(b, accent ? lv_color_hex(0x526E91) : C_CARD_HI,
				  LV_STATE_PRESSED);
	lv_obj_set_flex_flow(b, LV_FLEX_FLOW_COLUMN);
	lv_obj_set_flex_align(b, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);
	lv_obj_set_style_pad_row(b, 6, 0);
	lv_obj_set_style_pad_hor(b, 6, 0);
	label(b, icon, F40, accent ? C_TEXT : ic);
	lv_obj_t *l = label(b, text, F20B, C_TEXT);
	lv_obj_set_style_text_align(l, LV_TEXT_ALIGN_CENTER, 0);
	lv_obj_add_event_cb(b, cb, LV_EVENT_CLICKED, ud);
	return b;
}

static void page_home(void)
{
	memset(&hm, 0, sizeof(hm));
	/* Title: "Kiln OS — Recovery" */
	lv_obj_t *hdr = box(scr, LV_FLEX_FLOW_ROW);
	lv_obj_set_size(hdr, W - 2 * PAD, 52);
	lv_obj_set_pos(hdr, PAD, 2);
	lv_obj_set_flex_align(hdr, LV_FLEX_ALIGN_START, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);
	lv_obj_set_style_pad_column(hdr, 10, 0);
	label(hdr, "Kiln OS", F28B, C_TEXT);
	label(hdr, tr(RS_RECOVERY_TITLE), F28B, C_WARN);
	lv_obj_t *sp = box(hdr, LV_FLEX_FLOW_ROW);
	lv_obj_set_flex_grow(sp, 1);
	lv_obj_set_height(sp, 1);
	hm.chip = label(hdr, "", F16, C_TEXT);
	lv_obj_set_style_bg_opa(hm.chip, LV_OPA_COVER, 0);
	lv_obj_set_style_radius(hm.chip, 12, 0);
	lv_obj_set_style_pad_hor(hm.chip, 12, 0);
	lv_obj_set_style_pad_ver(hm.chip, 4, 0);

	int st_h = 4 * lv_font_get_line_height(F20) + 3 * 4 + 2 * 10 + 2;
	lv_obj_t *st = card(scr);
	lv_obj_set_pos(st, PAD, 56);
	lv_obj_set_size(st, W - 2 * PAD, st_h);
	lv_obj_set_flex_flow(st, LV_FLEX_FLOW_COLUMN);
	lv_obj_set_style_pad_row(st, 4, 0);
	lv_obj_set_style_pad_ver(st, 10, 0);
	lv_obj_set_style_pad_hor(st, 16, 0);
	hm.ip = label(st, "", F20, C_TEXT);
	hm.slot = label(st, "", F20, C_TEXT);
	hm.trace = label(st, "", F20, C_MUTED);
	hm.last = label(st, "", F20, C_MUTED);
	lv_obj_t *one[4] = { hm.ip, hm.slot, hm.trace, hm.last };
	for (int i = 0; i < 4; i++) {	/* one line each, "..." if longer */
		lv_label_set_long_mode(one[i], LV_LABEL_LONG_MODE_DOTS);
		lv_obj_set_size(one[i], lv_pct(100), lv_font_get_line_height(F20));
	}

	int gy = 56 + st_h + 10;
	lv_obj_t *grid = box(scr, LV_FLEX_FLOW_ROW_WRAP);
	lv_obj_set_pos(grid, PAD, gy);
	lv_obj_set_size(grid, W - 2 * PAD, H - gy - 8);
	lv_obj_set_style_pad_column(grid, 12, 0);
	lv_obj_set_style_pad_row(grid, 10, 0);
	tile(grid, LV_SYMBOL_PLAY, tr(RS_BOOT_MAIN_OS), C_TEXT, true, on_boot_main, NULL);
	tile(grid, LV_SYMBOL_DOWNLOAD, tr(RS_INSTALL_UPDATE), C_ACCENT, false, on_go, page_update);
	tile(grid, LV_SYMBOL_SAVE, tr(RS_BACK_UP), C_ACCENT, false, on_go, page_backup);
	tile(grid, LV_SYMBOL_REFRESH, tr(RS_RESTORE), C_WARN, false, on_go, page_restore);
	tile(grid, LV_SYMBOL_WARNING, tr(RS_RESTORE_STOCK), C_DANGER, false, on_go, page_return);
	tile(grid, LV_SYMBOL_WIFI, tr(RS_NETWORK_SSH), C_ACCENT, false, on_go, page_network);
	tile(grid, LV_SYMBOL_LIST, tr(RS_LOGS), C_MUTED, false, on_go, page_logs);
	tile(grid, LV_SYMBOL_POWER, tr(RS_REBOOT_POWER), C_MUTED, false, on_go, page_power);
	cur_refresh = home_refresh;
}

/* ------------------------------------------------------- selectable rows */

static lv_obj_t *row_item(lv_obj_t *list, const char *title, const char *sub,
			  lv_event_cb_t cb, int idx)
{
	lv_obj_t *b = lv_button_create(list);
	lv_obj_set_width(b, lv_pct(100));
	lv_obj_set_height(b, LV_SIZE_CONTENT);
	lv_obj_set_style_min_height(b, 64, 0);
	lv_obj_set_style_radius(b, 10, 0);
	lv_obj_set_style_shadow_width(b, 0, 0);
	lv_obj_set_style_bg_color(b, C_CARD_HI, 0);
	lv_obj_set_style_bg_color(b, lv_color_hex(0x465A76), LV_STATE_CHECKED);
	lv_obj_set_style_border_color(b, C_ACCENT, LV_STATE_CHECKED);
	lv_obj_set_style_border_width(b, 2, LV_STATE_CHECKED);
	lv_obj_set_style_border_width(b, 0, 0);
	lv_obj_set_style_pad_ver(b, 8, 0);
	lv_obj_set_style_pad_hor(b, 14, 0);
	lv_obj_set_flex_flow(b, LV_FLEX_FLOW_COLUMN);
	lv_obj_set_style_pad_row(b, 2, 0);
	lv_obj_t *t = label(b, title, F20B, C_TEXT);
	lv_label_set_long_mode(t, LV_LABEL_LONG_MODE_DOTS);
	lv_obj_set_width(t, lv_pct(100));
	if (sub) {
		lv_obj_t *s = label(b, sub, F16, C_MUTED);
		lv_label_set_long_mode(s, LV_LABEL_LONG_MODE_DOTS);
		lv_obj_set_width(s, lv_pct(100));
	}
	lv_obj_add_event_cb(b, cb, LV_EVENT_CLICKED, (void *)(intptr_t)idx);
	return b;
}

static void select_row(lv_obj_t *list, int idx)
{
	uint32_t n = lv_obj_get_child_count(list);
	for (uint32_t i = 0; i < n; i++) {
		lv_obj_t *c = lv_obj_get_child(list, i);
		if ((int)i == idx)
			lv_obj_add_state(c, LV_STATE_CHECKED);
		else
			lv_obj_remove_state(c, LV_STATE_CHECKED);
	}
}

static lv_obj_t *scroll_list(lv_obj_t *parent)
{
	lv_obj_t *l = lv_obj_create(parent);
	plain(l);
	lv_obj_set_flex_flow(l, LV_FLEX_FLOW_COLUMN);
	lv_obj_set_style_pad_row(l, 8, 0);
	lv_obj_set_style_pad_right(l, 6, 0);
	lv_obj_set_scroll_dir(l, LV_DIR_VER);
	return l;
}

/* ----------------------------------------------------------- USB sticks */

/* Sticks are mounted by `ad5x-usb mount` (at /run/ad5x/usb/<dev>); the UI
 * sees them in /proc/mounts. Pages with a USB card mount a stick that shows
 * up unmounted once by themselves; Eject runs `ad5x-usb umount`. */
static usb_vol usb[8];
static int nusb;
static struct {
	lv_obj_t *text, *mount, *umount;
	capture *cap;
	const char *doing;	/* "Mounting", "Ejecting" */
	bool tried;		/* automount done on this page */
	char result[160];
} ub;

static int usb_mounted_idx(void)
{
	for (int i = 0; i < nusb; i++)
		if (usb[i].dir[0])
			return i;
	return -1;
}

static void usb_run(rui_entry e, const char *doing)
{
	if (ub.cap)
		return;
	char *c = cmd_expand(e, NULL);
	slog("%s USB: %s", doing, c);
	ub.cap = capture_start(c, 2048);
	ub.doing = doing;
	free(c);
}

static void on_usb_mount(lv_event_t *e)
{
	(void)e;
	usb_run(CMD_USB_MOUNT, tr(RS_MOUNTING));
}

static void on_usb_umount(lv_event_t *e)
{
	(void)e;
	usb_run(CMD_USB_UMOUNT, tr(RS_EJECTING));
}

static void usb_card_free(lv_event_t *e)
{
	(void)e;
	capture_free(ub.cap);
	ub.cap = NULL;
}

/* A card with the USB status line and Mount / Eject */
static void usb_card(lv_obj_t *body)
{
	memset(&ub, 0, sizeof(ub));
	lv_obj_t *c = card(body);
	lv_obj_set_size(c, lv_pct(100), 84);
	lv_obj_set_flex_flow(c, LV_FLEX_FLOW_ROW);
	lv_obj_set_flex_align(c, LV_FLEX_ALIGN_START, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);
	lv_obj_set_style_pad_column(c, 10, 0);
	ub.text = label(c, "", F20, C_TEXT);
	lv_label_set_long_mode(ub.text, LV_LABEL_LONG_MODE_WRAP);
	lv_obj_set_flex_grow(ub.text, 1);
	ub.mount = button(c, NULL, tr(RS_MOUNT), 1, on_usb_mount, NULL);
	ub.umount = button(c, LV_SYMBOL_EJECT, tr(RS_EJECT), 0, on_usb_umount, NULL);
	lv_obj_add_event_cb(c, usb_card_free, LV_EVENT_DELETE, NULL);
}

/* Returns true when the set of mounted sticks may have changed */
static bool usb_card_refresh(void)
{
	bool changed = false;
	if (ub.cap && capture_done(ub.cap)) {
		const char *t = capture_text(ub.cap);
		const char *last = t;
		for (const char *p = t; p && *p; p++)
			if (*p == '\n' && p[1])
				last = p + 1;
		snprintf(ub.result, sizeof(ub.result), "%.*s", (int)strcspn(last ? last : "", "\n"),
			 last ? last : "");
		capture_free(ub.cap);
		ub.cap = NULL;
		ub.doing = NULL;
		changed = true;
	}
	int before = usb_mounted_idx();
	nusb = sys_usb_list(usb, 8);
	int m = usb_mounted_idx();
	if (m != before)
		changed = true;
	if (!ub.tried && !ub.cap && nusb > 0 && m < 0) {
		ub.tried = true;
		usb_run(CMD_USB_MOUNT, tr(RS_MOUNTING));
	}
	char t[300];
	if (ub.doing) {
		iconed(t, sizeof(t), LV_SYMBOL_USB, "  ", tr(RS_USB_BUSY), ub.doing);
	} else if (m >= 0) {
		char fr[32];
		human_size(usb[m].free_mb << 20, fr, sizeof(fr));
		char head[160];
		snprintf(head, sizeof(head), tr(RS_USB_MOUNTED), usb[m].dev, usb[m].fs, fr);
		iconed(t, sizeof(t), LV_SYMBOL_USB, "  ", "%s\n%s", head, usb[m].dir);
	} else if (nusb > 0) {
		char head[160];
		snprintf(head, sizeof(head), tr(RS_USB_NOT_MOUNTED), usb[0].dev);
		iconed(t, sizeof(t), LV_SYMBOL_USB, "  ", "%s%s%s", head,
			ub.result[0] ? "\n" : "", ub.result);
	} else {
		iconed(t, sizeof(t), LV_SYMBOL_USB, "  ", "%s", tr(RS_USB_NONE));
	}
	lv_label_set_text(ub.text, t);
	show(ub.mount, !ub.doing && nusb > 0 && m < 0);
	show(ub.umount, !ub.doing && m >= 0);
	return changed;
}

/* ---------------------------------------------------------- install page */

static struct {
	file_ent f[24];
	int n, sel;
	lv_obj_t *list, *install, *check, *hint;
	unsigned tick;
} up;

static void up_fill(void);

static void up_buttons(void)
{
	enable(up.install, up.sel >= 0);
	enable(up.check, up.sel >= 0);
}

static void on_up_row(lv_event_t *e)
{
	up.sel = (int)(intptr_t)lv_event_get_user_data(e);
	select_row(up.list, up.sel);
	up_buttons();
}

static void install_now(void)
{
	if (up.sel < 0 || up.sel >= up.n)
		return;
	const char *v[] = { "FILE", up.f[up.sel].path, NULL };
	char *c = cmd_expand(CMD_INSTALL, v);
	start_job_x(JK_INSTALL, tr(RS_INSTALLING_UPDATE), up.f[up.sel].path, c, false, false, true,
		    AFTER_BOOT_MAIN);
	free(c);
}

static void on_install(lv_event_t *e)
{
	(void)e;
	if (up.sel < 0 || up.sel >= up.n || return_lock())
		return;
	static char t1[400], t2[400];
	snprintf(t1, sizeof(t1), tr(RS_INSTALL_Q_TEXT), up.f[up.sel].name);
	snprintf(t2, sizeof(t2), "%s", tr(RS_INSTALL_Q_TEXT2));
	confirm(tr(RS_INSTALL_Q), t1, tr_sym(LV_SYMBOL_DOWNLOAD, RS_INSTALL_NOW), true, t2,
		install_now);
}

static void on_up_check(lv_event_t *e)
{
	(void)e;
	if (up.sel < 0 || up.sel >= up.n)
		return;
	const char *v[] = { "FILE", up.f[up.sel].path, NULL };
	char *c = cmd_expand(CMD_INSTALL_CHECK, v);
	start_job(JK_CMD, tr(RS_CHECKING_UPDATE), up.f[up.sel].path, c, true, false);
	free(c);
}

static void on_up_refresh(lv_event_t *e)
{
	(void)e;
	up_fill();
}

static void up_fill(void)
{
	char keep[256] = "";
	if (up.sel >= 0 && up.sel < up.n)
		snprintf(keep, sizeof(keep), "%s", up.f[up.sel].path);
	up.n = sys_list_swu(up.f, 24);
	up.sel = -1;
	lv_obj_clean(up.list);
	for (int i = 0; i < up.n; i++) {
		char sub[300], sz[32], when[32];
		time_t mt = up.f[i].mtime;
		human_size(up.f[i].size, sz, sizeof(sz));
		strftime(when, sizeof(when), "%Y-%m-%d %H:%M", localtime(&mt));
		snprintf(sub, sizeof(sub), "%s  \xc2\xb7  %s  \xc2\xb7  %s", sz, when, up.f[i].path);
		row_item(up.list, up.f[i].name, sub, on_up_row, i);
		if (!strcmp(keep, up.f[i].path))
			up.sel = i;
	}
	if (up.n == 1)
		up.sel = 0;
	if (!up.n) {
		char t[300];
		snprintf(t, sizeof(t), tr(RS_NO_UPDATE_FMT), rui_get(PATH_UPDATE_DIR));
		wrap_label(up.list, t, F20, C_MUTED);
	}
	select_row(up.list, up.sel);
	up_buttons();
}

static void up_refresh(void)
{
	if (usb_card_refresh())
		up.tick = 0;
	if (up.tick++ % 12)	/* every 3 s: web URL, new files */
		return;
	char ip[64], ifc[16];
	if (cur_ip(ip, sizeof(ip), ifc, sizeof(ifc)))
		lv_label_set_text_fmt(up.hint, tr(RS_UPLOAD_HINT), ip);
	else
		lv_label_set_text(up.hint, tr(RS_UPLOAD_HINT_NONET));
	file_ent f[24];
	int n = sys_list_swu(f, 24);
	bool same = n == up.n;
	for (int i = 0; same && i < n; i++)
		same = !strcmp(f[i].path, up.f[i].path);
	if (!same)
		up_fill();
}

static void page_update(void)
{
	memset(&up, 0, sizeof(up));
	up.sel = -1;
	lv_obj_t *body = page_frame(tr(RS_INSTALL_UPDATE), true);
	usb_card(body);
	up.hint = label(body, "", F16, C_MUTED);
	up.list = scroll_list(body);
	lv_obj_set_width(up.list, lv_pct(100));
	lv_obj_set_flex_grow(up.list, 1);
	lv_obj_t *row = box(body, LV_FLEX_FLOW_ROW);
	lv_obj_set_size(row, lv_pct(100), LV_SIZE_CONTENT);
	lv_obj_set_style_pad_column(row, 12, 0);
	lv_obj_t *r = button(row, LV_SYMBOL_REFRESH, tr(RS_RESCAN), 0, on_up_refresh, NULL);
	lv_obj_set_width(r, 180);
	up.check = button(row, LV_SYMBOL_EYE_OPEN, tr(RS_CHECK), 0, on_up_check, NULL);
	lv_obj_set_width(up.check, 180);
	up.install = button(row, LV_SYMBOL_DOWNLOAD, tr(RS_INSTALL), 1, on_install, NULL);
	lv_obj_set_flex_grow(up.install, 1);
	up_fill();
	cur_refresh = up_refresh;
}

/* ----------------------------------------------------------- backup page */

static struct {
	lv_obj_t *all, *dest, *start, *dry;
	unsigned tick;
	char destdir[300];
} bk;

static void bk_dest(void)
{
	int m = usb_mounted_idx();
	if (m < 0) {
		bk.destdir[0] = 0;
		lv_label_set_text(bk.dest, tr(RS_BK_DEST_NONE));
		return;
	}
	/* ad5x-backup makes <DEST>/ad5x-backup-<date>-<n>/ */
	snprintf(bk.destdir, sizeof(bk.destdir), "%s", usb[m].dir);
	lv_label_set_text_fmt(bk.dest, tr(RS_BK_DEST), usb[m].dir,
			      rui_get(PATH_BACKUP_PREFIX));
}

static void bk_refresh(void)
{
	if (usb_card_refresh())
		bk.tick = 0;
	if (bk.tick++ % 8)
		return;
	bk_dest();
	enable(bk.start, bk.destdir[0] != 0);
	enable(bk.dry, bk.destdir[0] != 0);
}

static void bk_run(bool dry)
{
	bk_dest();
	if (!bk.destdir[0])
		return;
	bool all = lv_obj_has_state(bk.all, LV_STATE_CHECKED);
	const char *v[] = { "DRY", dry ? "--dry-run" : "", "ALL", all ? "--all" : "",
			    "DEST", bk.destdir, NULL };
	char *c = cmd_expand(CMD_BACKUP, v);
	start_job(JK_CMD, dry ? tr(RS_BACKUP_DRY_RUN) : tr(RS_BACKING_UP), bk.destdir, c, true, false);
	free(c);
}

static void on_bk_start(lv_event_t *e)
{
	(void)e;
	bk_run(false);
}

static void on_bk_dry(lv_event_t *e)
{
	(void)e;
	bk_run(true);
}

static void page_backup(void)
{
	memset(&bk, 0, sizeof(bk));
	lv_obj_t *body = page_frame(tr(RS_BACK_UP_TITLE), true);
	usb_card(body);

	lv_obj_t *c = card(body);
	lv_obj_set_size(c, lv_pct(100), LV_SIZE_CONTENT);
	lv_obj_set_flex_flow(c, LV_FLEX_FLOW_COLUMN);
	lv_obj_set_style_pad_row(c, 10, 0);
	wrap_label(c, tr(RS_BACKUP_TEXT), F20, C_TEXT);
	lv_obj_t *r = box(c, LV_FLEX_FLOW_ROW);
	lv_obj_set_size(r, lv_pct(100), LV_SIZE_CONTENT);
	lv_obj_set_flex_align(r, LV_FLEX_ALIGN_START, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);
	lv_obj_set_style_pad_column(r, 14, 0);
	bk.all = lv_switch_create(r);
	lv_obj_set_size(bk.all, 76, 40);
	label(r, tr(RS_ALSO_USERDATA), F20, C_TEXT);
	bk.dest = label(c, "", F16, C_MUTED);
	lv_label_set_long_mode(bk.dest, LV_LABEL_LONG_MODE_DOTS);
	lv_obj_set_width(bk.dest, lv_pct(100));

	lv_obj_t *sp = box(body, LV_FLEX_FLOW_ROW);
	lv_obj_set_flex_grow(sp, 1);
	lv_obj_t *row = box(body, LV_FLEX_FLOW_ROW);
	lv_obj_set_size(row, lv_pct(100), LV_SIZE_CONTENT);
	lv_obj_set_style_pad_column(row, 12, 0);
	bk.dry = button(row, LV_SYMBOL_EYE_OPEN, tr(RS_DRY_RUN), 0, on_bk_dry, NULL);
	lv_obj_set_width(bk.dry, 220);
	bk.start = button(row, LV_SYMBOL_SAVE, tr(RS_START_BACKUP), 1, on_bk_start, NULL);
	lv_obj_set_flex_grow(bk.start, 1);
	cur_refresh = bk_refresh;
}

/* ---------------------------------------------------------- restore page */

static struct {
	backup_set *sets;
	int n, sel;
	bool part_on[16];
	lv_obj_t *list, *parts, *go, *dry;
	unsigned tick;
} rs;

/* Partitions ad5x-restore won't write from here: this recovery's own slot
 * (kernel, rootfs: refused while it runs) and the boot area (only with
 * --i-know, left to the command line). */
static bool rs_locked(const char *p)
{
	return !strcmp(p, "kernel") || !strcmp(p, "rootfs") || !strcmp(p, "boot");
}

static void rs_update_buttons(void)
{
	int k = 0;
	if (rs.sel >= 0)
		for (int i = 0; i < rs.sets[rs.sel].nparts; i++)
			k += rs.part_on[i];
	enable(rs.go, k > 0);
	enable(rs.dry, k > 0);
}

static void on_rs_part(lv_event_t *e)
{
	int i = (int)(intptr_t)lv_event_get_user_data(e);
	rs.part_on[i] = lv_obj_has_state(lv_event_get_target_obj(e), LV_STATE_CHECKED);
	rs_update_buttons();
}

static void rs_fill_parts(void)
{
	lv_obj_clean(rs.parts);
	memset(rs.part_on, 0, sizeof(rs.part_on));
	if (rs.sel < 0) {
		wrap_label(rs.parts, tr(RS_PICK_BACKUP), F20, C_MUTED);
		rs_update_buttons();
		return;
	}
	lv_obj_t *h = label(rs.parts, tr(RS_PARTITIONS_TO_WRITE), F20B, C_TEXT);
	lv_obj_set_width(h, lv_pct(100));
	backup_set *b = &rs.sets[rs.sel];
	bool locked_any = false;
	for (int i = 0; i < b->nparts; i++) {
		lv_obj_t *cb = lv_checkbox_create(rs.parts);
		lv_checkbox_set_text(cb, b->parts[i]);
		lv_obj_set_width(cb, lv_pct(48));
		lv_obj_set_style_text_font(cb, F20, 0);
		lv_obj_set_style_pad_ver(cb, 6, 0);
		lv_obj_set_style_pad_column(cb, 12, 0);
		lv_obj_set_style_width(cb, 30, LV_PART_INDICATOR);
		lv_obj_set_style_height(cb, 30, LV_PART_INDICATOR);
		lv_obj_set_ext_click_area(cb, 8);
		if (rs_locked(b->parts[i])) {
			lv_obj_add_state(cb, LV_STATE_DISABLED);
			lv_obj_set_style_text_color(cb, lv_color_hex(0x7B8394), 0);
			locked_any = true;
		}
		lv_obj_add_event_cb(cb, on_rs_part, LV_EVENT_VALUE_CHANGED, (void *)(intptr_t)i);
	}
	if (locked_any) {
		lv_obj_t *n = wrap_label(rs.parts, tr(RS_GREYED_OUT), F16, C_MUTED);
		lv_obj_set_style_pad_top(n, 4, 0);
	}
	rs_update_buttons();
}

static void on_rs_row(lv_event_t *e)
{
	rs.sel = (int)(intptr_t)lv_event_get_user_data(e);
	select_row(rs.list, rs.sel);
	rs_fill_parts();
}

static void rs_parts_str(char *buf, size_t cap)
{
	buf[0] = 0;
	backup_set *b = &rs.sets[rs.sel];
	for (int i = 0; i < b->nparts; i++)
		if (rs.part_on[i]) {
			size_t n = strlen(buf);
			snprintf(buf + n, cap - n, "%s%s", n ? " " : "", b->parts[i]);
		}
}

static void rs_run(bool dry)
{
	if (rs.sel < 0)
		return;
	char parts[400];
	rs_parts_str(parts, sizeof(parts));
	const char *v[] = { "DRY", dry ? "--dry-run" : "", "SRC", rs.sets[rs.sel].path,
			    "PARTS", parts, NULL };
	char *c = cmd_expand(CMD_RESTORE, v);
	/* After restoring slot B, offer to boot it */
	bool main_slot = strstr(parts, "kernel2") || strstr(parts, "rootfs2");
	start_job_x(JK_CMD, dry ? tr(RS_RESTORE_DRY_RUN) : tr(RS_RESTORING), rs.sets[rs.sel].path, c,
		    dry, false, !dry, !dry && main_slot ? AFTER_BOOT_MAIN : AFTER_NONE);
	free(c);
}

static void rs_go_now(void)
{
	rs_run(false);
}

static void on_rs_dry(lv_event_t *e)
{
	(void)e;
	rs_run(true);
}

static void on_rs_go(lv_event_t *e)
{
	(void)e;
	if (rs.sel < 0)
		return;
	char parts[400];
	static char t1[600], t2[600];
	rs_parts_str(parts, sizeof(parts));
	snprintf(t1, sizeof(t1), tr(RS_RESTORE_Q), rs.sets[rs.sel].label, parts);
	snprintf(t2, sizeof(t2), tr(RS_RESTORE_Q2), parts);
	confirm(tr(RS_RESTORE_BACKUP_Q), t1, tr_sym(LV_SYMBOL_REFRESH, RS_RESTORE_NOW), true, t2,
		rs_go_now);
}

static void rs_fill(void)
{
	rs.n = sys_list_backups(rs.sets, 32);
	rs.sel = rs.n == 1 ? 0 : -1;
	lv_obj_clean(rs.list);
	for (int i = 0; i < rs.n; i++) {
		char sub[200], sz[32], np[64];
		human_size(rs.sets[i].size, sz, sizeof(sz));
		snprintf(np, sizeof(np), tr(RS_N_PARTITIONS), rs.sets[i].nparts);
		snprintf(sub, sizeof(sub), "%s  \xc2\xb7  %s", np, sz);
		row_item(rs.list, rs.sets[i].label, sub, on_rs_row, i);
	}
	if (!rs.n) {
		char t[200];
		snprintf(t, sizeof(t), tr(usb_mounted_idx() >= 0 ? RS_NO_BACKUPS : RS_INSERT_BACKUP_USB),
			rui_get(PATH_BACKUP_PREFIX));
		wrap_label(rs.list, t, F20, C_MUTED);
	}
	select_row(rs.list, rs.sel);
	rs_fill_parts();
}

static void rs_refresh(void)
{
	if (usb_card_refresh() || rs.tick == 0)
		rs_fill();
	rs.tick++;
}

static void page_restore(void)
{
	static backup_set sets[32];
	memset(&rs, 0, sizeof(rs));
	rs.sets = sets;
	rs.sel = -1;
	lv_obj_t *body = page_frame(tr(RS_RESTORE_TITLE), true);
	usb_card(body);
	lv_obj_t *cols = box(body, LV_FLEX_FLOW_ROW);
	lv_obj_set_width(cols, lv_pct(100));
	lv_obj_set_flex_grow(cols, 1);
	lv_obj_set_style_pad_column(cols, 12, 0);
	rs.list = scroll_list(cols);
	lv_obj_set_size(rs.list, 360, lv_pct(100));
	lv_obj_t *right = card(cols);
	lv_obj_set_height(right, lv_pct(100));
	lv_obj_set_flex_grow(right, 1);
	lv_obj_set_flex_flow(right, LV_FLEX_FLOW_COLUMN);
	rs.parts = scroll_list(right);
	lv_obj_set_flex_flow(rs.parts, LV_FLEX_FLOW_ROW_WRAP);
	lv_obj_set_width(rs.parts, lv_pct(100));
	lv_obj_set_flex_grow(rs.parts, 1);
	lv_obj_set_style_pad_row(rs.parts, 0, 0);
	lv_obj_set_style_pad_column(rs.parts, 0, 0);
	lv_obj_t *row = box(right, LV_FLEX_FLOW_ROW);
	lv_obj_set_size(row, lv_pct(100), LV_SIZE_CONTENT);
	lv_obj_set_style_pad_column(row, 10, 0);
	rs.dry = button(row, LV_SYMBOL_EYE_OPEN, tr(RS_CHECK), 0, on_rs_dry, NULL);
	lv_obj_set_flex_grow(rs.dry, 1);
	rs.go = button(row, LV_SYMBOL_REFRESH, tr(RS_RESTORE), 2, on_rs_go, NULL);
	lv_obj_set_flex_grow(rs.go, 1);
	rs_fill();
	cur_refresh = rs_refresh;
}

/* ------------------------------------------- return to Flashforge page */

/* ad5x-return-stock --check runs in the background when the page opens (and
 * after Check): its "source:", "target:", "config:" (include lines of
 * stock's printer.cfg it switches off: zMod leftovers), "spl_option:",
 * "spl_missing:" and "result:" lines fill the page. The first three are English; the codes
 * next to them ("source_kind:" with "source_file:", "target_kind:",
 * "config_kind:" with "config_lines:") give the page's own translation, the
 * English line only when a code is unknown. Return to Flashforge is enabled only when
 * the result is "ready" (or "ready to go on" after a stop: Continue). Check
 * shows the whole check as a job. The return itself is a job that writes
 * the eMMC ("don't switch off"); after it, Shut down. */
static struct {
	lv_obj_t *card, *status, *files, *after, *cfg, *spl, *spl_note, *go, *check, *save;
	lv_obj_t *wipe, *prints, *wipe_note;	/* Kiln's data: the two boxes */
	capture *cap;
	char source[200], target[240], config[240], why[240];
	char source_kind[16], source_file[200], target_kind[24], config_kind[16];
	int config_lines, prints_files;
	unsigned long long kiln_kb, prints_kb;
	bool spl_offer, spl_missing, spl_ticked_once, ready, resume, done_already, checked, cfg_failed;
	bool wipe_offer, wipe_ticked_once;
	char wipe_asked[16];	/* "kiln" or "prints": an unfinished return asked it */
} rt;

static void rt_free(lv_event_t *e)
{
	/* the old page's card goes after the new page is made (go()): the
	 * page opened again over itself keeps its new check running */
	if (lv_event_get_target(e) != rt.card)
		return;
	capture_free(rt.cap);
	rt.cap = NULL;
}

/* "Also put back Flashforge's own boot loader": offered when this
 * printer's saved boot.img is found for a new return, and then ticked by
 * default (the tool's default too). Ticked: --flashforge-spl (required:
 * refused if boot.img went away since the check); unticked:
 * --keep-kiln-spl. Not offered (no boot.img, an unfinished return going on
 * with its own choice, Flashforge's boot loader there already): no
 * option, the tool decides as its check said */
static const char *rt_spl_flag(void)
{
	if (!rt.spl || !rt.spl_offer)
		return "";
	return lv_obj_has_state(rt.spl, LV_STATE_CHECKED) ? "--flashforge-spl" : "--keep-kiln-spl";
}

/* "Also remove Kiln OS's settings and files" and, only with it, "...and the
 * uploaded print files too" (ad5x-return-stock --remove-kiln-data,
 * --remove-prints: step 9, after the return) */
static bool rt_wipe(void)
{
	return rt.wipe && rt.wipe_offer && lv_obj_has_state(rt.wipe, LV_STATE_CHECKED);
}

static bool rt_prints(void)
{
	return rt_wipe() && rt.prints && lv_obj_has_state(rt.prints, LV_STATE_CHECKED);
}

static const char *rt_wipe_flags(void)
{
	return rt_prints() ? "--remove-kiln-data --remove-prints"
	       : rt_wipe() ? "--remove-kiln-data" : "";
}

static void rt_start_check(void)
{
	if (rt.cap || job_running())
		return;
	const char *v[] = { "SPL", rt_spl_flag(), "WIPE", rt_wipe_flags(), NULL };
	char *c = cmd_expand(CMD_RETURN_CHECK, v);
	slog("return to Flashforge: %s", c);
	rt.cap = capture_start(c, 16384);
	free(c);
	rt.checked = false;
	lv_label_set_text(rt.status, tr_sym(LV_SYMBOL_REFRESH, RS_RS_CHECKING));
	lv_obj_set_style_text_color(rt.status, C_MUTED, 0);
	enable(rt.go, false);
	enable(rt.check, false);
}

/* VALUE of the last line "KEY: VALUE" in text */
static bool rt_line(const char *text, const char *key, char *out, size_t cap)
{
	size_t kl = strlen(key);
	bool found = false;
	for (const char *l = text; l && *l; l = strchr(l, '\n') ? strchr(l, '\n') + 1 : NULL)
		if (!strncmp(l, key, kl) && l[kl] == ':' && l[kl + 1] == ' ') {
			snprintf(out, cap, "%.*s", (int)strcspn(l + kl + 2, "\n"), l + kl + 2);
			found = true;
		}
	return found;
}

static void rt_parse(const char *t)
{
	char res[240] = "", v[16] = "";
	rt.source[0] = rt.target[0] = rt.config[0] = rt.why[0] = 0;
	rt.source_kind[0] = rt.source_file[0] = rt.target_kind[0] = rt.config_kind[0] = 0;
	rt.config_lines = 0;
	rt_line(t, "source", rt.source, sizeof(rt.source));
	rt_line(t, "source_kind", rt.source_kind, sizeof(rt.source_kind));
	rt_line(t, "source_file", rt.source_file, sizeof(rt.source_file));
	rt_line(t, "target", rt.target, sizeof(rt.target));
	rt_line(t, "target_kind", rt.target_kind, sizeof(rt.target_kind));
	rt_line(t, "config", rt.config, sizeof(rt.config));
	rt_line(t, "config_kind", rt.config_kind, sizeof(rt.config_kind));
	if (rt_line(t, "config_lines", v, sizeof(v)))
		rt.config_lines = atoi(v);
	/* an earlier run couldn't change stock's printer.cfg (it went on) */
	rt.cfg_failed = text_has_line(t, "config_failed: yes");
	rt.spl_offer = rt_line(t, "spl_option", v, sizeof(v)) && !strcmp(v, "yes");
	rt.spl_missing = rt_line(t, "spl_missing", v, sizeof(v)) && !strcmp(v, "yes");
	rt.wipe_offer = rt_line(t, "wipe_option", v, sizeof(v)) && !strcmp(v, "yes");
	rt.kiln_kb = rt_line(t, "kiln_data_kb", v, sizeof(v)) ? strtoull(v, NULL, 10) : 0;
	rt.prints_kb = rt_line(t, "prints_kb", v, sizeof(v)) ? strtoull(v, NULL, 10) : 0;
	rt.prints_files = rt_line(t, "prints_files", v, sizeof(v)) ? atoi(v) : 0;
	if (!rt_line(t, "wipe_asked", rt.wipe_asked, sizeof(rt.wipe_asked)))
		rt.wipe_asked[0] = 0;
	rt_line(t, "result", res, sizeof(res));
	rt.ready = !strncmp(res, "ready", 5);
	rt.resume = !strncmp(res, "ready to go on", 14);
	rt.done_already = !strncmp(res, "done", 4);
	/* a refusal: its first FAIL line says why */
	for (const char *l = t; l && *l; l = strchr(l, '\n') ? strchr(l, '\n') + 1 : NULL)
		if (!strncmp(l, "  FAIL  ", 8)) {
			snprintf(rt.why, sizeof(rt.why), "%.*s", (int)strcspn(l + 8, "\n"), l + 8);
			break;
		}
	if (!rt.why[0] && !rt.ready && !rt.done_already)
		snprintf(rt.why, sizeof(rt.why), "%s", res[0] ? res : "?");
	if (rt.why[0])
		slog("return to Flashforge: not possible: %s", rt.why);
	rt.checked = true;
}

/* The source in the screen's language (the English "source:" line when
 * its source_kind is unknown) */
static const char *rt_source_text(char *buf, size_t cap)
{
	const char *k = rt.source_kind;
	if (!strcmp(k, "stock"))
		snprintf(buf, cap, "%s", tr(RS_RS_SRC_STOCK));
	else if (!strcmp(k, "usershare"))
		snprintf(buf, cap, "%s", tr(RS_RS_SRC_USERSHARE));
	else if (!strcmp(k, "copy") && rt.source_file[0])
		snprintf(buf, cap, tr(RS_RS_SRC_COPY), rt.source_file);
	else if (!strcmp(k, "backup") && rt.source_file[0])
		snprintf(buf, cap, tr(RS_RS_SRC_BACKUP), rt.source_file);
	else if (!strcmp(k, "package") && rt.source_file[0])
		snprintf(buf, cap, tr(RS_RS_SRC_PACKAGE), rt.source_file);
	else
		snprintf(buf, cap, "%s", rt.source);
	return buf;
}

/* The two boxes: shown while the return is still to do and there is Kiln
 * data to remove; the print files box (indented) only with print files,
 * and usable only with the first ticked */
static void rt_show_wipe(void)
{
	char t[480], a[32], b[32];
	bool on = rt.wipe_offer && !rt.done_already;
	human_size(rt.kiln_kb << 10, a, sizeof(a));
	lv_checkbox_set_text(rt.wipe, (snprintf(t, sizeof(t), tr(RS_RS_WIPE_BOX), a), t));
	human_size(rt.prints_kb << 10, b, sizeof(b));
	lv_checkbox_set_text(rt.prints,
			     (snprintf(t, sizeof(t), tr(RS_RS_PRINTS_BOX), rt.prints_files, b), t));
	show(rt.wipe, on);
	show(rt.prints, on && (rt.prints_files > 0 || rt.prints_kb > 0));
	if (!rt_wipe())
		lv_obj_remove_state(rt.prints, LV_STATE_CHECKED);
	enable(rt.prints, rt_wipe());
	show(rt.wipe_note, on && rt_wipe());
}

static void rt_show(void)
{
	char t[480], v[240];
	if (rt.source[0])
		iconed(t, sizeof(t), LV_SYMBOL_DRIVE, "  ", tr(RS_RS_FILES), rt_source_text(v, sizeof(v)));
	else
		iconed(t, sizeof(t), LV_SYMBOL_DRIVE, "  ", "%s", rt.checked ? tr(RS_RS_NO_FILES) : "");
	lv_label_set_text(rt.files, t);
	const char *tk = rt.target_kind;
	const char *after = !strcmp(tk, "kiln-spl") ? tr(RS_RS_AFTER_KILN)
			  : !strcmp(tk, "flashforge-spl") ? tr(RS_RS_AFTER_FFSPL)
			  : !strcmp(tk, "flashforge") ? tr(RS_RS_AFTER_FF) : rt.target;
	if (rt.target[0])
		iconed(t, sizeof(t), LV_SYMBOL_RIGHT, "  ", tr(RS_RS_AFTER), after);
	else
		t[0] = 0;
	lv_label_set_text(rt.after, t);
	const char *ck = rt.config_kind;
	if (rt.cfg_failed)
		iconed(t, sizeof(t), LV_SYMBOL_WARNING, "  ", "%s", tr(RS_RS_CFG_FAILED));
	else if (rt.config[0] && rt.config_lines > 0 && !strcmp(ck, "zmod"))
		iconed(t, sizeof(t), LV_SYMBOL_EDIT, "  ", tr(RS_RS_CFG_ZMOD), rt.config_lines);
	else if (rt.config[0] && rt.config_lines > 0 && !strcmp(ck, "missing"))
		iconed(t, sizeof(t), LV_SYMBOL_EDIT, "  ", tr(RS_RS_CFG_MISSING), rt.config_lines);
	else if (rt.config[0] && rt.config_lines > 0 && !strcmp(ck, "mixed"))
		iconed(t, sizeof(t), LV_SYMBOL_EDIT, "  ", tr(RS_RS_CFG_MIXED), rt.config_lines);
	else if (rt.config[0])
		iconed(t, sizeof(t), LV_SYMBOL_EDIT, "  ", tr(RS_RS_CONFIG), rt.config);
	else
		t[0] = 0;
	lv_label_set_text(rt.cfg, t);
	lv_obj_set_style_text_color(rt.cfg, rt.cfg_failed ? C_WARN : C_MUTED, 0);
	show(rt.cfg, rt.cfg_failed || rt.config[0] != 0);
	show(rt.spl, rt.spl_offer && !rt.done_already);
	if (rt.spl_missing)
		iconed(t, sizeof(t), LV_SYMBOL_WARNING, "  ", "%s", tr(RS_RS_SPL_MISSING));
	else
		t[0] = 0;
	lv_label_set_text(rt.spl_note, t);
	show(rt.spl_note, rt.spl_missing && !rt.done_already);
	rt_show_wipe();
	if (!rt.checked)
		return;
	lv_color_t c = C_OK;
	if (rt.done_already)
		snprintf(t, sizeof(t), "%s", tr_sym(LV_SYMBOL_OK, RS_RS_DONE_ALREADY));
	else if (rt.resume)
		snprintf(t, sizeof(t), "%s", tr_sym(LV_SYMBOL_WARNING, RS_RS_RESUME)), c = C_WARN;
	else if (rt.ready)
		snprintf(t, sizeof(t), "%s", tr_sym(LV_SYMBOL_OK, RS_RS_READY));
	else
		iconed(t, sizeof(t), LV_SYMBOL_CLOSE, "  ", tr(RS_RS_REFUSED),
		       why_text(rt.why, v, sizeof(v))), c = C_WARN;
	lv_label_set_text(rt.status, t);
	lv_obj_set_style_text_color(rt.status, c, 0);
	lv_label_set_text(lv_obj_get_child(rt.go, 0),
			  tr_sym(rt.resume ? LV_SYMBOL_PLAY : LV_SYMBOL_WARNING,
				 rt.resume ? RS_RS_CONTINUE : RS_RS_GO));
	enable(rt.go, rt.ready);
	enable(rt.check, true);
}

static void rt_refresh(void)
{
	if (rt.cap && capture_done(rt.cap)) {
		const char *t = capture_text(rt.cap);
		rt_parse(t ? t : "");
		capture_free(rt.cap);
		rt.cap = NULL;
		/* the boot loader box: ticked the first time it is offered */
		if (rt.spl_offer && !rt.spl_ticked_once) {
			rt.spl_ticked_once = true;
			lv_obj_add_state(rt.spl, LV_STATE_CHECKED);
		}
		/* an unfinished return was asked to remove Kiln's data: the
		 * boxes ticked again as then, and checked with them */
		if (rt.wipe_asked[0] && rt.wipe_offer && !rt.wipe_ticked_once) {
			rt.wipe_ticked_once = true;
			lv_obj_add_state(rt.wipe, LV_STATE_CHECKED);
			if (!strcmp(rt.wipe_asked, "prints"))
				lv_obj_add_state(rt.prints, LV_STATE_CHECKED);
			rt_show();
			rt_start_check();
			return;
		}
		rt_show();
	}
}

static void return_now(void)
{
	const char *v[] = { "SPL", rt_spl_flag(), "WIPE", rt_wipe_flags(), NULL };
	char *c = cmd_expand(CMD_RETURN_STOCK, v), src[240];
	start_job_x(JK_CMD, tr(RS_RS_RUNNING), rt_source_text(src, sizeof(src)), c, false, false,
		    true, AFTER_POWEROFF);
	jb.done_text = tr(RS_RS_DONE_ALREADY);
	free(c);
}

static void on_rt_go(lv_event_t *e)
{
	(void)e;
	if (!rt.ready)
		return;
	if (rt.resume && !rt_wipe()) {	/* asked before; finish it */
		return_now();
		return;
	}
	/* deleting Kiln's data is said on both steps, with the sizes, and
	 * that it can't be undone */
	char t1[1024], t2[1024], k[32], p[32], all[32], w[600];
	if (!rt_wipe()) {
		confirm(tr(RS_RS_Q), tr(RS_RS_Q_TEXT), tr_sym(LV_SYMBOL_WARNING, RS_RS_GO), true,
			tr(RS_RS_Q_TEXT2), return_now);
		return;
	}
	human_size(rt.kiln_kb << 10, k, sizeof(k));
	human_size(rt.prints_kb << 10, p, sizeof(p));
	human_size((rt.kiln_kb + rt.prints_kb) << 10, all, sizeof(all));
	if (rt_prints()) {
		snprintf(w, sizeof(w), tr(RS_RS_Q_WIPE_PRINTS), k, rt.prints_files, p);
		snprintf(t2, sizeof(t2), tr(RS_RS_Q2_WIPE_PRINTS), all);
	} else {
		snprintf(w, sizeof(w), tr(RS_RS_Q_WIPE), k);
		snprintf(t2, sizeof(t2), tr(RS_RS_Q2_WIPE), k);
	}
	snprintf(t1, sizeof(t1), "%s\n\n%s", tr(RS_RS_Q_TEXT), w);
	confirm(tr(RS_RS_Q), t1, tr_sym(LV_SYMBOL_WARNING, RS_RS_GO), true, t2, return_now);
}

static void on_rt_check(lv_event_t *e)
{
	(void)e;
	const char *v[] = { "SPL", rt_spl_flag(), "WIPE", rt_wipe_flags(), NULL };
	char *c = cmd_expand(CMD_RETURN_CHECK, v);
	start_job(JK_CMD, tr(RS_RS_CHECKING_TITLE), "", c, true, false);
	free(c);
}

static void on_rt_save(lv_event_t *e)
{
	(void)e;
	char *c = cmd_expand(CMD_STOCK_COPY_USB, NULL);
	start_job(JK_CMD, tr(RS_RS_SAVING), "", c, true, false);
	free(c);
}

static void on_rt_spl(lv_event_t *e)
{
	(void)e;
	rt_start_check();
}

static void on_rt_wipe(lv_event_t *e)
{
	(void)e;
	rt_show_wipe();		/* the print files box follows the first */
	if (rt_wipe()) {	/* the second box and the note into view */
		lv_obj_update_layout(lv_obj_get_parent(rt.wipe));
		lv_obj_scroll_to_view(rt.wipe_note, LV_ANIM_OFF);
	}
	rt_start_check();
}

/* A box of the page as the boot loader box, INDENT px in (the print files
 * box under Kiln's data box), its text wrapping */
static lv_obj_t *rt_box(lv_obj_t *parent, int indent)
{
	lv_obj_t *b = lv_checkbox_create(parent);
	lv_checkbox_set_text(b, "");
	lv_obj_set_width(b, lv_pct(100));
	lv_obj_set_style_text_font(b, F20, 0);
	lv_obj_set_style_pad_column(b, 12, 0);
	lv_obj_set_style_pad_left(b, indent, 0);
	lv_obj_set_style_width(b, 30, LV_PART_INDICATOR);
	lv_obj_set_style_height(b, 30, LV_PART_INDICATOR);
	lv_obj_set_ext_click_area(b, 8);
	lv_obj_add_event_cb(b, on_rt_wipe, LV_EVENT_VALUE_CHANGED, NULL);
	show(b, false);
	return b;
}

static void page_return(void)
{
	capture_free(rt.cap);
	memset(&rt, 0, sizeof(rt));
	lv_obj_t *body = page_frame(tr(RS_RS_TITLE), true);
	lv_obj_t *c = card(body);
	lv_obj_set_width(c, lv_pct(100));
	lv_obj_set_flex_grow(c, 1);
	lv_obj_set_flex_flow(c, LV_FLEX_FLOW_COLUMN);
	lv_obj_set_style_pad_all(c, 16, 0);
	lv_obj_set_style_pad_row(c, 8, 0);
	/* a longer translation (or every line at once) can be taller than the
	 * card: it scrolls, so the boot loader box stays reachable */
	lv_obj_add_flag(c, LV_OBJ_FLAG_SCROLLABLE);
	lv_obj_set_scroll_dir(c, LV_DIR_VER);
	lv_obj_add_event_cb(c, rt_free, LV_EVENT_DELETE, NULL);
	rt.card = c;
	wrap_label(c, tr(RS_RS_TEXT), F20, C_TEXT);
	rt.files = wrap_label(c, "", F16, C_MUTED);
	rt.after = wrap_label(c, "", F16, C_MUTED);
	/* no boot.img: Flashforge's boot loader can't go back, said plainly */
	rt.spl_note = wrap_label(c, "", F16, C_MUTED);
	show(rt.spl_note, false);
	rt.cfg = wrap_label(c, "", F16, C_MUTED);
	show(rt.cfg, false);
	rt.status = wrap_label(c, "", F20B, C_MUTED);
	rt.spl = lv_checkbox_create(c);
	lv_checkbox_set_text(rt.spl, tr(RS_RS_SPL_BOX));
	lv_obj_set_style_text_font(rt.spl, F20, 0);
	lv_obj_set_style_pad_column(rt.spl, 12, 0);
	lv_obj_set_style_width(rt.spl, 30, LV_PART_INDICATOR);
	lv_obj_set_style_height(rt.spl, 30, LV_PART_INDICATOR);
	lv_obj_set_ext_click_area(rt.spl, 8);
	lv_obj_add_event_cb(rt.spl, on_rt_spl, LV_EVENT_VALUE_CHANGED, NULL);
	show(rt.spl, false);
	rt.wipe = rt_box(c, 0);
	rt.prints = rt_box(c, 42);
	rt.wipe_note = wrap_label(c, tr(RS_RS_WIPE_NOTE), F16, C_WARN);
	lv_obj_set_style_pad_left(rt.wipe_note, 42, 0);
	show(rt.wipe_note, false);
	lv_obj_t *row = box(body, LV_FLEX_FLOW_ROW);
	lv_obj_set_size(row, lv_pct(100), LV_SIZE_CONTENT);
	lv_obj_set_style_pad_column(row, 12, 0);
	rt.check = button(row, LV_SYMBOL_EYE_OPEN, tr(RS_CHECK), 0, on_rt_check, NULL);
	lv_obj_set_width(rt.check, 170);
	rt.save = button(row, LV_SYMBOL_USB, tr(RS_RS_SAVE_USB), 0, on_rt_save, NULL);
	lv_obj_set_width(rt.save, 250);
	rt.go = button(row, LV_SYMBOL_WARNING, tr(RS_RS_GO), 2, on_rt_go, NULL);
	lv_obj_set_flex_grow(rt.go, 1);
	enable(rt.go, false);
	rt_start_check();
	cur_refresh = rt_refresh;
}

/* ------------------------------------------------- Kiln's boot loader */

/* "Install Kiln's boot loader (experimental)": ad5x-bootloader-install
 * --check runs in the background when the page opens (and after Check):
 * its "board:" and "result:" lines and its first FAIL line fill the page.
 * Install is enabled only when the result is "ready" (Continue after a
 * stop); it asks twice, the second step armed after 3 s, with the risk
 * spelled out, then runs the install as a job ("don't switch off") whose
 * after-button restarts the printer: Kiln's SPL and U-Boot start this
 * recovery OS again, which records the start (--verify-start) and opens
 * this page with the result. Offered (Reboot / power) only when
 * ad5x-status --slots says bootloader_offer=yes (the board on the
 * allowlist, no Kiln U-Boot there yet) or an install is unfinished. The
 * expert override (--unsupported-board, SSH only) is never run from here.
 * "Update Kiln's boot loader" (bl.up, page_bootloader_upgrade) is the same
 * page with its own words, offered when ad5x-status --slots says
 * bootloader_upgrade=yes (Kiln's boot loader of another build there) or an
 * update is unfinished: it runs the tool with --upgrade (refused unless
 * it is an upgrade, so never an install), and its "upgrade:" line shows
 * the build on the printer and the one this release carries.
 * The result page (bl.result: ad5x-status bootloader_open=result, or the
 * record verified or unverified after an install or update) leads with
 * the outcome from the record, before and whatever the check says; the
 * check's own line goes under it (bl.note): "installed and up to date"
 * ("result: already installed (this build)", Install hidden), or, should
 * something have changed, ready or why not. The check waits for the
 * start-up actions (ad5x-status auto=running, polled) on every page: run
 * meanwhile, it would only say "busy: start-up-actions". */
static struct {
	lv_obj_t *card, *status, *note, *board, *builds, *go, *check;
	capture *cap;
	char why[240], from[96], to[96];
	bool up, known, ready, resume, done_already, already, checked, result, waiting;
} bl;

/* The install's string, or the update's (bl.up) */
#define BL_S(install, update) (bl.up ? (update) : (install))

static void bl_free(lv_event_t *e)
{
	/* the page opened again over itself: the old card goes after the new
	 * one's check started, and must not take it along */
	if (lv_event_get_target(e) != bl.card)
		return;
	capture_free(bl.cap);
	bl.cap = NULL;
}

/* The page opens with the result of an install or update: ad5x-status
 * bootloader_open=result (--verify-start, the first start after it), or
 * the record says verified or unverified and no update is offered (with
 * bootloader_upgrade=yes another build is there now: that record's
 * result is an old one, and the page is the update's) */
static bool bl_result_page(void)
{
	char st[24], bo[16], up[8];
	if (kv("bootloader_open", bo, sizeof(bo)) && !strcmp(bo, "result"))
		return true;
	if (kv("bootloader_upgrade", up, sizeof(up)) && !strcmp(up, "yes"))
		return false;
	kv("bootloader_install", st, sizeof(st));
	return !strcmp(st, "verified") || !strcmp(st, "unverified");
}

/* The result page's headline: the outcome, from the record */
static void bl_outcome(void)
{
	char st[24];
	kv("bootloader_install", st, sizeof(st));
	if (!strcmp(st, "unverified")) {
		lv_label_set_text(bl.status, tr_sym(LV_SYMBOL_WARNING, BL_S(RS_BL_UNVERIFIED, RS_BL_UP_UNVERIFIED)));
		lv_obj_set_style_text_color(bl.status, C_WARN, 0);
	} else {
		lv_label_set_text(bl.status, tr_sym(LV_SYMBOL_OK, !strcmp(st, "verified")
						    ? BL_S(RS_BL_VERIFIED, RS_BL_UP_VERIFIED)
						    : BL_S(RS_BL_INSTALLED, RS_BL_UP_DONE)));
		lv_obj_set_style_text_color(bl.status, C_OK, 0);
	}
}

/* The check's line: the headline, or under the result page's outcome */
static void bl_line(const char *text, lv_color_t c)
{
	lv_obj_t *l = bl.result ? bl.note : bl.status;
	lv_label_set_text(l, text);
	lv_obj_set_style_text_color(l, c, 0);
	show(l, true);
}

static void bl_start_check(void)
{
	if (bl.cap || job_running())
		return;
	enable(bl.go, false);
	enable(bl.check, false);
	if (auto_running()) {
		/* bl_refresh starts it once they are done */
		if (!bl.waiting)
			slog("Kiln's boot loader: the check waits for the start-up actions");
		bl.waiting = true;
		bl_line(tr_sym(LV_SYMBOL_REFRESH, RS_BL_WAIT_AUTO), C_MUTED);
		return;
	}
	bl.waiting = false;
	char *c = cmd_expand(BL_S(CMD_BOOTLOADER_CHECK, CMD_BOOTLOADER_UPGRADE_CHECK), NULL);
	slog("Kiln's boot loader: %s", c);
	bl.cap = capture_start(c, 16384);
	free(c);
	bl.checked = false;
	bl_line(tr_sym(LV_SYMBOL_REFRESH, RS_BL_CHECKING), C_MUTED);
}

static void bl_parse(const char *t)
{
	char res[240] = "", b[32] = "";
	bl.why[0] = 0;
	rt_line(t, "result", res, sizeof(res));
	bl.known = rt_line(t, "board", b, sizeof(b)) && !strcmp(b, "known");
	bl.ready = !strncmp(res, "ready", 5);
	bl.resume = !strncmp(res, "ready to go on", 14);
	/* "already installed (this build)": nothing to do, Install hidden */
	bl.already = !strncmp(res, "already installed", 17);
	bl.done_already = bl.already || !strncmp(res, "done", 4);
	/* "upgrade: Kiln boot loader <on the disk> -> <this build>" */
	char up[240] = "";
	bl.from[0] = bl.to[0] = 0;
	if (rt_line(t, "upgrade", up, sizeof(up))) {
		const char *u = up, *arrow = strstr(up, " -> ");
		if (!strncmp(u, "Kiln boot loader ", 17))
			u += 17;
		if (arrow && arrow > u) {
			const char *to = arrow + 4;
			if (!strncmp(u, "built ", 6) && !strchr(u + 6, ','))
				u += 6;
			if (!strncmp(to, "built ", 6) && !strchr(to + 6, ','))
				to += 6;
			snprintf(bl.from, sizeof(bl.from), "%.*s", (int)(arrow - u), u);
			snprintf(bl.to, sizeof(bl.to), "%s", to);
		}
	}
	for (const char *l = t; l && *l; l = strchr(l, '\n') ? strchr(l, '\n') + 1 : NULL)
		if (!strncmp(l, "  FAIL  ", 8)) {
			snprintf(bl.why, sizeof(bl.why), "%.*s", (int)strcspn(l + 8, "\n"), l + 8);
			break;
		}
	if (!bl.why[0] && !bl.ready && !bl.done_already)
		snprintf(bl.why, sizeof(bl.why), "%s", res[0] ? res : "?");
	if (bl.why[0])
		slog("Kiln's boot loader: not possible: %s", bl.why);
	bl.checked = true;
}

static void bl_show(void)
{
	if (!bl.checked)
		return;
	char t[1024], st[24];
	lv_label_set_text(bl.board, tr(bl.known ? RS_BL_BOARD_KNOWN : RS_BL_BOARD_UNKNOWN));
	if (bl.up && bl.from[0] && bl.to[0] && !bl.done_already) {
		snprintf(t, sizeof(t), tr(RS_BL_UP_BUILDS), bl.from, bl.to);
		lv_label_set_text(bl.builds, t);
		show(bl.builds, true);
	} else {
		show(bl.builds, false);
	}
	lv_color_t c = C_OK;
	if (bl.already) {
		snprintf(t, sizeof(t), "%s", tr_sym(LV_SYMBOL_OK, RS_BL_UP_TO_DATE));
	} else if (bl.done_already) {
		kv("bootloader_install", st, sizeof(st));
		if (!strcmp(st, "verified"))
			snprintf(t, sizeof(t), "%s", tr_sym(LV_SYMBOL_OK, BL_S(RS_BL_VERIFIED, RS_BL_UP_VERIFIED)));
		else if (!strcmp(st, "unverified"))
			snprintf(t, sizeof(t), "%s", tr_sym(LV_SYMBOL_WARNING, BL_S(RS_BL_UNVERIFIED, RS_BL_UP_UNVERIFIED))), c = C_WARN;
		else
			snprintf(t, sizeof(t), "%s", tr_sym(LV_SYMBOL_OK, BL_S(RS_BL_INSTALLED, RS_BL_UP_DONE)));
	} else if (bl.resume) {
		snprintf(t, sizeof(t), "%s", tr_sym(LV_SYMBOL_WARNING, BL_S(RS_BL_RESUME, RS_BL_UP_RESUME))), c = C_WARN;
	} else if (bl.ready) {
		snprintf(t, sizeof(t), "%s", tr_sym(LV_SYMBOL_OK, BL_S(RS_BL_READY, RS_BL_UP_READY)));
	} else {
		char w[240];
		iconed(t, sizeof(t), LV_SYMBOL_CLOSE, "  ", tr(RS_RS_REFUSED), why_text(bl.why, w, sizeof(w)));
		c = C_WARN;
	}
	if (bl.result) {
		/* the outcome stays the headline; the check's line goes under
		 * it, the record's outcome in the headline already */
		bl_outcome();
		if (bl.done_already && !bl.already)
			show(bl.note, false);
		else
			bl_line(t, bl.already ? C_MUTED : c);
	} else {
		bl_line(t, c);
	}
	lv_label_set_text(lv_obj_get_child(bl.go, 0),
			  tr_sym(bl.resume ? LV_SYMBOL_PLAY : LV_SYMBOL_WARNING,
				 bl.resume ? RS_RS_CONTINUE : BL_S(RS_BL_GO, RS_BL_UP_GO)));
	/* nothing to install: no Install; on the result page only once the
	 * check says there is something to do */
	show(bl.go, !bl.already && (!bl.result || bl.ready));
	enable(bl.go, bl.ready);
	enable(bl.check, true);
}

static void bl_refresh(void)
{
	if (bl.waiting && !auto_running())
		bl_start_check();
	if (bl.cap && capture_done(bl.cap)) {
		const char *t = capture_text(bl.cap);
		bl_parse(t ? t : "");
		capture_free(bl.cap);
		bl.cap = NULL;
		bl_show();
	}
}

static void bl_install_now(void)
{
	char *c = cmd_expand(BL_S(CMD_BOOTLOADER_INSTALL, CMD_BOOTLOADER_UPGRADE), NULL);
	start_job_x(JK_CMD, tr(BL_S(RS_BL_RUNNING, RS_BL_UP_RUNNING)), "", c, false, false, true,
		    AFTER_REBOOT);
	jb.done_text = tr(BL_S(RS_BL_INSTALLED, RS_BL_UP_DONE));
	free(c);
}

static void on_bl_go(lv_event_t *e)
{
	(void)e;
	if (!bl.ready)
		return;
	if (bl.resume) {	/* asked before; finish it */
		bl_install_now();
		return;
	}
	confirm(tr(BL_S(RS_BL_Q, RS_BL_UP_Q)), tr(BL_S(RS_BL_Q_TEXT, RS_BL_UP_Q_TEXT)),
		tr_sym(LV_SYMBOL_WARNING, BL_S(RS_BL_GO, RS_BL_UP_GO)), true,
		tr(RS_BL_Q_TEXT2), bl_install_now);
}

static void on_bl_check(lv_event_t *e)
{
	(void)e;
	char *c = cmd_expand(BL_S(CMD_BOOTLOADER_CHECK, CMD_BOOTLOADER_UPGRADE_CHECK), NULL);
	start_job(JK_CMD, tr(RS_BL_CHECKING_TITLE), "", c, true, false);
	free(c);
}

static void bl_page(bool up)
{
	capture_free(bl.cap);
	memset(&bl, 0, sizeof(bl));
	bl.up = up;
	bl.result = bl_result_page();
	lv_obj_t *body = page_frame(tr(BL_S(RS_BL_TITLE, RS_BL_UP_TITLE)), true);
	lv_obj_t *c = card(body);
	lv_obj_set_width(c, lv_pct(100));
	lv_obj_set_flex_grow(c, 1);
	lv_obj_set_flex_flow(c, LV_FLEX_FLOW_COLUMN);
	lv_obj_set_style_pad_all(c, 16, 0);
	lv_obj_set_style_pad_row(c, 8, 0);
	bl.card = c;
	lv_obj_add_event_cb(c, bl_free, LV_EVENT_DELETE, NULL);
	if (bl.result) {
		/* the result first: the outcome and the check's line, then what
		 * the boot loader is, smaller */
		bl.status = wrap_label(c, "", F20B, C_MUTED);
		bl.note = wrap_label(c, "", F16, C_MUTED);
		show(bl.note, false);
		wrap_label(c, tr(BL_S(RS_BL_TEXT, RS_BL_UP_TEXT)), F16, C_MUTED);
		bl.board = wrap_label(c, "", F16, C_MUTED);
		bl.builds = wrap_label(c, "", F16, C_MUTED);
		show(bl.builds, false);
	} else {
		wrap_label(c, tr(BL_S(RS_BL_TEXT, RS_BL_UP_TEXT)), F20, C_TEXT);
		bl.board = wrap_label(c, "", F16, C_MUTED);
		bl.builds = wrap_label(c, "", F16, C_MUTED);
		show(bl.builds, false);
		bl.status = wrap_label(c, "", F20B, C_MUTED);
		bl.note = wrap_label(c, "", F16, C_MUTED);
		show(bl.note, false);
	}
	lv_obj_t *row = box(body, LV_FLEX_FLOW_ROW);
	lv_obj_set_size(row, lv_pct(100), LV_SIZE_CONTENT);
	lv_obj_set_style_pad_column(row, 12, 0);
	bl.check = button(row, LV_SYMBOL_EYE_OPEN, tr(RS_CHECK), 0, on_bl_check, NULL);
	lv_obj_set_width(bl.check, 170);
	bl.go = button(row, LV_SYMBOL_WARNING, tr(BL_S(RS_BL_GO, RS_BL_UP_GO)), 2, on_bl_go, NULL);
	lv_obj_set_flex_grow(bl.go, 1);
	enable(bl.go, false);
	if (bl.result) {
		slog("Kiln's boot loader: the result page (record %s)",
		     kv("bootloader_install", bl.why, sizeof(bl.why)) ? bl.why : "none");
		bl.why[0] = 0;
		bl_outcome();
		show(bl.go, false);
	}
	bl_start_check();
	cur_refresh = bl_refresh;
}

static void page_bootloader(void)
{
	bl_page(false);
}

static void page_bootloader_upgrade(void)
{
	bl_page(true);
}

/* ---------------------------------------------------------- network page */

static struct {
	lv_obj_t *rows, *qr, *qrl, *info;
	capture *cap;
	unsigned seen;
	char url[96];
} nw;

static void nw_row(const char *k, const char *v, lv_color_t vc)
{
	lv_obj_t *r = box(nw.rows, LV_FLEX_FLOW_ROW);
	lv_obj_set_size(r, lv_pct(100), LV_SIZE_CONTENT);
	lv_obj_t *kl = label(r, k, F20, C_MUTED);
	lv_obj_set_width(kl, 120);
	lv_obj_t *vl = label(r, v, F24B, vc);
	lv_label_set_long_mode(vl, LV_LABEL_LONG_MODE_DOTS);
	lv_obj_set_flex_grow(vl, 1);
}

static void nw_fill(void)
{
	lv_obj_clean(nw.rows);
	char ip[64], ifc[16], mode[16], t[200], v[64], host[64] = "ad5x";
	gethostname(host, sizeof(host));
	bool have = cur_ip(ip, sizeof(ip), ifc, sizeof(ifc));
	if (have) {
		bool m = kv("net_mode", mode, sizeof(mode));
		snprintf(t, sizeof(t), "%s  (%s%s%s)", ip, ifc, m ? ", " : "", m ? mode : "");
		nw_row(tr(RS_ADDRESS), t, C_TEXT);
	} else {
		nw_row(tr(RS_ADDRESS), tr(RS_NO_NETWORK), C_MUTED);
	}
	nw_row(tr(RS_NAME), host, C_TEXT);
	bool ssh_up = !kv("ssh", v, sizeof(v)) || !strcmp(v, "running");
	if (have && ssh_up)
		snprintf(t, sizeof(t), "ssh root@%s", ip);
	else
		snprintf(t, sizeof(t), "%s", ssh_up ? tr(RS_NO_NETWORK) : tr(RS_NOT_RUNNING));
	nw_row("SSH", t, have && ssh_up ? C_ACCENT : C_MUTED);
	char port[16] = "8080";
	kv("web_port", port, sizeof(port));
	if (have) {
		snprintf(nw.url, sizeof(nw.url), "http://%s:%s", ip, port);
		nw_row(tr(RS_UPLOAD), nw.url, C_ACCENT);
		lv_qrcode_update(nw.qr, nw.url, strlen(nw.url));
		show(nw.qr, true);
		lv_label_set_text(nw.qrl, tr(RS_UPDATE_UPLOAD_PAGE));
	} else {
		nw_row(tr(RS_UPLOAD), tr(RS_NO_NETWORK), C_MUTED);
		show(nw.qr, false);
		lv_label_set_text(nw.qrl, tr(RS_PLUG_IN));
	}
	if (kv("release", v, sizeof(v)))
		nw_row(tr(RS_RECOVERY_ROW), v, C_TEXT);
}

/* `ad5x-usb list` lines -> a short USB / rescue summary */
static void nw_usb(const char *list)
{
	char out[600] = "";
	for (const char *l = list; l && *l; l = strchr(l, '\n') ? strchr(l, '\n') + 1 : NULL) {
		char line[400], dev[64] = "", fs[16] = "", swu[200] = "", *save = NULL;
		int rr = 0, rb = 0, rf = 0, au = 0;
		snprintf(line, sizeof(line), "%.*s", (int)strcspn(l, "\n"), l);
		for (char *w = strtok_r(line, " ", &save); w; w = strtok_r(NULL, " ", &save)) {
			if (!strncmp(w, "dev=", 4)) snprintf(dev, sizeof(dev), "%s", w + 4);
			else if (!strncmp(w, "fs=", 3)) snprintf(fs, sizeof(fs), "%s", w + 3);
			else if (!strncmp(w, "swu=", 4)) snprintf(swu, sizeof(swu), "%s", w + 4);
			else if (!strncmp(w, "rescue_root=", 12)) rr = atoi(w + 12);
			else if (!strncmp(w, "rescue_boot=", 12)) rb = atoi(w + 12);
			else if (!strncmp(w, "rescue_flash=", 13)) rf = atoi(w + 13);
			else if (!strncmp(w, "autoupdate=", 11)) au = atoi(w + 11);
		}
		if (!dev[0])
			continue;
		int nswu = 0;
		for (const char *p = swu; *p; p++)
			nswu += *p == ',';
		nswu += swu[0] != 0;
		size_t n = strlen(out);
		snprintf(out + n, sizeof(out) - n, tr(RS_USB_SUMMARY), n ? "\n" : "", dev, fs, nswu,
			nswu == 1 ? tr(RS_UPDATE_ONE) : tr(RS_UPDATE_MANY));
		n = strlen(out);
		if (rr)
			snprintf(out + n, sizeof(out) - n, "%s", tr(RS_FLAG_RESCUE_SYSTEM));
		n = strlen(out);
		if (rb)
			snprintf(out + n, sizeof(out) - n, "%s", tr(RS_FLAG_RESCUE_BOOT));
		n = strlen(out);
		if (rf)
			snprintf(out + n, sizeof(out) - n, "%s", tr(RS_FLAG_RESCUE_FLASH));
		n = strlen(out);
		if (au)
			snprintf(out + n, sizeof(out) - n, "%s", tr(RS_FLAG_AUTOUPDATE));
	}
	lv_label_set_text(nw.info, out[0] ? out : tr(RS_USB_NO_STICK));
}

static void nw_refresh(void)
{
	if (nw.cap && capture_done(nw.cap)) {
		nw_usb(capture_text(nw.cap));
		capture_free(nw.cap);
		nw.cap = NULL;
	}
	if (nw.seen != stc.seq + 1) {
		nw.seen = stc.seq + 1;
		nw_fill();
	}
}

static void nw_free(lv_event_t *e)
{
	(void)e;
	capture_free(nw.cap);
	nw.cap = NULL;
}

static void page_network(void)
{
	memset(&nw, 0, sizeof(nw));
	lv_obj_t *body = page_frame(tr(RS_NETWORK_SSH), true);
	lv_obj_add_event_cb(scr, nw_free, LV_EVENT_DELETE, NULL);
	lv_obj_t *cols = box(body, LV_FLEX_FLOW_ROW);
	lv_obj_set_width(cols, lv_pct(100));
	lv_obj_set_flex_grow(cols, 1);
	lv_obj_set_style_pad_column(cols, 12, 0);
	lv_obj_t *left = card(cols);
	lv_obj_set_height(left, lv_pct(100));
	lv_obj_set_flex_grow(left, 1);
	lv_obj_set_flex_flow(left, LV_FLEX_FLOW_COLUMN);
	lv_obj_set_style_pad_all(left, 16, 0);
	lv_obj_set_style_pad_row(left, 10, 0);
	nw.rows = box(left, LV_FLEX_FLOW_COLUMN);
	lv_obj_set_size(nw.rows, lv_pct(100), LV_SIZE_CONTENT);
	lv_obj_set_style_pad_row(nw.rows, 8, 0);
	nw.info = wrap_label(left, "", F16, C_MUTED);
	wrap_label(left, tr(RS_SSH_LOGIN_TEXT), F16, C_MUTED);

	lv_obj_t *right = card(cols);
	lv_obj_set_size(right, 236, lv_pct(100));
	lv_obj_set_flex_flow(right, LV_FLEX_FLOW_COLUMN);
	lv_obj_set_flex_align(right, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER,
			      LV_FLEX_ALIGN_CENTER);
	lv_obj_set_style_pad_row(right, 12, 0);
	nw.qr = lv_qrcode_create(right);
	lv_qrcode_set_size(nw.qr, 196);
	lv_qrcode_set_dark_color(nw.qr, lv_color_black());
	lv_qrcode_set_light_color(nw.qr, lv_color_white());
	lv_obj_set_style_border_color(nw.qr, lv_color_white(), 0);
	lv_obj_set_style_border_width(nw.qr, 6, 0);
	nw.qrl = wrap_label(right, "", F16, C_MUTED);
	lv_obj_set_style_text_align(nw.qrl, LV_TEXT_ALIGN_CENTER, 0);

	char *c = cmd_expand(CMD_USB_LIST, NULL);
	nw.cap = capture_start(c, 2048);
	free(c);
	cur_refresh = nw_refresh;
}

/* ------------------------------------------------------------- logs page */

enum { LOG_SESSION, LOG_UPDATE, LOG_SWU, LOG_SYSTEM, LOG_N };
static struct {
	int which;
	lv_obj_t *tabs[LOG_N], *view, *text;
	capture *cap;
	unsigned seen;
	char *buf;
} lg;

#define LOG_CAP (24 * 1024)

static void lg_set(const char *t)
{
	lv_label_set_text(lg.text, t && *t ? t : tr(RS_EMPTY_LOG));
	lv_obj_update_layout(lg.view);
	lv_obj_scroll_to_y(lg.view, LV_COORD_MAX, LV_ANIM_OFF);
}

static void lg_load(void)
{
	for (int i = 0; i < LOG_N; i++)
		if (i == lg.which)
			lv_obj_add_state(lg.tabs[i], LV_STATE_CHECKED);
		else
			lv_obj_remove_state(lg.tabs[i], LV_STATE_CHECKED);
	capture_free(lg.cap);
	lg.cap = NULL;
	switch (lg.which) {
	case LOG_SESSION:
		lg.seen = slog_seq();
		slog_copy(lg.buf, LOG_CAP);
		lg_set(lg.buf);
		break;
	case LOG_SYSTEM: {
		char *c = cmd_expand(CMD_SYSLOG, NULL);
		lg.cap = capture_start(c, LOG_CAP);
		free(c);
		lv_label_set_text(lg.text, tr(RS_READING));
		break;
	}
	case LOG_UPDATE:
	case LOG_SWU: {
		char *q = sh_quote(rui_get(lg.which == LOG_SWU ? PATH_SWU_LOG : PATH_LAST_LOG));
		char cmd[600];
		snprintf(cmd, sizeof(cmd), "tail -n 300 %s 2>&1", q);
		free(q);
		lg.cap = capture_start(cmd, LOG_CAP);
		lv_label_set_text(lg.text, tr(RS_READING));
		break;
	}
	}
}

static void lg_refresh(void)
{
	if (lg.cap && capture_done(lg.cap)) {
		lg_set(capture_text(lg.cap));
		capture_free(lg.cap);
		lg.cap = NULL;
	}
	if (lg.which == LOG_SESSION && slog_seq() != lg.seen)
		lg_load();
}

static void on_lg_tab(lv_event_t *e)
{
	lg.which = (int)(intptr_t)lv_event_get_user_data(e);
	lg_load();
}

static void lg_free(lv_event_t *e)
{
	(void)e;
	capture_free(lg.cap);
	lg.cap = NULL;
}

static void page_logs(void)
{
	if (!lg.buf)
		lg.buf = malloc(LOG_CAP);
	lg.cap = NULL;
	lv_obj_t *body = page_frame(tr(RS_LOGS), true);
	lv_obj_add_event_cb(scr, lg_free, LV_EVENT_DELETE, NULL);
	lv_obj_t *row = box(body, LV_FLEX_FLOW_ROW);
	lv_obj_set_size(row, lv_pct(100), LV_SIZE_CONTENT);
	lv_obj_set_style_pad_column(row, 10, 0);
	static const enum rui_str names[LOG_N] = { RS_LOGS_TAB_SESSION, RS_LOGS_TAB_UPDATES, RS_LOGS_TAB_SWUPDATE, RS_LOGS_TAB_SYSTEM };
	for (int i = 0; i < LOG_N; i++) {
		lg.tabs[i] = button(row, NULL, tr(names[i]), 0, on_lg_tab, (void *)(intptr_t)i);
		lv_obj_set_flex_grow(lg.tabs[i], 1);
		lv_obj_set_height(lg.tabs[i], 52);
		lv_obj_set_style_bg_color(lg.tabs[i], C_ACCENT_FILL, LV_STATE_CHECKED);
	}
	lg.view = card(body);
	lv_obj_set_width(lg.view, lv_pct(100));
	lv_obj_set_flex_grow(lg.view, 1);
	lv_obj_add_flag(lg.view, LV_OBJ_FLAG_SCROLLABLE);
	lv_obj_set_scroll_dir(lg.view, LV_DIR_VER);
	lv_obj_set_style_bg_color(lg.view, lv_color_hex(0x242933), 0);
	lg.text = wrap_label(lg.view, "", FMONO, C_MUTED);
	lg_load();
	cur_refresh = lg_refresh;
}

/* ------------------------------------------------------------ power page */

static void reboot_now(void)
{
	char *c = cmd_expand(CMD_REBOOT, NULL);
	start_job(JK_CMD, tr(RS_REBOOTING), "", c, false, true);
	free(c);
}

static void poweroff_now(void)
{
	char *c = cmd_expand(CMD_POWEROFF, NULL);
	start_job(JK_CMD, tr(RS_SHUTTING_DOWN), "", c, false, true);
	free(c);
}

static void on_reboot(lv_event_t *e)
{
	(void)e;
	char flag[32];
	const char *where = (kv("flag", flag, sizeof(flag)) || sys_ota_flag(flag, sizeof(flag))) &&
			    !strcmp(flag, "ota:kernel2")
			    ? tr(RS_REBOOT_MAIN)
			    : tr(RS_REBOOT_RECOVERY);
	static char t[200];
	snprintf(t, sizeof(t), tr(RS_REBOOT_TEXT), where);
	confirm(tr(RS_REBOOT_Q), t, tr_sym(LV_SYMBOL_REFRESH, RS_REBOOT), false, NULL, reboot_now);
}

static void on_poweroff(lv_event_t *e)
{
	(void)e;
	confirm(tr(RS_SHUTDOWN_Q), tr(RS_SHUTDOWN_TEXT), tr_sym(LV_SYMBOL_POWER, RS_SHUT_DOWN),
		false, NULL, poweroff_now);
}

/* Kiln's own boot loader's entry on the power page: offered on a board on
 * the allowlist without it while slot B holds Kiln OS, or to finish an
 * install that stopped; its update when the printer has Kiln's boot
 * loader of another build (bootloader_upgrade=yes), or to finish an
 * update that stopped (ad5x-status --slots) */
enum pw_entry { PW_NONE, PW_INSTALL, PW_UPDATE };

static enum pw_entry power_entry(void)
{
	char v[16], sb[96];
	bool kiln_b = kv("slot_b", sb, sizeof(sb)) && !strncmp(sb, "ad5x ", 5);
	bool started = kv("bootloader_install", v, sizeof(v)) && !strcmp(v, "started");
	if ((kv("bootloader_upgrade", v, sizeof(v)) && !strcmp(v, "yes") && kiln_b) ||
	    (started && bl_record_upgrade()))
		return PW_UPDATE;
	if ((kv("bootloader_offer", v, sizeof(v)) && !strcmp(v, "yes") && kiln_b) || started)
		return PW_INSTALL;
	return PW_NONE;
}

/* A build date as ad5x-status has it ("Nov 19 2026 - 08:31:00 +0000",
 * or "SPL date / U-Boot date"), without the time zones; "?" when none */
static const char *bl_date(const char *key, char *out, size_t cap)
{
	char v[128];
	if (!kv(key, v, sizeof(v))) {
		snprintf(out, cap, "?");
		return out;
	}
	size_t k = 0;
	for (const char *p = v; *p && k + 1 < cap;) {
		if (!strncmp(p, " +0000", 6)) {
			p += 6;
			continue;
		}
		out[k++] = *p++;
	}
	out[k] = 0;
	return out;
}

/* The power page's boot loader line, always there and read only (issue
 * #97): Kiln's installed and the build this recovery carries (up to
 * date), installed with an update offered (a newer build here), installed
 * with an older build here (bootloader_carries_newer=no: never offered),
 * installed with another build here that isn't offered, Flashforge's, or "reading" until a --slots
 * run has finished (at start, or during the start-up actions: read again
 * when they are done) and only then "couldn't be read" */
static void power_bl_line(char *t, size_t cap, lv_color_t *c)
{
	char b[16], same[8], nw[16], d1[96], d2[96];
	if (!kv("bootloader", b, sizeof(b)) || !strcmp(b, "unknown")) {
		if (!stc.slots_read || stc.slots_auto || auto_running()) {
			iconed(t, cap, LV_SYMBOL_REFRESH, "  ", "%s", tr(RS_BL_LINE_READING));
			*c = C_MUTED;
		} else {
			iconed(t, cap, LV_SYMBOL_WARNING, "  ", "%s", tr(RS_BL_LINE_UNKNOWN));
			*c = C_WARN;
		}
		return;
	}
	*c = C_MUTED;
	if (!strcmp(b, "kiln")) {
		bl_date("bootloader_build", d1, sizeof(d1));
		if (power_entry() == PW_UPDATE) {
			iconed(t, cap, LV_SYMBOL_DOWNLOAD, "  ", tr(RS_BL_LINE_UPDATE), d1);
			*c = C_ACCENT;
		} else if (kv("bootloader_same", same, sizeof(same)) && !strcmp(same, "yes")) {
			iconed(t, cap, LV_SYMBOL_OK, "  ", tr(RS_BL_LINE_CURRENT), d1);
			*c = C_OK;
		} else if (kv("bootloader_carries", d2, sizeof(d2)) &&
			   kv("bootloader_carries_newer", nw, sizeof(nw)) && !strcmp(nw, "no")) {
			/* an older build here (someone went back to an older
			 * release): no Update, never a downgrade from the screen */
			iconed(t, cap, LV_SYMBOL_DRIVE, "  ", tr(RS_BL_LINE_OLDER), d1,
			       bl_date("bootloader_carries", d2, sizeof(d2)));
		} else if (kv("bootloader_carries", d2, sizeof(d2))) {
			iconed(t, cap, LV_SYMBOL_DRIVE, "  ", tr(RS_BL_LINE_OTHER), d1,
			       bl_date("bootloader_carries", d2, sizeof(d2)));
		} else {
			iconed(t, cap, LV_SYMBOL_DRIVE, "  ", tr(RS_BL_LINE_INSTALLED), d1);
		}
	} else if (!strcmp(b, "kiln-spl")) {
		iconed(t, cap, LV_SYMBOL_WARNING, "  ", "%s", tr(RS_BL_LINE_SPL));
		*c = C_WARN;
	} else {
		iconed(t, cap, LV_SYMBOL_DRIVE, "  ", "%s", tr(RS_BL_LINE_FLASHFORGE));
	}
}

static struct {
	lv_obj_t *bl;
	enum pw_entry entry;
	unsigned seen;
} pw;

/* A new ad5x-status: the line again; the page again when the entry
 * changes (the boot loader read at start, after the start-up actions) */
static void power_refresh(void)
{
	if (pw.seen == stc.seq + 1)
		return;
	pw.seen = stc.seq + 1;
	if (power_entry() != pw.entry) {
		go(page_power);
		return;
	}
	char t[300];
	lv_color_t c;
	power_bl_line(t, sizeof(t), &c);
	lv_label_set_text(pw.bl, t);
	lv_obj_set_style_text_color(pw.bl, c, 0);
}

static void page_power(void)
{
	lv_obj_t *body = page_frame(tr(RS_REBOOT_POWER), true);
	lv_obj_t *c = card(body);
	lv_obj_set_width(c, lv_pct(100));
	lv_obj_set_flex_grow(c, 1);
	lv_obj_set_flex_flow(c, LV_FLEX_FLOW_COLUMN);
	lv_obj_set_style_pad_all(c, 18, 0);
	lv_obj_set_style_pad_row(c, 8, 0);
	label(c, tr_sym(LV_SYMBOL_POWER, RS_POWER), F24B, C_TEXT);
	wrap_label(c, tr(RS_POWER_TEXT), F20, C_TEXT);
	wrap_label(c, tr(RS_POWER_TEXT2), F20, C_MUTED);
	/* the boot loader line: one line of 16 px, so it fits with the entry
	 * under it in English and Russian */
	memset(&pw, 0, sizeof(pw));
	pw.bl = wrap_label(c, "", F16, C_MUTED);
	pw.entry = power_entry();
	if (pw.entry == PW_UPDATE) {
		lv_obj_t *b = button(c, LV_SYMBOL_DRIVE, tr(RS_BL_UP_ENTRY), 0, on_go,
				     page_bootloader_upgrade);
		lv_obj_set_width(b, lv_pct(100));
	} else if (pw.entry == PW_INSTALL) {
		lv_obj_t *b = button(c, LV_SYMBOL_DRIVE, tr(RS_BL_ENTRY), 0, on_go, page_bootloader);
		lv_obj_set_width(b, lv_pct(100));
	}
	lv_obj_t *row = box(body, LV_FLEX_FLOW_ROW);
	lv_obj_set_size(row, lv_pct(100), LV_SIZE_CONTENT);
	lv_obj_set_style_pad_column(row, 12, 0);
	lv_obj_t *b1 = button(row, LV_SYMBOL_PLAY, tr(RS_BOOT_MAIN_OS), 1, on_boot_main, NULL);
	lv_obj_t *b2 = button(row, LV_SYMBOL_REFRESH, tr(RS_REBOOT), 0, on_reboot, NULL);
	lv_obj_t *b3 = button(row, LV_SYMBOL_POWER, tr(RS_SHUT_DOWN), 0, on_poweroff, NULL);
	lv_obj_set_flex_grow(b1, 1);
	lv_obj_set_flex_grow(b2, 1);
	lv_obj_set_flex_grow(b3, 1);
	cur_refresh = power_refresh;
}

/* -------------------------------------------------------------- job page */

static struct {
	lv_obj_t *status, *step, *bar, *pct, *spin, *log, *logtext, *cancel, *done, *boot;
	lv_obj_t *banner, *elapsed;
	char *buf;
	bool ended;
	long t0;		/* when the page began (elapsed time) */
	job_after after;	/* what the after-button does */
} jp;

/* The time a long page has been running, "2:14", next to its spinner: a
 * step that takes minutes still visibly moves, and the number stays when
 * it ends (how long it took). Monotonic: the clock may jump with NTP. */
static long mono_s(void)
{
	struct timespec t;
	clock_gettime(CLOCK_MONOTONIC, &t);
	return (long)t.tv_sec;
}

static void set_elapsed(lv_obj_t *l, long t0)
{
	long s = mono_s() - t0;
	if (s < 0)
		s = 0;
	lv_label_set_text_fmt(l, "%ld:%02ld", s / 60, s % 60);
}

#define JOB_VIEW_CAP 8192

static void reboot_now(void);
static void poweroff_now(void);

static void on_after(lv_event_t *e)
{
	if (jp.after == AFTER_REBOOT)
		confirm(tr(RS_REBOOT_Q), tr(RS_REBOOT_INTO_FLAG), tr_sym(LV_SYMBOL_REFRESH, RS_REBOOT),
			false, NULL, reboot_now);
	else if (jp.after == AFTER_POWEROFF)
		confirm(tr(RS_SHUTDOWN_Q), tr(RS_SHUTDOWN_TEXT), tr_sym(LV_SYMBOL_POWER, RS_SHUT_DOWN),
			false, NULL, poweroff_now);
	else
		on_boot_main(e);
}

static void on_cancel(lv_event_t *e)
{
	(void)e;
	job_cancel();
}

static void job_banner(bool ok, const char *text)
{
	lv_obj_set_style_bg_color(jp.banner, ok ? lv_color_hex(0x45504F)
						 : lv_color_hex(0x4B3D48), 0);
	lv_obj_set_style_border_color(jp.banner, ok ? C_OK : C_DANGER, 0);
	lv_label_set_text(jp.status, text);
	lv_obj_set_style_text_color(jp.status, ok ? C_OK : C_DANGER, 0);
}

static void job_refresh(void)
{
	job_state js;
	swu_state ss;
	if (jb.pending) {
		if (status_busy()) {
			lv_label_set_text(jp.step, tr(RS_WAITING_STATUS));
			return;
		}
		jb.started = job_start(jb.title, jb.pending);
		jb.failed_start = !jb.started;
		free(jb.pending);
		jb.pending = NULL;
	}
	job_poll(&js);
	swu_get(&ss);
	bool swu_mode = jb.kind == JK_INSTALL || jb.kind == JK_WEB;
	bool swu_fresh = ss.seq != jb.swu_seq_at_start;

	if (js.seq != jb.last_seq || ss.seq != jb.last_swu) {
		jb.last_seq = js.seq;
		jb.last_swu = ss.seq;
		if (jb.kind != JK_WEB) {
			job_output(jp.buf, JOB_VIEW_CAP);
			lv_label_set_text(jp.logtext, jp.buf[0] ? jp.buf : "\xe2\x80\xa6");
		} else {
			swu_log_copy(jp.buf, JOB_VIEW_CAP);
			lv_label_set_text(jp.logtext, jp.buf);
		}
		lv_obj_update_layout(jp.log);
		lv_obj_scroll_to_y(jp.log, LV_COORD_MAX, LV_ANIM_OFF);
	}

	/* Progress: SWUpdate's for installs, else the command's output */
	int pct = js.progress;
	char step[256] = "";
	if (swu_mode && swu_fresh) {
		pct = ss.overall;
		if (ss.status == SWU_DOWNLOAD)
			snprintf(step, sizeof(step), tr(RS_RECEIVING), ss.dwl_percent);
		else if (ss.nsteps)
			snprintf(step, sizeof(step), tr(RS_STEP_FMT), ss.cur_step,
				 ss.nsteps, ss.image[0] ? ss.image : tr(RS_PREPARING),
				 ss.handler[0] ? " (" : "", ss.handler, ss.handler[0] ? ")" : "");
		else
			snprintf(step, sizeof(step), tr(RS_SWU_STATUS), swu_status_tr(ss.status));
	} else if (js.step[0]) {
		pg_text(js.code, js.arg, js.step, step, sizeof(step));	/* screen's language */
	} else if (jb.what[0]) {
		snprintf(step, sizeof(step), "%s", jb.what);
	}
	if (!jp.ended)
		lv_label_set_text(jp.step, step);

	bool have_result = ss.result_seq != jb.swu_result_at_start;
	bool running = jb.kind == JK_WEB ? ss.active : js.running;
	bool ended = !running && (jb.kind == JK_WEB ? have_result
				  : js.finished || jb.failed_start);

	if (jp.ended) {
		/* result shown, nothing more to update */
	} else if (pct >= 0) {
		show(jp.bar, true);
		lv_bar_set_value(jp.bar, pct, LV_ANIM_OFF);
		lv_label_set_text_fmt(jp.pct, "%d%%", pct);
	} else {
		show(jp.bar, running);
		lv_bar_set_value(jp.bar, 0, LV_ANIM_OFF);
		lv_label_set_text(jp.pct, "");
	}
	show(jp.spin, running);
	if (running && !jp.ended)
		set_elapsed(jp.elapsed, jp.t0);

	if (running) {
		if (!jp.ended)
			lv_label_set_text(jp.status, jb.reboots ? tr(RS_RESTARTING)
					  : jb.critical || jb.kind == JK_WEB
					  ? tr(RS_WORKING_DONT_OFF)
					  : tr(RS_WORKING));
		show(jp.cancel, jb.cancelable);
		show(jp.done, false);
		show(jp.boot, false);
		enable(back_btn, false);
		return;
	}
	if (!ended || jp.ended)
		return;
	jp.ended = true;
	bool ok;
	if (jb.kind == JK_WEB)
		ok = ss.result == SWU_SUCCESS;
	else if (jb.kind == JK_INSTALL)
		ok = js.exit_code == 0 && !(have_result && ss.result == SWU_FAILURE);
	else
		ok = js.exit_code == 0;
	char msg[200];
	if (jb.failed_start)
		iconed(msg, sizeof(msg), LV_SYMBOL_CLOSE, "  ", "%s", tr(RS_COULD_NOT_START));
	else if (ok)
		iconed(msg, sizeof(msg), LV_SYMBOL_OK, "  ", tr(RS_JOB_DONE), jb.title);
	else if (js.exit_code < 0 && jb.kind != JK_WEB)
		iconed(msg, sizeof(msg), LV_SYMBOL_CLOSE, "  ", tr(RS_JOB_STOPPED), jb.title);
	else if (jb.kind == JK_WEB)
		iconed(msg, sizeof(msg), LV_SYMBOL_CLOSE, "  ", "%s", tr(RS_UPDATE_FAILED));
	else
		iconed(msg, sizeof(msg), LV_SYMBOL_CLOSE, "  ", tr(RS_JOB_FAILED), jb.title,
			js.exit_code);
	job_banner(ok, msg);
	if (ok) {
		show(jp.bar, true);
		lv_bar_set_value(jp.bar, 100, LV_ANIM_OFF);
		lv_label_set_text(jp.pct, "100%");
	}
	slog("%s", msg + 5);
	/* The tools' last line is their result ("backup: OK <dir>",
	 * "swu-apply: FAILED ..."): show it under the banner */
	if (jb.kind != JK_WEB) {
		const char *t = jp.buf, *last = NULL;
		for (const char *p = t; *p; p = strchr(p, '\n') ? strchr(p, '\n') + 1 : p + strlen(p))
			if (*p != '\n')
				last = p;
		if (last && ok && jb.done_text && !strncmp(last, "result: done", 12))
			lv_label_set_text(jp.step, jb.done_text);	/* in the screen's language */
		else if (last && !strncmp(last, "result: refused", 15) && tr_has(RS_WHY_OTHER)) {
			/* why: its first FAIL line, else the result's own text */
			char why[240], wt[240];
			snprintf(why, sizeof(why), "%.*s", (int)strcspn(last + 8, "\n"), last + 8);
			for (const char *l = t; *l; l = strchr(l, '\n') ? strchr(l, '\n') + 1 : l + strlen(l))
				if (!strncmp(l, "  FAIL  ", 8)) {
					snprintf(why, sizeof(why), "%.*s", (int)strcspn(l + 8, "\n"), l + 8);
					break;
				}
			lv_label_set_text_fmt(jp.step, tr(RS_RS_REFUSED), why_text(why, wt, sizeof(wt)));
		} else if (last)
			lv_label_set_text_fmt(jp.step, "%.*s", (int)strcspn(last, "\n"), last);
		/* Return to Flashforge firmware went on without its printer.cfg
		 * edit (ad5x-return-stock's "config_failed: yes"): said here */
		if (text_has_line(t, "config_failed: yes")) {
			set_iconed(jp.step, LV_SYMBOL_WARNING, "  ", "%s", tr(RS_RS_CFG_FAILED));
			lv_obj_set_style_text_color(jp.step, C_WARN, 0);
		}
		/* step 9, Kiln's data: what went ("wipe_removed_kb:" with
		 * "wipe_prints:"), or that not all of it could go */
		char wk[32], wp[16], sz[32], wt[600], was[1200];
		if (ok && rt_line(t, "wipe_removed_kb", wk, sizeof(wk))) {
			human_size(strtoull(wk, NULL, 10) << 10, sz, sizeof(sz));
			bool pr = rt_line(t, "wipe_prints", wp, sizeof(wp)) && !strcmp(wp, "removed");
			snprintf(wt, sizeof(wt), tr(pr ? RS_RS_WIPED_PRINTS : RS_RS_WIPED), sz);
			snprintf(was, sizeof(was), "%s", lv_label_get_text(jp.step));
			lv_label_set_text_fmt(jp.step, "%s\n%s", was, wt);
		}
		if (text_has_line(t, "wipe_failed: yes")) {
			snprintf(was, sizeof(was), "%s", lv_label_get_text(jp.step));
			lv_label_set_text_fmt(jp.step, "%s\n%s  %s", was, LV_SYMBOL_WARNING,
					      tr(RS_RS_WIPE_FAILED));
			lv_obj_set_style_text_color(jp.step, C_WARN, 0);
		}
	}
	show(jp.spin, false);
	show(jp.cancel, false);
	show(jp.done, true);
	if (ok && (jb.after == AFTER_BOOT_MAIN || (jb.kind == JK_WEB))) {
		lv_label_set_text(lv_obj_get_child(jp.boot, 0), tr_sym(LV_SYMBOL_PLAY, RS_BOOT_MAIN_OS));
		jp.after = AFTER_BOOT_MAIN;
		show(jp.boot, true);
	} else if (ok && jb.after == AFTER_REBOOT) {
		lv_label_set_text(lv_obj_get_child(jp.boot, 0), tr_sym(LV_SYMBOL_REFRESH, RS_REBOOT));
		jp.after = AFTER_REBOOT;
		show(jp.boot, true);
	} else if (ok && jb.after == AFTER_POWEROFF) {
		lv_label_set_text(lv_obj_get_child(jp.boot, 0), tr_sym(LV_SYMBOL_POWER, RS_SHUT_DOWN));
		jp.after = AFTER_POWEROFF;
		show(jp.boot, true);
	}
	enable(back_btn, true);
	status_kick(true);
}

static void page_job(void)
{
	memset(&jp, 0, sizeof(jp));
	static char buf[JOB_VIEW_CAP];
	jp.buf = buf;
	buf[0] = 0;
	lv_obj_t *body = page_frame(jb.kind == JK_WEB ? tr(RS_UPDATE_FROM_BROWSER) : jb.title, true);

	jp.banner = card(body);
	lv_obj_set_size(jp.banner, lv_pct(100), LV_SIZE_CONTENT);
	lv_obj_set_flex_flow(jp.banner, LV_FLEX_FLOW_COLUMN);
	lv_obj_set_style_pad_row(jp.banner, 8, 0);
	lv_obj_set_style_border_width(jp.banner, 2, 0);
	lv_obj_t *r = box(jp.banner, LV_FLEX_FLOW_ROW);
	lv_obj_set_size(r, lv_pct(100), LV_SIZE_CONTENT);
	lv_obj_set_flex_align(r, LV_FLEX_ALIGN_START, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);
	lv_obj_set_style_pad_column(r, 12, 0);
	jp.spin = lv_spinner_create(r);
	lv_obj_set_size(jp.spin, 32, 32);
	lv_obj_set_style_arc_width(jp.spin, 4, LV_PART_MAIN);
	lv_obj_set_style_arc_width(jp.spin, 4, LV_PART_INDICATOR);
	lv_obj_set_style_arc_color(jp.spin, C_ACCENT, LV_PART_INDICATOR);
	jp.status = label(r, tr(RS_WORKING), F24B, C_TEXT);
	lv_obj_set_flex_grow(jp.status, 1);
	jp.elapsed = label(r, "0:00", F20, C_MUTED);
	jp.t0 = mono_s();
	jp.pct = label(r, "", F24B, C_TEXT);
	jp.step = label(jp.banner, "", F20, C_MUTED);
	lv_label_set_long_mode(jp.step, LV_LABEL_LONG_MODE_DOTS);
	lv_obj_set_width(jp.step, lv_pct(100));
	jp.bar = lv_bar_create(jp.banner);
	lv_obj_set_size(jp.bar, lv_pct(100), 22);
	lv_bar_set_range(jp.bar, 0, 100);
	lv_obj_set_style_bg_color(jp.bar, C_BORDER, LV_PART_MAIN);
	lv_obj_set_style_bg_color(jp.bar, C_ACCENT, LV_PART_INDICATOR);
	lv_obj_set_style_radius(jp.bar, 8, LV_PART_MAIN);
	lv_obj_set_style_radius(jp.bar, 8, LV_PART_INDICATOR);

	jp.log = card(body);
	lv_obj_set_width(jp.log, lv_pct(100));
	lv_obj_set_flex_grow(jp.log, 1);
	lv_obj_add_flag(jp.log, LV_OBJ_FLAG_SCROLLABLE);
	lv_obj_set_scroll_dir(jp.log, LV_DIR_VER);
	lv_obj_set_style_bg_color(jp.log, lv_color_hex(0x242933), 0);
	jp.logtext = wrap_label(jp.log, "", FMONO, C_MUTED);

	lv_obj_t *row = box(body, LV_FLEX_FLOW_ROW);
	lv_obj_set_size(row, lv_pct(100), LV_SIZE_CONTENT);
	lv_obj_set_style_pad_column(row, 12, 0);
	lv_obj_set_flex_align(row, LV_FLEX_ALIGN_END, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);
	jp.cancel = button(row, LV_SYMBOL_STOP, tr(RS_STOP), 2, on_cancel, NULL);
	lv_obj_set_width(jp.cancel, 200);
	jp.boot = button(row, LV_SYMBOL_PLAY, tr(RS_BOOT_MAIN_OS), 1, on_after, NULL);
	lv_obj_set_width(jp.boot, 260);
	jp.done = button(row, LV_SYMBOL_OK, tr(RS_DONE), 0, on_home, NULL);
	lv_obj_set_width(jp.done, 200);
	show(jp.cancel, false);
	show(jp.boot, false);
	show(jp.done, false);
	jb.last_seq = jb.last_swu = ~0u;
	cur_refresh = job_refresh;
}

/* -------------------------------------------------- automatic install */

/* ad5x-recovery-auto installing an update at start-up: the first start
 * after the install stick (the main OS from /data/ad5x/update), or an
 * update the main OS staged. It runs in the background, without the UI;
 * its state file (PATH_AUTO_INSTALL, lib/recovery.sh rc_install_state:
 * state= check|write|restart|failed, step=, steps=, file=, pid=) opens
 * this page over any other, so the screen says what is going on and not
 * to switch off. Step 2's percentage is SWUpdate's. A check or write
 * whose process is gone is dropped; a failure stays until Done. */
typedef struct {
	char state[16];
	unsigned step, steps;
	char file[128];
	long pid;
	ino_t ino;		/* the file is replaced (mv) at each change */
	time_t mtime;
} auto_inst;

static struct {
	ino_t ino;		/* a failure dismissed with Done */
	time_t mtime;
	bool set;
} au_dismissed;

static bool auto_read(auto_inst *a)
{
	memset(a, 0, sizeof(*a));
	const char *p = rui_get(PATH_AUTO_INSTALL);
	FILE *f = fopen(p, "r");
	if (!f)
		return false;
	struct stat st;
	if (!fstat(fileno(f), &st)) {
		a->ino = st.st_ino;
		a->mtime = st.st_mtime;
	}
	char line[256];
	while (fgets(line, sizeof(line), f)) {
		line[strcspn(line, "\n")] = 0;
		if (!strncmp(line, "state=", 6))
			snprintf(a->state, sizeof(a->state), "%s", line + 6);
		else if (!strncmp(line, "step=", 5))
			a->step = (unsigned)strtoul(line + 5, NULL, 10);
		else if (!strncmp(line, "steps=", 6))
			a->steps = (unsigned)strtoul(line + 6, NULL, 10);
		else if (!strncmp(line, "file=", 5))
			snprintf(a->file, sizeof(a->file), "%s", line + 5);
		else if (!strncmp(line, "pid=", 4))
			a->pid = strtol(line + 4, NULL, 10);
	}
	fclose(f);
	if (!a->steps)
		a->steps = 3;
	if (a->step < 1 || a->step > a->steps)
		a->step = 1;
	return a->state[0] != 0;
}

/* The page is wanted: an install running (its process alive), restarting,
 * or a failure not yet dismissed */
static bool auto_wanted(const auto_inst *a)
{
	if (!a->state[0])
		return false;
	if (!strcmp(a->state, "failed"))
		return !(au_dismissed.set && au_dismissed.ino == a->ino &&
			 au_dismissed.mtime == a->mtime);
	if (!strcmp(a->state, "restart"))
		return true;
	return a->pid > 0 && (kill((pid_t)a->pid, 0) == 0 || errno == EPERM);
}

static bool auto_active(auto_inst *a)
{
	return auto_read(a) && auto_wanted(a);
}

static struct {
	lv_obj_t *banner, *spin, *status, *pct, *bar, *file, *warn, *warn_title, *warn_text;
	lv_obj_t *done, *elapsed;
	auto_inst shown;
	bool ended;
	long t0;		/* when this install's page began */
} au;

static void on_auto_done(lv_event_t *e)
{
	(void)e;
	au_dismissed.ino = au.shown.ino;
	au_dismissed.mtime = au.shown.mtime;
	au_dismissed.set = true;
	slog("install result seen (Done)");
	go(page_home);
}

static void auto_refresh(void)
{
	auto_inst a;
	if (!auto_active(&a)) {
		if (!au.ended)
			go(page_home);
		return;
	}
	if (au.ended) {
		/* The failure stays until Done, unless ad5x-recovery-auto goes
		 * on with the next file (drop folder, an autoupdate stick): a
		 * new state file (rc_install_state renames a fresh one in), or
		 * no longer "failed", is that install: its page again, with
		 * "Don't switch off" while it writes */
		if (a.ino != au.shown.ino || a.mtime != au.shown.mtime ||
		    strcmp(a.state, "failed"))
			go(page_auto);
		return;
	}
	au.shown = a;
	swu_state ss;
	swu_get(&ss);
	bool failed = !strcmp(a.state, "failed");
	bool restart = !strcmp(a.state, "restart");
	bool write = !strcmp(a.state, "write");
	/* SWUpdate already writing while the state still says check: write */
	if (!failed && !restart && ss.active && ss.status != SWU_IDLE)
		write = true;
	enum rui_str what = restart ? RS_AUTO_STEP_RESTART : write ? RS_AUTO_STEP_WRITE
		: RS_AUTO_STEP_CHECK;
	unsigned step = restart ? 3 : write ? 2 : a.step;
	if (step > a.steps)
		step = a.steps;
	lv_label_set_text_fmt(au.file, "%s", a.file);

	if (failed) {
		au.ended = true;
		lv_obj_set_style_bg_color(au.banner, lv_color_hex(0x4B3D48), 0);
		lv_obj_set_style_border_color(au.banner, C_DANGER, 0);
		set_iconed(au.status, LV_SYMBOL_CLOSE, "  ", "%s", tr(RS_AUTO_FAILED));
		lv_obj_set_style_text_color(au.status, C_DANGER, 0);
		lv_label_set_text(au.pct, "");
		show(au.spin, false);
		show(au.bar, false);
		lv_obj_set_style_border_color(au.warn, C_BORDER, 0);
		lv_label_set_text(au.warn_title, "");
		show(au.warn_title, false);
		lv_label_set_text(au.warn_text, tr(RS_AUTO_FAILED_TEXT));
		show(au.done, true);
		slog("automatic install failed: %s", a.file);
		return;
	}

	char t[256];
	snprintf(t, sizeof(t), tr(RS_AUTO_STEP_FMT), step, a.steps, tr(what));
	lv_label_set_text(au.status, t);
	int pct = -1;
	if (restart)
		pct = 100;
	else if (write && ss.active && ss.overall >= 0)
		pct = ss.overall > 100 ? 100 : ss.overall;
	if (pct >= 0) {
		show(au.bar, true);
		lv_bar_set_value(au.bar, pct, LV_ANIM_OFF);
		lv_label_set_text_fmt(au.pct, "%d%%", pct);
	} else {
		show(au.bar, false);
		lv_label_set_text(au.pct, "");
	}
	show(au.spin, !restart);
	set_elapsed(au.elapsed, au.t0);
	lv_label_set_text(au.warn_text, tr(restart ? RS_AUTO_RESTART_TEXT : RS_AUTO_DONT_OFF_TEXT));
}

static void page_auto(void)
{
	memset(&au, 0, sizeof(au));
	lv_obj_t *body = page_frame(tr(RS_AUTO_TITLE), false);

	au.banner = card(body);
	lv_obj_set_size(au.banner, lv_pct(100), LV_SIZE_CONTENT);
	lv_obj_set_flex_flow(au.banner, LV_FLEX_FLOW_COLUMN);
	lv_obj_set_style_pad_row(au.banner, 10, 0);
	lv_obj_set_style_pad_all(au.banner, 16, 0);
	lv_obj_set_style_border_width(au.banner, 2, 0);
	lv_obj_set_style_border_color(au.banner, C_ACCENT, 0);
	lv_obj_t *r = box(au.banner, LV_FLEX_FLOW_ROW);
	lv_obj_set_size(r, lv_pct(100), LV_SIZE_CONTENT);
	lv_obj_set_flex_align(r, LV_FLEX_ALIGN_START, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);
	lv_obj_set_style_pad_column(r, 14, 0);
	au.spin = lv_spinner_create(r);
	lv_obj_set_size(au.spin, 36, 36);
	lv_obj_set_style_arc_width(au.spin, 4, LV_PART_MAIN);
	lv_obj_set_style_arc_width(au.spin, 4, LV_PART_INDICATOR);
	lv_obj_set_style_arc_color(au.spin, C_ACCENT, LV_PART_INDICATOR);
	au.status = label(r, "", F24B, C_TEXT);
	lv_obj_set_flex_grow(au.status, 1);
	lv_label_set_long_mode(au.status, LV_LABEL_LONG_MODE_WRAP);
	au.elapsed = label(r, "0:00", F20, C_MUTED);
	au.t0 = mono_s();
	au.pct = label(r, "", F24B, C_TEXT);
	au.bar = lv_bar_create(au.banner);
	lv_obj_set_size(au.bar, lv_pct(100), 22);
	lv_bar_set_range(au.bar, 0, 100);
	lv_obj_set_style_bg_color(au.bar, C_BORDER, LV_PART_MAIN);
	lv_obj_set_style_bg_color(au.bar, C_ACCENT, LV_PART_INDICATOR);
	lv_obj_set_style_radius(au.bar, 8, LV_PART_MAIN);
	lv_obj_set_style_radius(au.bar, 8, LV_PART_INDICATOR);
	show(au.bar, false);
	au.file = label(au.banner, "", F16, C_MUTED);
	lv_label_set_long_mode(au.file, LV_LABEL_LONG_MODE_DOTS);
	lv_obj_set_width(au.file, lv_pct(100));

	/* Don't switch off: large, in the warning colour */
	au.warn = card(body);
	lv_obj_set_width(au.warn, lv_pct(100));
	lv_obj_set_flex_grow(au.warn, 1);
	lv_obj_set_flex_flow(au.warn, LV_FLEX_FLOW_COLUMN);
	lv_obj_set_flex_align(au.warn, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);
	lv_obj_set_style_pad_row(au.warn, 12, 0);
	lv_obj_set_style_pad_all(au.warn, 18, 0);
	lv_obj_set_style_border_width(au.warn, 2, 0);
	lv_obj_set_style_border_color(au.warn, C_WARN, 0);
	char t[160];
	au.warn_title = label(au.warn, iconed(t, sizeof(t), LV_SYMBOL_WARNING, "  ", "%s",
					     tr(RS_AUTO_DONT_OFF)), F28B, C_WARN);
	au.warn_text = wrap_label(au.warn, tr(RS_AUTO_DONT_OFF_TEXT), F20, C_TEXT);
	lv_obj_set_style_text_align(au.warn_text, LV_TEXT_ALIGN_CENTER, 0);

	lv_obj_t *row = box(body, LV_FLEX_FLOW_ROW);
	lv_obj_set_size(row, lv_pct(100), LV_SIZE_CONTENT);
	lv_obj_set_flex_align(row, LV_FLEX_ALIGN_END, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);
	au.done = button(row, LV_SYMBOL_OK, tr(RS_DONE), 0, on_auto_done, NULL);
	lv_obj_set_width(au.done, 200);
	show(au.done, false);
	slog("automatic install: showing its progress");
	cur_refresh = auto_refresh;
}

/* ------------------------------------------------------------------ tick */

static void tick(lv_timer_t *t)
{
	(void)t;
	/* An update started elsewhere (browser upload on :8080): follow it */
	swu_state s;
	swu_get(&s);
	/* An install at start-up (ad5x-recovery-auto): its page, which
	 * follows SWUpdate itself, over any other (not over a job started
	 * here) */
	auto_inst ai;
	bool auto_on = auto_active(&ai);
	/* Installing or restarting: SWUpdate's events are its own. A failure
	 * not yet dismissed isn't: a browser upload then gets its page */
	bool auto_busy = auto_on && strcmp(ai.state, "failed");
	if (auto_on && cur_page != page_auto && !job_running() &&
	    (auto_busy || cur_page != page_job))
		go(page_auto);
	static unsigned seen;
	if (s.seq != seen) {
		seen = s.seq;
		if (s.active && !auto_busy && cur_page != page_job && !job_running()) {
			if (auto_on) {
				/* the upload replaces the failure: seen */
				au_dismissed.ino = ai.ino;
				au_dismissed.mtime = ai.mtime;
				au_dismissed.set = true;
				slog("install result put aside for a browser upload");
			}
			memset(&jb, 0, sizeof(jb));
			jb.kind = JK_WEB;
			snprintf(jb.title, sizeof(jb.title), "%s", tr(RS_UPDATE));
			jb.swu_seq_at_start = s.seq - 1;
			jb.swu_result_at_start = s.result_seq;
			go(page_job);
		}
	}
	status_poll();
	if (cur_refresh)
		cur_refresh();
}

void ui_init(lv_display_t *disp)
{
	i18n_set_lang(lang_from_settings_file(rui_get(PATH_SETTINGS)));
	fonts_init();
	lv_theme_t *th = lv_theme_default_init(disp, C_ACCENT_FILL, C_DANGER_FILL, true, F20);
	lv_display_set_theme(disp, th);
	/* The first status run is a whole one (--slots): the power page's boot
	 * loader entry and what slot B holds come from it, and without it they
	 * stayed unknown until a job had run */
	status_kick(true);
	go(page_home);
	lv_timer_create(tick, 250, NULL);
	slog("ad5x-recovery-ui started");
}

/* ---------------------------------------------------------- screenshots */

static void settle(int ms)
{
	for (int t = 0; t < ms; t += 20) {
		lv_timer_handler();
		usleep(20000);
	}
}

static void wait_job(void)
{
	for (int i = 0; i < 500 && (job_running() || jb.pending); i++)
		settle(20);
	settle(300);
}

static void click(lv_obj_t *o)
{
	lv_obj_send_event(o, LV_EVENT_CLICKED, NULL);
	settle(100);
}

/* Write ad5x-recovery-auto's state file as rc_install_state does */
static void auto_put(const char *state, unsigned step, long pid)
{
	const char *p = rui_get(PATH_AUTO_INSTALL);
	char tmp[600];
	snprintf(tmp, sizeof(tmp), "%s.new", p);
	FILE *f = fopen(tmp, "w");
	if (!f)
		return;
	fprintf(f, "state=%s\nstep=%u\nsteps=3\nfile=ad5x-main-v1.0.0.zip\npid=%ld\n",
		state, step, pid);
	fclose(f);
	rename(tmp, p);
}

/* A file next to PATH_AUTO_INSTALL ($S/run/ad5x in the simulation), for
 * its stand-ins; NULL text removes it */
static void sim_file(const char *name, const char *text)
{
	char f[600];
	snprintf(f, sizeof(f), "%s", rui_get(PATH_AUTO_INSTALL));
	char *sl = strrchr(f, '/');
	if (!sl)
		return;
	*sl = 0;
	mkdir(f, 0755);
	snprintf(sl, sizeof(f) - (size_t)(sl - f), "/%s", name);
	if (!text) {
		unlink(f);
		return;
	}
	FILE *o = fopen(f, "w");
	if (o) {
		fputs(text, o);
		fclose(o);
	}
}

/* One whole ad5x-status run from now on (--slots with slots) */
static void status_wait(bool slots)
{
	for (int i = 0; i < 300 && stc.cap; i++)
		settle(20);
	unsigned s0 = stc.seq;
	status_kick(slots);
	for (int i = 0; i < 300 && (stc.seq == s0 || stc.cap); i++)
		settle(20);
}

/* The entry's text on the power page ("" when there is none) */
static const char *power_bl_entry(void)
{
	lv_obj_t *body = lv_obj_get_child(scr, -1);
	lv_obj_t *c = body ? lv_obj_get_child(body, 0) : NULL;
	for (uint32_t i = 0; c && i < lv_obj_get_child_count(c); i++) {
		lv_obj_t *b = lv_obj_get_child(c, (int32_t)i);
		if (lv_obj_check_type(b, &lv_button_class) && lv_obj_get_child_count(b))
			return lv_label_get_text(lv_obj_get_child(b, 0));
	}
	return "";
}

/* The power page's line holds this text (a translated format and its
 * build dates) */
static bool power_line_is(enum rui_str id, const char *d1, const char *d2)
{
	char want[300];
	snprintf(want, sizeof(want), tr(id), d1 ? d1 : "", d2 ? d2 : "");
	return pw.bl && cur_page == page_power && strstr(lv_label_get_text(pw.bl), want) != NULL;
}

/* The boot loader page shows a refusal ("Not possible now: ...", or the
 * busy start-up actions) in its headline or under it */
static bool bl_refused_shown(void)
{
	char pre[96];
	snprintf(pre, sizeof(pre), "%s", tr(RS_RS_REFUSED));
	pre[strcspn(pre, "%")] = 0;
	const char *h = lv_label_get_text(bl.status), *n = lv_label_get_text(bl.note);
	bool note = !lv_obj_has_flag(bl.note, LV_OBJ_FLAG_HIDDEN);
	return strstr(h, pre) || strstr(h, "start-up-actions") ||
	       (note && (strstr(n, pre) || strstr(n, "start-up-actions")));
}

/* sim-bl-calls (the simulated ad5x-bootloader-install's runs): how many,
 * and how many while the start-up actions ran */
static void bl_sim_calls(int *all, int *during_auto)
{
	char f[600];
	snprintf(f, sizeof(f), "%s", rui_get(PATH_AUTO_INSTALL));
	char *sl = strrchr(f, '/');
	*all = *during_auto = 0;
	if (!sl)
		return;
	snprintf(sl, sizeof(f) - (size_t)(sl - f), "/sim-bl-calls");
	FILE *i = fopen(f, "r");
	char l[256];
	while (i && fgets(l, sizeof(l), i)) {
		(*all)++;
		if (!strncmp(l, "auto=running", 12))
			(*during_auto)++;
	}
	if (i)
		fclose(i);
}

/* The first start after an install (the owner's printer, rc6): Kiln's
 * U-Boot started this recovery, --verify-start recorded it (verified) and
 * asked for the page (bootloader_open=result), and the start-up actions
 * are still running (no auto.done). The page opens by itself with the
 * result, runs no check meanwhile (it would say "busy: start-up-actions"),
 * then once they are done says it is up to date, Install hidden; never a
 * refusal. Then the same with unverified (the start not through Kiln's
 * U-Boot): the outcome with what to do */
static int bl_result_shots(void (*shot)(const char *name))
{
	int fails = 0, n, na;
#define BL_CHECK(cond, what) do { \
		if (cond) { slog("shots: ok   %s", what); } \
		else { slog("shots: FAIL %s", what); fails++; } } while (0)
	sim_file("sim-bl-slots", "bootloader=kiln\nbootloader_upgrade=no\nbootloader_offer=no\n");
	sim_file("sim-bl-state", "verified");
	sim_file("sim-bl-kind", "install");
	sim_file("sim-bl-open", "result");
	sim_file("sim-auto", "running");
	sim_file("sim-bl-calls", NULL);
	go(page_home);
	bl_shown = false;
	status_wait(true);
	for (int i = 0; i < 200 && cur_page != page_bootloader; i++)
		settle(20);
	settle(1500);
	bl_sim_calls(&n, &na);
	BL_CHECK(cur_page == page_bootloader && bl.result && !bl.up,
		 "result at start, start-up actions running: the boot loader page opens by itself");
	BL_CHECK(strstr(lv_label_get_text(bl.status), tr(RS_BL_VERIFIED)) != NULL,
		 "result at start: the headline is the outcome (installed, this start through it)");
	BL_CHECK(!bl_refused_shown(), "result at start, start-up actions running: no refusal, no busy line");
	BL_CHECK(bl.waiting && !bl.cap && n == 0 &&
		 strstr(lv_label_get_text(bl.note), tr(RS_BL_WAIT_AUTO)) != NULL,
		 "result at start, start-up actions running: no check run, the page waits for them");
	BL_CHECK(lv_obj_has_flag(bl.go, LV_OBJ_FLAG_HIDDEN), "result at start: no Install button");
	shot("21l-bl-result-waiting");
	/* auto.done: the check runs (polled), and finds this build there */
	sim_file("sim-auto", NULL);
	status_wait(false);
	for (int i = 0; i < 200 && (bl.waiting || bl.cap || !bl.checked); i++)
		settle(20);
	settle(300);
	bl_sim_calls(&n, &na);
	BL_CHECK(n == 1 && na == 0 && bl.checked && !bl.waiting,
		 "after auto.done: the check runs once, never while the start-up actions ran");
	BL_CHECK(bl.already && strstr(lv_label_get_text(bl.status), tr(RS_BL_VERIFIED)) &&
		 strstr(lv_label_get_text(bl.note), tr(RS_BL_UP_TO_DATE)),
		 "after auto.done: still the outcome first, then installed and up to date");
	BL_CHECK(!bl_refused_shown() && lv_obj_has_flag(bl.go, LV_OBJ_FLAG_HIDDEN),
		 "after auto.done: no refusal, Install hidden");
	shot("21m-bl-result-up-to-date");
	/* unverified: installed, this start not through Kiln's U-Boot */
	sim_file("sim-bl-state", "unverified");
	status_wait(false);
	go(page_bootloader);
	for (int i = 0; i < 200 && (bl.cap || !bl.checked); i++)
		settle(20);
	settle(300);
	BL_CHECK(bl.result && strstr(lv_label_get_text(bl.status), tr(RS_BL_UNVERIFIED)) &&
		 strstr(lv_label_get_text(bl.note), tr(RS_BL_UP_TO_DATE)) &&
		 lv_obj_has_flag(bl.go, LV_OBJ_FLAG_HIDDEN) && !bl_refused_shown(),
		 "unverified: the outcome with what to do, up to date, no refusal, no Install");
	shot("21n-bl-result-unverified");
	sim_file("sim-bl-slots", NULL);
	sim_file("sim-bl-state", NULL);
	sim_file("sim-bl-kind", NULL);
	sim_file("sim-bl-open", NULL);
	sim_file("sim-bl-calls", NULL);
	status_wait(true);
#undef BL_CHECK
	return fails;
}

/* "Update Kiln's boot loader": Kiln's boot loader of an older build on
 * the printer (bootloader_upgrade=yes): the entry, the page with both
 * builds, the two confirmations, the job, and the page at the first start
 * after it (the record's kind=upgrade, verified) */
static int bl_update_shots(void (*shot)(const char *name))
{
	int fails = 0;
#define BL_CHECK(cond, what) do { \
		if (cond) { slog("shots: ok   %s", what); } \
		else { slog("shots: FAIL %s", what); fails++; } } while (0)
	/* an earlier install's record, verified: not the page's result now */
	sim_file("sim-bl-slots", "bootloader=kiln\nbootloader_build=Nov 15 2026 - 19:48:50 +0000\n"
		 "bootloader_carries=Nov 19 2026 - 10:02:11 +0000\nbootloader_same=no\n"
		 "bootloader_carries_newer=yes\n"
		 "bootloader_upgrade=yes\nbootloader_offer=no\n");
	sim_file("sim-bl-state", "verified");
	sim_file("sim-bl-kind", "install");
	status_wait(true);
	go(page_power);
	settle(200);
	BL_CHECK(strstr(power_bl_entry(), tr(RS_BL_UP_ENTRY)) != NULL,
		 "bootloader_upgrade=yes: Update Kiln's boot loader on the power page");
	BL_CHECK(power_line_is(RS_BL_LINE_UPDATE, "Nov 15 2026 - 19:48:50", NULL),
		 "bootloader_upgrade=yes: the line says installed, its build, an update");
	shot("21f-power-bl-update");
	go(page_bootloader_upgrade);
	for (int i = 0; i < 100 && bl.cap; i++)
		settle(20);
	settle(200);
	BL_CHECK(bl.up && !bl.result && strstr(lv_label_get_text(bl.status), tr(RS_BL_UP_READY)) &&
		 !lv_obj_has_flag(bl.go, LV_OBJ_FLAG_HIDDEN),
		 "an update offered over an earlier install's verified record: the update's page, not that result");
	BL_CHECK(bl.up && bl.ready && !bl.resume && !strcmp(bl.from, "Nov 15 2026 - 19:48:50 +0000") &&
		 !strcmp(bl.to, "Nov 19 2026 - 10:02:11 +0000") &&
		 !lv_obj_has_flag(bl.builds, LV_OBJ_FLAG_HIDDEN),
		 "the update page: ready, both builds shown");
	shot("21g-bl-update");
	on_bl_go(NULL);
	settle(100);
	shot("21h-bl-update-confirm1");
	click(dlg.ok_btn);
	settle(2400);
	shot("21i-bl-update-confirm2");
	dlg_close();
	{
		char *c = cmd_expand(BL_S(CMD_BOOTLOADER_INSTALL, CMD_BOOTLOADER_UPGRADE), NULL);
		BL_CHECK(!strcmp(c, "ad5x-bootloader-install --yes --upgrade"),
			 "the update runs ad5x-bootloader-install --yes --upgrade");
		free(c);
	}
	bl_install_now();
	wait_job();
	shot("21j-bl-update-done");
	/* the first start after it: --verify-start recorded it */
	sim_file("sim-bl-slots", "bootloader=kiln\nbootloader_build=Nov 19 2026 - 10:02:11 +0000\n"
		 "bootloader_carries=Nov 19 2026 - 10:02:11 +0000\nbootloader_same=yes\n"
		 "bootloader_upgrade=no\nbootloader_offer=no\n");
	sim_file("sim-bl-state", "verified");
	sim_file("sim-bl-kind", "upgrade");
	status_wait(true);
	BL_CHECK(bl_record_upgrade(), "the record: an update, verified");
	go(page_power);
	settle(200);
	BL_CHECK(!power_bl_entry()[0], "after the update: no boot loader entry on the power page");
	BL_CHECK(power_line_is(RS_BL_LINE_CURRENT, "Nov 19 2026 - 10:02:11", NULL),
		 "after the update: the line says installed, the new build, up to date");
	go(bl_record_upgrade() ? page_bootloader_upgrade : page_bootloader);
	for (int i = 0; i < 100 && bl.cap; i++)
		settle(20);
	settle(200);
	BL_CHECK(bl.up && bl.done_already && lv_obj_has_flag(bl.builds, LV_OBJ_FLAG_HIDDEN),
		 "the update page after the restart: done, verified");
	BL_CHECK(bl.result && bl.already && strstr(lv_label_get_text(bl.status), tr(RS_BL_UP_VERIFIED)) &&
		 strstr(lv_label_get_text(bl.note), tr(RS_BL_UP_TO_DATE)) &&
		 lv_obj_has_flag(bl.go, LV_OBJ_FLAG_HIDDEN) && !bl_refused_shown(),
		 "the update page after the restart: updated and verified first, up to date, no Update");
	shot("21k-bl-update-verified");
	sim_file("sim-bl-slots", NULL);
	sim_file("sim-bl-state", NULL);
	sim_file("sim-bl-kind", NULL);
	status_wait(true);
#undef BL_CHECK
	return fails;
}

/* The power page's boot loader line (issue #97), always there: Kiln's
 * installed and up to date (the reporter's printer: the record of an
 * update, verified), another build here that isn't offered, Kiln's SPL
 * alone; "reading" at start and while the start-up actions run, read
 * again once they are done and only then "couldn't be read"; the line
 * and the entry follow a new read while the page is open */
static int bl_line_shots(void (*shot)(const char *name))
{
	int fails = 0;
#define BL_CHECK(cond, what) do { \
		if (cond) { slog("shots: ok   %s", what); } \
		else { slog("shots: FAIL %s", what); fails++; } } while (0)
	const char *now = "Nov 19 2026 - 08:31:00", *old = "Nov 15 2026 - 19:48:50";
	sim_file("sim-bl-slots", "bootloader=kiln\nbootloader_build=Nov 19 2026 - 08:31:00 +0000\n"
		 "bootloader_carries=Nov 19 2026 - 08:31:00 +0000\nbootloader_same=yes\n"
		 "bootloader_upgrade=no\nbootloader_offer=no\n");
	sim_file("sim-bl-state", "verified");
	sim_file("sim-bl-kind", "upgrade");
	status_wait(true);
	go(page_power);
	settle(200);
	BL_CHECK(!power_bl_entry()[0] && power_line_is(RS_BL_LINE_CURRENT, now, NULL),
		 "this build there: no entry, the line says installed, its build, up to date");
	shot("20b-power-bl-up-to-date");

	sim_file("sim-bl-slots", "bootloader=kiln\nbootloader_build=Nov 15 2026 - 19:48:50 +0000\n"
		 "bootloader_carries=Nov 19 2026 - 08:31:00 +0000\nbootloader_same=no\n"
		 "bootloader_carries_newer=yes\n"
		 "bootloader_upgrade=no\nbootloader_offer=no\n");
	sim_file("sim-bl-kind", "install");
	status_wait(true);
	settle(200);
	BL_CHECK(!power_bl_entry()[0] && power_line_is(RS_BL_LINE_OTHER, old, now),
		 "another build, no update offered: no entry, the line names both builds (a new read, the page open)");
	shot("20c-power-bl-other-build");

	/* an older build in this recovery (an older Kiln release went on):
	 * the line says so, no Update entry (never a downgrade from here) */
	sim_file("sim-bl-slots", "bootloader=kiln\nbootloader_build=Nov 19 2026 - 08:31:00 +0000\n"
		 "bootloader_carries=Nov 15 2026 - 19:48:50 +0000\nbootloader_same=no\n"
		 "bootloader_carries_newer=no\n"
		 "bootloader_upgrade=no\nbootloader_offer=no\n");
	status_wait(true);
	settle(200);
	BL_CHECK(!power_bl_entry()[0] && power_line_is(RS_BL_LINE_OLDER, now, old),
		 "an older build carried: no entry, the line says installed, its build, the older one here");
	shot("20g-power-bl-older-build");

	sim_file("sim-bl-slots", "bootloader=kiln-spl\nbootloader_upgrade=no\nbootloader_offer=no\n");
	sim_file("sim-bl-state", NULL);
	sim_file("sim-bl-kind", NULL);
	status_wait(true);
	settle(200);
	BL_CHECK(!power_bl_entry()[0] && power_line_is(RS_BL_LINE_SPL, NULL, NULL),
		 "Kiln's SPL alone: the line says so");
	shot("20d-power-bl-spl-only");

	/* the start: nothing read yet, the start-up actions running, and the
	 * tool can't tell (bootloader=unknown) */
	sim_file("sim-bl-slots", "bootloader=unknown\nbootloader_upgrade=no\nbootloader_offer=no\n");
	sim_file("sim-auto", "running");
	status_wait(false);
	stc.slots[0] = 0;
	stc.slots_read = stc.slots_auto = false;
	go(page_power);
	settle(200);
	BL_CHECK(power_line_is(RS_BL_LINE_READING, NULL, NULL),
		 "at start, before the first --slots run: reading, not unknown");
	shot("20e-power-bl-reading");
	status_wait(true);
	settle(200);
	BL_CHECK(stc.slots_read && stc.slots_auto && power_line_is(RS_BL_LINE_READING, NULL, NULL),
		 "read during the start-up actions, unknown: still reading");
	sim_file("sim-auto", NULL);
	status_wait(false);
	for (int i = 0; i < 300 && (stc.slots_auto || stc.want_slots || stc.cap); i++)
		settle(20);
	settle(200);
	BL_CHECK(!stc.slots_auto && power_line_is(RS_BL_LINE_UNKNOWN, NULL, NULL),
		 "the start-up actions done: read again by itself, then couldn't be read");
	shot("20f-power-bl-unknown");

	/* a read that finds Flashforge's with the install offered: the page
	 * again, with its entry */
	sim_file("sim-bl-slots", NULL);
	status_wait(true);
	settle(300);
	BL_CHECK(strstr(power_bl_entry(), tr(RS_BL_ENTRY)) && power_line_is(RS_BL_LINE_FLASHFORGE, NULL, NULL),
		 "Flashforge's, install offered, read with the page open: the entry appears, the line says Flashforge's");
	sim_file("sim-bl-calls", NULL);
#undef BL_CHECK
	return fails;
}

static int auto_shots(void (*shot)(const char *name))
{
	int fails = 0;
	const char *p = rui_get(PATH_AUTO_INSTALL);
	char dir[600];
	snprintf(dir, sizeof(dir), "%s", p);
	char *sl = strrchr(dir, '/');
	if (sl) {
		*sl = 0;
		mkdir(dir, 0755);
	}
#define AUTO_CHECK(cond, what) do { \
		if (cond) { slog("shots: ok   %s", what); } \
		else { slog("shots: FAIL %s", what); fails++; } } while (0)
	go(page_home);
	settle(200);
	auto_put("check", 1, (long)getpid());
	settle(400);
	AUTO_CHECK(cur_page == page_auto, "an install at start-up opens its page");
	shot("25-auto-check");
	swu_inject(SWU_START, SWU_SRC_LOCAL, 0, 0, 0, "", NULL);
	swu_inject(SWU_RUN, SWU_SRC_LOCAL, 2, 1, 40, "rootfs.squashfs", NULL);
	auto_put("write", 2, (long)getpid());
	settle(400);
	AUTO_CHECK(cur_page == page_auto, "SWUpdate's progress stays on the install page");
	shot("26-auto-write");
	swu_inject(SWU_SUCCESS, SWU_SRC_LOCAL, 2, 2, 100, "rootfs.squashfs", NULL);
	swu_inject(SWU_IDLE, SWU_SRC_LOCAL, 0, 0, 0, "", NULL);
	auto_put("restart", 3, (long)getpid());
	settle(400);
	shot("27-auto-restart");
	auto_put("check", 1, 999999999L);
	settle(400);
	AUTO_CHECK(cur_page == page_home, "an install whose process is gone: back home");
	auto_put("failed", 1, 999999999L);
	settle(400);
	AUTO_CHECK(cur_page == page_auto, "a failed install opens the page");
	shot("28-auto-failed");
	click(au.done);
	settle(300);
	AUTO_CHECK(cur_page == page_home, "Done: home, and it stays there");

	/* A failure, then ad5x-recovery-auto goes on with the next file (the
	 * drop folder's next one, an autoupdate stick): its progress and
	 * "Don't switch off" replace the failure */
	auto_put("failed", 1, (long)getpid());
	settle(400);
	AUTO_CHECK(cur_page == page_auto && au.ended, "a failure, before the next file");
	auto_put("check", 1, (long)getpid());
	settle(600);
	AUTO_CHECK(cur_page == page_auto && !au.ended &&
		   !lv_obj_has_flag(au.warn_title, LV_OBJ_FLAG_HIDDEN) &&
		   lv_obj_has_flag(au.done, LV_OBJ_FLAG_HIDDEN),
		   "the next file after a failure: its progress, Don't switch off");
	shot("28b-auto-next-check");
	swu_inject(SWU_START, SWU_SRC_LOCAL, 0, 0, 0, "", NULL);
	swu_inject(SWU_RUN, SWU_SRC_LOCAL, 2, 1, 60, "rootfs.squashfs", NULL);
	auto_put("write", 2, (long)getpid());
	settle(400);
	AUTO_CHECK(cur_page == page_auto && !au.ended, "the next file writing: its page");
	shot("28c-auto-next-write");
	swu_inject(SWU_FAILURE, SWU_SRC_LOCAL, 2, 1, 60, "rootfs.squashfs", NULL);
	swu_inject(SWU_IDLE, SWU_SRC_LOCAL, 0, 0, 0, "", NULL);
	auto_put("failed", 2, 999999999L);
	settle(400);
	AUTO_CHECK(cur_page == page_auto && au.ended &&
		   !lv_obj_has_flag(au.done, LV_OBJ_FLAG_HIDDEN),
		   "the next file failing too: the failure again, with Done");

	/* A browser upload while a failure is not dismissed: the upload's
	 * page, and it stays (the failure counts as seen) */
	swu_inject(SWU_START, SWU_SRC_WEBSERVER, 0, 0, 0, "", NULL);
	swu_inject(SWU_DOWNLOAD, SWU_SRC_WEBSERVER, 0, 0, 0, "", NULL);
	settle(400);
	AUTO_CHECK(cur_page == page_job && jb.kind == JK_WEB,
		   "a browser upload over an undismissed failure: its page");
	swu_inject(SWU_RUN, SWU_SRC_WEBSERVER, 3, 1, 50, "kernel.uimage", NULL);
	settle(600);
	AUTO_CHECK(cur_page == page_job, "the browser upload's page stays");
	swu_inject(SWU_SUCCESS, SWU_SRC_WEBSERVER, 3, 3, 100, "rootfs.squashfs", NULL);
	swu_inject(SWU_IDLE, SWU_SRC_WEBSERVER, 0, 0, 0, "", NULL);
	settle(400);
	go(page_home);
	settle(400);
	AUTO_CHECK(cur_page == page_home, "after the upload: home, the failure not back");
	unlink(p);
#undef AUTO_CHECK
	return fails;
}

int ui_run_shots(void (*shot)(const char *name))
{
	int fails = 0;
	settle(300);
	shot("01-home");

	/* Before any job: the start's own status run read the slots, so the
	 * power page offers Kiln's boot loader (the simulation's default:
	 * bootloader_offer=yes, Kiln OS in slot B) */
	for (int i = 0; i < 300 && !strstr(stc.slots, "bootloader_offer="); i++)
		settle(20);
	go(page_power);
	settle(200);
	if (strstr(power_bl_entry(), tr(RS_BL_ENTRY))) {
		slog("shots: ok   at start, before any job: Install Kiln's boot loader on the power page");
	} else {
		slog("shots: FAIL at start, before any job: Install Kiln's boot loader on the power page");
		fails++;
	}
	if (power_line_is(RS_BL_LINE_FLASHFORGE, NULL, NULL)) {
		slog("shots: ok   at start: the boot loader line says Flashforge's");
	} else {
		slog("shots: FAIL at start: the boot loader line says Flashforge's");
		fails++;
	}
	go(page_home);
	settle(200);

	go(page_update);
	settle(200);
	if (up.n > 0) {
		up.sel = 0;
		select_row(up.list, 0);
		up_buttons();
	}
	settle(400);
	shot("02-install-pick");
	click(up.install);
	shot("03-install-confirm1");
	click(dlg.ok_btn);
	shot("04-install-confirm2");
	settle(2400);
	shot("05-install-confirm2-armed");
	dlg_close();

	/* Install as it looks mid-way (SWUpdate progress injected) */
	start_job_x(JK_INSTALL, tr(RS_INSTALLING_UPDATE), "/data/ad5x/update/kiln-os.swu",
		    "echo 'swu-apply: /data/ad5x/update/kiln-os.swu via the daemon'; sleep 30",
		    false, false, true, AFTER_BOOT_MAIN);
	swu_inject(SWU_START, SWU_SRC_LOCAL, 0, 0, 0, "", NULL);
	swu_inject(SWU_RUN, SWU_SRC_LOCAL, 3, 2, 40, "rootfs.squashfs", "Writing rootfs2");
	settle(400);
	shot("06-install-progress");
	job_cancel();
	wait_job();
	swu_inject(SWU_SUCCESS, SWU_SRC_LOCAL, 3, 3, 100, "kernel.uimage", NULL);
	swu_inject(SWU_IDLE, SWU_SRC_LOCAL, 0, 0, 0, "", NULL);

	start_job_x(JK_INSTALL, tr(RS_INSTALLING_UPDATE), "/data/ad5x/update/kiln-os.swu",
		    "echo 'swu-apply: /data/ad5x/update/kiln-os.swu via the daemon'; "
		    "echo 'swu-apply: OK'", false, false, true, AFTER_BOOT_MAIN);
	swu_inject(SWU_START, SWU_SRC_LOCAL, 0, 0, 0, "", NULL);
	swu_inject(SWU_SUCCESS, SWU_SRC_LOCAL, 3, 3, 100, "kernel.uimage", NULL);
	wait_job();
	shot("07-install-done");

	go(page_backup);
	settle(300);
	shot("08-backup");
	bk_run(false);
	settle(1500);
	shot("09-backup-running");
	wait_job();
	shot("10-backup-done");

	go(page_restore);
	settle(300);
	if (rs.n > 0) {
		rs.sel = 0;
		select_row(rs.list, 0);
		rs_fill_parts();
		/* tick kernel2 + rootfs2 (the simulated restore fails on rootfs2) */
		uint32_t n = lv_obj_get_child_count(rs.parts);
		for (uint32_t i = 0; i < n; i++) {
			lv_obj_t *c = lv_obj_get_child(rs.parts, i);
			if (lv_obj_check_type(c, &lv_checkbox_class) &&
			    strstr(lv_checkbox_get_text(c), "2")) {
				lv_obj_add_state(c, LV_STATE_CHECKED);
				lv_obj_send_event(c, LV_EVENT_VALUE_CHANGED, NULL);
			}
		}
	}
	settle(400);
	shot("11-restore-pick");
	click(rs.go);
	shot("12-restore-confirm1");
	click(dlg.ok_btn);
	settle(2400);
	shot("13-restore-confirm2");
	dlg_close();
	rs_run(false);
	wait_job();
	shot("14-restore-failed");

	go(page_return);
	for (int i = 0; i < 100 && rt.cap; i++)
		settle(20);
	settle(200);
	shot("15-return");
	on_rt_go(NULL);
	settle(100);
	shot("16-return-confirm1");
	click(dlg.ok_btn);
	settle(2400);
	shot("16b-return-confirm2");
	dlg_close();
	return_now();
	settle(1500);
	shot("16c-return-running");
	wait_job();
	shot("16d-return-done");

	/* Flashforge's boot loader: the box ticked by default when this
	 * printer's boot.img is found (15 above); unticked it keeps Kiln's
	 * SPL; no boot.img: no box, the plain note; an unfinished return goes
	 * on with its own choice (no box) */
	go(page_return);
	for (int i = 0; i < 100 && rt.cap; i++)
		settle(20);
	settle(200);
	if (!lv_obj_has_flag(rt.spl, LV_OBJ_FLAG_HIDDEN) && lv_obj_has_state(rt.spl, LV_STATE_CHECKED) &&
	    !strcmp(rt.target_kind, "flashforge-spl") && lv_obj_has_flag(rt.spl_note, LV_OBJ_FLAG_HIDDEN) &&
	    !strcmp(rt_spl_flag(), "--flashforge-spl")) {
		slog("shots: ok   boot.img found: Flashforge's boot loader box shown and ticked, it goes back");
	} else {
		slog("shots: FAIL boot.img found: the boot loader box is not shown ticked (target %s)", rt.target_kind);
		fails++;
	}
	lv_obj_remove_state(rt.spl, LV_STATE_CHECKED);
	lv_obj_send_event(rt.spl, LV_EVENT_VALUE_CHANGED, NULL);
	for (int i = 0; i < 100 && rt.cap; i++)
		settle(20);
	settle(200);
	if (!lv_obj_has_flag(rt.spl, LV_OBJ_FLAG_HIDDEN) && !lv_obj_has_state(rt.spl, LV_STATE_CHECKED) &&
	    !strcmp(rt.target_kind, "kiln-spl") && !strcmp(rt_spl_flag(), "--keep-kiln-spl") && rt.ready) {
		slog("shots: ok   boot loader box unticked: Kiln's SPL stays (--keep-kiln-spl)");
	} else {
		slog("shots: FAIL boot loader box unticked: target %s, flag %s", rt.target_kind, rt_spl_flag());
		fails++;
	}
	shot("15b-return-keep-kiln-spl");
	sim_file("sim-no-bootimg", "");
	go(page_return);
	for (int i = 0; i < 100 && rt.cap; i++)
		settle(20);
	settle(200);
	if (lv_obj_has_flag(rt.spl, LV_OBJ_FLAG_HIDDEN) && !lv_obj_has_flag(rt.spl_note, LV_OBJ_FLAG_HIDDEN) &&
	    !strcmp(rt.target_kind, "kiln-spl") && !rt_spl_flag()[0] && rt.ready) {
		slog("shots: ok   no boot.img: no box, the note says Flashforge's boot loader can't go back");
	} else {
		slog("shots: FAIL no boot.img: box or note wrong (target %s)", rt.target_kind);
		fails++;
	}
	shot("15c-return-no-bootimg");
	sim_file("sim-no-bootimg", NULL);
	sim_file("sim-rs-resume", "kiln");
	go(page_return);
	for (int i = 0; i < 100 && rt.cap; i++)
		settle(20);
	settle(200);
	if (lv_obj_has_flag(rt.spl, LV_OBJ_FLAG_HIDDEN) && lv_obj_has_flag(rt.spl_note, LV_OBJ_FLAG_HIDDEN) &&
	    !strcmp(rt.target_kind, "kiln-spl") && rt.resume && !rt_spl_flag()[0]) {
		slog("shots: ok   unfinished return that kept Kiln's SPL: no box, goes on that way");
	} else {
		slog("shots: FAIL unfinished return that kept Kiln's SPL: box, note or target wrong (target %s)", rt.target_kind);
		fails++;
	}
	shot("15d-return-resume-kept");
	sim_file("sim-rs-resume", NULL);

	/* stock's printer.cfg couldn't be changed: the return went on (the
	 * sim's ad5x-return-stock says so when sim-cfg-failed is there) */
	{
		char cf[600];
		snprintf(cf, sizeof(cf), "%s", rui_get(PATH_AUTO_INSTALL));
		char *sl = strrchr(cf, '/');
		if (sl) {
			snprintf(sl + 1, sizeof(cf) - (size_t)(sl + 1 - cf), "sim-cfg-failed");
			*sl = 0;
			mkdir(cf, 0755);
			*sl = '/';
		}
		FILE *f = fopen(cf, "w");
		if (f)
			fclose(f);
		go(page_return);
		for (int i = 0; i < 100 && rt.cap; i++)
			settle(20);
		settle(200);
		if (rt.cfg_failed && !lv_obj_has_flag(rt.cfg, LV_OBJ_FLAG_HIDDEN)) {
			slog("shots: ok   printer.cfg not changed: the return page says so");
		} else {
			slog("shots: FAIL printer.cfg not changed: not on the return page");
			fails++;
		}
		shot("16e-return-cfg-failed");
		return_now();
		wait_job();
		shot("16f-return-done-cfg-failed");
		unlink(cf);
	}

	/* Kiln's data: the two boxes (the print files box usable only with
	 * the first), the confirmation with the sizes on both steps, and what
	 * went on the result */
	go(page_return);
	for (int i = 0; i < 100 && rt.cap; i++)
		settle(20);
	settle(200);
	if (!lv_obj_has_flag(rt.wipe, LV_OBJ_FLAG_HIDDEN) && !lv_obj_has_flag(rt.prints, LV_OBJ_FLAG_HIDDEN) &&
	    lv_obj_has_state(rt.prints, LV_STATE_DISABLED) && !rt_wipe()) {
		slog("shots: ok   Kiln's data: both boxes shown, off, the print files box disabled");
	} else {
		slog("shots: FAIL Kiln's data: the boxes are not as they should be at the start");
		fails++;
	}
	lv_obj_add_state(rt.wipe, LV_STATE_CHECKED);
	lv_obj_send_event(rt.wipe, LV_EVENT_VALUE_CHANGED, NULL);
	for (int i = 0; i < 100 && rt.cap; i++)
		settle(20);
	settle(200);
	if (!lv_obj_has_state(rt.prints, LV_STATE_DISABLED) && rt.ready &&
	    !lv_obj_has_flag(rt.wipe_note, LV_OBJ_FLAG_HIDDEN)) {
		slog("shots: ok   Kiln's data ticked: the print files box usable, the note shown");
	} else {
		slog("shots: FAIL Kiln's data ticked: the print files box or the note");
		fails++;
	}
	shot("16g-return-wipe");
	on_rt_go(NULL);
	settle(100);
	shot("16h-return-wipe-confirm1");
	click(dlg.ok_btn);
	settle(2400);
	shot("16i-return-wipe-confirm2");
	dlg_close();
	/* the print files box goes off with the first, and back on by hand */
	lv_obj_add_state(rt.prints, LV_STATE_CHECKED);
	lv_obj_remove_state(rt.wipe, LV_STATE_CHECKED);
	lv_obj_send_event(rt.wipe, LV_EVENT_VALUE_CHANGED, NULL);
	if (!lv_obj_has_state(rt.prints, LV_STATE_CHECKED) && !rt_prints() &&
	    lv_obj_has_state(rt.prints, LV_STATE_DISABLED)) {
		slog("shots: ok   Kiln's data unticked: the print files box goes off with it");
	} else {
		slog("shots: FAIL Kiln's data unticked: the print files box stayed on");
		fails++;
	}
	for (int i = 0; i < 100 && rt.cap; i++)
		settle(20);
	lv_obj_add_state(rt.wipe, LV_STATE_CHECKED);
	lv_obj_send_event(rt.wipe, LV_EVENT_VALUE_CHANGED, NULL);
	for (int i = 0; i < 100 && rt.cap; i++)
		settle(20);
	lv_obj_add_state(rt.prints, LV_STATE_CHECKED);
	lv_obj_send_event(rt.prints, LV_EVENT_VALUE_CHANGED, NULL);
	for (int i = 0; i < 100 && rt.cap; i++)
		settle(20);
	settle(200);
	shot("16j-return-wipe-prints");
	on_rt_go(NULL);
	settle(100);
	shot("16k-return-wipe-prints-confirm1");
	click(dlg.ok_btn);
	settle(2400);
	shot("16l-return-wipe-prints-confirm2");
	dlg_close();
	return_now();
	wait_job();
	shot("16m-return-wipe-done");

	go(page_network);
	settle(600);
	shot("17-network");

	go(page_logs);
	settle(300);
	shot("18-logs-session");
	lg.which = LOG_SYSTEM;
	lg_load();
	settle(600);
	shot("19-logs-system");

	go(page_power);
	settle(200);
	shot("20-power");
	on_reboot(NULL);
	settle(100);
	shot("21-reboot-confirm");
	dlg_close();

	go(page_bootloader);
	for (int i = 0; i < 100 && bl.cap; i++)
		settle(20);
	settle(200);
	shot("21b-bootloader");
	on_bl_go(NULL);
	settle(100);
	shot("21c-bootloader-confirm1");
	click(dlg.ok_btn);
	settle(2400);
	shot("21d-bootloader-confirm2");
	dlg_close();
	bl_install_now();
	settle(1500);
	shot("21dd-bootloader-running");
	wait_job();
	shot("21e-bootloader-done");
	fails += bl_update_shots(shot);
	fails += bl_result_shots(shot);
	fails += bl_line_shots(shot);

	/* A browser upload arriving while on the home screen, with a dialog
	 * open (its second stage, arm timer running): the job page replaces
	 * it and gets the taps (issue #47) */
	go(page_home);
	settle(200);
	confirm(tr(RS_RS_Q), tr(RS_RS_Q_TEXT), tr(RS_RS_GO), true, tr(RS_RS_Q_TEXT2), return_now);
	settle(100);
	click(dlg.ok_btn);
	swu_inject(SWU_START, SWU_SRC_WEBSERVER, 0, 0, 0, "", NULL);
	swu_inject(SWU_DOWNLOAD, SWU_SRC_WEBSERVER, 0, 0, 0, "", NULL);
	settle(400);
	if (cur_page != page_job || dlg.arm || dlg.ok_btn ||
	    lv_obj_has_flag(lv_layer_top(), LV_OBJ_FLAG_CLICKABLE) ||
	    lv_obj_get_child_count(lv_layer_top())) {
		slog("shots: FAIL a dialog was left behind by the page change");
		fails++;
	} else {
		slog("shots: ok   the page change closed the dialog");
	}
	swu_inject(SWU_RUN, SWU_SRC_WEBSERVER, 3, 1, 70, "kernel.uimage", NULL);
	settle(400);
	shot("22-web-upload");
	swu_inject(SWU_SUCCESS, SWU_SRC_WEBSERVER, 3, 3, 100, "rootfs.squashfs", NULL);
	settle(400);
	shot("23-web-upload-done");
	swu_inject(SWU_IDLE, SWU_SRC_WEBSERVER, 0, 0, 0, "", NULL);

	go(page_home);
	settle(300);
	shot("24-home-again");

	/* An install at start-up (ad5x-recovery-auto's state file): its page
	 * opens by itself, takes SWUpdate's progress (not the browser-upload
	 * page), and a failure stays until Done */
	fails += auto_shots(shot);
	return fails;
}
