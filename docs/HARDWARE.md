# Hardware e bateria: decisões, justificativa e como medir

Base de evidência: `docs/hw44.txt` (sysfs lido ao vivo no 4.4), `docs/dmesg.txt`, e os binários do
próprio firmware (strings/dexdump de `services.jar`, `framework.jar`, `power.rk3026.so`,
`bootanimation`, `libandroid_runtime.so`). Só uso nós de sysfs que aparecem nesses arquivos; o
resto está em "a medir" no `TEST-PLAN.md`. Valores ficam em `config/rom.conf` → `/system/etc/m7s.conf`
→ aplicados a cada boot por `/system/etc/install-recovery.sh`.

## CPU (cpufreq `interactive`)

Fatos (hw44): degraus 312/504/816/912/1008 MHz; governor `interactive`; `hispeed_freq=816000`,
`go_hispeed_load=99`, `target_loads=90`, `min_sample_time=80000`, `timer_rate=20000`,
`timer_slack=80000`, `boostpulse_duration=500000`. `time_in_state` da sessão medida: 312 MHz 6730,
504 279, 816 7451, 912 857, **1008 0**. dmesg: "rk3188 cpufreq version 2.2, suspend freq 312 MHz".
`power.rk3026.so` escreve em `interactive/boostpulse` (dica de interação = toque) e em
`interactive/input_boost` (nó que **não existe** neste kernel; escrita falha sem efeito).

| Parâmetro | Estoque | ROM | Por quê |
|---|---|---|---|
| `go_hispeed_load` | 99 | 85 | com 99 o salto para 816 MHz quase nunca acontece fora do toque; 85 sobe antes do engasgo em rolagem/decodificação |
| `hispeed_freq` | 816000 | 816000 | é também o alvo do boostpulse do toque; 816 dá resposta sem pagar a tensão de 1008 |
| `target_loads` | 90 | `85 1008000:95` | abaixo de 1008 mira 85% de carga; 1008 só com ≥95% sustentado |
| `min_sample_time` | 80000 | 40000 | desce de frequência em 40 ms em vez de 80 ms depois do pico: menos tempo em 816+ |
| `scaling_max_freq` | 1008000 | 1008000 | ver abaixo |

**1008 MHz fica?** Fica, mas só para carga sustentada. Na medição não foi usado (0 ticks) porque
nada exigiu: com `target_loads 90` o governor raramente passa de 816. Firefox carregando página e
vídeo decodificado em software são os casos que ganham com 1008 (~24% mais clock). O custo é a
tensão maior do último degrau (energia ∝ V²·f). Sem sensor térmico exposto (`== thermal` vazio),
não há como ver aquecimento direto; por isso deixei `CPU_MAX_KHZ` configurável (912000 corta o
degrau mais caro) e o teste A/B está no plano de teste.

Medir: `cat /sys/devices/system/cpu/cpu0/cpufreq/stats/time_in_state` antes/depois de uma sessão
padronizada; `am start -W` do Firefox (TotalTime); % de bateria por hora (telemetria).

## Bateria gasta (`m7s-powerguard`)

Fatos (telemetria real, `telemetry/20261114-0135/`): bateria de 2014 gasta. Desplugado com 100%, a
tensão cai na hora para ~3,80 V; 99%→1% em ~50 min; desligamentos súbitos com o Firefox a 81–94% de
CPU em 3,66 V (90% no gauge, CPU já em 816 MHz) e 3,38 V (35% no gauge); depois do 2º, o gauge
recomeçou em 1% a 3,51 V. O `rk30-battery` estima % por tensão, então sob carga ele mente nos dois
sentidos. Afundamentos isolados se recuperam (ex.: 3470 → 3569 mV na leitura seguinte).

O daemon (`/system/bin/m7s-powerguard`, iniciado pelo boot hook com `setsid`, ~1 processo `sh`
dormindo; lê 4 nós de `/sys/class/power_supply` e escreve 1 de cpufreq):

