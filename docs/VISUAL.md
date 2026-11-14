# Visual (v1.1 "remodernizado")

Objetivo: cara de Android atual sem desfazer o "o mais capado possível" da v1. Cada item é uma
variável de `config/rom.conf`, sobrescrevível no build (`FONTS=stock BOOTANIM=1 scripts/build.sh …`).
O custo de cada item vem da leitura do código do firmware e dos apps. Ele ainda **não foi medido no
aparelho**: a coluna "como medir" diz o comando, e o `TEST-PLAN.md` (item 12) diz em que ordem.

## Resumo

| Item | Variável (padrão) | Custo esperado | Como medir |
|---|---|---|---|
| Fontes Roboto 3 | `FONTS=roboto3` | +3,7 MB no /system. RAM ≈ 0: fonte é mapeada sob demanda e o cache de glifos do Skia tem o mesmo tamanho. A altura de linha é idêntica à do estoque (o build confere). | `cat /proc/$(pidof zygote)/smaps \| grep -A3 Roboto` (Rss) antes/depois |
| Papel de parede escuro | `WALLPAPER=1`, `WALLPAPER_SIZE=800x800` | ≈ zero. O padrão de fábrica da Rockchip é um JPEG 1024×720 que o 4.4 reduz para 800×800; o nosso já nasce 800×800 (mesmo bitmap residente de 2,4 MiB, sem a reescala). | `dumpsys meminfo com.android.systemui` antes/depois |
| Ícones Material no KISS | `ICON_PACK=org.xphnx.ameixa` | KISS lê o `appfilter.xml` do Ameixa ao abrir: +2–5 MB no KISS e alguns centésimos de segundo na 1ª abertura. | `dumpsys meminfo fr.neamar.kiss` com `ICON_PACK=default` × Ameixa |
| Tema escuro do KISS | `KISS_THEME=transparent-dark` | Zero (troca de estilo; o papel de parede já era desenhado atrás do KISS no tema de fábrica dele, `transparent`). | — |
| Apps escuros | `DARK_APPS=1` | Zero (Simple Keyboard tema 4 "Dark", F-Droid tema `dark`). | — |
| Bootanimation Material | `BOOTANIM=0` (OFF) | Se ligada: o `bootanimation` decodifica 30 PNGs de 160×160 em loop a 20 fps, competindo com o boot. Espere de +1 a +3 s até o `boot_completed`. A v1 mediu ~39 s sem animação. | `adb shell getprop` + cronômetro, ou `dmesg \| grep -i boot_completed`, com e sem |
| Xposed 2.7 + GravityBox 3.6.2 | `XPOSED=0` (OFF) | Se ligado: +8 a +15 MB somados (XposedBridge no zygote, GravityBox no system_server e no SystemUI) e chamada mais lenta nos métodos interceptados. Bateria em círculo a 20 fps enquanto carrega (por isso o padrão é o estilo 5). Risco de bootloop: ver abaixo. | `dumpsys meminfo` (Total PSS: system, com.android.systemui), `procrank` se existir |

## Fontes

**Padrão `roboto3`.**
- **Origem:** Roboto 3.016, de `googlefonts/roboto-3-classic` (OFL 1.1, sha256 fixo em `config/sources.txt`). Usa os TTFs estáticos da pasta `android/static` do pacote oficial.
- **O que muda:** são trocados os 12 `Roboto-*.ttf`/`RobotoCondensed-*.ttf` que o `system_fonts.xml` do 4.4 lista. O `DroidSans.ttf` é um link para `Roboto-Regular.ttf` e herda a troca.
- **Família nova:** `Roboto-Medium`/`MediumItalic` entram como família `sans-serif-medium`, que o 4.4 não tinha. Apps novos que pedem "medium" passam a ganhar o peso certo em vez do Regular.
- **Cobertura:** 3384 glifos contra 1052 no estoque (mais latim estendido, grego, cirílico, símbolos).
- **Métricas:** o Android usa a tabela `hhea` para a altura de linha, e a do Roboto 3 é igual à de 2014 (1900/-500 em 2048). O build falha se alguma fonte nova divergir mais de 0,5%. Portanto nenhum layout muda de altura e nenhum texto é cortado.
- **Licença:** o texto da OFL vai em `/system/etc/m7s/licenses/`.

