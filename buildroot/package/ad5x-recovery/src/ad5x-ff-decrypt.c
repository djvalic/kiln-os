// SPDX-License-Identifier: GPL-3.0-or-later
/*
 * ad5x-ff-decrypt: decrypt a Flashforge AD5X update package (AD5X-*.tgz,
 * the file Flashforge offers for download) for ad5x-return-stock.
 *
 *   ad5x-ff-decrypt [-p PASSFILE] < AD5X-x.y.z-....tgz > package.tar
 *
 * The package is OpenSSL "enc" output: "Salted__", an 8-byte salt, then
 * DES-EDE3-CBC data with PKCS#7 padding; key and IV come from the password
 * and the salt by OpenSSL's old key derivation (EVP_BytesToKey with MD5,
 * one round), as `openssl des3 -d -md md5 -salt -k PASSWORD` decrypts it
 * (docs/stock-firmware-3.1.0.md). The stock firmware's own updater
 * (/usr/prog/mytar) does the same with OpenSSL 1.0.2.
 *
 * The password is Flashforge's, built in (below), so it never appears on a
 * command line, in the environment or in a log. -p PASSFILE takes another
 * one from the first line of a file (the tests' fake packages).
 *
 * Uses mbedTLS (MD5, DES), which the recovery OS has for SWUpdate.
 * Streams: memory use doesn't grow with the package.
 *
 * Exit: 0 decrypted; 1 usage, read or write error; 2 not such a package
 * (no "Salted__" header, or its length isn't whole DES blocks); 3 wrong
 * password or damaged package (the padding at the end doesn't check).
 */
#include <errno.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#include <mbedtls/des.h>
#include <mbedtls/md5.h>

/*
 * Flashforge's public update password: the key of every AD5X-*.tgz update
 * package, as the stock firmware's updater (/usr/prog/mytar) passes it to
 * `openssl des3 -d -k`. Published by the zMod project (ghzserg,
 * github.com/ghzserg). The one place it is kept; never printed.
 */
static const char FF_PASSWORD[] = "FFP0302~%@ffroot800";

#define BLK 8
#define CHUNK 65536

static void die(int code, const char *msg)
{
	fprintf(stderr, "ad5x-ff-decrypt: %s\n", msg);
	exit(code);
}

static size_t read_full(int fd, unsigned char *buf, size_t n)
{
	size_t got = 0;
	while (got < n) {
		ssize_t r = read(fd, buf + got, n - got);
		if (r < 0) {
			if (errno == EINTR)
				continue;
			die(1, "read error");
		}
		if (r == 0)
			break;
		got += (size_t)r;
	}
	return got;
}

static void write_full(int fd, const unsigned char *buf, size_t n)
{
	while (n) {
		ssize_t w = write(fd, buf, n);
		if (w < 0) {
			if (errno == EINTR)
				continue;
			die(1, "write error");
		}
		buf += w;
		n -= (size_t)w;
	}
}

/* EVP_BytesToKey(MD5, one round): D1 = MD5(pass|salt), D2 = MD5(D1|pass|salt);
 * key = D1|D2[0..7] (24 bytes), IV = D2[8..15] */
static void derive(const char *pass, size_t plen, const unsigned char salt[8],
		   unsigned char key[24], unsigned char iv[8])
{
	unsigned char d1[16], d2[16];
	mbedtls_md5_context m;

	mbedtls_md5_init(&m);
	if (mbedtls_md5_starts(&m) || mbedtls_md5_update(&m, (const unsigned char *)pass, plen) ||
	    mbedtls_md5_update(&m, salt, 8) || mbedtls_md5_finish(&m, d1))
		die(1, "MD5 failed");
	mbedtls_md5_free(&m);
	mbedtls_md5_init(&m);
	if (mbedtls_md5_starts(&m) || mbedtls_md5_update(&m, d1, 16) ||
	    mbedtls_md5_update(&m, (const unsigned char *)pass, plen) ||
	    mbedtls_md5_update(&m, salt, 8) || mbedtls_md5_finish(&m, d2))
		die(1, "MD5 failed");
	mbedtls_md5_free(&m);
	memcpy(key, d1, 16);
	memcpy(key + 16, d2, 8);
	memcpy(iv, d2 + 8, 8);
	memset(d1, 0, sizeof(d1));
	memset(d2, 0, sizeof(d2));
}

int main(int argc, char **argv)
{
	char pbuf[256];
	const char *pass = FF_PASSWORD;
	size_t plen = sizeof(FF_PASSWORD) - 1;
	int opt;

	while ((opt = getopt(argc, argv, "p:h")) != -1) {
		if (opt == 'p') {
			FILE *f = fopen(optarg, "r");
			if (!f || !fgets(pbuf, sizeof(pbuf), f))
				die(1, "can't read the password file");
			fclose(f);
			pbuf[strcspn(pbuf, "\r\n")] = 0;
			pass = pbuf;
			plen = strlen(pbuf);
		} else {
			fprintf(stderr, "usage: ad5x-ff-decrypt [-p PASSFILE] < package.tgz > package.tar\n");
			return opt == 'h' ? 0 : 1;
		}
	}
	if (optind != argc)
		die(1, "usage: ad5x-ff-decrypt [-p PASSFILE] < package.tgz > package.tar");
	/* A reader that stops early (tar -t) ends this quietly */
	signal(SIGPIPE, SIG_DFL);

	unsigned char hdr[16];
	if (read_full(0, hdr, 16) != 16 || memcmp(hdr, "Salted__", 8))
		die(2, "not a Flashforge update package (no OpenSSL \"Salted__\" header)");

	unsigned char key[24], iv[8];
	derive(pass, plen, hdr + 8, key, iv);
	mbedtls_des3_context d;
	mbedtls_des3_init(&d);
	if (mbedtls_des3_set3key_dec(&d, key))
		die(1, "DES key setup failed");
	memset(key, 0, sizeof(key));

	static unsigned char in[CHUNK + BLK], out[CHUNK + BLK];
	size_t have = 0;	/* ciphertext bytes in `in` not decrypted yet */
	for (;;) {
		size_t got = read_full(0, in + have, CHUNK);
		have += got;
		if (got == 0)
			break;
		/* Decrypt whole blocks, but keep the last one back: it carries
		 * the padding, known to be the last only at the end */
		size_t n = have / BLK * BLK;
		if (n == have)
			n -= BLK;
		if (n) {
			if (mbedtls_des3_crypt_cbc(&d, MBEDTLS_DES_DECRYPT, n, iv, in, out))
				die(1, "DES failed");
			write_full(1, out, n);
			memmove(in, in + n, have - n);
			have -= n;
		}
	}
	if (have != BLK)
		die(2, "damaged package: its length isn't whole DES blocks");
	if (mbedtls_des3_crypt_cbc(&d, MBEDTLS_DES_DECRYPT, BLK, iv, in, out))
		die(1, "DES failed");
	mbedtls_des3_free(&d);
	unsigned pad = out[BLK - 1];
	if (pad < 1 || pad > BLK)
		die(3, "wrong password or damaged package (bad padding)");
	for (unsigned i = 0; i < pad; i++)
		if (out[BLK - 1 - i] != pad)
			die(3, "wrong password or damaged package (bad padding)");
	write_full(1, out, BLK - pad);
	return 0;
}
