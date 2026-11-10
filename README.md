<div align="center">

<img src="packaging/icon.png" alt="Ícone do Ascension" width="128">

# Ascension

**God of War: Ascension (PS3), recompilado para rodar nativamente no PC.**

[![Status](https://img.shields.io/badge/status-experimento-lightgrey)](docs/MILESTONES.pt-BR.md)
[![Release](https://img.shields.io/badge/release-ainda%20n%C3%A3o-lightgrey)](#onde-estamos)
[![Windows](https://img.shields.io/badge/Windows-10%2F11%20x64-0078D4)](#compilando)
[![Licença](https://img.shields.io/badge/licen%C3%A7a-MIT-green)](LICENSE)

**Português (Brasil)** · [English](docs/README.en.md)

</div>

---

O Ascension traduz o código do jogo, do processador principal (PPU) e dos SPUs do PS3, para C++ e o compila para o seu PC, sobre o runtime do [ps3recomp](https://github.com/sp00nznet/ps3recomp). Não é um emulador: é o próprio jogo, recompilado.

> [!WARNING]
> **Ainda experimental, mas já dá para zerar.** O [iSamigor](https://github.com/iSamigor) jogou do começo ao fim no PC dele (Ryzen 7 9800X3D, RX 9070 XT). Em processadores comuns o jogo ainda é lento (~20 fps na luta contra o chefe num Ryzen 7 5700G), e ainda pode travar. Feito para Windows; no macOS (Apple Silicon) ele voltou a rodar, por enquanto só para testes.

> [!IMPORTANT]
> **Nenhum dado do jogo está incluído.** Você precisa da sua própria cópia, a **versão europeia `BCES-01741`** (1.00), tirada do seu disco. Ninguém aqui pode te dar o jogo ou chaves. Projeto de fãs, sem ligação com a Sony Interactive Entertainment ou a Santa Monica Studio.

## Onde estamos

Novembro de 2026, no Windows (e no Mac, em testes):

- **O jogo inteiro, do boot ao fim:** o iSamigor zerou o jogo. Nos nossos testes: telas de abertura, carregamento, menus de primeiro uso, cinemática de abertura (imagem e som sincronizados), menu principal, o primeiro nível com o Kratos acorrentado e a primeira luta contra um chefe.
- **Renderizadores:** o RSX do [RPCS3](https://github.com/RPCS3/rpcs3) (Vulkan ou OpenGL), que desenha o jogo corretamente; o renderizador Vulkan próprio do projeto, onde está o trabalho de desempenho; e o *live draw* (D3D12).
- **Launcher** em português, inglês e espanhol, com vídeo (incluindo desligar efeitos como desfoque de profundidade, motion blur e MLAA, ainda experimental), controles, idioma, legendas, melhorias e o **online** com a sua conta do site; **português do Brasil** com vozes e textos, montado no [site](https://gow-ascension.com.br/pt-br) a partir dos seus discos.

Atualizado em 10 de novembro. As mudanças de novembro estão no branch [`ascension-perf`](https://github.com/arnaldolima1/gow-ascension-pc/tree/ascension-perf) até serem medidas no Windows. Ainda não há release. Os marcos estão em [docs/MILESTONES.pt-BR.md](docs/MILESTONES.pt-BR.md) (em inglês: [MILESTONES.md](docs/MILESTONES.md)).

### Desempenho

O objetivo é rodar bem em processadores comuns, não só nos fortes. Desde 6 de novembro o caminho é **sair do modelo do PS3**: em vez de emular cada vez melhor as SPUs e o RSX, o trabalho deles vira código nativo do PC e da placa de vídeo, com a meta de não sobrar nenhuma emulação de SPU.

> [!NOTE]
> **Um erro de medida corrigido (9 de novembro):** o contador de fps do nosso renderizador Vulkan contava cada quadro duas vezes (o mesmo quadro era apresentado de novo ~1 ms depois, sem nada desenhado). Os números desse renderizador publicados antes valem a metade. Os de baixo já são quadros reais.

A luta contra o chefe logo depois da cinemática de abertura, a cena mais pesada que medimos, num Ryzen 7 5700G (Windows, renderizador Vulkan do projeto, mediana de várias janelas de 5 s):

| Quando | fps na luta | Thread de vídeo, por draw |
| --- | --- | --- |
| 9 de novembro, à noite | ~15-17 | ~17,5 µs |
| 10 de novembro, de manhã | ~18 | ~16,0 µs |
| 10 de novembro, à tarde | **~20** | **~15,0 µs** |

**O que entrou de 6 a 10 de novembro** (cada parte medida e com a imagem conferida antes de virar padrão):

- **Renderizador Vulkan próprio** (no ps3kit), onde está o trabalho de desempenho: o anti-aliasing que o jogo fazia nas SPUs (o MLAA delas não roda mais) agora é feito na placa de vídeo (SMAA, FXAA ou MLAA), filtro anisotrópico, vértices convertidos em lotes e um contador de fps compacto nas cores do jogo.
- **60 fps:** o limite de 30 do jogo destravado, com o jogo andando na velocidade certa, e um limite de 60. Os carregamentos, que tinham ficado lentos com o destrave, voltaram a ~4,5 s.
- **SPUs em código nativo:** três módulos de geometria do EDGE (218, 202 e 210) rodam inteiros como código nativo, cada um conferido contra o original em centenas de jobs gravados do próprio jogo (resultado idêntico).
- **Thread de vídeo mais leve:** cópias 2D divididas entre 3 threads (4 → 1,7 ms por quadro); constantes dos shaders copiadas só quando mudam; os comandos de vídeo comuns despachados em bloco (-1,5 µs por draw); e as texturas: o jogo move ~150 texturas por segundo dentro da memória de vídeo, e agora uma textura movida fica com a imagem que já estava na placa em vez de ser decodificada e enviada de novo (texturas de 1,56 para 1,00 µs por draw).
- **macOS:** voltou a compilar e a abrir o jogo (Vulkan sobre MoltenVK), ~24 fps no primeiro nível num Mac com Apple Silicon; ainda trava em parte das aberturas.

**Para onde vai o quadro agora:** na luta, quem segura o quadro é o thread que executa os comandos de vídeo, e o maior custo dele é copiar os vértices que os jobs do EDGE acabaram de escrever (~5 dos ~15 µs de cada draw, perto de 50 MB por quadro).

**Próximos passos:** levar essa geometria para a placa de vídeo (as posições calculadas na GPU, sem a cópia no processador), que deve ser o primeiro salto grande (estimativa de ~28-32 fps, ainda a medir); depois o resto do EDGE na GPU e os outros módulos das SPUs em código nativo.

### Estabilidade

- **Corrigido:** num PC lento, o thread de vídeo desistia de uma espera depois de 2 s e perdia os comandos do quadro; o jogo ficava parado no carregamento do nível.
- **Corrigido:** o travamento no nível com as listas de geometria esperando para sempre (uma escrita do processador principal se perdia no meio de uma operação atômica de uma SPU: de 3 travamentos em 5 rodadas para nenhum em 4).
- **Corrigido:** o travamento com `CopyLocalMemory offset error` (um contador do Edge Zlib e a troca da tabela de streaming de texturas sem proteção): nenhum em 40 rodadas no nível.
- **Protegido:** comandos de vídeo corrompidos (`FIFO error: possible desync`) não derrubam mais o thread do RSX, e um draw pedindo uma quantidade absurda de vértices é descartado em vez de travar o jogo. A causa da corrupção ainda está aberta.
- **Problemas conhecidos:** logo depois da luta das criaturas, perto do braço gigante, um objeto da área aparece desenhado várias vezes, cada cópia um pouco deslocada (some quando a câmera sai dali); o jogo às vezes trava com uma lista de jobs das SPUs que não termina (`BATCHJOB: Waiting for batch job list ...`); e houve um crash silencioso ~70-105 s depois de entrar no nível em duas rodadas.

### Multijogador online (em desenvolvimento)

Os servidores originais do jogo ainda funcionam para quem joga no PS3, mas o jogo recompilado não entra na PSN. Por isso o projeto tem o próprio servidor (em Rust, ainda privado), no ar em [gow-ascension.com.br](https://gow-ascension.com.br) com o cadastro fechado por enquanto; o runtime manda para ele os nomes que o jogo procura. O servidor nunca se passa pela Sony: ele responde só o que o jogo espera, lido no código traduzido ou nas capturas do próprio jogo falando com ele. A partida usa o netcode do próprio jogo (uma malha P2P por UDP); como dois jogadores em casa quase nunca se alcançam direto (cada um atrás do seu roteador), os pacotes passam por um relay do servidor, e o jogo nem percebe.

| Passo | Estado |
| --- | --- |
| Entrar online, Online Pass | ok |
| Configuração do online (o jogo lê a nossa) | ok |
| Termos de uso, perfil do multijogador guardado na conta | ok |
| Tutorial pulado, lobby do guerreiro | ok |
| Partida rápida: localização do jogador | ok |
| Partida rápida: escolha do servidor de matchmaking | ok |
| Conexão com o matchmaking (sessão SSL 3.0) | ok |
| Dois jogadores casados numa partida, um deles host | ok (dois jogos no mesmo PC) |
| A rede da partida pelo relay do servidor | ok (dois jogos no mesmo PC) |
| Launcher: entrar na conta e jogar online | ok |
| Partida entre dois PCs pela internet | **em andamento** |
| A partida inteira, do lobby ao fim | falta |

```mermaid
flowchart LR
  subgraph PC["PC do jogador"]
    L["Launcher<br/>conta e online"]
    G["Jogo recompilado<br/>(runtime ps3kit)"]
    L -- "endereço, configuração e perfil" --> G
  end

  subgraph SRV["Servidor do projeto (Rust)"]
    API["Contas e API"]
    CFG["Configuração do online"]
    TUS["Perfil do multijogador<br/>por conta"]
    GEO["Localização"]
    SAM["Matchmaking<br/>(SSL 3.0)"]
    REL["Signaling e relay<br/>(UDP)"]
    DB[("PostgreSQL")]
    TUS --> DB
    API --> DB
  end

  WEB["Site do projeto<br/>perfil, ranking, painel"]
  G2["Jogo de outro jogador"]

  L -- "login por código" --> API
  L -- "configuração, perfil" --> CFG
  L -- "perfil" --> TUS
  G -- "TCP" --> GEO
  G -- "TCP + SSL" --> SAM
  G <-- "partida (UDP)" --> REL
  REL <-- "partida (UDP)" --> G2
  WEB -- "HTTP" --> API
```

No ar no servidor e no site: as contas, o perfil do multijogador guardado por conta, o perfil público com nível e conquistas, o ranking (vazio até haver partidas), um painel administrativo e o login do launcher por código. Planejado: os troféus do jogo assinados e conferidos pelo servidor. **"Jogar offline" vai continuar sempre funcionando**: a campanha nunca vai pedir conta.

## Jogando

Com o jogo compilado (abaixo), instale o launcher pelo `AscensionLauncher_<versão>_x64-setup.exe` das [releases](https://github.com/arnaldolima1/gow-ascension-pc/releases) e, na primeira vez, aponte a pasta `ascension` em **Avançado › Pasta do jogo**. Ele se atualiza sozinho quando sai uma versão nova.

<p align="center"><img src="docs/images/launcher/launcher-home.pt.jpg" alt="O launcher do Ascension" width="760"></p>

JOGAR abre o jogo; o launcher se esconde até ele fechar.

- **Vídeo:** renderizador (RPCS3 Vulkan ou OpenGL, live draw), resolução interna e filtro anisotrópico (RPCS3), janela ou tela cheia (F11 ou Alt+Enter também alternam durante o jogo), tamanho da janela, proporção, escala da imagem, sincronização vertical, contador de FPS.
- **Controles:** abas para teclado e mouse (duas teclas por comando, clique e aperte a nova) e para o controle (qual botão faz cada um, zona morta). Padrão: WASD anda, setas esquivam, Espaço/J/I/L ou o mouse nos botões, Shift defende, Esc ou Enter pausa. Teclado, mouse e controle funcionam juntos.
- **Launcher** em vários idiomas; o automático segue o idioma do jogo.
- **Jogo:** idioma (inglês, português, espanhol, francês, alemão, italiano, russo, polonês, turco) e legendas, que valem mesmo depois do primeiro uso; backup automático dos saves.
- **Melhorias:** liga e desliga. Vem com **Pular intro** (direto ao carregamento, sem as telas de abertura); o botão **Abrir a pasta de melhorias** é onde entram as outras, como o **português do Brasil**, que a [página do site](https://gow-ascension.com.br/pt-br) monta no seu navegador a partir das imagens dos seus discos (nada é enviado). As melhorias incluídas são receitas: o launcher as aplica aos arquivos do seu disco, sem trazer nada do jogo.
- **Online:** entra na sua conta do site por um código (como numa TV) e liga o online; os troféus do jogo ficam na mesma aba.

<p align="center"><img src="docs/images/launcher/launcher-controls.pt.jpg" alt="A página de controles" width="760"></p>


## Compilando

```
ascension-recomp/
  ps3kit/       o runtime e o recompilador (fork do ps3recomp, com as mudanças deste projeto)
  ascension/    este repositório
  work/         o seu disco e o que sai dele (nunca vai para o git)
```

1. **Disco:** extraia a sua imagem em `work/disc` e decripte `PS3_GAME/USRDIR/EBOOT.BIN` para `EBOOT.ELF` (com o RPCS3, ou `tools/decrypt_self.py` e o seu arquivo de chaves).
2. **Tradução:** gere o código C++ com o recompilador; os scripts de `scripts/` cobrem cada etapa (veja [scripts/README.md](scripts/README.md)).
3. **Build:** Visual Studio 2022 (clang-cl), CMake e Ninja, com `.\scripts\windows\build.ps1`; o renderizador do RPCS3 se compila antes com `.\scripts\windows\build-gpu.ps1` (MSVC e Vulkan SDK). As configurações da máquina ficam num `.env` local. Um build do zero leva de 20 a 40 minutos e pede 16 GB de memória.

Os saves ficam em `gamedata/dev_hdd0`.

## Créditos

- [ps3recomp](https://github.com/sp00nznet/ps3recomp), de sp00nznet e colaboradores: o recompilador, o runtime e as bibliotecas de sistema.
- [RPCS3](https://github.com/RPCS3/rpcs3): o código do RSX usado como renderizador (GPL-2.0; um build com ele fica sob a GPL-2.0).
- [iSamigor](https://github.com/iSamigor): testes num segundo PC (Ryzen 7 9800X3D, RX 9070 XT) e correções no runtime.
- `tools/decrypt_self.py`, do port do [Twisted Metal](https://github.com/sp00nznet/twistedmetal) (MIT).
- O launcher segue o estilo do de [gow3_pc](https://github.com/FelipePrado0/gow3_pc); fonte Cinzel (SIL Open Font License).
- God of War é marca registrada da Sony Interactive Entertainment.

## Licença

MIT: veja [LICENSE](LICENSE). Vale só para o código deste repositório, não para o jogo.
