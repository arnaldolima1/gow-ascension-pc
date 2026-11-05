# Marcos

O que o jogo passou a fazer, e quando. Tradução de [MILESTONES.md](MILESTONES.md): uma linha nova vai para os dois arquivos.

| Data | Marco |
| --- | --- |
| 2026-10-15 | `EBOOT.BIN` decriptado, imports e funções encontrados, 1,8 milhão de linhas de C++ traduzidas e compiladas; o executável inicia. |
| 2026-10-15 | Passa pelas verificações do sistema e monta os arquivos do jogo (layout do `sys_lwcond_t`, arquivos acima de 2 GB, Edge Zlib no host). |
| 2026-10-15 | As telas de abertura aparecem: o texto legal, "Sony Computer Entertainment presents", Santa Monica Studio, o aviso do jogo online (motor live draw). O mesmo no macOS, pelo Metal. |
| 2026-10-16 | O renderizador principal passa do segundo quadro: SPURS2 (32 workloads, tempArea, flags1), o pós-processamento do quadro nas SPUs, a sincronização entre GPU e SPUs. |
| 2026-10-16 | Traduzido de novo com o tradutor v0.15 (um erro de spill-reload corrompia um heap por volta do quadro 12): a tela de carregamento. |
| 2026-10-16 | Passa da tela de carregamento (tasksets do SPURS: inícios duplicados, tamanho do Taskset2 e event flags, tasks criadas pelas SPUs). |
| 2026-10-16 | Os menus ficam legíveis: atlas de fonte X16, sRGB do framebuffer e gama das texturas, `DDX`/`DDY` de fragmento no motor live draw. |
| 2026-10-17 | A cinemática de abertura passa com imagem e som (`cellVdec` com FFmpeg em tempo de execução; a "tela preta" era o fade do jogo esperando por ela). |
| 2026-10-17 | Desempenho: os 15 módulos de jobs do Wws traduzidos, um painel de desempenho. Menus de primeiro uso de 5-6 → ~10 fps. |
| 2026-10-17 | Desempenho, parte dois: traduções independentes de posição do código de jobs carregado por streaming, SSE4.1 no código das SPUs traduzido. Menus de ~10 → 26-55 fps, cinemática de ~35 → 45-60 fps. |
| 2026-10-17 | O RsxSync acordado pelos reports da GPU, operações SPU em SSE4.1, 381 entradas de módulos de jobs, o interpretador respeitando a habilitação de interrupções. O vídeo da cinemática a 72-90% da velocidade. |
| 2026-10-17 | **A cinemática na velocidade certa e sincronizada** (29,98 fps), a parada no fim do carregamento resolvida, o módulo 214 traduzido inteiro (os reports da GPU esperam as tasks de pós-processamento, nenhum aviso de task perdido, o `cellVdec` segura as AUs). |
| 2026-10-17 | O menu principal aparece (cerca de 1 fps). |
| 2026-10-17 | **Um launcher:** vídeo, idioma, legendas e mods; o jogo desenha dentro da janela dele. |
| 2026-10-17 | **Menu principal de 1 → 12 fps:** os 18 módulos de jobs que o carregamento nunca carrega também traduzidos (33 ao todo), código de streaming achado dentro de GETs maiores e pelo conteúdo. |
| 2026-10-17 | Português do Brasil (vozes do disco americano, textos já no disco europeu); mods como receitas, Pular intro incluído. |
| 2026-10-18 | **O primeiro nível** (Kratos acorrentado): corrigida uma corrida que perdia tasks no escalonador de tasksets do SPURS; o nível carrega e roda (~16 fps no live draw). |
| 2026-10-19 | **O RSX do RPCS3 como renderizador** (Windows e macOS): as rodadas de pós-processamento da GPU e das SPUs no ritmo do próprio jogo. |
| 2026-10-19 | Menu principal de 12 → 28 fps no RSX do RPCS3: as transferências das SPUs para superfícies que a GPU protegia estavam sendo descartadas. |
| 2026-10-19 | **Texturas do nível corretas:** o espaço de IO devolvido no unmap, então os vertex streams do cenário não leem mais o buffer de comandos. |
| 2026-10-20 | Nível de ~10 → ~15 fps: floats das SPUs traduzidos sem a verificação de faixa estendida (as regras "aproximadas" do RPCS3), sem diagnósticos de local store no código traduzido, código contíguo de módulos de jobs traduzido como uma função só, código de streaming achado por um índice. |
| 2026-10-21 | Nível de ~15 → ~16,7 fps: cada SPU no seu próprio núcleo, o thread principal do PPU no núcleo 0. |
| 2026-10-21 | **Replay de jobs das SPUs:** jobs gravados do jogo rodam de novo fora dele e são conferidos byte a byte pelo que escrevem, com tempo e profiling. Módulo 218 (geometria por draw) decifrado: descompressão de índices e transformação de posições escritas em código nativo, idênticas nos jobs gravados; o resto do job vai para nativo em seguida. |
| 2026-10-22 | Nível de ~15 → ~17,5 fps: o código traduzido do processador principal guarda os registradores do jogo em variáveis locais em vez da memória (traduzido de novo; 1,5-1,8x em funções isoladas). |
| 2026-10-23 | Mais código das SPUs que ainda era interpretado agora é recompilado, e duas partes carregadas por streaming do job de geometria rodam em código nativo. |
| 2026-10-23 | Launcher **Vídeo → Efeitos**: profundidade de campo, motion blur e MLAA podem ser desligados (os mesmos patches que o RPCS3 oferece, achados no disco 1.00). Experimental: as texturas ainda falham com eles desligados. |
| 2026-10-23 | Nível de ~17,5 → ~22 fps: código das SPUs traduzido compilado para AVX2, runtime das SPUs mais leve. |
| 2026-10-23 | **O pós-processamento que suaviza as bordas do quadro roda em código nativo:** suas quatro etapas mais pesadas nas SPUs reescritas em C, idênticas ao original em 12 milhões de chamadas conferidas; esse trabalho custa cerca da metade. |
| 2026-10-23 | **Primeira luta contra um chefe** (13-21 fps lutando). O perfil ali mostra o tempo das SPUs espalhado por muitas partes pequenas, então o próximo trabalho ataca os custos que todo job das SPUs paga, não uma função de cada vez. |
| 2026-11-03 | Medido no Windows contra o RPCS3 na mesma cena do primeiro nível: 22 fps nativo, 35-40 no RPCS3. Duas mudanças viram padrão: o thread do RSX dorme com a fila de comandos vazia em vez de girar (~8% a menos no tempo do quadro num PC de 4 núcleos), e as SPUs escolhem sozinhas o próximo trabalho (~1,6% a menos no mesmo PC). |
| 2026-11-03 | **O travamento intermitente no nível achado e corrigido:** uma escrita do processador principal podia se perder no meio de uma operação atômica de uma SPU, deixando as listas de geometria esperando para sempre. A reprodução passou de 3 travamentos em 5 rodadas para nenhum em 4. |
| 2026-11-04 | O quadro do primeiro nível medido parte por parte: dos ~50 ms, ~21 ms são as listas de geometria das SPUs (EDGE) e ~9-12 ms a espera pelo thread do RSX entre as duas passadas dessa geometria. |
| 2026-11-04 | **Roda no macOS de novo** (Apple Silicon, RSX do RPCS3), para testes: o thread do RSX agora se recupera de dados de comando corrompidos em vez de parar o jogo. |
| 2026-11-04 | **O multijogador chega ao lobby do guerreiro** com o servidor próprio do projeto (em desenvolvimento, ainda privado); o perfil do multijogador do jogador fica guardado na conta dele. As partidas online ainda não funcionam. |
| 2026-11-04 | Mais dois padrões, cada um medido dentro da mesma rodada num PC de 4 núcleos: o thread principal do jogo com prioridade acima do normal (-2,7 ms por quadro) e os jobs do fim do quadro espalhados por até 4-5 SPUs (-2,1 ms). O código do processador principal compilado com otimização guiada por perfil (PGO): ~10% a menos no tempo do quadro. |
| 2026-11-05 | **O travamento `CopyLocalMemory offset error` corrigido:** um contador do Edge Zlib, e uma proteção na troca da tabela de streaming de texturas. Nenhum em 40 rodadas no nível com 4 núcleos. |
| 2026-11-05 | **O RSX fora do caminho crítico:** a espera dele entre as duas passadas de geometria do EDGE caiu de 9-12 ms para ~0,1 ms. O primeiro nível roda a ~24 fps no PC inteiro e ~17-18 com 4 núcleos (era ~14-15); o quadro agora é ~55% o módulo 218 das SPUs, onde as interrupções do gerenciador de jobs custam tanto quanto o código dos próprios jobs. |
| 2026-11-05 | Multijogador: a partida rápida passa da localização do jogador e escolhe o servidor de matchmaking no servidor próprio do projeto; o jogo conecta e abre uma sessão SSL 3.0, que o servidor está aprendendo a responder. |