**Opção `googlesans` (experimental).**
- **Origem:** Google Sans Flex 5.000 (OFL 1.1, sem nomes reservados). A fonte é variável; o build gera instâncias estáticas com o fontTools 4.68.0, cujo wheel puro-Python é baixado com sha256 fixo, sem pip.
- **Instâncias:** peso 100/300/400/500/700, inclinação 0/-10 para itálico, largura 75 para "Condensed", opsz 18.
- **Métricas e nome:** a altura de linha é normalizada para a do Roboto do estoque e a família é renomeada para "M7s Sans", porque as marcas "Google Sans" só podem acompanhar a fonte original.
- **Cobertura:** a Google Sans Flex só tem latim. Por isso o Roboto 3 entra como primeiro fallback (`fallback_fonts.xml`), e grego/cirílico continuam aparecendo.
- **Custo de build:** ~20 s por instância; o resultado fica em cache.
- **Risco:** o desenho é mais alto que o Roboto dentro da mesma linha, então acentos em maiúsculas podem encostar no limite em views apertadas. Teste antes de adotar.

`stock` deixa as fontes de fábrica.

## Papel de parede

- **Geração:** um PNG próprio, gerado pelo `scripts/lib/art.py` (só stdlib, determinístico): gradiente grafite→azul-petróleo com duas formas suaves ao estilo Material You e dither 4×4 contra faixas. 76 KB.
- **Onde entra:** no lugar de `/system/media/rkfactory/default_wallpaper.jpg`. O `WallpaperManager.getDefaultWallpaperLocked()` da Rockchip (conferido no `framework.jar` deste firmware) usa esse arquivo como papel de parede padrão antes do `default_wallpaper` do `framework-res.apk`. O `BitmapFactory` reconhece PNG pelo conteúdo, então o nome `.jpg` não atrapalha.
- **Consequência:** vira o padrão de verdade, inclusive depois de "restaurar". Não precisa mexer no `framework-res.apk` nem no 1º boot.
- **Tamanho 800×800:** a tela é 800×480 (ver FINDINGS). O mesmo método pede ao serviço o tamanho desejado (`getWidthHint`/`getHeightHint`), que no 4.4 é `max(largura, altura)` nos dois lados quando o launcher não sugere outro (o KISS não sugere). Assim o bitmap entra sem reescala e serve nas duas orientações. Se a tela fosse outra: `WALLPAPER_SIZE=1024x1024`.
- **Trocar:** Configurações → Tela → Plano de fundo. Para manter o de fábrica: `WALLPAPER=0`.

## Ícones e launcher

O KISS continua o launcher padrão. O 1º boot grava nas preferências dele:
- `icons-pack=org.xphnx.ameixa`: ícones Material do Ameixa, já pré-instalado.
- `theme=transparent-dark`: lista escura sobre o papel de parede.

O KISS é parado e o sistema o reabre sozinho. Os nomes das chaves foram conferidos no código do KISS 3.24.2 (`IconsHandler`, `InterfaceTweaks`).

Avaliação de alternativas (sem ganho claro, então ficam fora):

| Launcher | Versão / origem | minSdk | Tamanho | RAM esperada | Veredito |
|---|---|---|---|---|---|
| **KISS** (atual) | 3.24.2, F-Droid | 15 | 1,2 MB, 1 dex de 254 KB | ~12–20 MB PSS | fica |
| TinyBit | 7.5, F-Droid (`rocks.tbog.tblauncher`, sha256 `d292bd3d…`) | 19 | 3,8 MB, **2 dex** (2,3 MB + 0,6 MB) | ~30–45 MB PSS | não: é um fork do KISS com mais recursos (widgets, tags), mas o multidex no Dalvik pesa no dexopt e na RAM residente; sem ganho visual que justifique |
| Nova 7 / 5.5.4 | proprietário; só em espelhos de APK (sem URL estável nem hash publicado pelo autor) | 16 | ~8 MB | ~40–60 MB PSS | não: sem fonte confiável com sha256 e não pode ser baixado pelo build de forma reprodutível |

As faixas de RAM são estimativas, a partir do tamanho do dex e do que cada um carrega. Para medir:
`dumpsys meminfo <pacote>` depois de 1 min na tela inicial.

## Tema escuro

- **Já é escuro no 4.4:** Configurações, diálogos do sistema, gaveta de notificações e barra de status usam Holo **Dark**.
- **Escurecido pelo 1º boot:** KISS, Simple Keyboard (tema "Dark") e F-Droid (tema `dark`).
- **Fica claro:** o que cada app escolhe por conta própria (Firefox 68 e SkyTube não têm preferência simples para isso).
- **Forçar escuro no sistema todo:** exige alterar estilos dentro do `framework-res.apk`. O 4.4 não tem RRO (sobreposição de recursos em tempo de execução, que chegou no 5.0), então seria reempacotar e reassinar o `framework-res.apk` e o SystemUI. Fica para a **v2**: é mexer no coração do sistema, com risco de não bootar, e precisa de teste no aparelho a cada mudança.

## Bootanimation (`BOOTANIM=1`)