| Situação | Ação | Por quê |
|---|---|---|
| `usb/online=0` e `ac/online=0` | `scaling_max_freq=PG_BATT_MAX_KHZ` (816000) | o degrau de 1008 MHz pede a maior tensão do núcleo: os picos de corrente derrubam a bateria velha. (`status` não serve: dá "Not charging" também desplugado) |
| na tomada | `scaling_max_freq=CPU_MAX_KHZ` (1008000) | sem limite de bateria |
| bateria, uptime ≥ `PG_GRACE_S` (120 s), `voltage_now` < `PG_CUTOFF_MV` (3480) em `PG_CONFIRM` (2) leituras seguidas, a `PG_CONFIRM_S` (5 s) uma da outra | `am start -a android.intent.action.ACTION_REQUEST_SHUTDOWN --ez android.intent.extra.KEY_CONFIRM false` (ShutdownActivity do 4.4, conferida no framework); se em 60 s ainda estiver de pé: `sync` + `reboot -p` | desliga limpo (apps fechados, `/data` desmontado) antes de a bateria cair sozinha; 2 leituras evitam o falso positivo de um pico isolado; a carência evita o pico de CPU do boot |

Amostra a cada `PG_INTERVAL` (25 s); não segura wakelock (em suspend o laço para junto). Log de
mudanças em `/data/m7s-telemetry/powerguard.log` (gira em ~200 KB); última leitura em
`powerguard.state` (`epoch fonte teto mV % leituras_baixas`). A telemetria (`m7s-telemetry`) não mudou.

Limite conhecido: o desligamento de 3,66 V aconteceu já em 816 MHz e acima de qualquer corte
razoável — o corte por tensão só cobre o fim da descarga. Se, com o powerguard, ainda houver
desligamento súbito com tensão alta, o próximo A/B é `PG_BATT_MAX_KHZ=504000` (o Firefox fica mais
lento na bateria) e, no fim, trocar a bateria. `PG_CUTOFF_MV` mais alto (3550) dá mais margem e
menos uso.

Desligar: `touch /data/m7s-powerguard.off` e reiniciar (ou matar o processo e devolver
`echo 1008000 > .../scaling_max_freq`); no build, `POWERGUARD=0`.

## Memória

| Ajuste | Valor | Por quê / como medir |
|---|---|---|
| zRAM | 128 MB (lzo, kernel 3.0) | 512 MB físicos, ~488 MB de lowmem. Páginas anônimas frias comprimem ~2–3×; o LMK mata menos apps em 2º plano. Medir: `cat /proc/swaps`, `/sys/block/zram0/{orig_data_size,compr_data_size}` (telemetria grava). |
| `page-cluster` | 0 | swap em RAM não tem custo de seek: ler 8 páginas por falta (padrão 3) só gasta CPU. |
| `swappiness` | 80 | prefere comprimir anônimas a descartar cache de código (APKs/dex) que teria de ser relido da NAND lenta. |
| `vfs_cache_pressure` | 50 | segura dentries/inodes (Android abre muitos arquivos pequenos). |
| KSM | 100 páginas / 1000 ms | custo: ~400 KB/s de varredura num núcleo, só com o aparelho acordado (o kernel congela no suspend, então não atrapalha o standby). Benefício: páginas idênticas entre processos Dalvik. Decidir pelos números: `/sys/kernel/mm/ksm/pages_sharing` × 4 KB = RAM economizada; tempo de CPU do `ksmd` em `/proc/<pid>/stat`. Se `pages_sharing` < ~2000 (8 MB) após 30 min de uso, desligar (`KSM=0`). |
| `dalvik.vm.heapsize` | 256m → 128m | teto para apps `largeHeap`; um app só não consome metade da RAM. `heapgrowthlimit` 48m mantido (apps normais iguais). |
| `ro.config.low_ram` | true | ver README (o que muda foi conferido nos dex deste firmware). |
| CheckJNI | ligado → desligado | o estoque define `ro.kernel.android.checkjni=0` e depois `=1` (vale o último), e o `libandroid_runtime.so` liga CheckJNI quando `dalvik.vm.checkjni` não é `false`. CheckJNI valida cada chamada JNI: custo em todo app. Agora `dalvik.vm.checkjni=false`. |

