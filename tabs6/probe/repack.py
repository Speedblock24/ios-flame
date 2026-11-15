#!/usr/bin/env python3
"""Build a Tab S6 test image from the stock boot.img and a probe Image.

Keeps everything from the stock image except the arm64 Image inside the kernel
blob: same header page (only kernel_size and id change), same appended DTBs,
same ramdisk, the SEANDROIDENFORCE marker, and an unsigned AVB hash footer.

  repack.py --stock-boot ~/boot.img --image out/Image --out recovery-probe.img \
            --partition-name recovery --partition-size-from ~/recovery.img \
            --avbtool ~/avb/avbtool.py

Only reads the stock image; writes only --out.
"""
import argparse, hashlib, os, struct, subprocess, sys

MAGIC = b"UNCOMPRESSED_IMG"
FDT = b"\xd0\x0d\xfe\xed"
SEANDROID = b"SEANDROIDENFORCE"
PAGE = 4096


def die(msg):
    sys.exit("error: " + msg)


def pad(b, n=PAGE):
    return b + b"\0" * (-len(b) % n)


def parse(img):
    if img[:8] != b"ANDROID!":
        die("not an Android boot image")
    ks, ka, rs, ra, ss, sa, ta, ps, hv = struct.unpack_from("<9I", img, 8)
    if hv != 1 or ps != PAGE or ss != 0:
        die(f"unexpected header: version {hv}, page {ps}, second {ss}")
    koff = PAGE
    roff = koff + len(pad(b"\0" * ks))
    return dict(ks=ks, rs=rs, koff=koff, roff=roff, id=img[576:608])


def boot_id(kernel, ramdisk):
    outs = []
    for variant in (False, True):
        h = hashlib.sha1()
        for d in (kernel, ramdisk, b""):
            h.update(d)
            h.update(struct.pack("<I", len(d)))
        if variant:
            h.update(b"")
            h.update(struct.pack("<I", 0))
        outs.append(h.digest().ljust(32, b"\0"))
    return outs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stock-boot", required=True)
    ap.add_argument("--image", required=True, help="probe arm64 Image")
    ap.add_argument("--out", required=True)
    ap.add_argument("--partition-name", default="recovery")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--partition-size", type=int)
    g.add_argument("--partition-size-from", help="a full-partition backup; its size is used")
    ap.add_argument("--avbtool", help="path to avbtool.py (AOSP external/avb)")
    ap.add_argument("--no-avb", action="store_true", help="skip the AVB footer (testing only)")
    a = ap.parse_args()

    stock = open(a.stock_boot, "rb").read()
    hdr = parse(stock)
    kblob = stock[hdr["koff"]:hdr["koff"] + hdr["ks"]]
    ramdisk = stock[hdr["roff"]:hdr["roff"] + hdr["rs"]]
    if kblob[:16] != MAGIC:
        die("stock kernel does not start with UNCOMPRESSED_IMG")
    ilen = struct.unpack_from("<I", kblob, 16)[0]
    tail = kblob[20 + ilen:]
    if tail[:4] != FDT:
        die("no DTB right after the stock Image")
    ndtb = tail.count(FDT)

    image = open(a.image, "rb").read()
    if image[56:60] != b"ARM\x64" or len(image) % 4:
        die("probe Image: bad arm64 header or size")
    new_k = MAGIC + struct.pack("<I", len(image)) + image + tail

    # stock marker and footer layout, to check our assumptions about it
    rend = hdr["roff"] + len(pad(b"\0" * hdr["rs"]))
    marker_ok = stock[rend:rend + 16] == SEANDROID
    if not marker_ok:
        print("warning: SEANDROIDENFORCE not where expected in the stock image")

    header = bytearray(stock[:PAGE])
    struct.pack_into("<I", header, 8, len(new_k))
    ids = boot_id(kblob, ramdisk)
    if hdr["id"] in ids:
        print("stock id matches sha1 variant", ids.index(hdr["id"]))
        newid = boot_id(new_k, ramdisk)[ids.index(hdr["id"])]
    else:
        print("note: stock id not reproducible; using the plain sha1 variant")
        newid = boot_id(new_k, ramdisk)[0]
    header[576:608] = newid

    out = bytes(header) + pad(new_k) + pad(ramdisk)
    if marker_ok:
        out += SEANDROID
    open(a.out, "wb").write(out)

    if not a.no_avb:
        if not a.avbtool:
            die("--avbtool is required (or --no-avb for testing)")
        psize = a.partition_size or os.path.getsize(a.partition_size_from)
        if psize % PAGE or psize < len(out) + 4096 or psize > (1 << 30):
            die(f"implausible partition size {psize}")
        subprocess.run([sys.executable, a.avbtool, "add_hash_footer", "--image", a.out,
                        "--partition_size", str(psize), "--partition_name", a.partition_name,
                        "--salt", os.urandom(32).hex()],  # avbtool reads /dev/urandom otherwise: not on Windows
                       check=True)

    # re-read what we wrote and check it against the stock image
    o = open(a.out, "rb").read()
    h2 = parse(o)
    assert h2["ks"] == len(new_k) and h2["rs"] == hdr["rs"]
    assert o[h2["koff"]:h2["koff"] + h2["ks"]] == new_k
    assert o[h2["roff"]:h2["roff"] + h2["rs"]] == ramdisk
    assert o[:8] == stock[:8] and o[12:576] == stock[12:576] and o[608:PAGE] == stock[608:PAGE]
    print(f"kernel blob {len(new_k)} bytes: Image {len(image)} + {ndtb} stock FDT(s) kept ({len(tail)} bytes)")
    print(f"ramdisk {hdr['rs']} bytes (unchanged), image {len(o)} bytes")
    print("sha256", hashlib.sha256(o).hexdigest())


if __name__ == "__main__":
    main()
