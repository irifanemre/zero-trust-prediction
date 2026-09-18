#!/usr/bin/env python3
"""CERT Insider Threat Test Dataset indiricisi (SEI/CMU, figshare, CC BY 4.0) — sha256 doğrulamalı.

Kullanım:
    python scripts/download_cert.py --release r1 --dest ./cert_data          # 87 MB, cevap anahtarı yok (gürültü tabanı)
    python scripts/download_cert.py --release r4.2 --dest ./cert_data        # 4.8 GB, 70 etiketli insider
    python scripts/download_cert.py --list

Kaynak: https://doi.org/10.1184/R1/12841247
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tarfile
import urllib.request
from pathlib import Path

ARTICLE = "https://api.figshare.com/v2/articles/12841247"
CHUNK = 1 << 20


def fetch_index() -> dict:
    with urllib.request.urlopen(ARTICLE, timeout=60) as r:
        return {f["name"]: f for f in json.load(r)["files"]}


def download(url: str, dest: Path, size: int) -> None:
    done = dest.stat().st_size if dest.exists() else 0
    if done == size:
        print(f"  mevcut: {dest.name}")
        return
    req = urllib.request.Request(url, headers={"Range": f"bytes={done}-"} if done else {})
    mode = "ab" if done else "wb"
    with urllib.request.urlopen(req, timeout=120) as r, open(dest, mode) as f:
        while True:
            block = r.read(CHUNK)
            if not block:
                break
            f.write(block)
            done += len(block)
            print(f"\r  {dest.name}: {done / 1e6:,.0f} / {size / 1e6:,.0f} MB", end="", flush=True)
    print()


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(CHUNK), b""):
            h.update(block)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--release", default="r4.2", help="r1, r2, r3.1, r3.2, r4.1, r4.2, r5.1, r5.2, r6.1, r6.2")
    ap.add_argument("--dest", default="./cert_data")
    ap.add_argument("--list", action="store_true", help="dosyaları ve boyutları listele")
    ap.add_argument("--no-extract", action="store_true")
    args = ap.parse_args()
    index = fetch_index()
    if args.list:
        for name, f in index.items():
            print(f"{name:<24} {f['size'] / 1e6:>10,.1f} MB")
        return 0
    dest = Path(args.dest)
    dest.mkdir(parents=True, exist_ok=True)
    checksums = {}
    with urllib.request.urlopen(index["CHECKSUMS-sha256.txt"]["download_url"], timeout=60) as r:
        for line in r.read().decode().splitlines():
            if line.strip():
                digest, name = line.split()
                checksums[name.strip()] = digest
    for name in (f"{args.release}.tar.bz2", "answers.tar.bz2"):
        if name not in index:
            sys.exit(f"Bilinmeyen dosya: {name}")
        path = dest / name
        print(f"{name} ({index[name]['size'] / 1e6:,.1f} MB)")
        download(index[name]["download_url"], path, index[name]["size"])
        digest = sha256(path)
        if checksums.get(name) and digest != checksums[name]:
            sys.exit(f"SHA256 uyuşmuyor: {name}\n  beklenen {checksums[name]}\n  hesaplanan {digest}")
        print(f"  sha256 doğrulandı: {digest[:16]}…")
        if not args.no_extract:
            print(f"  açılıyor → {dest}")
            with tarfile.open(path, "r:bz2") as tar:
                tar.extractall(dest, filter="data")
    print("Tamam. Koşu örneği:")
    print(f"  ztp --cert-dir {dest}/{args.release} --end 2010-11-30 --days 90 --budget 10 --tenant cert --out ./ztp_out")
    return 0


if __name__ == "__main__":
    sys.exit(main())
