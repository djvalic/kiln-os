/* SPDX-License-Identifier: GPL-2.0 */
/*
 * Chainload trampoline. Copied by chainload.ko into a page outside the
 * destination range and entered with interrupts off on the only online
 * CPU, after device_shutdown(). Position independent, no stack.
 *
 *   a0 = page list (KSEG0 addresses of 4 KiB source pages, in order)
 *   a1 = number of pages
 *   a2 = argc, a3 = argv (KSEG0) for the new kernel
 *
 * Copies the pages to LOAD_ADDR, writes back and invalidates L1 D, L2
 * (if Config2 reports one) and invalidates L1 I by index, then jumps to
 * LOAD_ADDR with a0 = argc, a1 = argv, a2 = a3 = 0, as the stock SPL does.
 */
#include <asm/regdef.h>

/* chainload.c's CHAINLOAD_LOAD; the bench variant (make uboot) sets 0x80100000 */
#ifdef CHAINLOAD_LOAD
#define LOAD_ADDR	CHAINLOAD_LOAD
#else
#define LOAD_ADDR	0x80f00000
#endif

	.text
	.set	noreorder
	.set	mips32r2
	.globl	chainload_tramp
	.globl	chainload_tramp_end
chainload_tramp:
	move	t8, a2
	move	t9, a3
	li	t0, LOAD_ADDR
1:	beqz	a1, 3f
	 nop
	lw	t1, 0(a0)
	li	t2, 4096
2:	lw	t3, 0(t1)
	addiu	t1, t1, 4
	sw	t3, 0(t0)
	addiu	t2, t2, -4
	bnez	t2, 2b
	 addiu	t0, t0, 4
	addiu	a0, a0, 4
	b	1b
	 addiu	a1, a1, -1

3:	/* L1 D-cache: Index Writeback Invalidate (op 0x01) */
	mfc0	t0, $16, 1
	srl	t1, t0, 10
	andi	t1, t1, 7
	beqz	t1, 5f
	 li	t2, 2
	sllv	t2, t2, t1		/* line size */
	srl	t3, t0, 13
	andi	t3, t3, 7
	li	t4, 64
	sllv	t4, t4, t3		/* sets */
	srl	t5, t0, 7
	andi	t5, t5, 7
	addiu	t5, t5, 1		/* ways */
	mul	t4, t4, t5
	mul	t4, t4, t2		/* bytes */
	lui	t6, 0x8000
	addu	t7, t6, t4
4:	cache	0x01, 0(t6)
	addu	t6, t6, t2
	bne	t6, t7, 4b
	 nop
5:	sync
	/* L2: Index Writeback Invalidate SD (op 0x03), if Config1.M and SL */
	bgez	t0, 7f			/* Config1.M clear: no Config2 */
	 nop
	mfc0	t0, $16, 2
	srl	t1, t0, 4
	andi	t1, t1, 0xf
	beqz	t1, 7f
	 li	t2, 2
	sllv	t2, t2, t1
	srl	t3, t0, 8
	andi	t3, t3, 0xf
	li	t4, 64
	sllv	t4, t4, t3
	andi	t5, t0, 0xf
	addiu	t5, t5, 1
	mul	t4, t4, t5
	mul	t4, t4, t2
	lui	t6, 0x8000
	addu	t7, t6, t4
6:	cache	0x03, 0(t6)
	addu	t6, t6, t2
	bne	t6, t7, 6b
	 nop
7:	sync
	/* L1 I-cache: Index Invalidate (op 0x00) */
	mfc0	t0, $16, 1
	srl	t1, t0, 19
	andi	t1, t1, 7
	beqz	t1, 9f
	 li	t2, 2
	sllv	t2, t2, t1
	srl	t3, t0, 22
	andi	t3, t3, 7
	li	t4, 64
	sllv	t4, t4, t3
	srl	t5, t0, 16
	andi	t5, t5, 7
	addiu	t5, t5, 1
	mul	t4, t4, t5
	mul	t4, t4, t2
	lui	t6, 0x8000
	addu	t7, t6, t4
8:	cache	0x00, 0(t6)
	addu	t6, t6, t2
	bne	t6, t7, 8b
	 nop
9:	sync
	move	a0, t8
	move	a1, t9
	move	a2, zero
	move	a3, zero
	li	t0, LOAD_ADDR
	jr.hb	t0
	 nop
chainload_tramp_end:
