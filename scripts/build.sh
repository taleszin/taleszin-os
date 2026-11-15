#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# m7s-kitkat-rom — build reproduzível da ROM a partir do firmware oficial 4.4.2 do
# Multilaser M7s Dual Core (ML01-M7-SD, RK3026).
#
#   scripts/build.sh /caminho/Multilaser_M7S_Dual_Core-SUPRA_ML01_140403_4.4_RBT.zip
#
# Saída em out/. Variáveis de config/rom.conf podem ser sobrescritas pelo ambiente.
# Requisitos: bash, python3 (só stdlib), e2fsprogs >= 1.47 (debugfs/e2fsck/dumpe2fs/resize2fs),
# cc + make (compilam zic e o CRC Rockchip), curl, awk. Nada roda como root; nada toca o tablet.
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
ZIP=${1:-}
[ -n "$ZIP" ] && [ -f "$ZIP" ] || { echo "uso: $0 firmware-oficial.zip" >&2; exit 2; }
ZIP=$(cd "$(dirname "$ZIP")" && pwd)/$(basename "$ZIP")

# shellcheck source=../config/rom.conf
. "$ROOT/config/rom.conf"
WORK=${WORK:-$ROOT/work}
OUT=${OUT:-$ROOT/out}
CACHE=${M7S_CACHE:-$WORK/cache}
B=$WORK/build                 # recriado a cada execução (idempotência)
LIB=$ROOT/scripts/lib
PY="python3 -I"

export TZ=UTC LC_ALL=C SOURCE_DATE_EPOCH
export E2FSPROGS_FAKE_TIME=$SOURCE_DATE_EPOCH E2FSCK_TIME=$SOURCE_DATE_EPOCH  # todo timestamp gravado pelo e2fsprogs = data fixa

log() { printf '\n==> %s\n' "$*"; }
die() { printf 'ERRO: %s\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------- ferramentas
find_tool() {
  local t=$1 d
  for d in "${E2FS_SBIN:-}" /usr/local/opt/e2fsprogs/sbin /opt/homebrew/opt/e2fsprogs/sbin /sbin /usr/sbin; do
    [ -n "$d" ] && [ -x "$d/$t" ] && { echo "$d/$t"; return; }
  done
  command -v "$t" || die "não achei $t (macOS: brew install e2fsprogs; Debian: apt install e2fsprogs)"
}
DEBUGFS=$(find_tool debugfs); E2FSCK=$(find_tool e2fsck); DUMPE2FS=$(find_tool dumpe2fs); RESIZE2FS=$(find_tool resize2fs)
export DEBUGFS
E2FS_VER=$("$DEBUGFS" -V 2>&1 | awk 'NR==1')
case "$E2FS_VER" in *" 1.47."*|*" 1.48."*|*" 1.5"*) ;; *) die "e2fsprogs >= 1.47 necessário (achei: $E2FS_VER)";; esac
for t in curl cc make awk python3 unzip; do command -v $t >/dev/null || die "falta $t"; done
if command -v sha256sum >/dev/null; then SHA() { sha256sum "$@"; }; else SHA() { shasum -a 256 "$@"; }; fi
sha_of() { SHA "$1" | awk '{print $1}'; }
src_sha() { awk -v n="$1" '$1==n{print $2}' "$ROOT/config/sources.txt"; }
src_url() { awk -v n="$1" '$1==n{print $3}' "$ROOT/config/sources.txt"; }
fetch_src() { # fetch_src NOME DEST — URL e sha256 de config/sources.txt
  fetch "$(src_url "$1")" "$(src_sha "$1")" "$2"
}
clone() { cp -c "$1" "$2" 2>/dev/null || cp --reflink=auto "$1" "$2" 2>/dev/null || cp "$1" "$2"; }

