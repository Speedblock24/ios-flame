/*
 * Tab S6 stage-0 probe. Runs with the MMU off, touches only DRAM and the
 * apps watchdog. It writes a text report into the four 256 KiB zones of the
 * ramoops region (0xc1300000, 1 MiB, no ECC), then forces a warm reset with a
 * watchdog bite so Android's pstore shows it in /sys/fs/pstore. Each zone
 * carries its own index in the first line, which maps the zone layout.
 * Deliberately does not print the DTB's bootargs (they hold the serial number).
 */
typedef unsigned long u64;
typedef unsigned int u32;
typedef unsigned char u8;

#define RAMOOPS		0xc1300000UL
#define ZONE_SZ		0x40000UL
#define NZONES		4
#define PRAM_SIG	0x43474244u	/* "DBGC" */
#define TAG		"TABS6PROBE zone="
#define TAG_POS		16
#define WDT		0x17c10000UL
#define RAM_LO		0x80000000UL
#define RAM_HI		0x240000000UL

extern u64 here(void);

#define RD(reg) ({ u64 v_; __asm__ volatile("mrs %0, " #reg : "=r"(v_)); v_; })

static char buf[12288];
static u32 blen;

static void pc(char c)
{
	if (blen < sizeof buf - 1)
		buf[blen++] = c;
}

static void ps(const char *s)
{
	while (*s)
		pc(*s++);
}

static void pn(const u8 *s, u32 n)
{
	for (u32 i = 0; i < n && s[i]; i++)
		pc(s[i] >= 0x20 && s[i] < 0x7f ? (char)s[i] : '.');
}

static void ph(u64 v)
{
	static const char d[] = "0123456789abcdef";
	int started = 0;
	ps("0x");
	for (int i = 60; i >= 0; i -= 4) {
		u32 n = (v >> i) & 15;
		if (n || started || i == 0) {
			pc(d[n]);
			started = 1;
		}
	}
}

static void kv(const char *k, u64 v)
{
	ps(k);
	pc('=');
	ph(v);
	pc('\n');
}

static void write_all(void)
{
	for (u32 z = 0; z < NZONES; z++) {
		volatile u8 *b = (volatile u8 *)(RAMOOPS + z * ZONE_SZ);
		buf[TAG_POS] = '0' + z;
		for (u32 i = 0; i < blen; i++)
			b[12 + i] = buf[i];
		*(volatile u32 *)(b + 4) = 0;
		*(volatile u32 *)(b + 8) = blen;
		__asm__ volatile("dsb sy" ::: "memory");
		*(volatile u32 *)b = PRAM_SIG;
		__asm__ volatile("dsb sy" ::: "memory");
	}
}

#ifdef PROBE_HANG
/* Hang variant: no readback needed. If this runs, the tablet freezes instead of booting Android. */
static void reset(void)
{
	for (;;)
		__asm__ volatile("wfe");
}
#else
static void delay_s(u64 s)
{
	u64 f = RD(cntfrq_el0);
	if (!f)
		f = 19200000;
	u64 t = RD(cntpct_el0);
	while (RD(cntpct_el0) - t < f * s)
		;
}

#ifndef RESET_DELAY
#define RESET_DELAY 0		/* seconds to wait before the reset: a timed reboot proves our code ran */
#endif

static void reset(void)
{
	delay_s(RESET_DELAY);
	volatile u32 *w = (volatile u32 *)WDT;
	w[0x14 / 4] = 1;	/* BITE_TIME: one tick */
	w[0x08 / 4] = 1;	/* EN */
	w[0x04 / 4] = 1;	/* RST: restart the counter, bite follows at once */
	__asm__ volatile("dsb sy" ::: "memory");
	delay_s(3);
	/* PSCI SYSTEM_RESET as a fallback (may be a cold reset) */
	__asm__ volatile("mov x0, %0\n\tsmc #0" :: "r"(0x84000009UL) : "x0", "x1", "x2", "x3", "memory");
	for (;;)
		__asm__ volatile("wfe");
}
#endif

/* ---- tiny FDT reader ---- */
static u32 be32(const u8 *p)
{
	return ((u32)p[0] << 24) | ((u32)p[1] << 16) | ((u32)p[2] << 8) | p[3];
}

static int streq(const char *a, const char *b)
{
	while (*a && *a == *b) {
		a++;
		b++;
	}
	return *a == *b;
}

