#!/system/bin/sh
# m7s-kitkat-rom — boot hook. O init.rc do 4.4 roda este arquivo como o serviço
# 'flash_recovery' (class main, root, oneshot) em todo boot, depois do /data montado.
# Valores em /system/etc/m7s.conf (gerado de config/rom.conf no build); padrões abaixo
# são os mesmos testados ao vivo. Justificativa e como medir: docs/HARDWARE.md.
BB=/system/bin/busybox
ZRAM_MB=128; KSM=1; IOSCHED=deadline; CPU_MAX_KHZ=1008000; HISPEED_KHZ=816000
GO_HISPEED_LOAD=85; TARGET_LOADS="85 1008000:95"; MIN_SAMPLE_US=40000; TELEMETRY=1; POWERGUARD=1
[ -r /system/etc/m7s.conf ] && . /system/etc/m7s.conf

# zRAM: swap comprimido em RAM (kernel 3.0 = lzo). Com 512 MB evita que o LMK mate apps em 2o plano.
if [ "$ZRAM_MB" -gt 0 ] && [ -e /sys/block/zram0 ] && ! grep -q zram0 /proc/swaps; then
  echo 1 > /sys/block/zram0/reset 2>/dev/null
  echo $((ZRAM_MB * 1024 * 1024)) > /sys/block/zram0/disksize
  $BB mkswap /dev/block/zram0 >/dev/null 2>&1
  $BB swapon /dev/block/zram0 >/dev/null 2>&1
fi
echo 0   > /proc/sys/vm/page-cluster        # swap em RAM: sem leitura antecipada de páginas
echo 80  > /proc/sys/vm/swappiness
echo 50  > /proc/sys/vm/vfs_cache_pressure  # segura dentries/inodes (muitos arquivos pequenos)

# KSM: funde páginas idênticas entre processos (heaps Dalvik). ~400 KB/s de varredura; ksmd
# não acorda o aparelho em suspend (kernel congelado). Medir: /sys/kernel/mm/ksm/pages_sharing.
if [ -e /sys/kernel/mm/ksm/run ]; then
  if [ "$KSM" = 1 ]; then
    echo 100  > /sys/kernel/mm/ksm/pages_to_scan
    echo 1000 > /sys/kernel/mm/ksm/sleep_millisecs
    echo 1    > /sys/kernel/mm/ksm/run
  else
    echo 0 > /sys/kernel/mm/ksm/run
  fi
fi

# NAND (rknand, FTL no driver): sem custo de seek. deadline em vez de cfq (sem idling) e em vez
# de noop (dá prazo menor às leituras: a UI não trava atrás de escrita grande, ex. dexopt).
for b in /sys/block/mtdblock*/queue/read_ahead_kb; do echo 128 > $b 2>/dev/null; done
for q in /sys/block/mtdblock*/queue/scheduler; do echo $IOSCHED > $q 2>/dev/null; done

# CPU (interactive). O power HAL (power.rk3026.so) faz boostpulse a cada toque -> sobe para
# hispeed_freq por 500 ms; 816 MHz cobre o toque. 1008 MHz só com carga >= 95% sustentada.
C=/sys/devices/system/cpu/cpu0/cpufreq
I=/sys/devices/system/cpu/cpufreq/interactive
[ -n "$CPU_MAX_KHZ" ] && echo $CPU_MAX_KHZ > $C/scaling_max_freq 2>/dev/null
[ -d $I ] && {
  echo $GO_HISPEED_LOAD > $I/go_hispeed_load
  echo $HISPEED_KHZ     > $I/hispeed_freq
  echo "$TARGET_LOADS"  > $I/target_loads
  echo $MIN_SAMPLE_US   > $I/min_sample_time
}

# padrões de Settings: uma vez só, depois do boot_completed (ver m7s-firstboot)
[ -x /system/bin/m7s-firstboot ] && [ ! -f /data/local/m7s-firstboot.done ] && \
  $BB setsid /system/bin/m7s-firstboot </dev/null >/dev/null 2>&1 &

# scaling_max_freq legível por apps (o app Diagnóstico mostra o teto que o powerguard aplica)
chmod 0664 /sys/devices/system/cpu/cpu*/cpufreq/scaling_max_freq /sys/devices/system/cpu/cpu*/cpufreq/scaling_min_freq 2>/dev/null

# Xposed sob SELinux: garante que o zygote consiga ler jar/módulos/prefs do GravityBox (ver o script)
[ -x /system/bin/m7s-xposed-selinux ] && /system/bin/m7s-xposed-selinux >/dev/null 2>&1

# telemetria leve (desligar: touch /data/m7s-telemetry.off)
[ "$TELEMETRY" = 1 ] && [ -x /system/bin/m7s-telemetry ] && [ ! -f /data/m7s-telemetry.off ] && \
  $BB setsid /system/bin/m7s-telemetry </dev/null >/dev/null 2>&1 &

# guarda de bateria: teto de CPU fora da tomada + desligamento limpo em tensão baixa
# (desligar: touch /data/m7s-powerguard.off). Ver docs/HARDWARE.md, seção Bateria.
[ "$POWERGUARD" = 1 ] && [ -x /system/bin/m7s-powerguard ] && [ ! -f /data/m7s-powerguard.off ] && \
  $BB setsid /system/bin/m7s-powerguard </dev/null >/dev/null 2>&1 &
