# Tab S6 stage-0 probe

A ~40 KB bare-metal arm64 Image that answers one question: **does Samsung's loader run a
kernel we built, and what does it hand over?** It never touches storage, display, USB or any
peripheral. It writes a text report into the ramoops region (`0xc1300000`, 4 x 256 KiB zones),
forces a warm reset with the apps watchdog, and Android's pstore shows the report afterwards.

The report holds: x0..x3 as the loader left them, load address, exception level, MIDR/MPIDR,
SCTLR, timer, the DTB pointer's header, model/compatible, initrd range, and `androidboot.dtb_idx`
(never the full bootargs, which hold the serial number). If anything faults, vectors catch it and
write ESR/ELR/FAR instead. The first line of each zone is `TABS6PROBE zone=N`, which also maps
which zone is which.

## Build (sources are here; `out/Image` is not committed)

    sudo pacman -S clang lld llvm      # or any clang + ld.lld + llvm-objcopy/readelf/nm
    tabs6/probe/build.sh

## Package for the `recovery` partition (boot stays untouched)

    git clone --depth 1 https://android.googlesource.com/platform/external/avb ~/avb
    adb shell su -c 'blockdev --getsize64 /dev/block/by-name/recovery'   # partition size
    ls -l ~/recovery.img                                                 # backup: same size?

    python3 tabs6/probe/repack.py --stock-boot ~/boot.img --image tabs6/probe/out/Image \
        --out ~/recovery-probe.img --partition-name recovery \
        --partition-size-from ~/recovery.img --avbtool ~/avb/avbtool.py

    python3 tabs6/probe/odin_tar.py ~/recovery-probe.img ~/recovery-probe.tar.md5
    python3 tabs6/probe/odin_tar.py ~/recovery.img ~/recovery-restore.tar.md5   # your current recovery, to put back

`repack.py` keeps the stock header page (only kernel_size and id change), the four stock DTBs
and trailer, the stock ramdisk, the `SEANDROIDENFORCE` marker, and adds an unsigned AVB hash
footer sized for the partition.

## Run

Flash `recovery-probe.tar.md5` in Odin's AP slot like you flashed TWRP, boot into recovery, wait
about 10 seconds. Normal outcomes: the tablet reboots to Android by itself. If it sits on a black
screen for more than a minute, hold Power + Volume Down about 7 seconds. Then read the report:

    adb shell su -c 'for f in /sys/fs/pstore/*; do echo "== $f"; cat "$f"; echo; done'

To put TWRP back, flash `recovery-restore.tar.md5` the same way.

## Reading the result

- A report with `stage=done`: the loader ran our code. Check `el`, `load_addr` and `x0`.
- A report with `EXCEPTION`: it ran and faulted. `esr`/`elr`/`far` say where.
- Only `stage=early alive`: it ran but died between the first and second write.
- Empty pstore and a normal boot: the loader rejected the image, or the reset was cold and DRAM
  did not survive, or Samsung cleared the zone. These look the same, so it is not proof of rejection.
