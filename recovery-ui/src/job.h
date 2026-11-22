/* Background commands: one job at a time, run through /bin/sh -c in its own
 * process group; a reader thread collects its output. The UI (main thread)
 * polls job_poll() from an LVGL timer, so it never blocks. */
#ifndef RUI_JOB_H
#define RUI_JOB_H

#include <stdbool.h>
#include <stddef.h>

typedef struct {
	unsigned seq;		/* changes whenever anything below changes */
	bool running;
	bool finished;		/* ran and ended (stays set until next start) */
	int exit_code;		/* valid when finished; -1 = killed/failed */
	int progress;		/* 0..100, or -1 = unknown */
	char step[160];		/* last "@step"/"@progress" text (English) */
	char code[32];		/* its "[code]" or "[code:arg]", empty if none */
	char arg[128];		/* (progress.h: pg_text gives the shown text) */
} job_state;

/* Start cmd (a /bin/sh -c string). False if a job is already running. */
bool job_start(const char *title, const char *cmd);
void job_cancel(void);			/* SIGTERM to the process group */
bool job_running(void);
void job_poll(job_state *st);
/* Copy the job's output (tail that fits) into buf */
size_t job_output(char *buf, size_t cap);

/* Session log: every job's output plus UI notes, for the log viewer */
void slog(const char *fmt, ...) __attribute__((format(printf, 1, 2)));
size_t slog_copy(char *buf, size_t cap);
unsigned slog_seq(void);

/* Quick read-only queries (system log, info): cmd runs in a thread and its
 * stdout (up to cap bytes, the tail is kept) is collected. Poll with
 * capture_done(); capture_free() may be called at any time. */
typedef struct capture capture;
capture *capture_start(const char *cmd, size_t cap);
bool capture_done(capture *c);
const char *capture_text(capture *c);	/* valid once done */
void capture_free(capture *c);

#endif