fetch() { # fetch URL SHA256 DEST
  local url=$1 sum=$2 dest=$3
  if [ -f "$dest" ] && [ "$(sha_of "$dest")" = "$sum" ]; then return; fi
  mkdir -p "$(dirname "$dest")"
  case "$url" in
    local:*) # local:VAR = arquivo local cujo caminho está na variável VAR (config/rom.conf); não baixa nada
      local v=${url#local:} src
      src=${!v:-}
      [ -n "$src" ] && [ -f "$src" ] || die "fonte local $v não encontrada: '${src}'"
      echo "    copiando $src"
      cp "$src" "$dest.part";;
    *)
      echo "    baixando $url"
      curl -fsSL --retry 3 -o "$dest.part" "$url";;
  esac
  [ "$(sha_of "$dest.part")" = "$sum" ] || { rm -f "$dest.part"; die "sha256 divergente: $url"; }
  mv "$dest.part" "$dest"
}

rm -rf "$B"; mkdir -p "$B"/{stage,xattr,stock,tz,bin} "$CACHE" "$OUT"

# ---------------------------------------------------------------- 1. firmware oficial
log "1/10 firmware oficial"
[ "$(sha_of "$ZIP")" = "$(src_sha stock-zip)" ] || die "zip não é o firmware oficial 140403 4.4 (sha256 diverge de config/sources.txt)"
UPD=$CACHE/stock-update.img
if ! [ -f "$UPD" ] || [ "$(sha_of "$UPD")" != "$(src_sha stock-update)" ]; then
  $PY "$LIB/rkimg.py" extract-zip "$ZIP" "update_3026v_4.4_jz_bx_201404032111.img" "$UPD"
  [ "$(sha_of "$UPD")" = "$(src_sha stock-update)" ] || die "update.img extraído com sha256 inesperado"
fi
$PY "$LIB/rkimg.py" unpack "$UPD" "$B/stock" >/dev/null
P=$B/stock/rkaf
[ "$(sha_of "$P/system")" = "$(src_sha stock-system)" ] || die "system.img do pacote com sha256 inesperado"
$PY "$LIB/rkimg.py" ramdisk "$P/boot" "$B/stock/ramdisk"
FC=$B/stock/ramdisk/file_contexts
[ -f "$FC" ] || die "file_contexts não encontrado no ramdisk"

# ---------------------------------------------------------------- 2. ferramentas auxiliares
log "2/10 compilando rkcrc32 e zic"
cc -O2 -o "$B/bin/rkcrc32" "$LIB/rkcrc32.c"
fetch "https://data.iana.org/time-zones/releases/tzdata2026f.tar.gz" "$(src_sha tzdata)" "$CACHE/tzdata2026f.tar.gz"
fetch "https://data.iana.org/time-zones/releases/tzcode2026f.tar.gz" "$(src_sha tzcode)" "$CACHE/tzcode2026f.tar.gz"
mkdir -p "$B/tz/src"
tar -xzf "$CACHE/tzcode2026f.tar.gz" -C "$B/tz/src"
tar -xzf "$CACHE/tzdata2026f.tar.gz" -C "$B/tz/src"
TZVER=tzdata$(cat "$B/tz/src/version")
( cd "$B/tz/src" && make -s zic CFLAGS="-O2 -DHAVE_GETTEXT=0" >/dev/null )

# ---------------------------------------------------------------- 3. tzdata (formato bionic 4.4)
log "3/10 tzdata $TZVER (sem horário de verão no Brasil)"
( cd "$B/tz/src" && awk -v DATAFORM=rearguard -f ziguard.awk \
    africa antarctica asia australasia europe northamerica southamerica etcetera backward > "$B/tz/rearguard.zi" )
"$B/tz/src/zic" -b fat -d "$B/tz/zoneinfo" "$B/tz/rearguard.zi"
mkdir -p "$B/stage/usr/share/zoneinfo"
$PY "$LIB/tzdata_bionic.py" pack "$B/tz/zoneinfo" "$B/tz/src/zone.tab" "$TZVER" "$B/stage/usr/share/zoneinfo/tzdata"
$PY "$LIB/tzdata_bionic.py" check "$B/stage/usr/share/zoneinfo/tzdata" America/Sao_Paulo America/Fortaleza America/Recife America/Manaus America/Cuiaba \
  || die "tzdata gerado ainda tem horário de verão no Brasil"