/* node path "" is the root; finds property `prop` of node `node` */
static const u8 *fdt_prop(const u8 *fdt, const char *node, const char *prop, u32 *len)
{
	u32 total = be32(fdt + 4), off_s = be32(fdt + 8), off_str = be32(fdt + 12);
	const u8 *p = fdt + off_s, *end = fdt + total;
	char cur[160];
	u32 stack[12];
	int depth = -1;
	u32 clen = 0;
	cur[0] = 0;
	while (p + 4 <= end) {
		u32 tok = be32(p);
		p += 4;
		if (tok == 1) {
			const char *nm = (const char *)p;
			u32 n = 0;
			while (nm[n])
				n++;
			p += (n + 1 + 3) & ~3u;
			if (depth + 1 >= 12)
				return 0;
			stack[++depth] = clen;
			if (depth > 0 && clen + n + 2 < sizeof cur) {
				cur[clen++] = '/';
				for (u32 i = 0; i < n; i++)
					cur[clen++] = nm[i];
				cur[clen] = 0;
			}
		} else if (tok == 2) {
			if (depth < 0)
				return 0;
			clen = stack[depth--];
			cur[clen] = 0;
		} else if (tok == 3) {
			u32 l = be32(p), no = be32(p + 4);
			const u8 *v = p + 8;
			p += 8 + ((l + 3) & ~3u);
			if (streq(cur, node) && streq((const char *)(fdt + off_str + no), prop)) {
				*len = l;
				return v;
			}
		} else if (tok == 9) {
			return 0;
		}
	}
	return 0;
}

static u64 beval(const u8 *v, u32 len)
{
	u64 r = 0;
	for (u32 i = 0; i < len && i < 8; i++)
		r = (r << 8) | v[i];
	return r;
}

static void fdt_report(u64 x0)
{
	if (x0 < RAM_LO || x0 >= RAM_HI || (x0 & 3)) {
		ps("fdt: x0 not a RAM pointer\n");
		return;
	}
	const u8 *fdt = (const u8 *)x0;
	u32 magic = be32(fdt);
	kv("fdt_magic", magic);
	if (magic != 0xd00dfeed)
		return;
	u32 total = be32(fdt + 4);
	kv("fdt_totalsize", total);
	kv("fdt_version", be32(fdt + 20));
	if (total < 64 || total > (8u << 20))
		return;
	u32 l;
	const u8 *v = fdt_prop(fdt, "", "model", &l);
	if (v) {
		ps("model=");
		pn(v, l);
		pc('\n');
	}
	v = fdt_prop(fdt, "", "compatible", &l);
	if (v) {
		ps("compatible=");
		pn(v, l);
		pc('\n');
	}
	v = fdt_prop(fdt, "/chosen", "linux,initrd-start", &l);
	if (v)
		kv("initrd_start", beval(v, l));
	v = fdt_prop(fdt, "/chosen", "linux,initrd-end", &l);
	if (v)
		kv("initrd_end", beval(v, l));
	/* only the dtb_idx digits from the bootargs, never the whole string */
	v = fdt_prop(fdt, "/chosen", "bootargs", &l);
	if (v) {
		kv("bootargs_len", l);
		static const char key[] = "androidboot.dtb_idx=";
		for (u32 i = 0; i + sizeof key < l; i++) {
			u32 j = 0;
			while (key[j] && v[i + j] == (u8)key[j])
				j++;
			if (!key[j]) {
				ps("dtb_idx=");
				pn(v + i + j, 3);
				pc('\n');
				break;
			}
		}
	}
}

void probe_main(u64 x0, u64 x1, u64 x2, u64 x3)
{
	u64 el = RD(CurrentEL) >> 2;
	ps(TAG "?\nstage=early alive\n");
	write_all();

	kv("x0", x0);
	kv("x1", x1);
	kv("x2", x2);
	kv("x3", x3);
	kv("load_addr", here());
	kv("el", el);
	kv("midr", RD(midr_el1));
	kv("mpidr", RD(mpidr_el1));
	kv("id_aa64pfr0", RD(id_aa64pfr0_el1));
	kv("sctlr_el1", RD(sctlr_el1));
	kv("daif", RD(daif));
	kv("cntfrq", RD(cntfrq_el0));
	kv("cntpct", RD(cntpct_el0));
	if (el == 2) {
		kv("hcr_el2", RD(hcr_el2));
		kv("sctlr_el2", RD(sctlr_el2));
	}
	write_all();
	fdt_report(x0);
	ps("stage=done\n");
	write_all();
	reset();
}

void exc_report(u64 n)
{
	u64 el = RD(CurrentEL) >> 2, esr, elr, far;
	if (el == 2) {
		esr = RD(esr_el2);
		elr = RD(elr_el2);
		far = RD(far_el2);
	} else {
		esr = RD(esr_el1);
		elr = RD(elr_el1);
		far = RD(far_el1);
	}
	blen = 0;
	ps(TAG "?\nEXCEPTION\n");
	kv("vec", n);
	kv("el", el);
	kv("esr", esr);
	kv("elr", elr);
	kv("far", far);
	write_all();
	reset();
}
