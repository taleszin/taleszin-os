# Taleszin OS

ROM autoral, com build reproduzível, para o tablet **Multilaser M7s Dual Core (ML01-M7-SD, RK3026)**:
tela inicial, tema, animação de boot, vigia de bateria, telemetria e app de diagnóstico próprios,
sobre os binários de hardware do firmware oficial (KitKat 4.4.2). Não há outra ROM para este aparelho.

Apps da ROM, cada um no seu repositório:
[taleszin-home](https://github.com/taleszin/taleszin-home) (tela inicial) ·
[taleszin-diagnostico](https://github.com/taleszin/taleszin-diagnostico) (diagnóstico estilo CPU-Z) ·
[taleszin-tema](https://github.com/taleszin/taleszin-tema) (tema laranja via Xposed).

Firmware e APKs de terceiros **não** são versionados: o build lê o zip oficial que você fornece e
baixa os apps por URL fixa, conferindo sha256 ([NOTICE](NOTICE)).

```sh
brew install e2fsprogs rkflashtool
scripts/build.sh ~/Downloads/Multilaser_M7S_Dual_Core-SUPRA_ML01_140403_4.4_RBT.zip
cd out && ./flash-mac.sh
```

Documentação: [docs/README.md](docs/README.md) (o que é, aviso, compatibilidade, build, gravação,
rollback, changelog) · [docs/HARDWARE.md](docs/HARDWARE.md) · [docs/TEST-PLAN.md](docs/TEST-PLAN.md)
· [docs/FLASH-WINDOWS.md](docs/FLASH-WINDOWS.md) · [docs/FINDINGS.md](docs/FINDINGS.md).

Licença: MIT para este repositório; firmware e APKs não são distribuídos (ver NOTICE).