# ---------------------------------------------------------------- 4. APKs
log "4/10 APKs (sha256 fixo em config/apks.txt)"
APKLIST=$B/apks.tsv; : > "$APKLIST"
grep -v '^\s*#' "$ROOT/config/apks.txt" | awk 'NF>=3' | while read -r dest sum url cond; do
  if [ -n "${cond:-}" ]; then cv=${cond%%=*}; [ "${!cv:-}" = "${cond#*=}" ] || continue; fi
  f=$CACHE/apk/$sum.apk
  fetch "$url" "$sum" "$f"
  printf '%s\t%s\n' "$f" "$dest" >> "$APKLIST"
done

# ---------------------------------------------------------------- 5. visual
log "5/10 visual: fontes=$FONTS papel=$WALLPAPER bootanim=$BOOTANIM xposed=$XPOSED"
[ "$BOOTANIM" = 1 ] && NO_BOOTANIM=0
VIS=$B/visual; mkdir -p "$VIS"
ART_KEY=$(sha_of "$LIB/art.py" | cut -c1-12)
cached_art() { # cached_art NOME CMD... — arte é determinística; reaproveita pelo hash do gerador
  local f=$CACHE/art/$ART_KEY-$1 a args=(); shift
  for a in "$@"; do [ "$a" = _OUT_ ] && args+=("$f.part") || args+=("$a"); done
  if ! [ -f "$f" ]; then mkdir -p "$CACHE/art"; "${args[@]}" >&2; mv "$f.part" "$f"; fi
  echo "$f"
}
FONT_FILES=""
case "$FONTS" in
  stock) ;;
  roboto3|googlesans)
    fetch_src roboto3 "$CACHE/fonts/Roboto_v3.016.zip"
    fetch_src roboto3-ofl "$CACHE/fonts/OFL-Roboto.txt"
    mkdir -p "$VIS/roboto3" "$VIS/stockfonts"
    ( cd "$VIS/roboto3" && unzip -oqj "$CACHE/fonts/Roboto_v3.016.zip" 'android/static/*.ttf' )
    "$DEBUGFS" -R "dump /fonts/Roboto-Regular.ttf $VIS/stockfonts/Roboto-Regular.ttf" "$P/system" 2>/dev/null
    "$DEBUGFS" -R "dump /etc/system_fonts.xml $VIS/system_fonts.stock.xml" "$P/system" 2>/dev/null
    "$DEBUGFS" -R "dump /etc/fallback_fonts.xml $VIS/fallback_fonts.stock.xml" "$P/system" 2>/dev/null
    FONTDIR=$VIS/roboto3
    if [ "$FONTS" = googlesans ]; then
      fetch_src gsflex "$CACHE/fonts/GoogleSansFlex-v5.000.zip"
      fetch_src gsflex-ofl "$CACHE/fonts/OFL-GoogleSansFlex.txt"
      fetch_src fonttools "$CACHE/fonts/fonttools-4.68.0-py3-none-any.whl"
      GS=$CACHE/fonts/gs-$(cat "$LIB/fonts.py" "$CACHE/fonts/GoogleSansFlex-v5.000.zip" "$CACHE/fonts/fonttools-4.68.0-py3-none-any.whl" | SHA | cut -c1-12)
      if ! [ -f "$GS/.ok" ]; then
        rm -rf "$GS"; mkdir -p "$GS/ft" "$GS/src"
        ( cd "$GS/ft" && unzip -oq "$CACHE/fonts/fonttools-4.68.0-py3-none-any.whl" )
        ( cd "$GS/src" && unzip -oqj "$CACHE/fonts/GoogleSansFlex-v5.000.zip" '*.ttf' -x '__MACOSX/*' )
        echo "    gerando instâncias estáticas do Google Sans Flex (lento: ~1 min por fonte, fica em cache)"
        $PY "$LIB/fonts.py" googlesans "$GS/ft" "$(ls "$GS"/src/*.ttf)" "$GS/out" "$VIS/stockfonts/Roboto-Regular.ttf"
        touch "$GS/.ok"
      fi
      FONTDIR=$GS/out
      cp "$VIS/roboto3/Roboto-Regular.ttf" "$VIS/Roboto3Fallback-Regular.ttf"
      $PY "$LIB/fonts.py" fallbackxml "$VIS/fallback_fonts.stock.xml" "$VIS/fallback_fonts.xml" Roboto3Fallback-Regular.ttf
    fi
    FONT_FILES="Roboto-Regular.ttf Roboto-Bold.ttf Roboto-Italic.ttf Roboto-BoldItalic.ttf Roboto-Light.ttf Roboto-LightItalic.ttf Roboto-Thin.ttf Roboto-ThinItalic.ttf Roboto-Medium.ttf Roboto-MediumItalic.ttf RobotoCondensed-Regular.ttf RobotoCondensed-Bold.ttf RobotoCondensed-Italic.ttf RobotoCondensed-BoldItalic.ttf"
    for f in $FONT_FILES; do [ -f "$FONTDIR/$f" ] || die "fonte $f ausente em $FONTDIR"; done
    # mesma altura de linha do Roboto de fábrica = nenhum layout muda de altura nem corta texto
    $PY "$LIB/fonts.py" samemetrics "$VIS/stockfonts/Roboto-Regular.ttf" $(for f in $FONT_FILES; do echo "$FONTDIR/$f"; done) \
      || die "fontes novas com métricas verticais diferentes do estoque"
    $PY "$LIB/fonts.py" systemxml "$VIS/system_fonts.stock.xml" "$VIS/system_fonts.xml"
    ;;
  *) die "FONTS=$FONTS inválido (roboto3|googlesans|stock)";;
