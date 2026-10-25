# Produto

<!-- impeccable:product-schema 1 -->

## Plataforma

web

## Stack

Delegado: servidor e simulador em Python 3 usando apenas a biblioteca padrão, interface em HTML/CSS/JavaScript sem framework e firmware ESP32 em Arduino/PlatformIO. A escolha privilegia execução local e reduz a dependência de internet.

## Usuários

- Integrantes do Grupo 2 durante desenvolvimento, demonstração e diagnóstico do protótipo.
- Operador do robô durante missões manuais e autônomas.
- Professor e avaliadores durante a validação técnica da AV2.

## Propósito do produto

Controlar e demonstrar digitalmente um robô móvel 4×4 de logística e fuga. O sistema reúne teleoperação, navegação autônoma assistida por visão, telemetria, acionamento temporizado de uma bomba d'água e habilitação de uma caixa de som.

## Posicionamento

O painel não é uma maquete visual: ele opera um gêmeo digital com a mesma máquina de estados, os mesmos contratos de comando e as mesmas regras de segurança previstos para o ESP32 físico.

## Contexto de operação

- Desenvolvimento acadêmico em laboratório e computadores pessoais.
- Demonstração em notebook, tablet ou celular na mesma rede do servidor.
- Internet pode ser instável; o núcleo local deve funcionar sem serviços externos.
- A navegação autônoma deve usar exclusivamente a câmera ESP32-CAM. O mundo Webots fornece a imagem monocular; nenhuma distância do simulador é entregue ao algoritmo.

## Capacidades e restrições

- Tração 4×4 diferencial com quatro motores DC de 3–6 V e rodas de 65 mm, agrupados por lado.
- Modos seguro/parado, manual e autônomo.
- No modo autônomo, estimação visual dos espaços frontal, esquerdo e direito para centralização e escolha do caminho.
- No modo manual, a trajetória é escolhida pelo operador; a câmera não corrige direção.
- Parada por perda de comunicação, perda da visão no modo autônomo e parada de emergência.
- É proibido usar HC-SR04, lidar ou outro sensor de distância no projeto.
- Relé de dois canais: bomba e caixa MS-129BT.
- Bomba limitada por temporizador e desligada em falhas críticas.
- Driver de motores e fonte de potência ainda são decisões físicas abertas; o software usa uma abstração de ponte H.
- O modelo CAD 6×6 existente é obsoleto e não representa os requisitos do produto.

## Evidências disponíveis

- Relatórios acadêmicos em `/home/olua-dev/Downloads/`.
- Motorredutores amarelos 130/TT de 3–6 V com rodas de 65 mm.
- ESP32 NodeMCU, ESP32-CAM OV2640, módulo de relé Songle de dois canais e caixa MS-129BT.
- A bomba foi reaproveitada de um dispenser recarregável; tensão e corrente ainda precisam ser medidas.
- Não há dados reais de autonomia, corrente de travamento, latência de vídeo ou precisão da visão. Valores mostrados no simulador são explicitamente sintéticos.

## Princípios do produto

- Falhar parado: movimento e bomba desligam quando a comunicação ou o estado é incerto.
- A função vem antes do espetáculo: estado, comando e recuperação precisam ser compreendidos em segundos.
- Um contrato, dois ambientes: simulação e hardware compartilham os mesmos comandos e telemetria.
- Operação não bloqueante: temporizadores e comunicação nunca congelam o controle do robô.
- Toda demonstração sintética é identificada como tal.

## Acessibilidade e inclusão

O painel deve funcionar por toque e teclado, preservar foco visível, não depender apenas de cor e respeitar a preferência por movimento reduzido.
