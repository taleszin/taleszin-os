#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Arte gerada (só stdlib, determinística — mesmo bytes a cada build).

  art.py wallpaper OUT.png LARGURA ALTURA
      Papel de parede escuro estático: gradiente diagonal grafite→azul-petróleo com duas
      formas suaves no estilo Material You. Dither ordenado 4x4 evita faixas (banding).
  art.py bootanim OUT.zip
      bootanimation.zip curto (160x160, 20 fps, loop): spinner circular indeterminado do
      Material (arco que gira e "respira") em azul sobre preto. Zip sem compressão (STORED),
      como o bootanimation do 4.4 exige.
"""
import math
import struct
import sys
import zipfile
import zlib

BAYER4 = [[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]


def png(width, height, rows, alpha=False):
    """rows: lista de bytes (já com o byte de filtro 0 no início de cada linha)."""
    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6 if alpha else 2, 0, 0, 0)
    raw = b"".join(rows)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")


def lerp(a, b, t):
    return a + (b - a) * t


def smoothstep(e0, e1, x):
    t = min(1.0, max(0.0, (x - e0) / (e1 - e0)))
    return t * t * (3 - 2 * t)


def wallpaper(out, w, h):
    top = (0x10, 0x13, 0x18)      # grafite quase preto
    bottom = (0x0d, 0x22, 0x2b)   # azul-petróleo escuro
    blob1 = (0x1f, 0x4e, 0x5f)    # forma grande, canto inferior direito
    blob2 = (0x2a, 0x2f, 0x45)    # forma menor, canto superior esquerdo
    s = max(w, h)
    c1 = (w * 0.82, h * 0.86, s * 0.62)
    c2 = (w * 0.12, h * 0.10, s * 0.34)
    rows = []
    for y in range(h):
        row = bytearray(b"\x00")
        for x in range(w):
            t = (x / w * 0.35 + y / h * 0.65)
            col = [lerp(top[i], bottom[i], t) for i in range(3)]
            d1 = math.hypot(x - c1[0], y - c1[1]) / c1[2]
            a1 = (1 - smoothstep(0.55, 1.0, d1)) * 0.55
            d2 = math.hypot(x - c2[0], y - c2[1]) / c2[2]
            a2 = (1 - smoothstep(0.50, 1.0, d2)) * 0.45
            col = [lerp(col[i], blob1[i], a1) for i in range(3)]
            col = [lerp(col[i], blob2[i], a2) for i in range(3)]
            a3 = court_alpha(x + 0.5, y + 0.5, w, h, s)
            if a3 > 0:
                col = [lerp(col[i], COURT[i], a3) for i in range(3)]
            dth = (BAYER4[y & 3][x & 3] + 0.5) / 16.0
            row.extend(min(255, int(v + dth)) for v in col)
        rows.append(bytes(row))
    open(out, "wb").write(png(w, h, rows))


# Meia quadra de basquete vista de cima (identidade da ROM: Prancheta do Taleszin), em laranja
# bem translúcido sobre o degradê. Linhas antisserrilhadas pela distância ao traço.
COURT = (0xff, 0x7a, 0x1a)
COURT_ALPHA = 0.20


def _seg(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - ax - t * dx, py - ay - t * dy)


def court_alpha(x, y, w, h, s):
    lw = max(1.4, s / 520)                       # meia espessura do traço
    cx = w / 2
    base = h * 0.93                              # linha de fundo
    rim_y = base - s * 0.065
    key_w, key_h = s * 0.115, s * 0.30
    ft_y = base - key_h
    r3 = s * 0.40
    corner_y = rim_y - math.sqrt(max(r3 * r3 - (s * 0.37) ** 2, 0))
    mid_y = base - s * 0.78                      # linha do meio da quadra
    d = 1e9
    d = min(d, _seg(x, y, w * 0.04, base, w * 0.96, base))
    d = min(d, _seg(x, y, cx - key_w, base, cx - key_w, ft_y))
    d = min(d, _seg(x, y, cx + key_w, base, cx + key_w, ft_y))
    d = min(d, _seg(x, y, cx - key_w, ft_y, cx + key_w, ft_y))
    d = min(d, abs(math.hypot(x - cx, y - ft_y) - key_w))                 # círculo do lance livre
    if y <= corner_y:
        d = min(d, abs(math.hypot(x - cx, y - rim_y) - r3))               # arco de três
    d = min(d, _seg(x, y, cx - s * 0.37, base, cx - s * 0.37, corner_y))
    d = min(d, _seg(x, y, cx + s * 0.37, base, cx + s * 0.37, corner_y))
    d = min(d, abs(math.hypot(x - cx, y - rim_y) - s * 0.018))            # aro
    d = min(d, _seg(x, y, cx - s * 0.05, base - s * 0.04, cx + s * 0.05, base - s * 0.04))  # tabela
    d = min(d, _seg(x, y, w * 0.04, mid_y, w * 0.96, mid_y))
    d = min(d, abs(math.hypot(x - cx, y - mid_y) - s * 0.12))             # círculo central
    d = min(d, _seg(x, y, w * 0.04, mid_y, w * 0.04, base))
    d = min(d, _seg(x, y, w * 0.96, mid_y, w * 0.96, base))
    if d > lw + 1:
        return 0.0
    return COURT_ALPHA * (1 - smoothstep(lw - 0.6, lw + 0.6, d))


def bootanim(out):
    size, fps, frames = 160, 20, 30
    cx = cy = (size - 1) / 2
    r_out, r_in = 46.0, 38.0                # arco de 8 px de espessura
    blue = (0xff, 0x7a, 0x1a)               # laranja da Taleszin OS (o nome da variável ficou da v1.1)
    track = (0x1c, 0x1f, 0x24)              # trilha discreta
    ball_r = 27.0                           # bola de basquete no centro, parada; o arco gira em volta
    ball = (0xe8, 0x6a, 0x12)
    seam = (0x14, 0x10, 0x0c)
    zf = zipfile.ZipFile(out, "w", zipfile.ZIP_STORED)

    def add(name, data):
        zi = zipfile.ZipInfo(name, date_time=(2026, 11, 13, 0, 0, 0))
        zi.compress_type = zipfile.ZIP_STORED
        zi.external_attr = 0o644 << 16
        zi.create_system = 3
        zf.writestr(zi, data)

    add("desc.txt", f"{size} {size} {fps}\np 0 0 part0\n".encode())
    for f in range(frames):
        ph = f / frames
        head = (ph * 360 * 1.0 + 270 * (0.5 - 0.5 * math.cos(2 * math.pi * ph))) % 360
        sweep = 40 + 230 * (0.5 - 0.5 * math.cos(2 * math.pi * ph))  # 40°..270°
        start = (head - sweep) % 360
        rows = []
        for y in range(size):
            row = bytearray(b"\x00")
            for x in range(size):
                dx, dy = x - cx, y - cy
                d = math.hypot(dx, dy)
                ring = min(smoothstep(r_in - 1, r_in, d), 1 - smoothstep(r_out, r_out + 1, d))
                if ring <= 0:
                    bal = 1 - smoothstep(ball_r - 0.5, ball_r + 0.5, d)
                    if bal <= 0:
                        row.extend(b"\x00\x00\x00")
                        continue
                    # gomos: vertical, horizontal e dois arcos laterais (1,6 px de traço)
                    sd = min(abs(dx), abs(dy),
                             abs(math.hypot(dx - ball_r * 1.32, dy) - ball_r * 0.95),
                             abs(math.hypot(dx + ball_r * 1.32, dy) - ball_r * 0.95))
                    sm = 1 - smoothstep(0.8, 1.6, sd)
                    shade = 1 - 0.25 * smoothstep(0, ball_r, math.hypot(dx + 8, dy + 8))  # luz de cima/esquerda
                    col = [lerp(ball[i] * shade, seam[i], sm) * bal for i in range(3)]
                    row.extend(int(round(v)) for v in col)
                    continue
                ang = (math.degrees(math.atan2(dy, dx)) + 90) % 360
                rel = (ang - start) % 360
                # dentro do arco = 1, fora = 0, bordas com 1,5° de suavização
                on = max(0.0, min(1.0, min(rel, sweep - rel) / 1.5)) if rel <= sweep else 0.0
                col = [lerp(track[i], blue[i], on) * ring for i in range(3)]
                row.extend(int(round(v)) for v in col)
            rows.append(bytes(row))
        add(f"part0/{f:03d}.png", png(size, size, rows))
    zf.close()


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "wallpaper" and len(sys.argv) == 5:
        wallpaper(sys.argv[2], int(sys.argv[3]), int(sys.argv[4]))
    elif cmd == "bootanim" and len(sys.argv) == 3:
        bootanim(sys.argv[2])
    else:
        sys.exit(__doc__)