esac
if [ "$WALLPAPER" = 1 ]; then
  WP=$(cached_art "wallpaper-$WALLPAPER_SIZE.png" $PY "$LIB/art.py" wallpaper _OUT_ "${WALLPAPER_SIZE%x*}" "${WALLPAPER_SIZE#*x}")
fi
if [ "$BOOTANIM" = 1 ]; then
  BA=$(cached_art bootanimation.zip $PY "$LIB/art.py" bootanim _OUT_)
fi
if [ "$XPOSED" = 1 ]; then
  XI=$CACHE/apk/$(awk '$1=="/system/preinstall/XposedInstaller.apk"{print $2}' "$ROOT/config/apks.txt").apk
  [ -f "$XI" ] || die "Xposed Installer não baixado"
  mkdir -p "$VIS/xposed/lib"
  ( cd "$VIS/xposed" && unzip -oqj "$XI" assets/arm/app_process_xposed_sdk16 assets/XposedBridge.jar )
  "$DEBUGFS" -R "dump /bin/app_process $VIS/xposed/app_process.orig" "$P/system" 2>/dev/null
  # o app_process do Xposed precisa achar todos os símbolos nas libs DESTE firmware (senão o zygote não sobe)
  for l in $($PY "$LIB/elfcheck.py" needed "$VIS/xposed/app_process_xposed_sdk16"); do
    "$DEBUGFS" -R "dump /lib/$l $VIS/xposed/lib/$l" "$P/system" 2>/dev/null
  done
  $PY "$LIB/elfcheck.py" resolve "$VIS/xposed/app_process_xposed_sdk16" "$VIS/xposed/lib" \
    || die "app_process do Xposed tem símbolos sem resolução nas libs do firmware"
  [ "$(unzip -p "$VIS/xposed/XposedBridge.jar" assets/VERSION | tr -d '\r\n')" = 54 ] || die "XposedBridge.jar inesperado"
fi

