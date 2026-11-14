#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Leitura e escrita de imagens Rockchip (RKFW update.img / RKAF) e do boot.img.

Subcomandos:
  extract-zip ZIP MEMBER_SUFFIX OUT     extrai do zip o membro que termina em MEMBER_SUFFIX
  unpack UPDATE_IMG OUTDIR              RKFW -> loader + RKAF; RKAF -> partições (paths do package-file)
  repack UPDATE_IMG OUTDIR NAME=FILE... reconstrói o update.img trocando partições (ex.: system=out/system.img)
  ramdisk BOOT_IMG OUTDIR               extrai o ramdisk (gzip + cpio newc) do boot.img Android
  info UPDATE_IMG                       lista o conteúdo

Formatos (engenharia reversa, conferida por ida-e-volta byte a byte contra o firmware oficial):
  RKFW: cabeçalho 0x66 B; u32le @0x19 off/@0x1d tam do loader; @0x21 off/@0x25 tam do RKAF;
        trailer = 32 B ASCII = md5 hex de tudo que vem antes.
  RKAF: 'RKAF', u32le @4 = tamanho_total-4, modelo @8, fabricante @0x48, n @0x88,
        entradas de 0x70 B a partir de 0x8c: nome[32] caminho[64] off nand_addr nblocos(2 KiB) tamanho;
        dados alinhados em 2 KiB, nblocos = tamanho//2048 + 1; trailer = u32le CRC rockchip (poly 0x04c10db7, init 0, não refletido).
