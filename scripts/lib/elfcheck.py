#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Checagem offline de ligação dinâmica (ELF32 ARM), só stdlib.

  elfcheck.py needed BIN          lista as bibliotecas DT_NEEDED
  elfcheck.py resolve BIN LIBDIR  falha se algum símbolo indefinido forte de BIN não for
                                  exportado pelas libs DT_NEEDED encontradas em LIBDIR
Usado para o app_process do Xposed: se um símbolo faltar, o linker aborta o zygote = bootloop.
"""
import os
import struct
import sys


def parse(path):
    d = open(path, "rb").read()
    if d[:4] != b"\x7fELF" or d[4] != 1 or d[5] != 1:
        sys.exit(f"{path}: não é ELF32 little-endian")
    shoff, = struct.unpack_from("<I", d, 0x20)
    shentsize, shnum, _ = struct.unpack_from("<HHH", d, 0x2E)
    sh = [struct.unpack_from("<IIIIIIIIII", d, shoff + i * shentsize) for i in range(shnum)]

    def cstr(off):
        return d[off:d.index(b"\0", off)].decode()

    undef, defined, needed = set(), set(), []
    for s in sh:
        if s[1] == 11:  # SHT_DYNSYM
            stro = sh[s[6]][4]
            for i in range(s[5] // 16):
                name, _v, _sz, info, _o, shndx = struct.unpack_from("<IIIBBH", d, s[4] + i * 16)
                n = cstr(stro + name)
                if not n:
                    continue
                if shndx == 0:
                    if info >> 4 != 2:  # ignora STB_WEAK
                        undef.add(n)
                else:
                    defined.add(n)
        elif s[1] == 6:  # SHT_DYNAMIC
            stro = sh[s[6]][4]
            for i in range(s[5] // 8):
                tag, val = struct.unpack_from("<iI", d, s[4] + i * 8)
                if tag == 1:
                    needed.append(cstr(stro + val))
    return undef, defined, needed


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["needed"] and len(a) == 2:
        print("\n".join(parse(a[1])[2]))
    elif a[:1] == ["resolve"] and len(a) == 3:
        undef, _, needed = parse(a[1])
        avail = set()
        for n in needed:
            p = os.path.join(a[2], n)
            if not os.path.isfile(p):
                sys.exit(f"biblioteca {n} não existe no firmware")
            avail |= parse(p)[1]
        missing = sorted(undef - avail)
        for m in missing:
            print(f"    sem resolução: {m}", file=sys.stderr)
        if missing:
            sys.exit(1)
        print(f"    {os.path.basename(a[1])}: {len(undef)} símbolos, todos resolvidos em {len(needed)} libs do firmware")
    else:
        sys.exit(__doc__)