# ---------------------------------------------------------------- 6. arquivos gerados
log "6/10 build.prop, m7s.conf"
"$DEBUGFS" -R "dump /build.prop $B/stock/build.prop" "$P/system" 2>/dev/null
ANIM_SCALE_I32=$(python3 -I -c "import struct,sys;print(struct.unpack('<i',struct.pack('<f',float(sys.argv[1])))[0])" "$ANIM_SCALE")
$PY "$LIB/buildprop.py" "$B/stock/build.prop" "$B/stage/build.prop" \
  "ro.build.display.id=$ROM_NAME $ROM_VERSION" \
  "ro.taleszin.name=$ROM_NAME" \
  "ro.taleszin.version=$ROM_VERSION" \
  "ro.taleszin.base=KitKat 4.4.2 KOT49H (Rockchip 20140403)" \
  "ro.m7s.version=$ROM_VERSION" \
  "dalvik.vm.heapsize=$DALVIK_HEAPSIZE" \
  "dalvik.vm.heapgrowthlimit=$DALVIK_GROWTHLIMIT" \
  "dalvik.vm.checkjni=false" \
  "ro.kernel.android.checkjni=0" \
  "ro.config.low_ram=$LOW_RAM" \
  "debug.sf.nobootanimation=$NO_BOOTANIM" \
  "persist.sys.timezone=$TIMEZONE" \
  "persist.sys.usb.config=$USB_CONFIG" \
  "ro.rk.def_brightness=$BRIGHTNESS" \
  "ro.rk.screenoff_time=$SCREEN_OFF_MS" \
  "ro.rk.install_non_market_apps=$INSTALL_NON_MARKET" \
  "ro.lockscreen.disable.default=$([ "$LOCKSCREEN_DISABLED" = 1 ] && echo true || echo false)"
mkdir -p "$B/stage/etc"
{
  echo "# gerado por scripts/build.sh a partir de config/rom.conf — m7s-kitkat-rom $ROM_VERSION"
  for v in ZRAM_MB KSM IOSCHED CPU_MAX_KHZ HISPEED_KHZ GO_HISPEED_LOAD TARGET_LOADS MIN_SAMPLE_US TELEMETRY \
           POWERGUARD PG_CUTOFF_MV PG_CONFIRM PG_CONFIRM_S PG_INTERVAL PG_GRACE_S PG_BATT_MAX_KHZ PG_BATT_BRIGHT \
           ANIM_SCALE ANIM_SCALE_I32 HAPTIC TOUCH_SOUNDS LOCKSCREEN_SOUNDS LOCKSCREEN_DISABLED \
           WIFI_SLEEP_POLICY WIFI_SCAN_INTERVAL_MS WIFI_SCAN_ALWAYS IME \
           KISS_THEME ICON_PACK DARK_APPS XPOSED XPOSED_REBOOT GB_BATTERY_STYLE GB_CENTER_CLOCK GB_FLAT_ICONS GB_MODERN HOME_LAUNCHER; do
    printf '%s="%s"\n' "$v" "${!v}"
  done
} > "$B/stage/etc/m7s.conf"

# ---------------------------------------------------------------- 6. plano de edição
log "7/10 plano (remoções, overlay, apps, libs nativas)"
INV0=$B/inventory.stock.tsv
$PY "$LIB/sysimg.py" inventory "$P/system" "$INV0" >/dev/null
$PY "$LIB/sysimg.py" labelcheck "$INV0" "$FC" | tail -1
# cada pacote desativado ao vivo precisa ter sido mapeado para remoção
while read -r pkg; do
  [ -z "$pkg" ] && continue
  grep -q "# $pkg\$" "$ROOT/config/remove.txt" || die "pacote $pkg (disable-packages.txt) sem APK em remove.txt"
done < "$ROOT/config/disable-packages.txt"