- **O que é:** um `bootanimation.zip` de 56 KB, gerado pelo `art.py`, com um spinner circular indeterminado do Material (arco azul `#8AB4F8` que gira e "respira" sobre trilha grafite e fundo preto).
- **Formato:** 160×160, 30 quadros, 20 fps, em loop até o boot terminar. O zip é sem compressão, como o `bootanimation` do 4.4 exige.
- **Efeito no build:** ligar a variável força `debug.sf.nobootanimation=0` e põe o nosso zip no lugar do `/system/media/bootanimation.zip` de fábrica (1,4 MB). O binário procura esse caminho (conferido nas strings do `/system/bin/bootanimation`). Para a animação de fábrica em vez da nossa: `NO_BOOTANIM=0` sem `BOOTANIM`.

## Xposed + GravityBox (`XPOSED=1`, OFF por padrão)

**O que entra.**
- Xposed Installer 2.7 experimental1 (versionCode 33): `app_process` v58 e XposedBridge 54, para 4.0.3–4.4 com Dalvik.
- GravityBox [KK] 3.6.2 (versionCode 138), a última para KitKat.

**Origem e verificação.** O servidor oficial (`dl-xda.xposed.info`) está fora do ar, então os APKs vêm do Internet Archive. A integridade foi conferida assim:
- o md5 bate com o prefixo que o próprio nome oficial carrega (`_36570c`, `_84d42f`);
- o SHA-1 bate com o índice do arquivo;
- a assinatura é do autor (CN=rovo89 e CN=C3C0);
- o sha256 fica fixo em `config/apks.txt`.

**Instalação sem o instalador.** O instalador precisaria de root e de reboot:
- `/system/bin/app_process` ← `app_process_xposed_sdk16` do APK. O original fica em `app_process.orig`, como faz o zip de recovery do próprio Xposed.
- `XposedBridge.jar` vai em `/system/etc/m7s/`. O binário só o procura em `/data/data/de.robv.android.xposed.installer/bin/`, caminho fixo, então o 1º boot copia para lá.
- O 1º boot também grava `conf/modules.list` (caminho do APK do GravityBox) e `enabled_modules.xml`.
- As preferências do GravityBox, legíveis por todos porque o módulo as lê de dentro do SystemUI:

| Preferência | Valor | Variável |
|---|---|---|
| `pref_battery_style` | `5` (KitKat com porcentagem) | `GB_BATTERY_STYLE` |
| `pref_statusbar_center_clock` | `true` | `GB_CENTER_CLOCK` |
| `pref_signal_cluster_lollipop_icons` | `true` (ícones planos de sinal/Wi-Fi do Lollipop) | `GB_FLAT_ICONS` |
| `pref_statusbar_icon_color_enable` | `false` (sem colorização) | — |

  O estilo 5 é o padrão porque os estilos de círculo (2/3/6/7) redesenham a 20 fps enquanto carrega (`CmCircleBattery.updateChargeAnim`) e o SystemUI, com `low_ram`, desenha sem GPU. Círculo: `GB_BATTERY_STYLE=3`.
- O 1º boot reinicia **uma vez** sozinho para ativar (`XPOSED_REBOOT=0` desliga isso).

**Compatibilidade, conferida sem o aparelho.**
- O `app_process` de fábrica é o AOSP 4.4 sem mudanças da Rockchip: mesmos imports, mais só `atrace_set_tracing_enabled`.
- `persist.sys.dalvik.vm.lib=libdvm.so`: é Dalvik, não ART.
- O build roda `scripts/lib/elfcheck.py` e falha se algum dos 95 símbolos do `app_process` do Xposed não existir nas 12 libs deste firmware. Hoje todos resolvem.
- **O que não dá para conferir fora do aparelho:**
  - offsets internos do Dalvik (o Xposed tem `conf/jit_reset_offset` para corrigir isso);
  - se as classes do SystemUI da Rockchip têm os métodos que o GravityBox intercepta. Hooks que falham ficam no log do Xposed e o recurso não aparece, sem travar.

**Risco de bootloop: médio, e a recuperação é fácil.**
1. O `adb` já funciona antes do zygote e o `ro.secure=0` dá shell root. Para desligar o Xposed: `adb shell touch /data/data/de.robv.android.xposed.installer/conf/disabled` e `adb reboot`.
2. Modo de segurança do Xposed 2.7: apertar uma tecla de volume várias vezes logo no início do boot.
3. Regravar o `system.img` de um build com `XPOSED=0`.

**Por que OFF.** Nunca rodou neste aparelho, custa RAM em todos os processos (o aparelho tem 421 MB úteis) e a única mudança visível é a barra de status.

Para ligar: `XPOSED=1 scripts/build.sh …` e seguir o item 12.5 do `TEST-PLAN.md`.
