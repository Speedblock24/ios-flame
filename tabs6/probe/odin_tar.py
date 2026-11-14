#!/usr/bin/env python3
"""Wrap a partition image into an Odin AP .tar.md5.

  odin_tar.py recovery-probe.img recovery-probe.tar.md5            (member: recovery.img)
  odin_tar.py ~/recovery.img recovery-restore.tar.md5              (the TWRP backup)
"""
import hashlib, os, sys, tarfile

src, out = sys.argv[1], sys.argv[2]
member = sys.argv[3] if len(sys.argv) > 3 else "recovery.img"
with tarfile.open(out, "w", format=tarfile.USTAR_FORMAT) as t:
    ti = t.gettarinfo(src, arcname=member)
    ti.uid = ti.gid = 0
    ti.uname = ti.gname = ""
    with open(src, "rb") as f:
        t.addfile(ti, f)
md5 = hashlib.md5(open(out, "rb").read()).hexdigest()
with open(out, "ab") as f:
    f.write(f"{md5}  {os.path.basename(out)}\n".encode())
print(out, md5)
