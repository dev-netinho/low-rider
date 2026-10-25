# Sistema visual do Centro de Comando

## Direção

O Dashboard segue a linguagem de um console de instrumentação de campo: direto, legível sob pressão e claramente técnico, sem imitar um painel automotivo decorativo. A hierarquia coloca percepção, comando e segurança antes de métricas secundárias. Todo dado sintético é identificado na própria interface.

## Paleta

| Token | Valor | Uso |
|---|---|---|
| `--canvas` | `#d9ddd4` | plano de fundo mineral |
| `--paper` | `#f4f3ec` | superfícies principais |
| `--paper-strong` | `#fffef7` | controles e leitura de alto contraste |
| `--ink` | `#18231f` | texto principal |
| `--ink-soft` | `#52615b` | texto auxiliar |
| `--rail` | `#20332c` | barra superior e registro operacional |
| `--line` | `#9ba69f` | divisórias e contornos |
| `--safety` | `#f04b23` | parada de emergência |
| `--signal` | `#b7e44c` | estado conectado e detecção visual |
| `--warning` | `#e3a52b` | atenção e estados preventivos |
| `--critical` | `#d43428` | falha crítica |
| `--focus` | `#006fca` | foco de teclado |

As cores de estado nunca são o único portador de significado: rótulos, números, ícones e mensagens acompanham cada mudança.

## Tipografia

- Interface: `DejaVu Sans`, com fallback para `Liberation Sans` e `system-ui`.
- Dados: `DejaVu Sans Mono`, com fallback para `Liberation Mono` e `ui-monospace`.
- Cabeçalhos usam peso forte e espaçamento levemente negativo; telemetria usa algarismos monoespaçados e tabulares.
- O projeto não depende de fontes remotas e permanece íntegro sem internet.

## Estrutura

1. Barra crítica fixa: identidade, estado do enlace, relógio e emergência.
2. Operação: câmera sintética em destaque e console do chassi ao lado.
3. Telemetria: leitura contínua dos dois bancos, energia, enlace e estado.
4. Ensaio e diagnóstico: injeção de cenários e registro de eventos.

No celular, a ordem vira um fluxo vertical. A emergência continua na barra superior, antes do conteúdo rolável. O layout tem largura mínima de 320 px e não cria rolagem horizontal.

## Componentes e estados

- Seletor de modo: `PARADO`, `MANUAL` e `AUTONOMO`, com `aria-pressed`.
- Direcional: botões grandes para toque, atalhos WASD/setas e parada central.
- Atuadores: bomba momentânea com limite explícito e som alternável.
- Faixas de segurança: informam repouso, bloqueio e falhas em linguagem operacional.
- Telemetria: números e barras com rótulo físico de cada banco de motores.
- Registro: eventos recentes com origem, instante e severidade.
- Notificações: região `aria-live` para mensagens operacionais e falhas.

## Acessibilidade e movimento

- Foco visível azul em controles interativos.
- Link de salto para o conteúdo principal.
- Alvos de toque amplos nos comandos críticos.
- Operação por mouse, toque e teclado.
- Preferência `prefers-reduced-motion` respeitada globalmente.
- Canvas decorativo complementado por telemetria textual; as funções não dependem da imagem.

## Regras de manutenção

- Preservar a emergência na primeira viewport em todos os tamanhos.
- Manter valores simulados identificados como sintéticos.
- Não transformar telemetria em cartões decorativos independentes; usar divisórias e agrupamento funcional.
- Reservar laranja/vermelho para ações ou falhas críticas.
- Novos estados precisam de texto, cor e comportamento de recuperação.
- Antes de alterar tokens ou estrutura, validar desktop, 390 px e navegação por teclado.

## Extensão: Bancada virtual

A Bancada prolonga o mesmo console de instrumentação sob a seed `inherited-bancada-physical-v1` como uma vista superior vetorial da montagem real, não como fluxograma. Protoboard e ESP32 dominam a primeira viewport; o pan horizontal permite seguir cada jumper até os pinos e bornes da ponte H ou do relé e, depois, até M1–M4, bomba e som.

- Cada jumper de controle conserva uma cor própria da origem GPIO ao terminal de destino; rótulos repetem o par `GPIO → pino` para a leitura não depender da cor.
- Fios de motor formam pares vermelho/preto entre `OUT1–OUT4` e os bornes visíveis de M1–M4. Pinos e bornes físicos devem permanecer desenhados e nomeados nas placas e nos atuadores.
- Os quatro motores são identificados individualmente como M1–M4 e mostram comando, `rad/s` e `rpm`; rotação e fios animados apenas reforçam esses valores.
- Alimentação e ligações ainda não dimensionadas usam vermelho-laranja interrompido e rótulos `PROVISÓRIA` ou `PENDENTE`; nunca devem parecer conexões finais.
- No celular, o esquema pode rolar horizontalmente, anuncia essa possibilidade e preserva servidor e emergência na primeira viewport.
- A câmera é apresentada como visão do robô, não como visão principal da montagem.
- Movimento respeita `prefers-reduced-motion`; foco de teclado e dados textuais permanecem suficientes para operar e compreender a tela.
