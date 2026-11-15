#!/usr/bin/env python3
"""One step: probe Image -> recovery image (keeps the stock recovery layout) -> plain Odin .tar.

  make_flash.py --image out/Image-delay20 --name delay20

Defaults match the Windows folders used so far. Writes <outdir>/recovery-probe-<name>.img and
.tar (member recovery.img), then prints the sha256 of the image and the size of the tar.
"""
import argparse, hashlib, os, subprocess, sys, tarfile

here = os.path.dirname(os.path.abspath(__file__))
ap = argparse.ArgumentParser()
ap.add_argument("--image", required=True)
ap.add_argument("--name", required=True)
ap.add_argument("--stock", default="~/OneDrive/Desktop/t6info/recovery.img",
                help="the recovery image whose layout is kept (and whose size is the partition size)")
ap.add_argument("--outdir", default="~/Downloads/tabs6-out")
ap.add_argument("--avbtool", default="~/avb/avbtool.py")
ap.add_argument("--no-avb", action="store_true")
a = ap.parse_args()
stock, outdir, avb = (os.path.expanduser(p) for p in (a.stock, a.outdir, a.avbtool))
os.makedirs(outdir, exist_ok=True)
img = os.path.join(outdir, f"recovery-probe-{a.name}.img")
tar = os.path.join(outdir, f"recovery-probe-{a.name}.tar")

cmd = [sys.executable, os.path.join(here, "repack.py"), "--stock-boot", stock, "--image", a.image,
       "--out", img, "--partition-name", "recovery", "--partition-size-from", stock]
cmd += ["--no-avb"] if a.no_avb else ["--avbtool", avb]
subprocess.run(cmd, check=True)

with tarfile.open(tar, "w", format=tarfile.USTAR_FORMAT) as t:
    ti = t.gettarinfo(img, arcname="recovery.img")
    ti.uid = ti.gid = 0
    ti.uname = ti.gname = ""
    with open(img, "rb") as f:
        t.addfile(ti, f)

print()
print("image", img, os.path.getsize(img), "bytes (partition", os.path.getsize(stock), ")")
print("image sha256", hashlib.sha256(open(img, "rb").read()).hexdigest())
print("tar  ", tar, os.path.getsize(tar), "bytes")
if not a.no_avb:
    assert os.path.getsize(img) == os.path.getsize(stock), "image size differs from the stock recovery"
