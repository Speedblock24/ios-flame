/*
 * Tab S6 stage-0 probe: arm64 Image header, entry, exception vectors.
 * Linked at 0, position independent (adr only); Samsung's loader puts it at
 * its kernel address with x0 = DTB pointer (Linux boot protocol).
 */
	.section .text.head, "ax"
	.global _start
_start:
	b	entry
	.long	0
	.quad	0x80000			/* text_offset, same as the stock Image */
	.quad	_end			/* image_size (linked at 0, so = size) */
	.quad	0xa			/* flags, same as stock: LE, 4K, anywhere */
	.quad	0
	.quad	0
	.quad	0
	.long	0x644d5241		/* "ARM\x64" */
	.long	0

	.text
entry:
	msr	daifset, #0xf
	mov	x19, x0
	mov	x20, x1
	mov	x21, x2
	mov	x22, x3
	adr	x4, stack_top
	mov	sp, x4
	adr	x4, vectors
	mrs	x5, CurrentEL
	cmp	x5, #8
	b.ne	1f
	msr	vbar_el2, x4
	b	2f
1:	msr	vbar_el1, x4
2:	isb
	mov	x0, x19
	mov	x1, x20
	mov	x2, x21
	mov	x3, x22
	bl	probe_main
3:	wfe
	b	3b

	.global here
here:
	adr	x0, _start
	ret

exc_common:
	adr	x4, stack_top
	mov	sp, x4
	bl	exc_report
4:	wfe
	b	4b

.macro vec n
	.balign 128
	mov	x0, #\n
	b	exc_common
.endm

	.balign 2048
vectors:
	vec 0
	vec 1
	vec 2
	vec 3
	vec 4
	vec 5
	vec 6
	vec 7
	vec 8
	vec 9
	vec 10
	vec 11
	vec 12
	vec 13
	vec 14
	vec 15

	.section .bss
	.balign 16
	.skip	0x4000
stack_top:
