# Gravar pelo Windows

Só para **Multilaser M7s Dual Core ML01-M7-SD** (RK3026). Os dois caminhos apagam `/data`.

Pré-requisitos: driver Rockchip (`DriverAssitant` / RKDriverAssistant v4.x ou o do RKBatchTool),
bateria acima de 50%, cabo direto na placa-mãe. Para entrar em modo loader: `adb reboot bootloader`,
ou tablet desligado segurando Vol- ao conectar o USB. O programa deve mostrar "Found One LOADER Device".

## Caminho A (recomendado): AndroidTool / RKDevTool, aba "Download Image"

Grava as mesmas partições que o `flash-mac.sh`, sem tocar no loader nem no parameter.

1. Abra o AndroidTool (v2.3x+) e vá em **Download Image**.
2. Desmarque as linhas **Loader** e **Parameter**.
3. Preencha uma linha por partição, com estes endereços (setores de 512 B) e os arquivos de `images/`:

   | Nome     | Endereço   | Arquivo               |
   |----------|------------|-----------------------|
   | misc     | 0x00002000 | images/misc.img       |
   | kernel   | 0x00004000 | images/kernel.img     |
   | boot     | 0x00008000 | images/boot.img       |
   | recovery | 0x00010000 | images/recovery.img   |
   | backup   | 0x00020000 | images/backup.img     |
   | system   | 0x00282000 | images/system.img     |

4. Clique em **Run**. Ao terminar, o tablet reinicia e o recovery faz o wipe (o `misc.img` contém `--wipe_all`).

## Caminho B: RKBatchTool 1.7/1.8 com `update.img`

O `update.img` é o pacote oficial reempacotado com o `system.img` da ROM (o resto é idêntico ao
oficial; o empacotador reproduz o update.img de fábrica byte a byte quando nada é trocado).
**Diferença importante:** o RKBatchTool também grava o **loader e o parameter** do pacote oficial 4.4.
É o mesmo que a fábrica faz numa atualização normal, mas é mais invasivo que o caminho A.
Atenção: se o aparelho ainda tem o parameter do 4.2.2 (caso do aparelho de referência), o do 4.4
move o início da partição `user` (armazenamento interno) de `0x402000` para `0x462000` — os arquivos
do armazenamento interno se perdem e ele precisa ser formatado. Prefira o caminho A.

1. Abra o RKBatchTool, em **FW Path** escolha `update.img`.
2. Com o tablet em modo loader (quadrado verde), clique em **Upgrade**.

## Voltar ao estoque

Grave o `update.img` oficial (de dentro do zip original) pelo RKBatchTool, ou as partições do
pacote oficial pelo caminho A. Detalhes em `README.md`.