PLAN=$B/plan.txt
gput() { # gput ORIGEM DESTINO [MODO UID GID] — cria (mkdir) os diretórios que faltarem
  local src=$1 p=$2 d missing=""; shift 2
  d=$(dirname "$p")
  while [ "$d" != /system ] && ! grep -q "^$d"$'\t' "$INV0"; do missing="$d $missing"; d=$(dirname "$d"); done
  for d in $missing; do echo "mkdir $d 0755 0 0"; done
  echo "put $src $p${*:+ $*}"
}
{
  echo "# plano gerado — $(date -u -r "$SOURCE_DATE_EPOCH" 2>/dev/null || date -u -d "@$SOURCE_DATE_EPOCH")"
  sed 's/#.*//' "$ROOT/config/remove.txt" | awk 'NF{print "rm", $1}'
  # overlay versionado
  ( cd "$ROOT/overlay" && find system -type f | LC_ALL=C sort ) | while read -r rel; do
    p=/$rel; src=$ROOT/overlay/$rel
    if grep -q "^$p"$'\t' "$INV0"; then gput "$src" "$p"
    else case "$p" in
      /system/bin/*|/system/xbin/*) gput "$src" "$p" 0755 0 2000;;
      /system/etc/install-recovery.sh) gput "$src" "$p" 0755 0 0;;
      *) gput "$src" "$p" 0644 0 0;;
    esac; fi
  done
  # gerados
  echo "put $B/stage/build.prop /system/build.prop"
  [ "$TZDATA_UPDATE" = 1 ] && echo "put $B/stage/usr/share/zoneinfo/tzdata /system/usr/share/zoneinfo/tzdata"
  echo "put $B/stage/etc/m7s.conf /system/etc/m7s.conf 0644 0 0"
  # visual
  for f in $FONT_FILES; do
    if grep -q "^/system/fonts/$f"$'\t' "$INV0"; then gput "$FONTDIR/$f" "/system/fonts/$f"
    else gput "$FONTDIR/$f" "/system/fonts/$f" 0644 0 0; fi
  done
  if [ -n "$FONT_FILES" ]; then
    gput "$VIS/system_fonts.xml" /system/etc/system_fonts.xml
    gput "$CACHE/fonts/OFL-Roboto.txt" /system/etc/m7s/licenses/OFL-Roboto.txt 0644 0 0
    if [ "$FONTS" = googlesans ]; then
      gput "$VIS/Roboto3Fallback-Regular.ttf" /system/fonts/Roboto3Fallback-Regular.ttf 0644 0 0
      gput "$VIS/fallback_fonts.xml" /system/etc/fallback_fonts.xml
      gput "$CACHE/fonts/OFL-GoogleSansFlex.txt" /system/etc/m7s/licenses/OFL-GoogleSansFlex.txt 0644 0 0
    fi
  fi
  # o WallpaperManager da Rockchip usa este arquivo como papel de parede padrão (getDefaultWallpaperLocked,
  # conferido no framework.jar); o BitmapFactory reconhece PNG pelo conteúdo, o nome .jpg não importa
  [ "$WALLPAPER" = 1 ] && gput "$WP" /system/media/rkfactory/default_wallpaper.jpg
  [ "$BOOTANIM" = 1 ] && gput "$BA" /system/media/bootanimation.zip 0644 0 0
  if [ "$XPOSED" = 1 ]; then
    gput "$VIS/xposed/app_process.orig" /system/bin/app_process.orig 0755 0 2000
    gput "$VIS/xposed/app_process_xposed_sdk16" /system/bin/app_process
    gput "$VIS/xposed/XposedBridge.jar" /system/etc/m7s/XposedBridge.jar 0644 0 0
  fi
  # apps + libs nativas de apps de sistema
  while IFS=$'\t' read -r f dest; do
    echo "put $f $dest 0644 0 0"
    case "$dest" in /system/app/*|/system/priv-app/*)
      $PY - "$f" "$B/stage/lib" "$INV0" "$ROOT/config/remove.txt" <<'PYEOF'
import os, sys, zipfile
apk, outd, inv, rm = sys.argv[1:5]
z = zipfile.ZipFile(apk)
names = [n for n in z.namelist() if n.startswith("lib/") and n.endswith(".so")]
for abi in ("armeabi-v7a", "armeabi"):
    sel = [n for n in names if n.split("/")[1] == abi]
    if sel:
        break
else:
    sel = []
existing = {l.split("\t")[0] for l in open(inv)}
removed = {l.split("#")[0].strip() for l in open(rm)}
os.makedirs(outd, exist_ok=True)
for n in sorted(sel):
    base = os.path.basename(n)
    dest = "/system/lib/" + base
    if dest in existing and dest not in removed:
        sys.exit(f"lib nativa {base} de {apk} colide com {dest} do sistema")
    with open(os.path.join(outd, base), "wb") as o:
        o.write(z.read(n))
    print(f"put {os.path.join(outd, base)} {dest} 0644 0 0")
PYEOF
    ;; esac
  done < "$APKLIST"
} > "$PLAN"
grep -c '^put' "$PLAN" | sed 's/^/    arquivos gravados: /'
grep -c '^rm' "$PLAN" | sed 's/^/    arquivos removidos: /'

# ---------------------------------------------------------------- 7. aplica no system.img
log "8/10 aplicando no system.img (debugfs, metadados explícitos)"
IMG=$B/system.img
clone "$P/system" "$IMG"
$PY "$LIB/sysimg.py" plan "$INV0" "$FC" "$PLAN" "$B" "$B/edit.debugfs" >/dev/null
$PY "$LIB/sysimg.py" xattrs "$P/system" "$B/edit.debugfs"

BS=$("$DUMPE2FS" -h "$IMG" 2>/dev/null | awk -F: '/^Block size/{gsub(/ /,"",$2);print $2}')
FREE=$("$DUMPE2FS" -h "$IMG" 2>/dev/null | awk -F: '/^Free blocks/{gsub(/ /,"",$2);print $2}')
NEED=$($PY - "$PLAN" "$INV0" "$BS" <<'PYEOF'
import os, sys
plan, inv, bs = sys.argv[1], sys.argv[2], int(sys.argv[3])
size = {l.split("\t")[0]: l.split("\t")[5] for l in open(inv)}
need = 0
for l in open(plan):
    a = l.split()
    if not a or a[0].startswith("#"): continue
    if a[0] == "put":
        need += -(-os.path.getsize(a[1]) // bs) + 2  # dados + folga p/ árvore de extents
        if a[2] in size: need -= -(-int(size[a[2]]) // bs)
    elif a[0] == "rm":
        need -= -(-int(size[a[1]]) // bs)
print(need)
PYEOF
)
PART_BLOCKS=$(( 0x180000 * 512 / BS ))
echo "    blocos livres: $FREE, saldo do plano: $NEED (partição comporta $PART_BLOCKS blocos)"
if [ "$NEED" -gt $(( FREE - 256 )) ]; then
  echo "    espaço insuficiente: expandindo o FS até o tamanho da partição (resize2fs)"
  "$E2FSCK" -fy "$IMG" >/dev/null || [ $? -le 1 ]
  "$RESIZE2FS" "$IMG" "$PART_BLOCKS" >/dev/null
fi
grep -v '^#' "$B/edit.debugfs" > "$B/edit.clean.debugfs"
"$DEBUGFS" -w -f "$B/edit.clean.debugfs" "$IMG" > "$B/debugfs.log" 2>&1
if grep -E -i 'error|could not|not found|no free space|failed' "$B/debugfs.log" | grep -v '^debugfs:' >&2; then
  die "debugfs reportou erro (ver $B/debugfs.log)"
fi

# ---------------------------------------------------------------- 8. validação
log "9/10 validação"
set +e; "$E2FSCK" -fy "$IMG" > "$B/e2fsck-fix.log" 2>&1; rc=$?; set -e
[ $rc -le 1 ] || die "e2fsck -fy retornou $rc (ver $B/e2fsck-fix.log)"
"$E2FSCK" -fn "$IMG" > "$B/e2fsck.log" 2>&1 || die "e2fsck -fn acusou erro (ver $B/e2fsck.log)"
tail -1 "$B/e2fsck.log" | sed 's/^/    e2fsck: /'
[ "$("$DUMPE2FS" -h "$P/system" 2>/dev/null | grep '^Filesystem features')" = "$("$DUMPE2FS" -h "$IMG" 2>/dev/null | grep '^Filesystem features')" ] \
  || die "features do ext4 mudaram (kernel 3.0 pode não montar)"
WT=$($PY - "$IMG" <<'PYEOF'
import struct, sys
f = open(sys.argv[1], "rb"); f.seek(1024); sb = f.read(1024)
print(struct.unpack_from("<I", sb, 0x30)[0])
PYEOF
)
[ "$WT" = "$SOURCE_DATE_EPOCH" ] || die "s_wtime=$WT != SOURCE_DATE_EPOCH (e2fsprogs sem suporte a E2FSPROGS_FAKE_TIME?)"
TMPDIR_VERIFY=$B $PY "$LIB/sysimg.py" verify "$IMG" "$PLAN"
INV1=$B/inventory.rom.tsv
$PY "$LIB/sysimg.py" inventory "$IMG" "$INV1" >/dev/null
$PY "$LIB/sysimg.py" labelcheck "$INV1" "$FC" | tail -1
$PY "$LIB/sysimg.py" diff "$INV0" "$INV1" > "$B/system-diff.tsv"
IMGSZ=$(wc -c < "$IMG" | tr -d ' ')
[ "$IMGSZ" -le $(( 0x180000 * 512 )) ] || die "system.img ($IMGSZ B) não cabe na partição (805306368 B)"
"$DUMPE2FS" -h "$IMG" 2>/dev/null | awk -F: '/^Block count|^Free blocks|^Inode count|^Free inodes/{gsub(/^ +/,"",$2);printf "    %s: %s\n",$1,$2}'

# ---------------------------------------------------------------- 9. saída
log "10/10 out/"
rm -rf "$OUT"; mkdir -p "$OUT/images"
pad16k() { # rkflashtool escreve em blocos de 16 KiB; completa com zeros para não mandar lixo do buffer
  local f=$1 sz rem
  sz=$(wc -c < "$f" | tr -d ' '); rem=$(( sz % 16384 ))
  [ $rem -eq 0 ] || head -c $(( 16384 - rem )) /dev/zero >> "$f"
}
cp "$IMG" "$OUT/images/system.img"; pad16k "$OUT/images/system.img"
for n in kernel boot recovery misc backup; do cp "$P/$n" "$OUT/images/$n.img"; done
psz=$(wc -c < "$P/parameter" | tr -d ' ')   # tira cabeçalho PARM+tamanho (8 B) e CRC (4 B): só referência, não é gravado
dd if="$P/parameter" of="$OUT/parameter.txt" bs=1 skip=8 count=$(( psz - 12 )) 2>/dev/null
RKCRC32=$B/bin/rkcrc32 $PY "$LIB/rkimg.py" repack "$UPD" "$OUT/update.img" "system=$OUT/images/system.img"
$PY "$LIB/rkimg.py" info "$OUT/update.img" > "$B/update-info.txt"
cp "$ROOT/scripts/flash-mac.sh" "$OUT/flash-mac.sh"; chmod 755 "$OUT/flash-mac.sh"
cp "$ROOT/docs/FLASH-WINDOWS.md" "$OUT/FLASH-WINDOWS.md"
cp "$B/system-diff.tsv" "$INV0" "$INV1" "$OUT/"
{
  echo "m7s-kitkat-rom $ROM_VERSION"
  echo "SOURCE_DATE_EPOCH=$SOURCE_DATE_EPOCH"
  echo "base: $(basename "$ZIP") sha256=$(src_sha stock-zip)"
  echo "tzdata: $TZVER"
  echo "e2fsprogs: $E2FS_VER"
  echo "python: $(python3 -V 2>&1)"
  echo "host: $(uname -sm)"
  echo "git: $(cd "$ROOT" && git rev-parse --short HEAD 2>/dev/null || echo 'sem commit')$(cd "$ROOT" && [ -n "$(git status --porcelain 2>/dev/null)" ] && echo ' (árvore suja)')"
  echo; echo "[config]"; cat "$B/stage/etc/m7s.conf" | grep -v '^#'
  echo "TZDATA_UPDATE=$TZDATA_UPDATE LOW_RAM=$LOW_RAM DALVIK_HEAPSIZE=$DALVIK_HEAPSIZE NO_BOOTANIM=$NO_BOOTANIM TIMEZONE=$TIMEZONE USB_CONFIG=$USB_CONFIG BRIGHTNESS=$BRIGHTNESS SCREEN_OFF_MS=$SCREEN_OFF_MS"
  echo; echo "[system.img]"
  "$DUMPE2FS" -h "$IMG" 2>/dev/null | grep -E '^(Filesystem features|Block count|Free blocks|Inode count|Free inodes|Last write time)'
  echo; echo "[diff vs estoque: + novo, - removido, M alterado]"
  awk -F'\t' '{c[$1]++} END{for(k in c) printf "%s %d\n", k, c[k]}' "$B/system-diff.tsv" | sort
} > "$OUT/BUILDINFO.txt"
( cd "$OUT" && SHA images/*.img update.img > SHA256SUMS )
cat "$OUT/SHA256SUMS"
echo
echo "pronto: $OUT"