"""
import gzip
import hashlib
import io
import os
import struct
import subprocess
import sys
import zipfile

ALIGN = 0x800


def die(msg):
    sys.exit(f"rkimg: erro: {msg}")


def rkcrc(path, length, helper):
    out = subprocess.run([helper, path, str(length)], check=True, capture_output=True, text=True).stdout
    return int(out.strip(), 16)


def parse_rkfw(f):
    f.seek(0)
    h = f.read(0x66)
    if h[:4] != b"RKFW":
        die("não é RKFW")
    loff, lsz, ioff, isz = struct.unpack_from("<4I", h, 0x19)
    return h, loff, lsz, ioff, isz


def parse_rkaf(buf):
    if buf[:4] != b"RKAF":
        die("não é RKAF")
    n = struct.unpack_from("<I", buf, 0x88)[0]
    ents = []
    for i in range(n):
        p = 0x8C + i * 0x70
        raw = buf[p:p + 0x70]
        name = raw[:0x20].split(b"\0")[0].decode()
        path = raw[0x20:0x60].split(b"\0")[0].decode()
        off, nand, nblk, size = struct.unpack_from("<4I", raw, 0x60)
        ents.append(dict(name=name, path=path, off=off, nand=nand, nblk=nblk, size=size, raw=raw))
    return ents


def copy_range(src, off, size, dst):
    src.seek(off)
    left = size
    while left:
        chunk = src.read(min(left, 8 << 20))
        if not chunk:
            die("arquivo truncado")
        dst.write(chunk)
        left -= len(chunk)


def cmd_extract_zip(zpath, suffix, out):
    with zipfile.ZipFile(zpath) as z:
        names = [n for n in z.namelist() if n.endswith(suffix)]
        if len(names) != 1:
            die(f"esperava 1 membro terminando em {suffix}, achei {names}")
        with z.open(names[0]) as s, open(out, "wb") as d:
            while True:
                b = s.read(8 << 20)
                if not b:
                    break
                d.write(b)


def cmd_unpack(img, outdir):
    os.makedirs(outdir, exist_ok=True)
    with open(img, "rb") as f:
        h, loff, lsz, ioff, isz = parse_rkfw(f)
        with open(os.path.join(outdir, "rkfw-header.bin"), "wb") as d:
            d.write(h)
        with open(os.path.join(outdir, "loader.bin"), "wb") as d:
            copy_range(f, loff, lsz, d)
        f.seek(ioff)
        hdr = f.read(0x2000)
        with open(os.path.join(outdir, "rkaf-header.bin"), "wb") as d:
            d.write(hdr[:ALIGN])
        for e in parse_rkaf(hdr):
            if e["path"] in ("SELF", "RESERVED") or e["size"] == 0:
                continue
            dest = os.path.join(outdir, "rkaf", e["name"])
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "wb") as d:
                copy_range(f, ioff + e["off"], e["size"], d)
            print(f"{e['name']:16s} nand=0x{e['nand']:08x} size={e['size']}")


def cmd_info(img):
    with open(img, "rb") as f:
        h, loff, lsz, ioff, isz = parse_rkfw(f)
        print(f"RKFW loader {loff:#x}+{lsz:#x} rkaf {ioff:#x}+{isz:#x}")
        f.seek(ioff)
        for e in parse_rkaf(f.read(0x2000)):
            print(f"{e['name']:16s} {e['path']:40s} off={e['off']:#010x} nand={e['nand']:#010x} nblk={e['nblk']:#x} size={e['size']:#x}")


def cmd_repack(orig, out, repl, helper):
    """Reconstrói RKFW/RKAF. Cabeçalhos copiados do original (preserva bytes não documentados);
    só tamanhos, offsets, CRC e MD5 são recalculados."""
    repl = dict(r.split("=", 1) for r in repl)
    with open(orig, "rb") as f:
        rkfw_h, loff, lsz, ioff, isz = parse_rkfw(f)
        f.seek(ioff)
        hdr = bytearray(f.read(ALIGN))
        ents = parse_rkaf(bytes(hdr) + f.read(0x2000 - ALIGN))
        for k in repl:
            if k not in [e["name"] for e in ents]:
                die(f"partição {k} não existe no pacote")
        tmp = out + ".rkaf.tmp"
        with open(tmp, "wb") as d:
            d.write(b"\0" * ALIGN)
            pos = ALIGN
            first = min(e["off"] for e in ents if e["size"])
            if first > pos:  # região entre cabeçalho e 1o arquivo (vazia no original)
                copy_range(f, ioff + pos, first - pos, d)
                pos = first
            opos = pos
            for i, e in enumerate(ents):
                if e["size"] == 0:
                    continue
                if e["off"] != opos:  # confere que entendemos o layout do original
                    die(f"layout inesperado em {e['name']}: {e['off']:#x} != {opos:#x}")
                opos += (e["size"] // ALIGN + 1) * ALIGN
                src = repl.get(e["name"])
                size = os.path.getsize(src) if src else e["size"]
                if src:
                    with open(src, "rb") as s:
                        copy_range(s, 0, size, d)
                else:
                    copy_range(f, ioff + e["off"], size, d)
                nblk = size // ALIGN + 1  # afptool sempre reserva +1 bloco (mesmo com tamanho múltiplo de 2 KiB)
                pad = nblk * ALIGN - size
                d.write(b"\0" * pad)
                struct.pack_into("<4I", hdr, 0x8C + i * 0x70 + 0x60, pos, e["nand"], nblk, size)
                pos += nblk * ALIGN
        struct.pack_into("<I", hdr, 4, pos)  # total = pos + 4 (crc) ; campo = total - 4
        with open(tmp, "r+b") as d:
            d.write(hdr)
        crc = rkcrc(tmp, pos, helper)
        with open(tmp, "ab") as d:
            d.write(struct.pack("<I", crc))
        rkaf_size = pos + 4
        # RKFW
        h = bytearray(rkfw_h)
        struct.pack_into("<I", h, 0x25, rkaf_size)
        md5 = hashlib.md5()
        with open(out, "wb") as d:
            def w(b):
                d.write(b)
                md5.update(b)
            w(bytes(h))
            f.seek(loff)
            w(f.read(lsz))
            if loff + lsz != ioff:
                die("RKFW com lacuna entre loader e RKAF")
            with open(tmp, "rb") as s:
                while True:
                    b = s.read(8 << 20)
                    if not b:
                        break
                    w(b)
            d.write(md5.hexdigest().encode())
        os.unlink(tmp)


def cmd_ramdisk(boot, outdir):
    b = open(boot, "rb").read()
    if b[:8] != b"ANDROID!":
        die("boot.img sem cabeçalho ANDROID!")
    ks, ka, rs, ra, ss, sa, ta, ps = struct.unpack_from("<8I", b, 8)
    off = ps + ((ks + ps - 1) // ps) * ps
    data = gzip.decompress(b[off:off + rs])
    os.makedirs(outdir, exist_ok=True)
    p = 0
    while True:
        if data[p:p + 6] != b"070701":
            die("cpio não-newc")
        fld = [int(data[p + 6 + i * 8:p + 14 + i * 8], 16) for i in range(13)]
        mode, fsize, nsize = fld[1], fld[6], fld[11]
        name = data[p + 110:p + 110 + nsize - 1].decode()
        p = (p + 110 + nsize + 3) & ~3
        content = data[p:p + fsize]
        p = (p + fsize + 3) & ~3
        if name == "TRAILER!!!":
            break
        if (mode & 0o170000) == 0o100000 and "/" not in name:
            with open(os.path.join(outdir, name), "wb") as d:
                d.write(content)


def main(a):
    if len(a) < 2:
        die(__doc__)
    c = a[1]
    if c == "extract-zip":
        cmd_extract_zip(a[2], a[3], a[4])
    elif c == "unpack":
        cmd_unpack(a[2], a[3])
    elif c == "info":
        cmd_info(a[2])
    elif c == "repack":
        helper = os.environ.get("RKCRC32") or die("defina RKCRC32 (binário de scripts/lib/rkcrc32.c)")
        cmd_repack(a[2], a[3], a[4:], helper)
    elif c == "ramdisk":
        cmd_ramdisk(a[2], a[3])
    else:
        die(f"subcomando desconhecido {c}")


if __name__ == "__main__":
    main(sys.argv)
