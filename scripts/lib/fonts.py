#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Fontes do sistema (KitKat lê /system/etc/system_fonts.xml e fallback_fonts.xml).

  fonts.py metrics FONT.ttf...
      Imprime upm e métricas verticais (hhea, que é o que o Skia/Android usa para altura de linha).
  fonts.py samemetrics STOCK.ttf NEW.ttf...
      Falha se a altura de linha (hhea ascent/descent em em) de algum NEW divergir mais de 0,5%
      da STOCK. Mesmas métricas = nenhum texto muda de altura nem é cortado em layout fixo.
  fonts.py systemxml IN OUT
      Acrescenta a família sans-serif-medium (Roboto-Medium/MediumItalic) antes de
      sans-serif-condensed. No 4.4 ela não existe e pedidos por ela caem no Regular.
  fonts.py fallbackxml IN OUT ARQ.ttf
      Põe ARQ.ttf como primeiro fallback (cobre grego/cirílico quando o principal não cobre).
  fonts.py googlesans FONTTOOLS_DIR VAR.ttf OUTDIR STOCK_ROBOTO_REGULAR.ttf
      Gera instâncias estáticas do Google Sans Flex com os nomes de arquivo que o 4.4 espera
      (Roboto-*.ttf), métricas verticais normalizadas para as do Roboto de fábrica e família
      renomeada para "M7s Sans" (as marcas "Google Sans" ficam só com a fonte original).
"""
import os
import re
import struct
import sys


def tables(d):
    n = struct.unpack_from(">H", d, 4)[0]
    t = {}
    for i in range(n):
        tag, _cs, off, ln = struct.unpack_from(">4sIII", d, 12 + 16 * i)
        t[tag.decode("latin-1")] = (off, ln)
    return t


def metrics(path):
    d = open(path, "rb").read()
    t = tables(d)
    upm = struct.unpack_from(">H", d, t["head"][0] + 18)[0]
    asc, desc, gap = struct.unpack_from(">hhh", d, t["hhea"][0] + 4)
    return upm, asc, desc, gap


def cmd_metrics(paths):
    for p in paths:
        upm, a, de, g = metrics(p)
        print(f"{os.path.basename(p)}\tupm={upm}\thhea={a}/{de}/{g}\tlinha={(a - de + g) / upm:.4f}em")


def cmd_samemetrics(stock, news):
    su, sa, sd, sg = metrics(stock)
    ref = ((sa) / su, (sd) / su, sg / su)
    bad = 0
    for p in news:
        u, a, d, g = metrics(p)
        cur = (a / u, d / u, g / u)
        if any(abs(x - y) > 0.005 for x, y in zip(ref, cur)):
            print(f"métricas divergentes: {p} {cur} vs estoque {ref}", file=sys.stderr)
            bad = 1
    if bad:
        sys.exit(1)
    print(f"    métricas verticais iguais às do estoque em {len(news)} fontes")


MEDIUM = """    <family>
        <nameset>
            <name>sans-serif-medium</name>
        </nameset>
        <fileset>
            <file>Roboto-Medium.ttf</file>
            <file>Roboto-MediumItalic.ttf</file>
        </fileset>
    </family>