## Armazenamento (NAND rknand)

dmesg: `rknand_buffer.c version: 4.40`, ext4 montado com `discard`; mtdblock5=cache,
mtdblock6=userdata, mtdblock8=system. hw44: `noop deadline [cfq]`, `ra=128`.

- **deadline** (estoque: cfq). A NAND tem FTL no driver: não há seek. O cfq faz idling entre
  filas (espera I/O do mesmo processo), que só atrasa em flash. Entre `noop` e `deadline`:
  o deadline dá prazo de 500 ms às leituras e 5 s às escritas, então a UI (leituras de APK/dex)
  não fica atrás de uma escrita grande (dexopt, instalação, download). O custo de CPU do deadline
  é desprezível. Medir: `am start -W` de um app enquanto `dd if=/dev/zero of=/data/local/tmp/x
  bs=1M count=100` roda; comparar com `IOSCHED=noop`.
- **read_ahead_kb 128**: já é o valor de fábrica (hw44); a linha só garante.

## Tela e entrada

- Brilho padrão `ro.rk.def_brightness` 200 → **102** (40%). A luz de fundo é o maior consumo
  com a tela ligada. Lido pelo `SettingsProvider` deste firmware (string conferida no dex) só
  na criação do banco, ou seja, após o wipe. Modo manual (não há sensor de luz listado).
- Timeout `ro.rk.screenoff_time` mantido em 60 s (o dono já usa assim).
- Touch AW5306: dmesg diz "Start aw5306_ts in **polling mode**". Polling acorda a CPU
  periodicamente com a tela ligada mesmo sem toque. Só muda no kernel (fora do escopo v1).

## Wi-Fi (RTL8188EU)

- `wifi_sleep_policy` 2 (nunca desliga) → **1** (desliga com a tela apagada, exceto na tomada).
  Sem GMS não há push, então Wi-Fi ligado no standby só gasta: o RTL8188EU é USB e segura o
  wakelock `rtw_wifi`. Na tomada continua ligado (downloads longos). Desliga após `wifi_idle_ms`
  (padrão do framework, 15 min).
- Intervalo de busca desconectado: `wifi_supplicant_scan_interval_ms` 15000 → **60000** (Settings
  Global lido pelo `WifiStateMachine`). A propriedade `wifi.supplicant_scan_interval=15` do
  build.prop **não é lida** por nada neste firmware (nem framework, nem `libhardware_legacy`, nem
  `wpa_supplicant`): é resto do Android 2.x e ficou como está.
- `wifi_scan_always_enabled` = 0 (sem varredura para localização com Wi-Fi desligado).

## GPU e DDR

- Mali-400: dmesg "mali freq table : 192, 256, 384" MHz; o driver faz DVFS sozinho. O hw44 não
  achou nó de sysfs (`== mali` vazio): nada é mexido. A medir no aparelho (só leitura).
- DDR: dmesg "ddrfreq: normal 396MHz video 0MHz … idle 0MHz suspend 0MHz". `idle 0`/`suspend 0`
  significa que a DDR **não** baixa de frequência em ocioso nem em suspend. É um ganho potencial
  de standby, mas exige kernel (ou nó do ddrfreq, se existir). A medir.
- Temperatura: nenhum `thermal_zone` nem `temp` na bateria (`rk30_adc_battery`); não há leitura
  de temperatura disponível. A medir: procurar `tsadc`.

## Boot

- `debug.sf.nobootanimation=1` (lido pelo `/system/bin/bootanimation` deste firmware): sem
  animação de boot, menos CPU/GPU disputando com o zygote. Medido ao vivo: boot_completed em ~39 s.
- Bateria: `rk30_adc_battery` estima % por tensão (ADC); a % oscila. Para comparar, use
  também `voltage_now` (a telemetria grava os dois) e sessões longas (≥1 h).
