- Fuso: tzdata do 4.4 ainda tem horário de verão BR (extinto em 2019) → relógio 1 h adiantado em America/Sao_Paulo. Workaround: persist.sys.timezone=America/Fortaleza. Na ROM: atualizar /system/usr/share/zoneinfo/tzdata.
  - **Resolvido na ROM (v1.0.0):** o 4.4.2 usa o formato único `tzdata` do bionic/libcore (cabeçalho `tzdata2013h`, índice de 52 B por zona, TZif concatenados, zone.tab no fim) — não `zoneinfo.dat/.idx` (isso é do 4.0–4.2). O build compila o `zic` do tzcode 2026f, gera os TZif com `-b fat` (o KitKat é 32 bits e lê só o bloco v1; o padrão `slim` deixaria o bloco vazio) a partir do formato `rearguard` (sem DST negativo, ex. Europe/Dublin), e empacota no mesmo formato (`scripts/lib/tzdata_bionic.py`). Conferido: no 2013h de fábrica, America/Sao_Paulo tem DST 2026-10-18 (vigente -02 hoje); no gerado, a última transição é 2019-02-17 (vigente -03). Fuso padrão continua America/Fortaleza. Escape: `TZDATA_UPDATE=0`.
- USB: firmware vem com `persist.sys.usb.config=mass_storage,adb` no **/system/build.prop** (o `default.prop` do ramdisk tem `persist.sys.usb.config=adb`, mas o init lê o build.prop depois e ele vence; sem `/data/property` após o wipe, é o valor efetivo). Ao plugar, o host monta a partição `user` como pendrive, o Android perde o `/sdcard` e o adb fica instável. Na ROM: `persist.sys.usb.config=mtp,adb` só no build.prop — não precisou repacotar o ramdisk. O `init.rk30board.usb.rc` tem o bloco `mtp,adb` (PID 0x0011). `ro.factory.hasUMS=true` ficou: só habilita a opção de pendrive no MountService/notificação, não força o modo.
- CheckJNI ligado no estoque: build.prop define `ro.kernel.android.checkjni=0` e mais abaixo `=1` (vale o último); `libandroid_runtime.so` liga CheckJNI quando `dalvik.vm.checkjni` não é `false`. Na ROM: `dalvik.vm.checkjni=false` e uma única linha `ro.kernel.android.checkjni=0`.
- `wifi.supplicant_scan_interval` (build.prop) é placebo neste firmware: nenhuma referência em framework/services/libhardware_legacy/wpa_supplicant. O que vale é Settings.Global `wifi_supplicant_scan_interval_ms` (aplicado no 1º boot).
- Firefox 68 não funciona como app de sistema no 4.4: `libmozglue` abre `$MOZ_ANDROID_LIBDIR/libxul.so`, e o Java preenche com `nativeLibraryDir`, que para app de sistema não atualizado aponta para `/data/app-lib/<nome>` vazio (o PackageManager do 4.4 não extrai libs de apps de sistema). Solução: `/system/preinstall` — o `PackageManagerService` da Rockchip (`copyPackagesToAppInstallDir`, guardado por `persist.sys.preinstalled`) copia para `/data/app` no 1º boot após wipe, e aí as libs são extraídas normalmente.
- `/system/preinstall` de fábrica tinha 11 APKs de 2014 (~156 MB: Facebook, Skype, Angry Birds, Office…) copiados para `/data` a cada wipe. Removidos.
- O aparelho roda com o **parameter do 4.2.2** (dmesg: `firmware_ver=4.2.2`, `user` em `0x402000`); o do pacote 4.4 põe `user` em `0x462000`. As partições que gravamos (misc…system) estão no mesmo lugar nos dois. Gravar o `update.img` pelo RKBatchTool troca o parameter e muda o início da partição `user` (armazenamento interno): conteúdo perdido/reformatar. Por isso o caminho recomendado não grava parameter.
- Touch AW5306 roda em **polling mode** (dmesg) e o ddrfreq não baixa a DDR em ocioso nem em suspend (`idle 0MHz suspend 0MHz`). Ambos só mudam no kernel — candidatos a v2.
- `power.rk3026.so` faz `boostpulse` no toque (sobe para `hispeed_freq` por 500 ms) e tenta `interactive/input_boost`, que não existe neste kernel.
- `ro.config.low_ram`: quem consulta neste firmware — ActivityThread (tira GPU de processos persistentes), InputMethodService, ActivityStack/ActivityManagerService/BroadcastQueue/ActiveServices/SyncManager (limites menores), WindowManagerGlobal.startTrimMemory, AudioService, e no SystemUI BarTransitions/PhoneStatusBar/ImageWallpaper/RecentsPanelView.
- IWindowManager neste framework.jar: `TRANSACTION_setAnimationScale = 51` (`service call window 51 i32 <qual> i32 <bits do float>`), usado pelo 1º boot para as escalas valerem sem reiniciar.

## v1.1 (visual)

