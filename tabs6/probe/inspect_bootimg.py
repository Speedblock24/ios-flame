#!/usr/bin/env python3
"""Print the structure of an Android boot/recovery image (read-only, stdlib only).

  inspect_bootimg.py recovery.img [boot.img ...]

Shows the header fields, what the kernel and ramdisk start with, where appended DTBs
are, and what follows the ramdisk (Samsung marker, AVB footer). The cmdline is printed
with any serialno value masked.
"""
import re, struct, sys

PAGE_DEFAULT = 4096


def pages(n, ps):
    return -(-n // ps) * ps


def sniff(b):
    if b[:16] == b"UNCOMPRESSED_IMG":
        return "Samsung UNCOMPRESSED_IMG wrapper, le32 length 0x%x, then %s" % (
            struct.unpack_from("<I", b, 16)[0], sniff(b[20:]))
    if b[56:60] == b"ARM\x64":
        t, sz, fl = struct.unpack_from("<QQQ", b, 8)
        return "arm64 Image (text_offset 0x%x, image_size 0x%x, flags 0x%x)" % (t, sz, fl)
    if b[:2] == b"\x1f\x8b":
        return "gzip"
    if b[:4] == b"\x04\x22\x4d\x18":
        return "lz4 frame"
    if b[:4] == b"\x02\x21\x4c\x18":
        return "lz4 legacy"
    if b[:2] == b"\x30\x37":
        return "cpio (newc)"
    if b[:4] == b"\xd0\x0d\xfe\xed":
        return "FDT"
    return "unknown, first bytes " + b[:16].hex()


def inspect(path):
    d = open(path, "rb").read()
    print("=" * 70)
    print(path, len(d), "bytes (0x%x)" % len(d))
    if d[:8] != b"ANDROID!":
        print("not an ANDROID! boot image; first bytes", d[:16].hex())
        return
    ks, ka, rs, ra, ss, sa, ta, ps, hv = struct.unpack_from("<9I", d, 8)
    osv = struct.unpack_from("<I", d, 44)[0]
    name = d[48:64].split(b"\0")[0].decode(errors="replace")
    cmd = d[64:576].split(b"\0")[0].decode(errors="replace")
    extra = d[608:1632].split(b"\0")[0].decode(errors="replace")
    mask = lambda s: re.sub(r"(serialno=)\S+", r"\1<masked>", s)
    print("header version %d, page %d, board %r, os_version 0x%x" % (hv, ps, name, osv))
    print("kernel size %d addr 0x%x | ramdisk size %d addr 0x%x | second %d | tags 0x%x" % (ks, ka, rs, ra, ss, ta))
    print("cmdline:", mask(cmd))
    if extra:
        print("extra cmdline:", mask(extra))
    hsz = None
    if hv >= 1:
        dts, dto, hsz = struct.unpack_from("<IQI", d, 1632)
        print("recovery_dtbo size %d offset 0x%x, header_size %d" % (dts, dto, hsz))
    if hv >= 2:
        dsz, daddr = struct.unpack_from("<IQ", d, 1648)
        print("dtb size %d addr 0x%x" % (dsz, daddr))
    ko = ps
    k = d[ko:ko + ks]
    ro = ko + pages(ks, ps)
    r = d[ro:ro + rs]
    print("kernel  @0x%x: %s" % (ko, sniff(k)))
    print("ramdisk @0x%x: %s" % (ro, sniff(r)))
    fdts = []
    for m in re.finditer(b"\xd0\x0d\xfe\xed", k):
        sz = struct.unpack(">I", k[m.start() + 4:m.start() + 8])[0]
        if 64 < sz < (8 << 20) and m.start() + sz <= len(k):
            fdts.append((m.start(), sz))
    print("FDTs inside the kernel blob (offset,size):", fdts[:12], "..." if len(fdts) > 12 else "")
    end = ro + pages(rs, ps)
    if hv >= 1 and dts:
        end = max(end, dto + pages(dts, ps))
    if hv >= 2 and dsz:
        end += pages(dsz, ps)
    print("end of last component: 0x%x" % end)
    print("after it: %r" % d[end:end + 16])
    print("SEANDROIDENFORCE marker:", d[end:end + 16] == b"SEANDROIDENFORCE")
    print("AVBf footer in the last 64 bytes:", b"AVBf" in d[-64:])
    if b"AVBf" in d[-64:]:
        orig, vbo, vbs = struct.unpack_from(">QQQ", d, len(d) - 64 + 12)
        print("  AVB original image size %d, vbmeta offset %d, vbmeta size %d" % (orig, vbo, vbs))


for p in sys.argv[1:]:
    inspect(p)
