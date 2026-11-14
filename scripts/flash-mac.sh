#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Grava a m7s-kitkat-rom pelo Mac/Linux com rkflashtool (tablet em modo loader).
# SÓ para Multilaser M7s Dual Core ML01-M7-SD (RK3026). NÃO grava parameter nem loader.
# O misc.img do pacote contém "--wipe_all": no 1º boot o recovery APAGA /data e /cache.
#
# uso:  ./flash-mac.sh            (pede confirmação)
#       VERIFY=1 ./flash-mac.sh   (relê cada partição depois de gravar e compara; +~10 min)
set -euo pipefail
cd "$(dirname "$0")"

command -v rkflashtool >/dev/null || { echo "instale o rkflashtool (macOS: brew install rkflashtool)"; exit 1; }
if command -v sha256sum >/dev/null; then SHA="sha256sum"; else SHA="shasum -a 256"; fi

echo "== conferindo SHA256SUMS"
$SHA -c SHA256SUMS

# nome  setor_inicial  setores_da_partição  (parameter oficial 4.4: mtdparts=rk29xxnand:...)
PARTS="kernel 0x4000 0x4000
boot 0x8000 0x8000
recovery 0x10000 0x10000
backup 0x20000 0x20000
system 0x282000 0x180000
misc 0x2000 0x2000"

while read -r n off sz; do
  f=images/$n.img
  bytes=$(wc -c < "$f" | tr -d ' ')
  [ "$bytes" -le $(( sz * 512 )) ] || { echo "$f ($bytes B) maior que a partição $n"; exit 1; }
done <<< "$PARTS"

cat <<'EOF'

ANTES DE CONTINUAR
  1. Bateria > 50% e cabo USB direto no Mac (sem hub).
  2. Tablet em modo loader:  adb reboot bootloader
     (ou desligado: segure Vol- e conecte o USB).
  3. Isto APAGA apps e dados do usuário (/data). Faça backup do que importa.
  4. Rollback: docs/README.md, seção "Voltar ao estoque".
EOF
echo
rkflashtool v 2>&1 | grep -i -E 'RK3026|chip|version' || true
read -r -p "Digite GRAVAR para gravar: " ans
[ "$ans" = "GRAVAR" ] || { echo "cancelado"; exit 1; }

while read -r n off sz; do
  echo "== gravando $n ($off, $sz setores)"
  rkflashtool w "$off" "$sz" < "images/$n.img"
  if [ "${VERIFY:-0}" = 1 ]; then
    bytes=$(wc -c < "images/$n.img" | tr -d ' ')
    tmp=$(mktemp)
    # rkflashtool lê em blocos de 0x20 setores: arredonda e compara só os bytes da imagem
    rkflashtool r "$off" $(( ((bytes + 511) / 512 + 31) / 32 * 32 )) > "$tmp" 2>/dev/null
    if [ "$(head -c "$bytes" "$tmp" | shasum -a 256 | cut -d' ' -f1)" = "$(shasum -a 256 < "images/$n.img" | cut -d' ' -f1)" ]; then echo "   conferido"; rm -f "$tmp"
    else echo "   DIVERGE: regrave antes de reiniciar"; rm -f "$tmp"; exit 1; fi
  fi
done <<< "$PARTS"

echo "== reiniciando (1º boot: wipe + otimização dos apps, 3-6 min)"
rkflashtool b