"""


def cmd_systemxml(src, out):
    s = open(src, encoding="utf-8").read()
    if "sans-serif-medium" in s:
        sys.exit("system_fonts.xml já tem sans-serif-medium")
    m = re.search(r"( *<family>\s*<nameset>\s*<name>sans-serif-condensed</name>)", s)
    if not m:
        sys.exit("não achei a família sans-serif-condensed em system_fonts.xml")
    s = s[:m.start()] + MEDIUM + s[m.start():]
    open(out, "w", encoding="utf-8").write(s)


def cmd_fallbackxml(src, out, fname):
    s = open(src, encoding="utf-8").read()
    i = s.index("<familyset>") + len("<familyset>")
    fam = f"\n    <family>\n        <fileset>\n            <file>{fname}</file>\n        </fileset>\n    </family>"
    open(out, "w", encoding="utf-8").write(s[:i] + fam + s[i:])


# (arquivo, peso, inclinação, largura)
GS_INSTANCES = [
    ("Roboto-Regular.ttf", 400, 0, 100), ("Roboto-Bold.ttf", 700, 0, 100),
    ("Roboto-Italic.ttf", 400, -10, 100), ("Roboto-BoldItalic.ttf", 700, -10, 100),
    ("Roboto-Light.ttf", 300, 0, 100), ("Roboto-LightItalic.ttf", 300, -10, 100),
    ("Roboto-Thin.ttf", 100, 0, 100), ("Roboto-ThinItalic.ttf", 100, -10, 100),
    ("Roboto-Medium.ttf", 500, 0, 100), ("Roboto-MediumItalic.ttf", 500, -10, 100),
    ("RobotoCondensed-Regular.ttf", 400, 0, 75), ("RobotoCondensed-Bold.ttf", 700, 0, 75),
    ("RobotoCondensed-Italic.ttf", 400, -10, 75), ("RobotoCondensed-BoldItalic.ttf", 700, -10, 75),
]


def cmd_googlesans(ftdir, var, outdir, stock_regular):
    sys.path.insert(0, ftdir)
    from fontTools.ttLib import TTFont
    from fontTools.varLib import instancer
    su, sa, sd, sg = metrics(stock_regular)
    os.makedirs(outdir, exist_ok=True)
    for fname, wght, slnt, wdth in GS_INSTANCES:
        f = TTFont(var, recalcTimestamp=False)
        inst = instancer.instantiateVariableFont(
            f, {"wght": wght, "slnt": slnt, "wdth": wdth, "opsz": 18, "ROND": 0},
            updateFontNames=False)
        upm = inst["head"].unitsPerEm
        # altura de linha idêntica ao Roboto de fábrica (em em) — nada corta em layout fixo
        inst["hhea"].ascent = round(sa * upm / su)
        inst["hhea"].descent = round(sd * upm / su)
        inst["hhea"].lineGap = round(sg * upm / su)
        os2 = inst["OS/2"]
        os2.usWinAscent = inst["hhea"].ascent
        os2.usWinDescent = -inst["hhea"].descent
        bold = wght >= 700
        italic = slnt != 0
        os2.fsSelection = (os2.fsSelection & ~0b1100001) | (1 if italic else 0) | (0b100000 if bold else 0) | \
            (0b1000000 if not (bold or italic) else 0)
        inst["head"].macStyle = (1 if bold else 0) | (2 if italic else 0)
        os2.usWeightClass = wght
        inst["post"].italicAngle = float(slnt)
        style = {(False, False): "Regular", (True, False): "Bold", (False, True): "Italic", (True, True): "Bold Italic"}[(bold, italic)]
        fam = "M7s Sans" + (" Condensed" if wdth != 100 else "") + {100: " Thin", 300: " Light", 500: " Medium"}.get(wght, "")
        name = inst["name"]
        for rec in list(name.names):
            if rec.nameID in (1, 2, 3, 4, 6, 16, 17, 21, 22, 25):
                name.removeNames(nameID=rec.nameID)
        full = f"{fam} {style}".replace(" Regular", "") if style != "Regular" else fam
        ps = re.sub(r"[^A-Za-z0-9-]", "", fam.replace(" ", "") + "-" + style.replace(" ", ""))
        for nid, val in ((1, fam), (2, style), (3, f"m7s-kitkat-rom:{ps}"), (4, full), (6, ps)):
            name.setName(val, nid, 3, 1, 0x409)
            name.setName(val, nid, 1, 0, 0)
        inst.save(os.path.join(outdir, fname), reorderTables=True)
        print(f"    {fname}: wght={wght} slnt={slnt} wdth={wdth}")


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["metrics"] and len(a) >= 2:
        cmd_metrics(a[1:])
    elif a[:1] == ["samemetrics"] and len(a) >= 3:
        cmd_samemetrics(a[1], a[2:])
    elif a[:1] == ["systemxml"] and len(a) == 3:
        cmd_systemxml(a[1], a[2])
    elif a[:1] == ["fallbackxml"] and len(a) == 4:
        cmd_fallbackxml(a[1], a[2], a[3])
    elif a[:1] == ["googlesans"] and len(a) == 5:
        cmd_googlesans(*a[1:])
    else:
        sys.exit(__doc__)
