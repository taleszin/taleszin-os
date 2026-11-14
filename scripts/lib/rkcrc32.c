/* SPDX-License-Identifier: MIT
 * rkcrc32 ARQUIVO [TAMANHO] -> imprime em hex o CRC32 Rockchip dos primeiros TAMANHO bytes.
 * Polinômio 0x04c10db7, valor inicial 0, sem reflexão, sem xor final
 * (mesmo algoritmo do rkcrc do rkflashtool; usado no trailer do RKAF). */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

int main(int argc, char **argv) {
    static uint32_t t[256];
    static unsigned char buf[1 << 20];
    uint32_t crc = 0;
    unsigned long long left = ~0ULL;
    FILE *f;
    size_t n;
    int i, j;

    if (argc < 2 || argc > 3) { fprintf(stderr, "uso: rkcrc32 arquivo [tamanho]\n"); return 2; }
    if (argc == 3) left = strtoull(argv[2], NULL, 0);
    for (i = 0; i < 256; i++) {
        uint32_t c = (uint32_t)i << 24;
        for (j = 0; j < 8; j++) c = (c & 0x80000000u) ? (c << 1) ^ 0x04c10db7u : (c << 1);
        t[i] = c;
    }
    if (!(f = fopen(argv[1], "rb"))) { perror(argv[1]); return 1; }
    while (left && (n = fread(buf, 1, left < sizeof buf ? (size_t)left : sizeof buf, f)) > 0) {
        for (size_t k = 0; k < n; k++) crc = (crc << 8) ^ t[(crc >> 24) ^ buf[k]];
        left -= n;
    }
    if (argc == 3 && left) { fprintf(stderr, "rkcrc32: arquivo menor que o tamanho pedido\n"); return 1; }
    fclose(f);
    printf("%08x\n", crc);
    return 0;
}
