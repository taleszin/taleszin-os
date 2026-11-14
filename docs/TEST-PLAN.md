# Plano de teste no aparelho

Ordem pensada para parar cedo se algo básico falhar. Tudo pelo adb, de leitura, salvo onde está
escrito. A telemetria (`/data/m7s-telemetry/*.csv`) cobre RAM, CPU, bateria e Wi-Fi a cada 30 s;
`tools/telemetry_report.py` resume.

## 0. Antes de gravar (linha de base)

1. Backup: o que houver em `/sdcard` e o backup do 4.2.2 já existente.
2. Linha de base no sistema atual (4.4 + ajustes ao vivo), mesmas condições do pós-ROM
   (brilho 102, Wi-Fi ligado, mesma rede):
   - RAM 3 min após boot_completed: `adb shell cat /proc/meminfo | head -5`; `adb shell dumpsys meminfo | tail -8`
   - carga: `adb shell cat /proc/loadavg` (3 min após o boot, parado)
   - boot: ligar e cronometrar até `adb shell getprop sys.boot_completed` = 1 (ou `adb logcat -b events -d | grep boot_progress`)
   - apps: `adb shell am start -W -n org.mozilla.firefox/.App` (TotalTime, 3×, frio após `am force-stop`)
   - bateria tela ligada: 60 min de vídeo no SkyTube a brilho 102 → Δ% e Δmv (telemetria)
   - standby: 8 h tela apagada, fora da tomada → Δ% (telemetria; lacunas no `ts` = sono profundo)
   - `cat /sys/devices/system/cpu/cpu0/cpufreq/stats/time_in_state` no início e fim de cada sessão

## 1. Gravação e 1º boot

1. `cd out && VERIFY=1 ./flash-mac.sh`. Esperado: todas as partições "conferido".
2. 1º boot (wipe + dexopt): cronometrar até a tela do KISS. Esperado 3–6 min. Se passar de
   15 min em loop de logo: `adb logcat` (o adb sobe cedo em eng) e voltar ao estoque.

## 2. Sanidade do sistema

```sh
adb shell getprop ro.m7s.version                 # 1.0.0
adb shell getprop ro.build.display.id
adb shell getenforce 2>/dev/null; adb shell cat /sys/fs/selinux/enforce 2>/dev/null  # registrar (Permissive/ausente esperado)
adb shell ls -lZ /system/etc/install-recovery.sh /system/bin/m7s-*   # u:object_r:system_file:s0
adb shell dmesg | grep -i -E 'avc|ext4.*error'                       # nada
adb logcat -d -b events | grep -E 'am_crash|am_anr'                  # nada recorrente
adb shell df /system /data
```

## 3. Boot hook (a cada boot)

```sh
adb shell cat /proc/swaps                                   # /dev/block/zram0 ~131068 KB
adb shell cat /sys/kernel/mm/ksm/run                        # 1
adb shell cat /sys/block/mtdblock8/queue/scheduler          # [deadline]
adb shell 'cd /sys/devices/system/cpu/cpufreq/interactive && cat go_hispeed_load hispeed_freq target_loads min_sample_time'
adb shell cat /proc/sys/vm/swappiness /proc/sys/vm/page-cluster   # 80 0
adb shell ps | grep m7s-telemetry
```

## 4. 1º boot: padrões de Settings

```sh
adb shell cat /data/local/m7s-firstboot.log; adb shell ls /data/local/m7s-firstboot.done
adb shell settings get global window_animation_scale        # 0
adb shell settings get secure default_input_method          # rkr.simplekeyboard.inputmethod/.latin.LatinIME
adb shell settings get global wifi_sleep_policy             # 1
adb shell settings get system screen_brightness             # 102
adb shell settings get secure lockscreen.disabled           # 1
adb shell dumpsys window | grep -i animat                   # escalas 0 já no 1º boot (service call 51)
```
Manual: abrir um campo de texto (Simple Keyboard aparece); botão Home (KISS, sem seletor);
apagar/acender a tela (sem tela de bloqueio); sem som/vibração no toque.

## 5. Pré-instalação

```sh
adb shell getprop persist.sys.preinstalled                  # 1
adb shell pm list packages -3                               # firefox, skytube.oss, fdroid, ameixa, sufficientlysecure.viewer
adb shell ls /data/app-lib/                                 # libs do Firefox extraídas
```

## 6. Relógio e fuso (bug do horário de verão)

