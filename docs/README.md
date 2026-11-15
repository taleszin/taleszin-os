# Taleszin OS

ROM autoral para o tablet **Multilaser M7s Dual Core (ML01-M7-SD)**: tela inicial, tema, animação
de boot, vigia de bateria, telemetria e app de diagnóstico próprios. O hardware é sustentado pelos
binários do firmware oficial (KOT49H, Rockchip, 03/04/2014), que o build usa como base.
O repositório se chama m7s-kitkat-rom por histórico.

O build é um script: você entra com o zip oficial, ele baixa os apps livres por URL fixa, confere
tudo por sha256 e gera as imagens prontas para gravar. Não versionamos nem distribuímos firmware
nem APKs. Duas execuções com as mesmas entradas dão os mesmos bytes (sha256 idêntico).

> **Aviso.** Gravar firmware pode deixar o aparelho sem ligar se algo der errado (cabo solto,
> bateria acabando, aparelho errado). O loader e a tabela de partições **não são tocados** pelo
> caminho recomendado, então o modo loader continua disponível para voltar ao estoque. Mesmo
> assim, você assume o risco. Sem garantia (ver LICENSE).

## Compatibilidade

Só **ML01-M7-SD** (RK3026, 2× Cortex-A9 1008 MHz, Mali-400, 512 MB, NAND rknand, Wi-Fi RTL8188EU,
touch AW5306, tela 7" 800×480). O `parameter` do aparelho precisa ter `system` em `0x282000`
com `0x180000` setores (é assim no 4.2.2 e no 4.4 oficiais). O `flash-mac.sh` não grava em outro
lugar. Outros "M7s" (quad core, 3G, M7S Plus) têm outro hardware: **não use**.

## O que muda em relação ao 4.4 oficial

| Área | Mudança |
|---|---|
| Apps removidos | 36 pacotes já testados desativados no aparelho (Google/GMS/Play, que não funcionam em 4.4 em 2026; papéis de parede animados; RKUpdateService; StressTest; Email/Exchange; Dialer; etc.), LatinIME e Launcher3 (substituídos), e os 11 APKs de pré-instalação de 2014 (Facebook, Skype, Angry Birds…). Lista: `config/remove.txt`. |
| Apps incluídos | Simple Keyboard e KISS (de sistema; teclado e launcher padrão). Firefox 68.11 ESR, SkyTube, F-Droid e ícones Ameixa via pré-instalação (viram apps comuns no 1º boot: atualizáveis e desinstaláveis). Desde a 1.2: Prancheta do Taleszin (APK local, 1º favorito do KISS), Little File Explorer e My Notes (de sistema), Document Viewer (PDF/EPUB/DjVu, pré-instalação). Lista: `config/apks.txt`; escolha em [Apps (1.2)](#apps-12). |
| Relógio | `tzdata` 2013h trocado pelo IANA 2026f no formato do KitKat: acaba a 1 h de adiantamento (o 2013h ainda tinha horário de verão no Brasil). Fuso padrão America/Fortaleza. |
| Certificados | ISRG Root X1 (Let's Encrypt) adicionado: HTTPS volta a funcionar na maioria dos sites. |
| Desempenho | zRAM 128 MB, KSM, VM ajustada, escalonador `deadline` na NAND, governor `interactive` ajustado, CheckJNI desligado, `heapsize` 128m, `ro.config.low_ram=true`, sem animação de boot, animações 0. Detalhes: `docs/HARDWARE.md`. |
| Bateria | brilho padrão 40%, Wi-Fi desliga com tela apagada fora da tomada, busca de rede a cada 60 s, sem varredura "sempre ligada", sem vibração/sons de toque. |
| USB | `mtp,adb` em vez de `mass_storage,adb` (o pendrive tirava o `/sdcard` do Android e deixava o adb instável). |
| Visual (1.1) | Roboto 3 no lugar do Roboto de 2014 (mesma altura de linha) + família `sans-serif-medium`; papel de parede escuro próprio como padrão; KISS com ícones Material (Ameixa) e tema escuro; Simple Keyboard e F-Droid escuros. Opcionais, desligados: bootanimation Material, Xposed + GravityBox, Google Sans Flex. Custos, flags e riscos: `docs/VISUAL.md`. |
| Guarda de bateria (1.2) | `m7s-powerguard`: na bateria limita a CPU a 816 MHz (na tomada volta a 1008); abaixo de 3480 mV em 2 leituras seguidas (fora da tomada, depois de 120 s de boot) desliga limpo pelo framework. Log em `/data/m7s-telemetry/powerguard.log`. Desligar: `touch /data/m7s-powerguard.off` ou `POWERGUARD=0`. Detalhes: `docs/HARDWARE.md#bateria-gasta-m7s-powerguard`. |
| Telemetria | `m7s-telemetry`: registrador leve (30 s, CSV em `/data/m7s-telemetry`). Desligar: `touch /data/m7s-telemetry.off`. |

### `ro.config.low_ram=true` (ligado por padrão)

Conferido no `framework.jar`, `services.jar` e `SystemUI.apk` deste firmware (quem consulta
`isLowRamDevice()`/`isHighEndGfx()`): barras de status e navegação sem translucidez; SystemUI,
papel de parede e teclado desenhados sem GPU (processos persistentes perdem a aceleração);
só 1 serviço em segundo plano iniciando por vez (`ActiveServices`); menos tarefas recentes e
histórico de broadcasts; sincronizações uma por vez (`SyncManager`); caches de GPU liberados com
mais agressividade (`WindowManagerGlobal.startTrimMemory`); AudioFlinger em modo de pouca RAM.
Ganho: menos RAM fixa ocupada pelo SystemUI e menos picos de CPU no boot. Perda: visual mais
"chapado". Para desligar: `LOW_RAM=false scripts/build.sh …`.

### Como reverter cada padrão

Tudo que é Settings pode ser mudado normalmente no aparelho depois do 1º boot (o script de 1º
boot só roda uma vez). Para mudar o padrão da ROM, sobrescreva a variável no build:
`ANIM_SCALE=0.5 HAPTIC=1 TOUCH_SOUNDS=1 LOCKSCREEN_DISABLED=0 NO_BOOTANIM=0 LOW_RAM=false
WIFI_SLEEP_POLICY=2 USB_CONFIG=mass_storage,adb scripts/build.sh …` (lista completa em
`config/rom.conf`). Animações no aparelho: Configurações → Opções do desenvolvedor → escalas de
animação. Tela de bloqueio: Configurações → Segurança.

## Apps (1.2)

Critério: FOSS do F-Droid com versão de `minSdk <= 19` no índice (repo ou archive), sha256 do índice
fixado em `config/apks.txt`, sem serviço em segundo plano nem receptor de boot (só gastam RAM com o app
aberto). `/system/app` para APK sem lib nativa; `/system/preinstall` para quem tem (`.so` extraída
normalmente no 1º boot; ver FINDINGS). O estoque já traz relógio, calculadora, galeria, câmera, música,
vídeo (RkVideoPlayer) e o gerenciador de arquivos RkExplorer — todos mantidos.

| App | Versão (minSdk) | Onde | /system | RAM aberto (estim.) | Por quê |
|---|---|---|---|---|---|
| Prancheta do Taleszin (`app.mamba.prancheta`) | 1.2 (19) | `/system/app` | 0,15 MB | ~10–15 MB | Pedido do dono. Java puro, sem `.so`. Vem do APK local (`PRANCHETA_APK`), sha256 fixo; 1º favorito no KISS. |
| Little File Explorer | 4.18 (1) | `/system/app` | 0,04 MB | ~6–10 MB | O menor gerenciador FOSS que ainda roda no 4.4 (Amaze, Material Files e Ghost Commander exigem 21+). Copiar/mover/apagar e abrir com outro app; o RkExplorer continua. |
| My Notes (`com.aa.mynotes`) | 1.5.1 (17) | `/system/app` | 1,5 MB | ~15–20 MB | Bloco de notas simples, 1 dex, **nenhuma permissão**. Descartado: NotePad (trevin) 1.7.1 — 2 dex (multidex lento no Dalvik), serviço em primeiro plano e receptor de boot. Markor 2.16 = 12 MB. |
| Document Viewer (`org.sufficientlysecure.viewer`) | 2.8.2 (14), só armeabi-v7a | `/system/preinstall` | 9,0 MB | ~25–40 MB com PDF | PDF, EPUB, DjVu, XPS e CBZ (MuPDF/EBookDroid) num app só. Descartados: MuPDF 1.19 (11,8 MB, APK com 3 ABIs), Orion 0.97 (11 MB, sem EPUB), KOReader (30 MB), APV (só PDF, 2014). |

Total: ~10,7 MB a mais no `/system` (ainda sobram ~159 MB livres na partição); no `/data`, o Document
Viewer ocupa mais ~18 MB (cópia do APK + `.so`). Sem player de música novo: o Music do AOSP 4.4 é leve e
cumpre; SicMu (4 MB) ficaria como alternativa via F-Droid. `PRANCHETA=0` / `EXTRA_APPS=0` tiram tudo.

## Construir

Requisitos (Mac ou Linux, sem root, sem Docker): `python3`, `e2fsprogs` ≥ 1.47 (`debugfs`,
`e2fsck`, `dumpe2fs`, `resize2fs`), `cc` + `make`, `curl`, `awk`, `unzip`.

```sh
brew install e2fsprogs            # macOS (keg-only; o script acha em /usr/local/opt ou /opt/homebrew/opt)
# Debian/Ubuntu: sudo apt install e2fsprogs build-essential curl python3
scripts/build.sh ~/Downloads/Multilaser_M7S_Dual_Core-SUPRA_ML01_140403_4.4_RBT.zip
```

Leva ~2 min e usa ~3 GB em `work/` e `out/`. Downloads ficam em `work/cache` (ou `$M7S_CACHE`);
os links do F-Droid saem do ar quando sai versão nova — se um link quebrar, coloque o APK com o
sha256 certo em `work/cache/apk/<sha256>.apk` ou atualize `config/apks.txt`.

O que o build faz, em ordem: confere o sha256 do zip; extrai o `update.img` (RKFW) e as partições
(RKAF); extrai o `file_contexts` do ramdisk; compila `zic` (tzcode 2026f) e gera o `tzdata` no
formato do bionic 4.4; baixa e confere os APKs; gera `build.prop` e `/system/etc/m7s.conf`; monta
um plano de edição; aplica no `system.img` com `debugfs` (dono, grupo, modo, horário e rótulo
SELinux explícitos em cada arquivo novo; arquivos substituídos herdam os metadados e xattrs do
original); valida; reempacota o `update.img`.

Validações automáticas (o build para se alguma falhar):

- `e2fsck -fn` limpo; mesmas features ext4 do original (o kernel 3.0 não monta `metadata_csum` etc.);
- rótulo SELinux de **todos** os arquivos confere com o `file_contexts` do ramdisk (o rotulador é
  testado antes contra os 1750 arquivos de fábrica: 0 divergências);
- cada arquivo gravado é relido da imagem e comparado por sha256; cada removido sumiu;
- `tzdata` gerado sem horário de verão no Brasil depois de 2019;
- `system.img` cabe na partição (768 MiB); `s_wtime` = `SOURCE_DATE_EPOCH`;
- o empacotador RKFW/RKAF reproduz o `update.img` de fábrica byte a byte quando nada é trocado
  (conferido também com `rkunpack`/`rkcrc` do rkflashtool).

Reprodutibilidade: mesmo zip + mesmo `config/` + mesma versão do e2fsprogs ⇒ mesmo sha256.
Todos os timestamps do FS são `SOURCE_DATE_EPOCH` (via `E2FSPROGS_FAKE_TIME`/`E2FSCK_TIME`).
`out/BUILDINFO.txt` registra versões e configuração; `out/SHA256SUMS` os hashes.

### Saída (`out/`)

```
images/{kernel,boot,recovery,backup,misc,system}.img   partições a gravar (só system muda)
update.img            pacote RKFW para RKBatchTool (Windows)
parameter.txt         parameter oficial 4.4 (referência; não é gravado pelo flash-mac.sh)
flash-mac.sh          gravação via rkflashtool
FLASH-WINDOWS.md      gravação via AndroidTool / RKBatchTool
SHA256SUMS  BUILDINFO.txt
system-diff.tsv       arquivos adicionados (+), removidos (-) e alterados (M) vs. estoque
inventory.{stock,rom}.tsv   inventário completo (modo, uid, gid, tamanho, xattrs) das duas imagens
```

## Gravar pelo Mac

```sh
brew install rkflashtool
adb reboot bootloader          # ou: desligado, segure Vol- e conecte o USB
cd out && ./flash-mac.sh       # confere SHA256SUMS, pede "GRAVAR"; VERIFY=1 relê e compara
```

Equivale a (setores de 512 B; **nunca** grava parameter nem loader):

```sh
rkflashtool w 0x4000   0x4000   < images/kernel.img
rkflashtool w 0x8000   0x8000   < images/boot.img
rkflashtool w 0x10000  0x10000  < images/recovery.img
rkflashtool w 0x20000  0x20000  < images/backup.img
rkflashtool w 0x282000 0x180000 < images/system.img
rkflashtool w 0x2000   0x2000   < images/misc.img     # contém --wipe_all: apaga /data no próximo boot
rkflashtool b
```

O 1º boot demora (wipe + otimização de todos os apps, 3–6 min). Depois disso, em ~10 s após a
tela inicial, o `m7s-firstboot` aplica os padrões (log em `/data/local/m7s-firstboot.log`).

Windows: ver `FLASH-WINDOWS.md`.

## Voltar ao estoque (rollback)

O loader e o parameter não mudam, então o modo loader sempre volta.

- **Para o 4.4 oficial:** grave as partições do pacote oficial com os mesmos comandos acima
  (extraia com `python3 scripts/lib/rkimg.py unpack update_….img dir/`: os arquivos em
  `dir/rkaf/` são as partições), ou o `update.img` oficial pelo RKBatchTool (este também grava
  o loader e o parameter 4.4 — ver o aviso sobre a partição `user` em `FLASH-WINDOWS.md`).
- **Para o 4.2.2 de fábrica:** grave as partições do backup do 4.2.2 nos mesmos endereços (misc,
  kernel, boot, recovery, backup e system ficam no mesmo lugar nos parameters 4.2.2 e 4.4).
- Sem loader (tela preta, nada responde): modo MASKROM (procedimento de hardware descrito nos
  guias do RK3026) + RKBatchTool com o `update.img` oficial. Só em último caso — a ROM não
  grava o loader, então isto não deveria ser necessário.

Problemas conhecidos de recuperação:
- Sem launcher (KISS quebrou): `adb install` de qualquer launcher, ou religue o Launcher3 gravando
  a ROM com `config/remove.txt` sem a linha dele.
- Sem teclado: `adb shell ime set rkr.simplekeyboard.inputmethod/.latin.LatinIME`.
- Relógio errado: `TZDATA_UPDATE=0` reconstrói com o tzdata de fábrica (e use America/Fortaleza).

## Estrutura

```
config/rom.conf           todos os padrões (sobrescrevíveis pelo ambiente)
config/remove.txt         o que sai do /system
config/apks.txt           o que entra (URL ou local:VAR + sha256)
config/sources.txt        sha256 do firmware e do tzdata
config/disable-packages.txt  pacotes desativados ao vivo (o build exige que todos estejam em remove.txt)
overlay/system/           arquivos copiados para /system (boot hook, scripts, certificado)
scripts/build.sh          build
scripts/flash-mac.sh      gravação (copiado para out/)
scripts/lib/              rkimg.py (RKFW/RKAF/boot.img), sysimg.py (debugfs, inventário,
                          SELinux), tzdata_bionic.py, buildprop.py, rkcrc32.c,
                          fonts.py (fontes), art.py (papel de parede/bootanimation),
                          elfcheck.py (símbolos do app_process do Xposed)
docs/                     este README, VISUAL.md, HARDWARE.md, TEST-PLAN.md, FINDINGS.md, FLASH-WINDOWS.md
```

## Changelog

### 1.5.4 — 2026-11-15 (autonomia)

Medição antes de mexer (tablet ao vivo + telemetria de 14–15/11):
- **Standby já está limpo.** Com a tela apagada na bateria o aparelho dorme de fato: só 4 alarmes acordaram o aparelho desde o boot, o Wi-Fi dorme (`wifi_sleep_policy=1`, driver 8188eu com LPS/IPS) e os nossos daemons ficam congelados no suspend.
- **O gasto é com a tela ligada.** Na telemetria fora da tomada são ~1,3 h, quase tudo com a tela acesa, e a bateria de 2014 cai ~100 %/h (o gauge é por tensão e não é preciso). Com o aparelho parado, a CPU fica perto de zero: Estante ~0,6 %, KSM ~1 % de um núcleo (economiza ~18 MB de RAM, fica), e os quatro daemons ~0,7 % de um núcleo somados. O que sobra é a **luz de fundo**, que a 175–219/255 (a média de uso) é o maior consumidor.
- **A CPU já está contida.** Na bateria o teto é 816 MHz (1008 nunca é usado), o Wi-Fi está em economia e as animações estão desligadas.

Mudanças:
- **Brilho de bateria** (`PG_BATT_BRIGHT=170`): ao desplugar, se o brilho estiver acima de 170/255 o powerguard baixa para 170 **uma vez**. O usuário pode subir de novo e o guarda não insiste. Na tomada, o brilho de antes volta. A luz de fundo é ~linear no PWM: 219→170 corta ~22 % dela. Ganho esperado de **~5–10 % de autonomia** com a tela ligada quando se usa brilho alto. `0` desliga.
- **Sentinela sem sync a cada 5 s na bateria**: o pulso vai para o disco a cada 15 s, como na tomada, e só passa a ir a cada pulso quando o apagão é provável (tensão < 3650 mV ou load ≥ 4). A faxina da caixa preta (ls/sort/rm, wc) roda a cada ~5 min em vez de a cada pulso. Ganho pequeno, ~1 %: menos escrita na NAND e ~6 processos a menos a cada 5 s.
- **Wi-Fi**: `wifi_networks_available_notification_on=0` (o aviso de "redes abertas" fazia o Wi-Fi varrer sozinho quando desconectado). Vai no `m7s-firstboot` e foi aplicado ao vivo.
- **Correção do botão**: em 15/11 20:39 o `m7s-botao` não subiu no boot. O `install-recovery.sh` agora apaga os `.pid` da sessão anterior antes de subir os daemons (um PID velho que no boot novo caísse num processo cujo cmdline citasse o daemon fazia ele achar que já rodava). Além disso, o botão espera o nó `/dev/input/event0` existir e ignora o processo pai.

Ficou de fora (de propósito):
- **Teto de CPU ou governor mais preguiçoso com a tela ligada**: o travamento por thrash foi o grande problema e o toque não pode piorar. Na bateria já valem os 816 MHz.
- **Brilho automático**: o "Light sensor" da lista é o HAL de mentira do AOSP (sempre 0), não existe sensor de luz.
- **Escurecer depois de N s sem toque**: o Android 4.4 só escurece nos últimos segundos antes do timeout. Daria para fazer lendo o touchscreen cru (como o `m7s-botao`), mas é invasivo; fica como ideia.
- **`dirty_writeback` mais longo**: aumentaria a perda de dados nos apagões, que são frequentes com esta bateria.
- **Tirar a KSM**: custa ~1 % de um núcleo e devolve ~18 MB de RAM. Num aparelho de 512 MB vale.
- **O ganho grande de verdade é trocar a bateria**: são 2200 mAh nominais de 2014, que hoje rendem menos de 1 h de tela. Uma Li-Po nova de 3,7 V e mesmo tamanho daria várias horas.

Como medir: compare o `batt_mv` por hora com a tela ligada (`backlight>0`, `usb=0`) nos CSVs de `/data/m7s-telemetry` antes e depois de 15/11, e procure "bateria: brilho" no `powerguard.log`.

### 1.5.3 — 2026-11-15 (anti-travamento e caixa preta)
Telemetria de 15/11: os congelamentos são **falta de memória com o Bromite** (165 MB de ~400 MB úteis).
Às 13:12 o tablet ficou 15 min parado com load 25 e a telemetria sem conseguir gravar; só voltou com
reinício forçado. O LMK do kernel 3.0 conta o ashmem do Chromium como cache descartável e nunca matava.
- `m7s-sentinela` (novo, prioridade alta, só /proc e kill): mede load, memória realmente livre
  (MemFree + Cached − Shmem − Mapped) e page faults/s a cada 5 s. Em aperto confirmado mata **um**
  processo, do menos importante ao mais: app em 2º plano → serviço/visível → renderizador da aba da
  frente (a aba recarrega; o navegador continua). Registra tudo na **caixa preta**.
- **Caixa preta** (`/data/m7s-telemetry/caixa-preta-*.log`): pulso de 5 s em RAM, persistido a cada
  60 s (e sempre na bateria/aperto); retrato em cada intervenção (top memória/CPU, meminfo, dmesg);
  no boot diz **como a sessão anterior acabou** (desligamento limpo, bateria, travou, parou sem aviso).
- Telemetria: novas colunas `majflt_s, swpin_s, swpout_s, shmem_kb, top_app, top_app_cpu`; retrato a
  cada 15 min com meminfo/vmstat/LMK; `erros-*.log` com crashes Java e nativos.
- LMK: 2º plano/cache passam a 48/64/96/128 MB. Bromite: `--renderer-process-limit=1`,
  `--disable-site-isolation-trials`; o `chrome-command-line` da ROM sempre substitui o antigo.
- powerguard: o brilho devolvido na tomada sobrescrevia a variável de fonte ("fonte=0" no log).
- `m7s-botao` (novo): **segurar o liga/desliga 8 s reinicia à força**, mesmo com o Android travado
  (lê o teclado cru no kernel; sync, remonta só-leitura e reinicia via sysrq). Antes só o palito no
  furo de reset resolvia. A caixa preta registra o reinício e o boot seguinte o classifica.
- LMK: o ActivityManager regrava o `minfree` ao subir; o sentinela reaplica o da ROM.

### 1.5.2 — 2026-11-14 (proteção de bateria em degraus)
Telemetria de 14/11 à noite (bateria, com a tensão ao vivo da 1.5.1): o degrau de 3,80 V descia a CPU
para 504 MHz quase o tempo todo (a bateria gasta fica em 3,7 V com o Bromite já a 73%) e o Bromite a
97% de CPU em 504 MHz **travava a tela** (20:07 e 20:30, reinício forçado). O corte em 3,48 V x2
desligou três vezes com a tela marcando 33–47%, sem aviso nenhum.
- `m7s-powerguard`: escada de economia no lugar do "desliga cedo". **Economia** (< 3,60 V): brilho
  ≤ 110 e fecha apps em segundo plano gastando > 30% de CPU. **Crítico** (< 3,48 V): CPU 504 MHz,
  brilho ≤ 60 e fecha o app da frente se ele passar de 55% de CPU (Bromite = navegador + renderizador
  somados). **Desligar** só abaixo de 3,40 V em 3 leituras, 30 s depois do crítico, com aviso e
  contagem de 15 s que o carregador cancela. Cada degrau exige 2 medianas seguidas (3 leituras em 2 s).
  O brilho do usuário volta ao ligar na tomada.
- Diagnóstico 1.2: janela `Aviso` que o guarda abre para explicar o que fez.

### 1.5.1 — 2026-11-14 (acabamento visual)
- Barras de status e de navegação translúcidas de verdade: o `low_ram` desligava a transição do KitKat
  (`ActivityManager.isHighEndGfx()`); o tema responde "sim" só dentro do construtor do `BarTransitions`
  da SystemUI — sem aceleração por GPU nas janelas, o resto continua econômico.
- Configurações: item ativo vira pílula laranja translúcida (antes bloco chapado); título de seção sem o
  sublinhado do Holo.
- Notificações: some o quadrado azulado atrás do ícone (`notification_template_icon_bg`).
- Cortina no padrão de celular: a tela de 480 dp caía no layout de tablet (sw480dp) — painel estreito
  com margem, 40% de altura mínima (bloco preto vazio) e atalhos escondidos numa zona de arrasto.
  Agora: largura total, altura do conteúdo, botão de atalhos no cabeçalho que vira o painel, alça em
  pílula, ícones do cabeçalho redesenhados e grade 3x3 de atalhos de tablet Wi-Fi (Wi-Fi, brilho,
  ajustes, rotação, bateria, avião, captura, volume, dormir).
- Ícone de depuração USB: o "IIII" do firmware RK vira um terminal (`>_`).
- **GravityBox e Xposed Installer sumiam do PackageManager** desde a 1.4.1: a pasta do pacote rotulada
  `dalvikcache_data_file` impedia o installd de recriar o link `lib` ("missing metadata"), e o GB
  perdia o próprio contexto (atalhos sem gerência, app de ajustes ausente, `pm path` vazio). A pasta de
  cima agora é `system_data_file`; só `bin/conf/shared_prefs` ficam `dalvikcache_data_file`.
- **Tensão ao vivo**: o `rk30_adc_battery` só reescreve `voltage_now` quando o % muda — o degrau de
  afundamento e o corte nunca viam a queda. Powerguard, telemetria e Diagnóstico (1.1) leem o
  `cur adc value` do `batinfo` (6,06 mV/unidade, calibrado com os pares que o kernel loga).
- Powerguard mede a cada 10 s na bateria (era 25 s; o tablet apagou segundos depois de desplugar com
  o Bromite a 90%). Telemetria faz `sync` a cada linha na bateria (antes nenhuma linha com usb=0
  sobrevivia aos apagões).
- firstboot: caminho dos módulos Xposed cai no `packages.xml` quando o `pm path` volta vazio;
  `setprefs` aceita `set|nome|a,b,c`.

### 1.5.0 — 2026-11-14 (linguagem visual)
- Taleszin Tema desenha os componentes (tools/material.py), em vez de só recolorir: caixas de
  marcar e rádios arredondados, interruptor em pílula sem o texto LIGADO/DESLIGADO (hook no Switch),
  janelas com cantos de 16dp e menus com 12dp, toast em pílula, notificações em cartões, painel
  grafite liso e blocos arredondados nas configurações rápidas.
- GravityBox: barras translúcidas forçadas (`pref_translucent_decor=1`), ícones de sinal lisos,
  rótulos dos atalhos sem caixa alta.
- SmartCookieWeb 16.3 como navegador leve (`NAVEGADOR_LEVE=1`). Usa o WebView do sistema
  (Chromium 30, não atualizável no 4.4): bom para páginas simples; sites modernos continuam no
  Bromite. Os únicos livres com motor próprio e minSdk 19 são o Bromite 81 e o Gecko 68
  (Firefox/IceCat), ver pesquisa no histórico do projeto.

### 1.4.2 — 2026-11-14 (correções da telemetria)
- Telemetria e powerguard podiam não subir no boot: o .pid sobrevive ao reboot e o número era de
  outro processo (surfaceflinger), então o script achava que já estava rodando e saía. Agora confere
  o /proc/PID/cmdline. Efeito do bug: tablet sem vigia de bateria naquele boot.
- Powerguard em degraus: 14/11 03:44 o tablet apagou na bateria com Bromite a 95% de CPU
  (3,78 → 3,63 V em 1 min, entre duas leituras). Abaixo de 3,80 V o teto desce para 504 MHz e a
  leitura passa a cada 5 s; volta a 816 MHz acima de 3,88 V.
- Bromite: o chrome.sh de fábrica copiava para /data/local/chrome-command-line (777)
  `--ignore-gpu-blacklist` (força a Mali-400; crash nativo "Bus error" no Bromite) e UA do Chrome 30.
  A ROM traz /system/etc/chrome-command-line com `--enable-low-end-device-mode`, e o boot troca o de
  fábrica (644).

### 1.4.1 — 2026-11-14
- Correção: numa gravação limpa o Xposed não carregava (barra de navegação e tema voltavam ao
  KitKat). O zygote roda com SELinux enforcing e tem `search/read` negado em `app_data_file`
  (`avc: denied … tcontext=app_data_file`), então não lia o XposedBridge.jar, a modules.list nem as
  prefs do GravityBox. Novo `m7s-xposed-selinux` rotula só esses caminhos como
  `dalvikcache_data_file`; roda no 1º boot e a cada boot (idempotente). Na 1.3 tinha passado
  despercebido porque o Xposed foi montado à mão.
- Aviso: `flash-mac.sh` grava o misc com `--wipe_all`, então o /data é apagado (faça backup da Prancheta).

### 1.4.0 — 2026-11-14 ("Taleszin OS")
- Nome próprio: `ro.build.display.id=Taleszin OS 1.4.0` (Sobre o tablet), `ro.taleszin.name/version/base`.
- Animação de boot autoral: bola de basquete com arco laranja girando (art.py).
- Tela inicial: assinatura "TALESZIN OS · versão"; Bromite no lugar do Firefox na doca.
- Diagnóstico: card de Temperatura na aba CPU. O RK3026 não tem sensor (nem a bateria), então mostra
  estimativa de aquecimento (média de 1 min de uso × velocidade²), rotulada como estimativa; se algum
  thermal_zone/hwmon/temp de bateria existir, mostra °C real. Textos "ROM m7s" → Taleszin OS.
- Navegador: Bromite 81.0.4044.127 (Chromium, open source, bloqueio de anúncios; último com minSdk 19).
  Firefox 68 fora por padrão (`FIREFOX=1` traz de volta); libera ~100 MB de /data.
- Jogos (`JOGOS=1`, preinstall, ~36 MB): Puzzles do Simon Tatham, 2048, Frozen Bubble, OpenSudoku,
  Paciência, Xadrez, Blockinger, Klooni.

### 1.3.0 — 2026-11-14 ("identidade")
- **Taleszin Home** (`~/dev/taleszin-home`) é a tela inicial: relógio grande, saudação, bateria e RAM, dock de
  favoritos e gaveta com busca (~9 MB). O KISS fica instalado mas desativado (`HOME_LAUNCHER=kiss` volta).
- **m7s-tema** (`~/dev/m7s-tema`, módulo Xposed): 9 cores + 180 drawables do framework trocam o azul Holo pelo
  laranja #FF7A1A em todos os apps. `touch /data/local/tmp/m7s-tema.off` desliga no próximo boot.
- **Diagnóstico** (`~/dev/m7s-diagnostico`): app estilo CPU-Z, didático, com 11 telas e leitura da telemetria.
- Papel de parede com meia quadra de basquete (`art.py`). Barra de navegação sempre embaixo, ícones grandes.
- Apps: SkyTube travado na 2.999 (3.00x não toca no 4.4), BravePipe KitKat, VLC 3.7.2, Open Camera 1.53.1.
  Removidos Browser, RkExplorer, RkVideoPlayer e Contacts (duplicados).
- Telemetria legível por apps (`umask 022`); `scaling_max_freq` legível (0664) no boot.

### 1.2.2 — 2026-11-14 ("cara nova")
- **Xposed + GravityBox ligados por padrão** (`XPOSED=1`). Os 95 símbolos do `app_process` v58 resolvem nas
  libs do firmware; validado no aparelho.
- `GB_MODERN=1`: botões de navegação ◀ ● ■ (estilo Lollipop), bateria com %, relógio centralizado, ícones
  planos, notificações flutuantes, "limpar tudo" + barra de RAM nos recentes, brilho deslizando na barra de
  status, painel de volume expansível, GravityBox em tema escuro.
- `m7s-firstboot`: o mksh do 4.4 não tem `printf` (arquivo de prefs novo saía sem cabeçalho XML).

### 1.2.1 — 2026-11-14 (correções do 1º flash real)
- `m7s-firstboot`: o mksh do 4.4 não trata `|` sem aspas em `${e%%|*}` (devolve vazio), então o
  `setprefs` gravava entradas inválidas e **nenhum** tema (KISS escuro, Ameixa, teclado e F-Droid escuros)
  nem o favorito da Prancheta era aplicado, embora o log dissesse que sim. Corrigido com `"|"` e limpeza das
  entradas inválidas antigas. O KISS também leva um force-stop depois da gravação (ele volta sozinho como
  home e regravaria as prefs que tem em memória).
- `flash-mac.sh`: a conferência lia `ceil(bytes/512)` setores, mas o rkflashtool lê em blocos de 0x20,
  então voltava curto e o `cmp -n` do macOS acusava EOF. Agora arredonda pra 0x20 e compara sha256.
- `m7s-powerguard`: log no horário local (o `busybox date` ignora `persist.sys.timezone` e escrevia UTC).

### 1.2.0 — 2026-11-14 ("robustez")
- **Guarda de bateria** `m7s-powerguard` (amostra a cada 25 s, só sysfs): teto de CPU 816 MHz na
  bateria / 1008 MHz na tomada; desligamento limpo (`ACTION_REQUEST_SHUTDOWN` sem confirmação; se em 60 s
  não desligar, `sync` + `reboot -p`) quando a tensão fica abaixo de 3480 mV em 2 leituras seguidas fora
  da tomada, ignorando os primeiros 120 s. Configurável em `config/rom.conf` (`POWERGUARD`, `PG_*`).
  Motivo: telemetria de 13–14/11 (bateria gasta, gauge por tensão mentindo, desligamentos súbitos sob carga).
- Prancheta do Taleszin embutida em `/system/app` a partir do APK local (sha256 fixo) e posta como 1º
  favorito do KISS.
- Apps FOSS leves: Little File Explorer, My Notes, Document Viewer (ver [Apps (1.2)](#apps-12)).
- Build: `config/apks.txt` aceita `local:VAR` (arquivo local conferido por sha256, sem download).
- Telemetria (`m7s-telemetry`) inalterada; o powerguard grava `powerguard.log` e `powerguard.state` na
  mesma pasta.
- Ainda **não testada no aparelho**.


### 1.1.0 — 2026-11-13 ("visual remodernizado")
- Fontes Roboto 3.016 (OFL) com as mesmas métricas verticais do estoque, mais `sans-serif-medium`. Opção experimental `FONTS=googlesans` (Google Sans Flex em instâncias estáticas, renomeada "M7s Sans").
- Papel de parede escuro gerado no build (800×800, 76 KB) no lugar do padrão de fábrica da Rockchip (`/system/media/rkfactory/default_wallpaper.jpg`).
- 1º boot: KISS com ícones Ameixa e tema `transparent-dark`; Simple Keyboard e F-Droid em tema escuro.
- Opcionais, desligados por padrão:
  - `BOOTANIM=1`: spinner Material de 56 KB.
  - `XPOSED=1`: Xposed 2.7 exp1 + GravityBox 3.6.2 pré-configurado, com checagem de símbolos do `app_process` no build.
- TinyBit e Nova avaliados e descartados (ver VISUAL.md). Tema escuro global fica para a v2 (exige mod do framework-res).
- Ainda **não testada no aparelho**.

### 1.0.0 — 2026-11-13
- Primeira versão. Base: firmware oficial 4.4.2 140403 (KOT49H).
- Remoção de 36 pacotes + LatinIME + Launcher3 + pré-instalação de fábrica (~260 MB a menos no /system).
- Simple Keyboard 5.36 e KISS 3.24.2 como teclado e launcher padrão; Firefox 68.11.0, SkyTube 3.003,
  F-Droid 1.12.1, Ameixa 4.11.1 pré-instalados.
- tzdata 2026f (fim do horário de verão BR), ISRG Root X1.
- Boot hook: zRAM, KSM, VM, deadline, interactive; 1º boot com padrões de Settings; telemetria.
- build.prop: heapsize 128m, CheckJNI off, low_ram, sem bootanimation, MTP, brilho 40%.
- Ainda **não testada no aparelho**: ver `docs/TEST-PLAN.md`.
