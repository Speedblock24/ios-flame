#!/bin/bash
# Build the Tab S6 stage-0 probe: out/Image (raw arm64 Image, linked at 0).
# Needs clang + ld.lld + llvm-objcopy (+ llvm-readelf/llvm-nm for the checks).
set -euo pipefail
cd "$(dirname "$0")"
CC="clang --target=aarch64-none-elf"
CFLAGS="-O2 -ffreestanding -nostdlib -fno-builtin -fno-pic -fno-pie -mgeneral-regs-only -mstrict-align
	-fno-stack-protector -fno-asynchronous-unwind-tables -Wall -Wextra"
mkdir -p out
$CC $CFLAGS -c start.S -o out/start.o
$CC $CFLAGS -c probe.c -o out/probe.o
# Only start.o may carry an absolute relocation (image_size, linked at 0).
abs=$(llvm-readelf -r out/probe.o | grep -c R_AARCH64_ABS64 || true)
[ "$abs" = 0 ] || { echo "error: $abs absolute relocations in probe.o" >&2; exit 1; }
ld.lld -static -nostdlib -T probe.ld --build-id=none -N out/start.o out/probe.o -o out/probe.elf
llvm-objcopy -O binary out/probe.elf out/Image
# Pad to the full image size so .bss/stack exist as zero bytes in the file.
size=$(llvm-nm out/probe.elf | awk '$3=="_end"{print $1}')
truncate -s $((16#$size)) out/Image
sz=$(stat -c %s out/Image)
[ $((sz % 4)) = 0 ] || { echo "error: Image size $sz is not 4-byte aligned" >&2; exit 1; }
[ "$(od -An -tx1 -j56 -N4 out/Image | tr -d ' ')" = 41524d64 ] || { echo "error: arm64 magic missing" >&2; exit 1; }
ls -l out/Image
sha256sum out/Image
