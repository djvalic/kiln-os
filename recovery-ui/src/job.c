/* Background command runner (see job.h) */
#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include "job.h"
#include "progress.h"

#include <errno.h>
#include <fcntl.h>
#include <pthread.h>
#include <signal.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

/* ---------------------------------------------------------------- text buf */

/* Text buffer that keeps the tail: when full, the oldest third is dropped
 * at a line boundary. A '\r' (dd/progress style) rewinds to the start of
 * the current line. */
struct tbuf {
	char *s;
	size_t len, cap, line_start;
	bool cr_pending;
};

static void tbuf_init(struct tbuf *t, size_t cap)
{
	t->s = calloc(1, cap);
	t->cap = cap;
	t->len = t->line_start = 0;
	t->cr_pending = false;
}

static void tbuf_trim(struct tbuf *t)
{
	size_t drop = t->cap / 3;
	char *nl = memchr(t->s + drop, '\n', t->len - drop);
	if (nl)
		drop = nl - t->s + 1;
	memmove(t->s, t->s + drop, t->len - drop);
	t->len -= drop;
	t->line_start = t->line_start > drop ? t->line_start - drop : 0;
	t->s[t->len] = 0;
}

static void tbuf_putc(struct tbuf *t, char c)
{
	if (t->cr_pending && c != '\n') {	/* "\r" then text: overwrite line */
		t->len = t->line_start;
		t->s[t->len] = 0;
	}
	t->cr_pending = false;
	if (c == '\r') {
		t->cr_pending = true;
		return;
	}
	if (t->len + 2 >= t->cap)
		tbuf_trim(t);
	t->s[t->len++] = c;
	t->s[t->len] = 0;
	if (c == '\n')
		t->line_start = t->len;
}

static void tbuf_puts(struct tbuf *t, const char *s)
{
	while (*s)
		tbuf_putc(t, *s++);
}

static size_t tbuf_copy(const struct tbuf *t, char *buf, size_t cap)
{
	if (!cap)
		return 0;
	size_t n = t->len, off = 0;
	if (n >= cap) {
		off = n - (cap - 1);
		const char *nl = memchr(t->s + off, '\n', n - off);
		if (nl)
			off = nl - t->s + 1;
		n -= off;
	}
	memcpy(buf, t->s + off, n);
	buf[n] = 0;
	return n;
}

/* ------------------------------------------------------------- session log */

static pthread_mutex_t slog_mu = PTHREAD_MUTEX_INITIALIZER;
static struct tbuf slog_buf;
static unsigned slog_n;

static void slog_raw(const char *s)
{
	pthread_mutex_lock(&slog_mu);
	if (!slog_buf.s)
		tbuf_init(&slog_buf, 96 * 1024);
	tbuf_puts(&slog_buf, s);
	slog_n++;
	pthread_mutex_unlock(&slog_mu);
}

void slog(const char *fmt, ...)
{
	char line[512], stamp[16];
	time_t now = time(NULL);
	strftime(stamp, sizeof(stamp), "%H:%M:%S", localtime(&now));
	va_list ap;
	va_start(ap, fmt);
	int n = snprintf(line, sizeof(line), "[%s] ", stamp);
	vsnprintf(line + n, sizeof(line) - n - 1, fmt, ap);
	va_end(ap);
	strcat(line, "\n");
	fputs(line, stderr);
	slog_raw(line);
}

size_t slog_copy(char *buf, size_t cap)
{
	pthread_mutex_lock(&slog_mu);
	size_t n = slog_buf.s ? tbuf_copy(&slog_buf, buf, cap) : 0;
	if (!slog_buf.s && cap)
		buf[0] = 0;
	pthread_mutex_unlock(&slog_mu);
	return n;
}

unsigned slog_seq(void)
{
	pthread_mutex_lock(&slog_mu);
	unsigned n = slog_n;
	pthread_mutex_unlock(&slog_mu);
	return n;
}

/* --------------------------------------------------------------------- job */

static pthread_mutex_t mu = PTHREAD_MUTEX_INITIALIZER;
static struct tbuf out;
static job_state st;
static pid_t pid = -1;
static char linebuf[1024];
static size_t linelen;

