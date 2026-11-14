#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""buildprop.py ENTRADA SAIDA CHAVE=VALOR...

Remove TODAS as ocorrências de cada chave (o estoque tem duplicatas, ex.: ro.kernel.android.checkjni
aparece com 0 e depois 1 — vale a última) e acrescenta um bloco único no fim. Chave com valor vazio
('CHAVE=') só remove. Preserva o resto byte a byte.
"""
import re
import sys


def main(src, dst, pairs):
    kv = []
    for p in pairs:
        k, v = p.split("=", 1)
        kv.append((k.strip(), v))
    keys = {k for k, _ in kv}
    out = []
    removed = []
    for line in open(src, encoding="utf-8", errors="surrogateescape"):
        m = re.match(r"^\s*([^#=\s][^=]*?)\s*=", line)
        if m and m.group(1) in keys:
            removed.append(line.rstrip("\n"))
            continue
        out.append(line)
    if out and not out[-1].endswith("\n"):
        out[-1] += "\n"
    out.append("\n# --- m7s-kitkat-rom (scripts/lib/buildprop.py; ver docs/README.md) ---\n")
    for k, v in kv:
        if v != "":
            out.append(f"{k}={v}\n")
    with open(dst, "w", encoding="utf-8", errors="surrogateescape") as f:
        f.writelines(out)
    for r in removed:
        print(f"  removido: {r}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2], sys.argv[3:])
