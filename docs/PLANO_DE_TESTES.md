# Plano de testes: digital antes do físico

Este roteiro separa o que pode ser comprovado no gêmeo digital do que depende de medições reais. O veículo considerado é sempre 4×4, com dois motores em cada lado.

## Critério de avanço

Só avançar para a montagem física quando todos os testes digitais críticos estiverem aprovados e a corrente/tensão dos motores, bomba, relé, MS-129BT e fonte tiverem sido medidas. Nenhum motor ou bomba deve ser alimentado por um GPIO ou pelo regulador da ESP32.

## Etapa 1 — servidor e Dashboard

| ID | Ensaio | Procedimento | Resultado esperado |
|---|---|---|---|
| D01 | Partida segura | Iniciar `python3 server.py` e abrir o painel | Modo `PARADO`; motores, bomba e som em 0/desligados |
| D02 | Tração reta | Selecionar Manual e manter Frente | Bancos esquerdo e direito com mesmo PWM positivo |
| D03 | Ré | Manter Ré | Dois bancos com mesmo PWM negativo |
| D04 | Giro | Manter esquerda ou direita | Bancos com sinais opostos |
| D05 | Liberação do comando | Soltar o botão ou a tecla de direção | Ambos os bancos chegam imediatamente a 0% |
| D06 | Timeout | Em Manual, interromper heartbeats por mais de 750 ms | Estado `SEM_COMANDO` e motores em 0% |
| D07 | Decisão manual | Publicar parede próxima e dirigir em Manual | Câmera não altera a trajetória escolhida pelo operador |
| D08 | Perda de enlace | Selecionar “Perda de sinal” | Motores, bomba e som desligados |
| D09 | Emergência | Acionar a faixa laranja | Estado `EMERGENCIA`; todas as saídas desligadas |
| D10 | Bomba | Acionar “Dispersar água” | Pulso termina sozinho em no máximo 3 s |
| D11 | Som | Alternar “Caixa de som” | Segundo canal muda de estado e aparece no registro |
| D12 | Autônomo | Selecionar Autônomo e variar frente/esquerda/direita da visão | Centralização e escolha do lado mais livre aparecem na telemetria |
| D13 | Responsividade | Abrir a 390 px e em desktop | Sem rolagem horizontal; emergência permanece no topo |
| D14 | Teclado | Usar WASD/setas e o pad com Espaço/Enter | Pressionar move; soltar para imediatamente |

Comando de regressão:

```sh
python3 -m unittest discover -s tests -v
```

## Etapa 2 — simulação física no Webots

| ID | Ensaio | Procedimento | Resultado esperado |
|---|---|---|---|
| V01 | Quatro motores | Comandar frente, ré e giro pelo Dashboard | As quatro rodas giram; as duas de cada lado recebem a mesma velocidade |
| V02 | Câmera única | Inspecionar dispositivos do robô | Existe apenas `esp32 camera`; não existe sensor de distância, GPS ou lidar |
| V03 | Corredor centralizado | Rodar em trecho reto no modo Autônomo | Espaços esquerdo/direito convergem e o carro segue centralizado |
| V04 | Curva | Aproximar-se da parede frontal com abertura lateral | Visão estima frente curta e escolhe o lado com maior espaço |
| V05 | Perda de visão | Parar o Webots ou interromper `/api/vision` | Estado `SEM_VISAO` e motores em 0% após 1,5 s |
| V06 | Controle manual | Selecionar Manual diante de parede próxima | Somente os comandos do usuário definem a trajetória |
| V07 | Bomba | Acionar “Dispersar água” | Gotas azuis saem do bico e cessam em até 3 s |
| V08 | Perda da API | Encerrar `server.py` durante movimento | Controlador Webots zera as rodas em até 1 s |

## Etapa 3 — circuito Wokwi