static pid_t spawn_sh(const char *cmd, int *rfd)
{
	int p[2];
	if (pipe2(p, O_CLOEXEC))
		return -1;
	pid_t c = fork();
	if (c < 0) {
		close(p[0]);
		close(p[1]);
		return -1;
	}
	if (!c) {
		setsid();
		int nul = open("/dev/null", O_RDONLY);
		dup2(nul, 0);
		dup2(p[1], 1);
		dup2(p[1], 2);
		signal(SIGPIPE, SIG_DFL);
		setenv("LANG", "C", 1);
		execl("/bin/sh", "sh", "-c", cmd, (char *)NULL);
		_exit(127);
	}
	close(p[1]);
	*rfd = p[0];
	return c;
}

/* "[code] text" or "text" of a progress line (progress.h) */
static void set_step(const char *s)
{
	const char *text;
	pg_split(s, st.code, sizeof(st.code), st.arg, sizeof(st.arg), &text);
	snprintf(st.step, sizeof(st.step), "%s", text);
}

/* A finished output line: look for progress. Returns true if the line is
 * a directive (not shown). Called with mu held. */
static bool parse_line(const char *l)
{
	if (!strncmp(l, "@progress ", 10)) {
		char *end;
		long v = strtol(l + 10, &end, 10);
		if (v >= 0 && v <= 100)
			st.progress = (int)v;
		while (*end == ' ')
			end++;
		if (*end)
			set_step(end);
		return true;
	}
	if (!strncmp(l, "@step ", 6)) {
		set_step(l + 6);
		return true;
	}
	/* last "NN%" or "NN.N%" on the line */
	int found = -1;
	for (const char *p = strchr(l, '%'); p; p = strchr(p + 1, '%')) {
		const char *q = p;
		while (q > l && (q[-1] == '.' || (q[-1] >= '0' && q[-1] <= '9')))
			q--;
		if (q < p && *q != '.') {
			int v = atoi(q);
			if (v >= 0 && v <= 100)
				found = v;
		}
	}
	if (found >= 0)
		st.progress = found;
	return false;
}

static void feed(const char *s, size_t n)
{
	for (size_t i = 0; i < n; i++) {
		char c = s[i];
		if (c == '\n' || c == '\r') {
			linebuf[linelen] = 0;
			bool directive = parse_line(linebuf);
			if (directive) {
				/* not shown: drop the partial line already in out */
				out.len = out.line_start;
				out.s[out.len] = 0;
				out.cr_pending = false;
			} else {
				tbuf_putc(&out, c);
				if (c == '\n') {
					linebuf[linelen] = '\n';
					linebuf[linelen + 1] = 0;
					slog_raw(linebuf);
				}
			}
			linelen = 0;
			continue;
		}
		if (linelen < sizeof(linebuf) - 2)
			linebuf[linelen++] = c;
		tbuf_putc(&out, c);
	}
	st.seq++;
}

static void *reader(void *arg)
{
	int fd = (int)(long)arg;
	char buf[1024];
	for (;;) {
		ssize_t n = read(fd, buf, sizeof(buf));
		if (n < 0 && errno == EINTR)
			continue;
		if (n <= 0)
			break;
		pthread_mutex_lock(&mu);
		feed(buf, n);
		pthread_mutex_unlock(&mu);
	}
	close(fd);
	int status = 0;
	pid_t me;
	pthread_mutex_lock(&mu);
	me = pid;
	pthread_mutex_unlock(&mu);
	while (waitpid(me, &status, 0) < 0 && errno == EINTR)
		;
	pthread_mutex_lock(&mu);
	if (linelen)
		feed("\n", 1);
	st.running = false;
	st.finished = true;
	st.exit_code = WIFEXITED(status) ? WEXITSTATUS(status) : -1;
	if (st.exit_code == 0)
		st.progress = 100;
	pid = -1;
	st.seq++;
	pthread_mutex_unlock(&mu);
	slog("finished: exit %d", st.exit_code);
	return NULL;
}