```sh
adb shell date; date -u                                     # mesma hora (fuso -03)
adb shell getprop persist.sys.timezone                      # America/Fortaleza
adb shell ls /data/misc/zoneinfo 2>/dev/null                # não deve existir (senão ele tem prioridade)
```
Trocar o fuso para São Paulo em Configurações → hora continua -03 (antes ficava -02). Conferir o
relógio da barra de status e o `date` do shell (Java e bionic leem o mesmo arquivo).
Abrir o Firefox em um site que mostre a hora local (ex.: time.is) e conferir.

## 7. USB

Plugar no Mac: deve aparecer como MTP (Android File Transfer/OpenMTP), **não** como pendrive;
`adb devices` estável; `/sdcard` continua acessível no tablet.

## 8. Apps

- Firefox: abrir https://letsencrypt.org e https://valid-isrgrootx1.letsencrypt.org (cadeia ISRG)
  — sem erro de certificado. Rolar uma página longa.
- SkyTube: tocar 10 min de vídeo 360p.
- F-Droid: atualizar o repositório.
- KISS: busca e lista de apps; ícones Ameixa nas configurações do KISS.

## 9. Métricas antes/depois (mesmas condições do item 0)

| Métrica | Como | Esperado |
|---|---|---|
| RAM livre pós-boot | `/proc/meminfo` (MemFree+Cached), `dumpsys meminfo` 3 min após boot | mais livre que o estoque |
| Load | `/proc/loadavg` 3 min após boot, parado | menor |
| Tempo de boot | ligar → `sys.boot_completed=1` | ≤ 39 s (medido ao vivo sem bootanimation) |
| Bateria tela ligada | 60 min SkyTube, brilho 102 → %/h e mV/h | menor consumo |
| Standby | 8 h tela apagada fora da tomada → %/h | menor (Wi-Fi desliga) |
| Abrir Firefox / SkyTube | `am start -W` frio, 3× | menor TotalTime |
| zRAM / KSM | `compr_data_size`, `pages_sharing` após 30 min de uso | registrar |
| CPU | `time_in_state` por sessão | mais tempo em 312/504 |
| Temperatura | sem sensor exposto (ver item 10) | — |

## 10. A medir (só leitura; para decidir a v2)

```sh
adb shell 'ls /sys/devices/platform/mali-utgard.0/ /sys/module/mali/parameters/ 2>/dev/null'
adb shell 'find /sys -maxdepth 5 \( -iname "*mali*" -o -iname "*ddr*" -o -iname "*gpu*" \) 2>/dev/null'
adb shell 'ls /sys/module/ | grep -i -E "ddr|mali|rk"'
adb shell 'find /sys -maxdepth 6 -iname "*temp*" 2>/dev/null; ls /sys/class/thermal 2>/dev/null'
adb shell 'cat /proc/clocks 2>/dev/null | head -50'
adb shell 'cat /sys/devices/system/cpu/cpu1/online; ls /sys/devices/system/cpu/cpu0/cpufreq/'
adb shell 'cat /sys/module/lowmemorykiller/parameters/minfree /sys/module/lowmemorykiller/parameters/adj'
```

## 11. Experimentos A/B (um por vez, ≥1 h cada, mesma rotina)

1. `CPU_MAX_KHZ` 1008000 vs 912000: %/h tela ligada, `am start -W` do Firefox, time_in_state.
2. `IOSCHED` deadline vs noop: `am start -W` com `dd` de 100 MB rodando em `/data/local/tmp`.
3. `KSM` 1 vs 0: `pages_sharing`, CPU do `ksmd`, %/h.
4. `WIFI_SLEEP_POLICY` 1 vs 2: standby %/h.
5. `LOW_RAM` true vs false: RAM livre, fluidez percebida (rolagem no Firefox, barra de notificações).

Para A/B sem regravar: os valores do boot hook podem ser escritos ao vivo nos mesmos nós (root);
os de build.prop exigem rebuild.

## 12. Visual (v1.1)

1. **Tela:** `adb shell wm size; adb shell wm density`. Esperado: `800x480` e `160`. Se der outro tamanho, refazer com `WALLPAPER_SIZE=<maior>x<maior>`.
2. **Fontes:**
   - `adb shell ls -l /system/fonts/Roboto-Regular.ttf` deve mostrar 355956 bytes.
   - Olhar Configurações, a barra de notificações e um texto com acentos em maiúsculas (ex.: "ÁÉÍ ÇÃO"). Nada deve aparecer cortado.
   - `cat /proc/$(pidof zygote)/smaps | grep -A2 Roboto` → Rss.
3. **Papel de parede:**
   - Na tela inicial deve aparecer o gradiente escuro. Configurações → Tela → Plano de fundo → padrão deve continuar o mesmo.
   - `adb shell dumpsys meminfo com.android.systemui | grep -E "TOTAL|Graphics"` e comparar com o item 0.
