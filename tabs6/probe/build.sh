#!/bin/bash
# Build the Tab S6 stage-0 probe: out/Image (reset at once), out/Image-hang (spins forever),
# out/Image-delay20 and out/Image-delay50 (wait 20 s / 50 s, then reset).
# Needs clang + ld.lld + llvm-objcopy (+ llvm-readelf/llvm-nm for the checks).
set -euo pipefail
cd "$(dirname "$0")"
CC="clang --target=aarch64-none-elf"
CFLAGS="-O2 -ffreestanding -nostdlib -fno-builtin -fno-pic -fno-pie -mgeneral-regs-only -mstrict-align
	-fno-stack-protector -fno-asynchronous-unwind-tables -Wall -Wextra"
mkdir -p out
$CC $CFLAGS -c start.S -o out/start.o

# build NAME EXTRA_CFLAGS
build() {
	local name=$1 extra=$2
	$CC $CFLAGS $extra -c probe.c -o out/$name.o
	# Only start.o may carry an absolute relocation (image_size, linked at 0).
	local abs
	abs=$(llvm-readelf -r out/$name.o | grep -c R_AARCH64_ABS64 || true)
	[ "$abs" = 0 ] || { echo "error: $abs absolute relocations in $name.o" >&2; exit 1; }
	ld.lld -static -nostdlib -T probe.ld --build-id=none -N out/start.o out/$name.o -o out/$name.elf
	local img=out/$3
	llvm-objcopy -O binary out/$name.elf $img
	# Pad to the full image size so .bss/stack exist as zero bytes in the file.
	local size
	size=$(llvm-nm out/$name.elf | awk '$3=="_end"{print $1}')
	truncate -s $((16#$size)) $img
	local sz
	sz=$(stat -c %s $img)
	[ $((sz % 4)) = 0 ] || { echo "error: $img size $sz is not 4-byte aligned" >&2; exit 1; }
	[ "$(od -An -tx1 -j56 -N4 $img | tr -d ' ')" = 41524d64 ] || { echo "error: arm64 magic missing in $img" >&2; exit 1; }
	ls -l $img
	sha256sum $img
}

build probe "" Image
build probe-hang "-DPROBE_HANG" Image-hang
build probe-delay20 "-DRESET_DELAY=20" Image-delay20
build probe-delay50 "-DRESET_DELAY=50" Image-delay50