bool job_start(const char *title, const char *cmd)
{
	pthread_mutex_lock(&mu);
	if (st.running) {
		pthread_mutex_unlock(&mu);
		return false;
	}
	if (!out.s)
		tbuf_init(&out, 128 * 1024);
	out.len = out.line_start = 0;
	out.s[0] = 0;
	linelen = 0;
	unsigned seq = st.seq;
	memset(&st, 0, sizeof(st));
	st.seq = seq + 1;
	st.progress = -1;
	int fd;
	pid = spawn_sh(cmd, &fd);
	if (pid < 0) {
		st.finished = true;
		st.exit_code = -1;
		tbuf_puts(&out, "cannot start command\n");
		pthread_mutex_unlock(&mu);
		return false;
	}
	st.running = true;
	pthread_mutex_unlock(&mu);
	slog("%s: %s", title, cmd);
	pthread_t th;
	pthread_attr_t a;
	pthread_attr_init(&a);
	pthread_attr_setdetachstate(&a, PTHREAD_CREATE_DETACHED);
	pthread_create(&th, &a, reader, (void *)(long)fd);
	pthread_attr_destroy(&a);
	return true;
}

void job_cancel(void)
{
	pthread_mutex_lock(&mu);
	if (st.running && pid > 0) {
		kill(-pid, SIGTERM);
		slog("cancel: SIGTERM to %d", (int)pid);
	}
	pthread_mutex_unlock(&mu);
}

bool job_running(void)
{
	pthread_mutex_lock(&mu);
	bool r = st.running;
	pthread_mutex_unlock(&mu);
	return r;
}

void job_poll(job_state *s)
{
	pthread_mutex_lock(&mu);
	*s = st;
	pthread_mutex_unlock(&mu);
}

size_t job_output(char *buf, size_t cap)
{
	pthread_mutex_lock(&mu);
	size_t n = out.s ? tbuf_copy(&out, buf, cap) : 0;
	if (!out.s && cap)
		buf[0] = 0;
	pthread_mutex_unlock(&mu);
	return n;
}

/* ----------------------------------------------------------------- capture */

struct capture {
	pthread_mutex_t mu;
	struct tbuf t;
	char *cmd;
	bool done, orphan;
};

static void capture_destroy(capture *c)
{
	pthread_mutex_destroy(&c->mu);
	free(c->t.s);
	free(c->cmd);
	free(c);
}

static void *capture_thread(void *arg)
{
	capture *c = arg;
	int fd;
	pid_t p = spawn_sh(c->cmd, &fd);
	if (p > 0) {
		char buf[1024];
		ssize_t n;
		while ((n = read(fd, buf, sizeof(buf) - 1)) != 0) {
			if (n < 0) {
				if (errno == EINTR)
					continue;
				break;
			}
			buf[n] = 0;
			pthread_mutex_lock(&c->mu);
			tbuf_puts(&c->t, buf);
			pthread_mutex_unlock(&c->mu);
		}
		close(fd);
		while (waitpid(p, NULL, 0) < 0 && errno == EINTR)
			;
	}
	pthread_mutex_lock(&c->mu);
	c->done = true;
	bool orphan = c->orphan;
	pthread_mutex_unlock(&c->mu);
	if (orphan)
		capture_destroy(c);
	return NULL;
}

capture *capture_start(const char *cmd, size_t cap)
{
	capture *c = calloc(1, sizeof(*c));
	pthread_mutex_init(&c->mu, NULL);
	tbuf_init(&c->t, cap);
	c->cmd = strdup(cmd);
	pthread_t th;
	pthread_attr_t a;
	pthread_attr_init(&a);
	pthread_attr_setdetachstate(&a, PTHREAD_CREATE_DETACHED);
	if (pthread_create(&th, &a, capture_thread, c))
		c->done = true;
	pthread_attr_destroy(&a);
	return c;
}

bool capture_done(capture *c)
{
	pthread_mutex_lock(&c->mu);
	bool d = c->done;
	pthread_mutex_unlock(&c->mu);
	return d;
}

const char *capture_text(capture *c)
{
	return c->t.s;
}

void capture_free(capture *c)
{
	if (!c)
		return;
	pthread_mutex_lock(&c->mu);
	bool done = c->done;
	c->orphan = true;
	pthread_mutex_unlock(&c->mu);
	if (done)
		capture_destroy(c);
}