- **Tela 800×480, por dedução.** O dmesg dá `fb0 len 0x500000` e `lcdc0: dclk:37125000 fps:67`. 37,125 MHz ÷ 67 fps ≈ 554 mil pixels por quadro, o que bate com 800×480 na temporização padrão 1056×525 (66,96 fps). 1024×600 sozinho já teria 614 mil pixels ativos, impossível nesse clock. A densidade é `ro.sf.lcd_density=160`. Confirmar com `adb shell wm size` (TEST-PLAN 12.1).
- **Papel de parede padrão da Rockchip.** O `WallpaperManager.getDefaultWallpaperLocked()` deste `framework.jar` abre primeiro `system/media/rkfactory/default_wallpaper.jpg` (JPEG 1024×720). Só se ele não existir cai no `default_wallpaper.jpg` do `framework-res.apk` (2160×1920). Ele decodifica e chama `generateBitmap(getWidthHint, getHeightHint)`. Trocar esse arquivo muda o padrão sem mexer no framework-res.
- **Fontes.** O 4.4 usa `system_fonts.xml` (12 arquivos Roboto) e não tem família `sans-serif-medium`. O Roboto de fábrica (2014) e o Roboto 3.016 têm a mesma `hhea` (1900/-500 em 2048). O `DroidSans*.ttf` é link simbólico para o Roboto.
- **Xposed.**
  - O servidor oficial (`dl.xposed.info`/`dl-xda.xposed.info`) não responde, e o F-Droid só tem o Installer 3.1.5, que não traz o framework para KitKat (baixava do servidor oficial).
  - O Installer v33 ("2.7 experimental1": `app_process` v58, XposedBridge 54) e o GravityBox [KK] v138 (3.6.2) estão no Internet Archive. Integridade: md5 igual ao prefixo do nome oficial, SHA-1 igual ao índice do arquivo, assinaturas CN=rovo89 / CN=C3C0.
  - O `app_process` de fábrica é o AOSP 4.4 puro: os imports são os mesmos do Xposed, mais `atrace_set_tracing_enabled`. Os 95 símbolos do `app_process_xposed_sdk16` resolvem nas 12 libs do firmware (`scripts/lib/elfcheck.py`, roda no build).
  - O binário procura o jar só em `/data/data/de.robv.android.xposed.installer/bin/XposedBridge.jar` (caminho fixo). Desliga com `conf/disabled`. Tem modo de segurança (`safemode_*`).
- **GravityBox 3.6.2.**
  - Lê as prefs de `com.ceco.kitkat.gravitybox_preferences.xml` via XSharedPreferences, por isso o arquivo precisa ser legível por todos.
  - Os estilos de bateria em círculo animam a 50 ms enquanto carrega (`CmCircleBattery.updateChargeAnim`).
  - `pref_signal_cluster_lollipop_icons` é a única opção do grupo "signal cluster" que sobra em aparelho não-MTK.
- **IME e force-stop.** O `InputMethodManagerService` do 4.4 desmarca o IME atual quando o pacote dele leva `force-stop`. Por isso o 1º boot só mata o processo do teclado para ele reler as prefs.
- **Launchers avaliados.**
  - TinyBit 7.5 (F-Droid, minSdk 19): 2 dex, 3 MB no total. Multidex no Dalvik pesa no dexopt e na RAM.
  - Nova: não há fonte confiável com hash publicado pelo autor.
  - KISS continua o padrão.

## v1.2 (robustez)

- **Bateria (telemetria 13–14/11):** gasta. Os dois desligamentos súbitos foram sob carga (Firefox
  81–94% de CPU) a 3,66 V e 3,38 V; o primeiro já estava em 816 MHz, então limitar a CPU sozinho não
  garante — o `m7s-powerguard` limita a 816 MHz na bateria e desliga limpo abaixo de 3480 mV (2 leituras).
  O `status` da bateria fica "Not charging" também desplugado: a fonte é decidida por `usb/online` e
  `ac/online`. Desligar sem diálogo: `com.android.server.ShutdownActivity` (permissão SHUTDOWN, que o
  root do boot hook tem), ação `android.intent.action.ACTION_REQUEST_SHUTDOWN`, extra
  `android.intent.extra.KEY_CONFIRM=false`.
- **KISS e favoritos:** no 1º `onCreate` o KISS 3.24.2 cria os favoritos padrão com
  `DataHandler.addToFavorites` (guardado por `first-run-favorites` e histórico vazio), que só
  acrescenta. O 1º boot põe a Prancheta na frente da lista `favorite-apps-list` sem apagar as outras.
- **Apps leves com minSdk ≤ 19:** quase todos os gerenciadores de arquivos, editores e leitores
  atuais do F-Droid exigem 21+ (Amaze, Material Files, Ghost Commander, Librera, MuPDF ≥ 1.20,
  Fossify). Sobram Little File Explorer, My Notes e, no archive, Document Viewer 2.8.2 (split
  armeabi-v7a). A pré-instalação depende do wipe, e a gravação sempre faz wipe (`misc.img` com
  `--wipe_all`), então o Document Viewer entra como app comum.

## v1.2.1 (1º flash real, 14/11)

- **mksh do 4.4 e `|` em padrões:** `e="a|b"; echo ${e%%|*}` devolve vazio no aparelho (o sh do macOS
  devolve `a`). Use sempre `${e%%"|"*}`. Os scripts do overlay precisam ser testados **no aparelho**, não
  no Mac.
- **Launcher e SharedPreferences:** depois do `am force-stop` o KISS volta na hora (é a home); se estiver
  vivo quando o arquivo é gravado, o próximo commit dele sobrescreve. Pare de novo depois de gravar.
- **rkflashtool r** lê em blocos de 0x20 setores; uma leitura de tamanho não alinhado volta curta.
- `KEYCODE_WAKEUP` (224) não existe no 4.4; para acordar a tela, `input keyevent 26` se `mScreenOn=false`.