| ID | Componente | Evidência no simulador | Resultado esperado |
|---|---|---|---|
| W01 | ESP32 | Monitor serial e telemetria HTTP | Conecta ao Wi-Fi, recebe sequência e publica telemetria |
| W02 | Banco esquerdo | LEDs `L FWD`, `L REV` e `L PWM` | Sentido e intensidade correspondem ao comando esquerdo |
| W03 | Banco direito | LEDs `R FWD`, `R REV` e `R PWM` | Sentido e intensidade correspondem ao comando direito |
| W04 | Ausência de sonar | Inspecionar circuito e firmware | Nenhum HC-SR04 ou leitura equivalente está presente |
| W05 | Relé da bomba | Relé `pumpRelay` | Aciona em nível baixo e desliga no timeout/failsafe |
| W06 | Relé do som | Relé `soundRelay` | Acompanha a habilitação do som e desliga em falha crítica |
| W07 | E-stop local | Pressionar o botão vermelho | Firmware desliga as saídas sem depender do servidor |
| W08 | Servidor ausente | Parar `server.py` durante movimento | Timeout local de 1 s desliga todas as saídas |

Os LEDs representam os sinais da ponte H; o Wokwi não modela torque, corrente de travamento, ruído elétrico ou aquecimento dos quatro motores.

## Etapa 4 — bancada física, sem rodas no chão

Realizar inicialmente com as rodas suspensas e fonte limitada em corrente.

| ID | Medição/ensaio | Decisão que depende do resultado |
|---|---|---|
| F01 | Corrente sem carga e de travamento de **cada** motor em 3 V, 5 V e 6 V | Escolha e quantidade de pontes H, fusível, cabos e fonte |
| F02 | Tensão/corrente nominal da bomba retirada do dispenser | Fonte ou conversor, contato do relé e diodo de roda livre |
| F03 | Saída real da powerbank, corrente contínua, queda de tensão e desligamento automático | Se ela pode alimentar lógica e/ou potência com segurança |
| F04 | Corrente e tensão de alimentação da MS-129BT; comportamento ao religar | Forma correta de usar o segundo relé e preservar pareamento/volume |
| F05 | Módulo Songle acionado por sinal de 3,3 V | Compatibilidade direta com ESP32 ou necessidade de interface |
| F06 | Calibração intrínseca/extrínseca da ESP32-CAM | Campo de visão, distorção, altura e inclinação usados na projeção monocular |
| F07 | Partida simultânea dos quatro motores | Queda de tensão, reset da ESP32 e aquecimento do driver |
| F08 | Inversão rápida e frenagem | Picos, estabilidade e temperatura da ponte H |
| F09 | Bomba acionada com motores rodando | Ruído, reset e interferência no áudio/sensores |
| F10 | Emergência física | Corte confiável dos atuadores em todas as condições |

## Proteções mínimas para a montagem

- Fonte dos motores dimensionada pela corrente de travamento, com margem; não escolher o driver apenas pela tensão nominal.
- Terra comum entre ESP32, driver e interfaces de sinal, mantendo o caminho de potência separado do caminho lógico.
- Fusível na alimentação de potência e chave geral acessível.
- Capacitores de desacoplamento próximos à ESP32 e ao driver; supressão de ruído nos motores conforme a bancada indicar.
- Diodo de roda livre na bomba DC, mesmo quando comandada por contato de relé.
- Confirmação em bancada de que os dois canais do módulo Songle ficam desligados durante boot/reset.
- Parada segura se o fluxo da ESP32-CAM ou o serviço de visão ficar indisponível.

## Itens ainda necessários para fechar o esquema elétrico

1. Modelo e especificações da powerbank.
2. Medições de corrente dos quatro motores, principalmente corrente de travamento.
3. Tensão e corrente da bomba reaproveitada.
4. Tensão/corrente de entrada e comportamento de boot da MS-129BT.
5. Modelo final da ponte H, escolhido somente após as medições.
6. Altura e inclinação finais da ESP32-CAM no chassi para concluir a calibração monocular.
