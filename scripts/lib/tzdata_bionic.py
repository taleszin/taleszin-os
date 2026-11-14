#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Gera /system/usr/share/zoneinfo/tzdata no formato do bionic/libcore do Android 4.4 (KitKat).

Formato (o mesmo do ZoneCompactor.java do AOSP 4.4, conferido contra o tzdata2013h de fábrica):
  char version[12]   "tzdata2026f\\0"
  be32 index_offset, data_offset, zonetab_offset
  índice: entradas de 52 B ordenadas por nome: char name[40]; be32 start, length, raw_utc_offset_ms
  dados:  arquivos TZif compilados pelo zic (deduplicados por conteúdo, como os links do original)
  zonetab: linhas não-comentário do zone.tab

O KitKat é 32 bits (time_t 32) e lê só o bloco v1 do TZif; por isso o zic precisa rodar com
'-b fat' (o padrão moderno 'slim' deixa o bloco v1 vazio).

uso:
  tzdata_bionic.py pack ZIC_OUT_DIR ZONE_TAB VERSION OUT
  tzdata_bionic.py check TZDATA ZONA [ZONA...]     imprime transições de DST >= 2016 (via bloco v1)
"""
import hashlib
import os
import re
import struct
import sys

# limites do tzcode do bionic 4.4 (tzfile.h): TZ_MAX_TIMES 1200, TZ_MAX_TYPES 256, TZ_MAX_CHARS 50
MAX_TIMES, MAX_TYPES, MAX_CHARS = 1200, 256, 50


def parse_v1(b):
    if b[:4] != b"TZif":
        raise ValueError("sem magic TZif")
    isutc, isstd, leap, timecnt, typecnt, charcnt = struct.unpack(">6l", b[20:44])
    p = 44
    trans = struct.unpack(f">{timecnt}l", b[p:p + 4 * timecnt]); p += 4 * timecnt
    idx = b[p:p + timecnt]; p += timecnt
    types = [struct.unpack(">lBB", b[p + 6 * i:p + 6 * i + 6]) for i in range(typecnt)]
    return dict(timecnt=timecnt, typecnt=typecnt, charcnt=charcnt, leap=leap, trans=trans, idx=idx, types=types)


def footer(b):
    # TZif v2+: ...\nPOSIX-TZ\n no fim
    if b[4:5] in (b"2", b"3", b"4") and b.endswith(b"\n"):
        return b[b.rstrip(b"\n").rfind(b"\n") + 1:-1].decode()
    return ""


def raw_offset_ms(b, v1):
    f = footer(b)
    m = re.match(r"^(<[^>]+>|[A-Za-z]+)([+-]?)(\d+)(?::(\d+))?(?::(\d+))?", f)
    if m:
        secs = int(m.group(3)) * 3600 + int(m.group(4) or 0) * 60 + int(m.group(5) or 0)
        if m.group(2) != "-":
            secs = -secs  # POSIX: positivo = oeste
        return secs * 1000
    std = [t for t in v1["types"] if t[1] == 0] or v1["types"]
    return std[-1][0] * 1000


def pack(zdir, zonetab, version, out):
    names = []
    for root, _, files in os.walk(zdir):
        for fn in files:
            p = os.path.join(root, fn)
            rel = os.path.relpath(p, zdir)
            with open(p, "rb") as fh:
                if fh.read(4) != b"TZif":
                    continue
            names.append(rel)
    names.sort()
    blobs, index, seen, data = [], [], {}, bytearray()
    for n in names:
        b = open(os.path.join(zdir, n), "rb").read()
        v1 = parse_v1(b)
        if v1["timecnt"] == 0 and v1["typecnt"] <= 1 and footer(b) and "," in footer(b):
            raise SystemExit(f"{n}: bloco v1 vazio — rode o zic com -b fat")
        if v1["timecnt"] > MAX_TIMES or v1["typecnt"] > MAX_TYPES or v1["charcnt"] > MAX_CHARS or v1["leap"]:
            raise SystemExit(f"{n}: excede limites do bionic 4.4 {v1['timecnt'], v1['typecnt'], v1['charcnt'], v1['leap']}")
        if len(n.encode()) >= 40:
            raise SystemExit(f"{n}: nome >= 40 bytes")
        h = hashlib.sha256(b).digest()
        if h not in seen:
            seen[h] = len(data)
            data += b
        index.append(struct.pack(">40s3l", n.encode(), seen[h], len(b), raw_offset_ms(b, v1)))
    zt = "".join(l for l in open(zonetab, encoding="utf-8") if not l.startswith("#")).encode()
    hdr_len = 12 + 12
    io_ = hdr_len
    do_ = io_ + 52 * len(index)
    zo_ = do_ + len(data)
    v = version.encode()
    if not re.fullmatch(rb"tzdata\d{4}[a-z]", v):
        raise SystemExit(f"versão inválida {version}")
    with open(out, "wb") as f:
        f.write(struct.pack(">12s3l", v, io_, do_, zo_))
        f.write(b"".join(index))
        f.write(data)
        f.write(zt)
    print(f"{out}: {len(index)} zonas, {len(seen)} blobs únicos, {zo_ + len(zt)} bytes")


def check(path, zones):
    b = open(path, "rb").read()
    ver = b[:12].split(b"\0")[0].decode()
    io_, do_, zo_ = struct.unpack(">3l", b[12:24])
    ent = {}
    for i in range((do_ - io_) // 52):
        n, s, l, r = struct.unpack(">40s3l", b[io_ + 52 * i:io_ + 52 * i + 52])
        ent[n.split(b"\0")[0].decode()] = (s, l, r)
    print(f"{path}: {ver}, {len(ent)} zonas")
    import datetime as dt
    rc = 0
    for z in zones:
        s, l, r = ent[z]
        v1 = parse_v1(b[do_ + s:do_ + s + l])
        recent = [(t, v1["types"][v1["idx"][i]]) for i, t in enumerate(v1["trans"]) if t >= 1451606400]  # >= 2016
        dst_after_2019 = [t for t, ty in recent if ty[1] and t >= 1577836800]
        last = v1["types"][v1["idx"][-1]] if v1["timecnt"] else v1["types"][0]
        print(f"  {z}: raw={r // 3600000:+d}h transições>=2016: "
              + ", ".join(f"{dt.datetime.fromtimestamp(t, dt.timezone.utc):%Y-%m-%d}{'(DST)' if ty[1] else ''}" for t, ty in recent)
              + f" | vigente={last[0] // 3600:+d}h isdst={last[1]}")
        if dst_after_2019:
            rc = 1
    return rc


if __name__ == "__main__":
    a = sys.argv
    if len(a) >= 6 and a[1] == "pack":
        pack(a[2], a[3], a[4], a[5])
    elif len(a) >= 4 and a[1] == "check":
        sys.exit(check(a[2], a[3:]))
    else:
        sys.exit(__doc__)