4. **KISS:**
   - Ícones do Ameixa e lista escura.
   - `adb shell cat /data/data/fr.neamar.kiss/shared_prefs/fr.neamar.kiss_preferences.xml | grep -E "theme|icons-pack"`.
   - `adb shell dumpsys meminfo fr.neamar.kiss | grep TOTAL`.
   - **Teclado:** abrir um campo de texto; o teclado deve estar escuro e continuar sendo o padrão (`settings get secure default_input_method`).
5. **Xposed (só num build `XPOSED=1`, como experimento separado):**
   - O 1º boot reinicia uma vez sozinho, ~10 s depois de terminar. Ver `/data/local/m7s-firstboot.log`.
   - `adb logcat -d | grep -i xposed` deve mostrar "Xposed version: 58" e "Loading modules from …gravitybox". O Xposed Installer deve mostrar o framework ativo e o GravityBox marcado.
   - Barra de status: relógio no centro, bateria KitKat com %, ícones planos de sinal/Wi-Fi.
   - RAM: `dumpsys meminfo | grep -E "system|systemui|Total"` contra o build sem Xposed. Se passar de +15 MB ou a fluidez cair, ficar sem.
   - Se não bootar (logo em loop por mais de 2 min): `adb shell touch /data/data/de.robv.android.xposed.installer/conf/disabled; adb reboot`, ou regravar o `system.img` padrão.
6. **Bootanimation (só num build `BOOTANIM=1`):** cronometrar ligar → `sys.boot_completed=1` três vezes e comparar com os ~39 s sem animação.
7. **Google Sans (só num build `FONTS=googlesans`):** os mesmos olhos do passo 2, com atenção a acentos em maiúsculas e a textos gregos/cirílicos (devem aparecer pelo fallback Roboto).

## 13. Guarda de bateria (v1.2)

1. **Rodando:** `adb shell "ps | grep powerguard; cat /data/m7s-telemetry/powerguard.log"`. O log
   deve ter `início: corte=3480mV x2 …` e `fonte=… teto=…`.
2. **Teto de CPU:**
   - Na tomada: `adb shell cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_max_freq` → `1008000`.
   - Desplugar (adb por Wi-Fi, ou desplugar, esperar 30 s e replugar para ler): o log deve mostrar
     `fonte=bateria teto=816000kHz`; `powerguard.state` com `bateria 816000`.
   - Replugar: em até 25 s, volta `fonte=tomada teto=1008000kHz`.
3. **Corte por tensão:** na rotina normal (Firefox + vídeo, desplugado), deixar descarregar até o
   fim. Esperado: linhas `tensão baixa …(1/2)`, `(2/2)`, `DESLIGANDO`, e o tablet desliga com a
   tela normal de "Desligando…", não um apagão. No próximo boot (na tomada), o fim do
   `powerguard.log` deve ser a linha `DESLIGANDO` (sem `framework não desligou`) e o CSV da telemetria deve
   continuar íntegro até o último minuto.
4. **Falso positivo:** ligar com bateria baixa: nada de desligamento nos primeiros 120 s; um pico
   isolado abaixo de 3480 mV registra `(1/2)` e zera na leitura seguinte.
5. **Comparar com a telemetria de 13–14/11:** minutos de bateria de 100% até desligar e se houve
   desligamento súbito acima de 3,5 V. Se houver, repetir com `PG_BATT_MAX_KHZ=504000`.

## 14. Apps (v1.2)

- **Prancheta do Taleszin:** é o 1º favorito na barra do KISS
  (`adb shell grep favorite-apps-list /data/data/fr.neamar.kiss/shared_prefs/fr.neamar.kiss_preferences.xml`
  começa com `app://app.mamba.prancheta/…`) e aparece buscando "pran". Abrir, usar, girar a tela.
  `adb shell pm path app.mamba.prancheta` → `/system/app/PranchetaTaleszin.apk`.
- **Little File Explorer:** navegar em `/sdcard`, abrir um PDF (deve oferecer o Document Viewer).
- **My Notes:** criar, editar e apagar uma nota; reiniciar e conferir que ficou.
- **Document Viewer:** abrir um PDF de várias páginas e um EPUB; rolar e dar zoom.
  `adb shell dumpsys meminfo org.sufficientlysecure.viewer | grep TOTAL` com o PDF aberto (esperado
  25–40 MB).
- Nenhum deles deve aparecer em `dumpsys activity services` depois de fechado.
