# Galaxy Tab S6 (SM-T860 Wi-Fi, `gts6lwifi`) - hardware notes

Same SoC as the Pixel 4 (SM8150), so most of NOTES.md applies. Facts below come from the tablet's live FDT
(`/sys/firmware/fdt`, kept out of git: it contains the serial number) and Samsung's public kernel source for the
Wi-Fi model (github.com/ianmacd/gts6lwifi). Firmware T860XXS5DWH1, Android 12, bootloader unlocked (orange).

## Same as flame

| | Tab S6 |
|---|---|
| RAM | `<0x80000000 0x3cc00000>`, then 0xc0000000..0x200000000 (same coverage as flame) |
| GIC | GICD 0x17a00000, GICR 0x17a60000 stride 0x20000 |
| WDT | qcom,msm-watchdog @0x17c10000 |
| UFS | UFSHCI @0x1d84000 (UFS storage, `boot` = sda20, `recovery` = sda21, `userdata` = sda30) |
| USB | DWC3 @0xa600000 |
| PMIC arb | spmi @0xc440000, pm8150 / pm8150b / pm8150l |
| Splash framebuffer | `cont_splash_region` 0x9c400000, 32 MiB (flame's ABL fb is at the same address) |

## Different from flame

| | flame | Tab S6 |
|---|---|---|
| Panel | NT37280 cmd-mode DSC, 1080x2280, one DSI | Samsung ANA38401_AMSA05RB06, cmd mode, no DSC, two DSI links (ctrl0 + ctrl1), 1280x1600 each (2560x1600 total), 4 lanes, 60 Hz, 898 MHz, TE on TLMM GPIO 8 |
| Touch | ST FTS on GENI SPI @0x890000 | STM FTS (`stm,fts_touch`, fts1ba90a) on GENI I2C @0xc80000 (i2c-10), addr 0x49, IRQ TLMM GPIO 87 (type 0x2008), dvdd pm8150_l14, avdd pm8150_l17, max coords 1599x2559 |
| Volume up | PM8150 GPIO6 | PM8150L (SID 4) GPIO12, active low |
| Boot | `fastboot boot` | Odin only; Android boot image v1, 4 KiB pages, kernel_addr 0x8000, tags 0x01e00000; DTBs selected by `dtb_idx`/`dtbo_idx` |
| Samsung carve-outs | none | tima 0xb0000000 (2 MiB), rkp 0xb0200000 (2 MiB), uh_heap 0xb0400000 (20 MiB); kaslrOffset 0x80001000; sec debug 0xc1100000-0xc1c01000; ramoops 0xc1300000 (1 MiB) |

## Stock boot.img layout (decoded from the stock image)

- Header v1, 4 KiB pages, base 0, kernel 0x8000, ramdisk 0x0, tags 0x01e00000, os 12.0.0 / 2023-08, board `SRPSD11A005`, cmdline `console=null ... androidboot.usbcontroller=a600000.dwc3 ...` (no dtb/dtbo in the header).
- Kernel blob (50,836,849 bytes) = 16-byte magic `UNCOMPRESSED_IMG` + le32 length (0x02e94810) + a plain, uncompressed arm64 Image
  (text_offset 0x80000, flags 0xa, image_size 0x038d2000) + **four appended SM8150 DTBs** (~497-500 KB each, at blob offsets
  0x2e94824, 0x2f0dedb, 0x2f87e74, 0x3001e11; `dtb_idx=2` selects the third) + a 173-byte trailing FDT. The Image ends exactly where the first DTB starts.
- After the ramdisk: the 16-byte `SEANDROIDENFORCE` marker, then an AVB hash footer (original image size 0x030e6010 = image + marker,
  vbmeta at 0x030e7000, 2112 bytes, `AVBf` footer at the end of the 64 MiB partition).
- Unlike Google's ABL (flame), Samsung's loader takes an **uncompressed** Image, so no LZ4 step is needed.

## Open questions

- Does Samsung's loader accept a rebuilt image (new Image + stock DTBs + stock ramdisk + `SEANDROIDENFORCE` + unsigned AVB hash footer) on an unlocked bootloader?
- Does the panel stay running for a custom kernel? It is command mode on two DSI links, so writing the splash framebuffer shows nothing by itself: a frame has to be
  started through SDE (see shim/sde.c), and the dual-link SDE setup differs from flame's single INTF.
- Log read-back without a display: ramoops at 0xc1300000 is 1 MiB with 256 KiB each for dmesg, console, ftrace and pmsg, no ECC. The plan is to leave a message in
  the console zone and force a warm reset through the watchdog (0x17c10000), then read `/sys/fs/pstore` in Android. Needs checking: pstore enabled in
  Samsung's kernel, DDR kept across the reset, and sec_debug not clearing the zone.
- Whether Samsung's hypervisor (uh/rkp) stays out of the way of a kernel that never calls it.
