# Relatório da bancada física — ESP32, drivers e relés

**Projeto:** Robô móvel 4×4 — Grupo 2  
**Data do registro:** 23/09/2026  
**Última atualização prática:** 24/09/2026  
**Estado ao encerrar:** montagem desmontada preventivamente; ESP32 testado sozinho e considerado funcional

> [!CAUTION]
> Este documento registra a montagem realizada e serve como mapa para a continuação. Ele **não autoriza religar o TB6612** antes do teste de continuidade. Houve aquecimento anormal e queda da alimentação quando os circuitos externos estavam conectados.

## 1. Objetivo da bancada

A bancada foi iniciada para construir e testar, por partes, o sistema eletrônico do robô final:

- uma ESP32 principal para controle;
- quatro motores DC com redução, de 3–6 V, e rodas de 65 mm;
- um TB6612FNG para dois motores;
- um DRV8833 planejado para os outros dois motores;
- um relé de dois canais para bomba d'água e caixa de som MS-129BT;
- uma ESP32-CAM para a navegação baseada exclusivamente em imagem;
- dois powerbanks separados: um para lógica e outro para potência.

O robô é **4×4**, com quatro rodas motorizadas. Não existe versão 6×6 neste projeto.

## 2. Estado resumido

| Parte | Situação ao encerrar |
|---|---|
| ESP32 principal | Funciona sozinha; LED vermelho permanece aceso e a placa não aquece. |
| Encaixe da ESP32 nas duas protoboards | Testado sem jumpers; permaneceu frio e ligado. |
| Cabo micro-USB | Cabo de dados obtido e reconhecido como `/dev/ttyACM0`. |
| Firmware físico | Gravado e verificado em 24/09; iniciou com `safety=ON`, motores em zero, bomba e som desligados. |
| TB6612FNG vermelho | Sem curto direto entre VCC–GND ou VM–GND no teste de continuidade; ainda deve ser religado uma conexão por vez. |
| DRV8833 preto | Fora de uso; um componente SMD marcado `472` desprendeu durante a soldagem. |
| Relé de dois canais | Chegou a energizar e os dois relés clicaram; ficou desconectado para investigação segura. |
| Quatro motores | Ainda não foram energizados nem conectados aos drivers. |
| Bomba e MS-129BT | Identificados, mas ainda não foram ligados aos contatos do relé. |
| Powerbank PN-951 | Reservado para lógica, 5 V e 2,1 A no total. |
| Powerbank Minimen MM-CDB300 | Candidato à alimentação dos motores somente em 5 V; capacidade real ainda não foi ensaiada. |

## 3. Identificação das protoboards

As duas protoboards grandes foram unidas lateralmente:

```text
P1 — protoboard da esquerda                  P2 — protoboard da direita

+/- | A B C D E | canal | F G H I J | +/-   +/- | A B C D E | canal | F G H I J | +/-
```

Convenções usadas neste relatório:

- `P1` = protoboard da esquerda;
- `P2` = protoboard da direita;
- `P1-G63` = protoboard 1, coluna G, linha 63;
- `P2-A49` = protoboard 2, coluna A, linha 49.

### 3.1 Como os furos se conectam

Em uma linha comum:

```text
A — B — C — D — E     F — G — H — I — J
```

- `A–E` são eletricamente conectados entre si na mesma linha;
- `F–J` são eletricamente conectados entre si na mesma linha;
- o canal central separa `E` de `F`;
- linhas diferentes não são conectadas;
- os barramentos laterais vermelho/azul não devem ser considerados contínuos sem medição: algumas protoboards dividem esses barramentos no meio.

Exemplo: `P2-A63`, `P2-B63`, `P2-C63`, `P2-D63` e `P2-E63` pertencem ao mesmo ponto elétrico.

## 4. Posição da ESP32 de 30 pinos

Orientação usada:

- conector micro-USB voltado para baixo;
- fileira esquerda da ESP32 encaixada em `P1-G`;
- fileira direita encaixada em `P2-A`;
- pinos inferiores na linha 63;
- pinos superiores na linha 49.

Os extremos confirmados foram:

- `VIN` em `P1-G63`;
- `3V3` em `P2-A63`.

### 4.1 Mapa completo da ESP32 nessa posição

| Linha | P1-G — lado esquerdo da ESP32 | P2-A — lado direito da ESP32 |
|---:|---|---|
| 49 | EN | GPIO23 |
| 50 | VP / GPIO36 | GPIO22 |
| 51 | VN / GPIO39 | TX0 / GPIO1 |
| 52 | GPIO34 | RX0 / GPIO3 |
| 53 | GPIO35 | GPIO21 |
| 54 | GPIO32 | GPIO19 |
| 55 | GPIO33 | GPIO18 |
| 56 | GPIO25 | GPIO5 |
| 57 | GPIO26 | GPIO17 |
| 58 | GPIO27 | GPIO16 |
| 59 | GPIO14 | GPIO4 |
| 60 | GPIO12 | GPIO2 |
| 61 | GPIO13 | GPIO15 |
| 62 | GND | GND |
| 63 | VIN / 5 V | 3V3 |

### 4.2 GPIOs reservados pelo firmware

| Função | GPIO | Coordenada equivalente |
|---|---:|---|
| Motor/canal A — IN1 | 18 | P2-A55 |
| Motor/canal A — IN2 | 19 | P2-A54 |
| Motor/canal A — PWM | 23 | P2-A49 |
| Motor/canal B — IN1 | 16 | P2-A58 |
| Motor/canal B — IN2 | 17 | P2-A57 |
| Motor/canal B — PWM | 22 | P2-A50 |
| Relé da bomba | 25 | P1-G56 |
| Relé do som | 26 | P1-G57 |
| Emergência local planejada | 32 | P1-G54 |

`D25`, `D26` e `GPIO25`, `GPIO26` são nomes usados para os mesmos pinos nesse modelo de placa.

## 5. TB6612FNG vermelho — HW-166

### 5.1 Função

O TB6612FNG possui duas pontes H:

- canal A: controla um motor com `AIN1`, `AIN2` e `PWMA`;
- canal B: controla outro motor com `BIN1`, `BIN2` e `PWMB`.

Ele não é a fonte dos motores. Ele recebe energia e decide sentido e velocidade.

### 5.2 Posição usada na protoboard

Orientação registrada:

- olhando o lado dos componentes;
- capacitor amarelo na parte superior;
- texto `TB6612FNG HW-166` na parte inferior;
- fileira esquerda na coluna `P1-D`;
- fileira direita na coluna `P1-H`;
- módulo ocupando as linhas 20–27.

| Linha | P1-D — fileira esquerda | P1-H — fileira direita |
|---:|---|---|
| 20 | VM | PWMA |
| 21 | VCC | AIN2 |
| 22 | GND | AIN1 |
| 23 | AO1 | STBY |
| 24 | AO2 | BIN1 |
| 25 | BO2 | BIN2 |
| 26 | BO1 | PWMB |
| 27 | GND | GND |

> [!WARNING]
> Esse mapa só vale com a orientação acima. Girar o módulo em 180° muda todas as posições físicas.

> [!IMPORTANT]
> Correção confirmada fisicamente em 24/09/2026: quando o módulo está com
> os componentes voltados para cima, capacitor amarelo em cima e texto embaixo,
> os rótulos impressos no verso aparecem espelhados. A alimentação e as saídas
> ficam na fileira esquerda (`P1-D`); `PWMA`, as entradas, `STBY` e `PWMB`
> ficam na fileira direita (`P1-H`).

### 5.3 Significado das siglas do TB6612

| Sigla | Significado |
|---|---|
| `VM` | Alimentação de potência dos motores. Planejada em 5 V. |
| `VCC` | Alimentação da lógica do driver. Ligada à lógica de 3,3 V da ESP32. |
| `GND` | Referência de zero volt comum. |
| `STBY` | Standby. Precisa estar em nível alto para habilitar o driver. |
| `AIN1/AIN2` | Entradas que determinam o sentido do canal A. |
| `BIN1/BIN2` | Entradas que determinam o sentido do canal B. |
| `PWMA/PWMB` | Entradas PWM que controlam a velocidade dos canais A e B. |
| `AO1/AO2` | Saídas para os dois terminais do motor A. |
| `BO1/BO2` | Saídas para os dois terminais do motor B. |

### 5.4 Ligações corrigidas para a remontagem

A primeira montagem usou os lados do módulo invertidos porque os rótulos foram
lidos pelo verso. Ao ligar o antigo fio azul, o LED da ESP32 apagou. O USB foi
retirado imediatamente; sem esse fio, a ESP32 voltou a funcionar e permaneceu
fria. A tabela abaixo substitui integralmente a pinagem anterior.

| Cor usada | Origem no TB6612 | Destino na ESP32 | Função |
|---|---|---|---|
| Vermelho | `VCC`, P1-D21 via P1-B21 | `3V3`, P2-C63 | Alimentação lógica do driver |
| Preto | `GND`, P1-D22 via P1-B22 | `GND`, P2-C62 | Terra da lógica |
| Amarelo | `STBY`, P1-H23 via P1-J23 | `3V3`, P2-D63 | Manter o driver habilitado |
| Azul | `PWMA`, P1-H20 via P1-J20 | GPIO23, P2-E49 | Velocidade do canal A |
| Laranja | `AIN2`, P1-H21 via P1-J21 | GPIO19, P2-E54 | Sentido do canal A |
| Verde | `AIN1`, P1-H22 via P1-J22 | GPIO18, P2-E55 | Sentido do canal A |
| Roxo | `PWMB`, P1-H26 via P1-J26 | GPIO22, P2-E50 | Velocidade do canal B |
| Branco | `BIN1`, P1-H24 via P1-J24 | GPIO16, P2-E58 | Sentido do canal B |
| Cinza | `BIN2`, P1-H25 via P1-J25 | GPIO17, P2-E57 | Sentido do canal B |

`VM`, `AO1`, `AO2`, `BO1` e `BO2` não chegaram a ser ligados à fonte ou aos motores.

## 6. DRV8833 preto

O DRV8833 seria o segundo driver, permitindo controlar os outros dois motores individualmente.

Pinagem lida na própria placa, com a face dos rótulos voltada para quem observa:

| Fileira esquerda, de cima para baixo | Fileira direita, de cima para baixo |
|---|---|
| IN4 | EEP / SLEEP |
| IN3 | OUT1 |
| GND | OUT2 |
| VCC | OUT3 |
| IN2 | OUT4 |
| IN1 | ULT / FAULT |

Durante a tentativa de soldagem, desprendeu-se um componente SMD marcado `472`. O código `472` normalmente representa um resistor de **4,7 kΩ**. A função exata dele nessa placa ainda precisa ser rastreada pelas trilhas.

Estado de segurança:

- não energizar o DRV8833;
- não ligar motores nele;
- reparar o componente e inspecionar pontes de solda antes do teste;
- de preferência substituir o módulo caso a ilha ou trilha tenha sido arrancada.

## 7. Relé de dois canais

### 7.1 Finalidade planejada

| Canal | GPIO | Carga planejada |
|---|---:|---|
| IN1 | 25 | Bomba d'água |
| IN2 | 26 | Caixa de som MS-129BT |

O módulo usa relés Songle `SRD-05VDC-SL-C`, portanto as bobinas são de 5 V.

### 7.2 Jumpers usados

O usuário confirmou as conexões pelos rótulos da ESP32:

| Cor | ESP32 | Relé | Significado |
|---|---|---|---|
| Azul | D25 / GPIO25 | IN1 | Comando da bomba |
| Azul | D26 / GPIO26 | IN2 | Comando do som |
| Roxo | VIN / 5 V | VCC | Alimentação do módulo na bancada |
| Roxo | GND | GND | Referência elétrica comum |

Havia ainda um terceiro jumper azul disponível como reserva.

Como os dois fios de alimentação tinham a mesma cor roxa, foi recomendado marcar:

- fita vermelha no roxo de `VCC`;
- fita preta no roxo de `GND`.

Na montagem final, é melhor distribuir o 5 V da fonte lógica em paralelo para ESP32 e relé, em vez de fazer toda a corrente passar pela placa da ESP32.

### 7.3 Significado dos terminais de potência

Cada canal possui três bornes:

| Sigla | Nome | Comportamento |
|---|---|---|
| `COM` | Comum | Terminal central da comutação. |
| `NO` | Normalmente aberto | Desconectado em repouso; conecta ao COM quando o relé aciona. |
| `NC` | Normalmente fechado | Conectado ao COM em repouso; abre quando o relé aciona. |

Durante os testes, `COM`, `NO` e `NC` permaneceram vazios. Portanto, os cliques observados não energizaram bomba nem caixa de som.

### 7.4 Relé ativo em nível baixo

O módulo é tratado no firmware como **ativo em nível baixo**:

```text
GPIO em HIGH ou desconectado -> relé desligado
GPIO em LOW                  -> relé ligado
```

O firmware foi corrigido para configurar GPIO25 e GPIO26 como `OUTPUT_OPEN_DRAIN` e escrever `HIGH` antes de habilitar as saídas. Isso evita o pulso baixo que pode ocorrer ao iniciar a ESP32.

Essa correção foi compilada e gravada na placa física em 24/09/2026.

## 8. Bomba d'água

A bomba foi retirada de um dispenser recarregável. Ela possui:

- motor da bomba;
- bateria cilíndrica de uma célula;
- placa original de carga e controle;
- terminais `M+`, `M-`, `B+` e `GND`;
- dois botões identificados como `S1` e `S2`.

Plano de integração:

1. manter a bateria e a placa original da bomba;
2. identificar qual botão inicia/interrompe a bomba;
3. ligar `COM` e `NO` de um canal do relé em paralelo aos dois contatos desse botão;
4. fazer o relé simular um toque, sem alimentar o motor da bomba pela ESP32.

Ainda não foi determinado se `S1` ou `S2` é o comando correto. Nenhum borne do relé foi conectado à bomba.

## 9. Caixa de som MS-129BT

A caixa possui placa Bluetooth, alto-falante e bateria própria. O plano é preservar seu circuito original.

Antes de ligar o relé, é necessário verificar:

- se a placa liga automaticamente quando a alimentação retorna;
- se existe botão ou chave de liga/desliga que possa ser simulada;
- se a interrupção deve ocorrer no botão ou no fio positivo da bateria;
- se volume e pareamento são preservados depois do desligamento.

Nenhum contato do relé foi ligado à MS-129BT.

## 10. Alimentação planejada com dois powerbanks

O projeto não utilizará pilhas avulsas. A arquitetura decidida usa dois powerbanks.

### 10.1 Powerbank lógico — BM PN-951

Dados da etiqueta:

- bateria interna: 3,7 V, 10.000 mAh, 37 Wh;
- OUT1: 5 V / 2,1 A;
- OUT2: 5 V / 2,1 A;
- corrente total combinada: 5 V / 2,1 A máximo.

Uso planejado:

- ESP32 principal;
- ESP32-CAM;
- módulo de relé;
- demais circuitos lógicos.

As duas portas não fornecem 4,2 A somados; o limite indicado é compartilhado.

### 10.2 Powerbank dos motores — Minimen MM-CDB300

Dados da etiqueta:

- 10.000 mAh / 38,5 Wh / 3,85 V;
- saída USB-C: 4,5 V / 5 A, 5 V / 3 A, 9 V / 2 A ou 12 V / 1,5 A;
- potência máxima anunciada: 20 W.

Uso planejado:

- `VM` do TB6612;
- alimentação de potência do segundo driver;
- quatro motores, se os ensaios confirmarem corrente suficiente.

Regras:

- usar apenas 5 V para os motores de 3–6 V;
- nunca aplicar 9 V ou 12 V aos motores;
- confirmar se a saída permanece ligada e suporta a partida simultânea;
- o powerbank já apresentou descarga rápida e não pode ser considerado aprovado sem ensaio.

### 10.3 Separação das fontes e terra comum

```text
POWERBANK LÓGICO (5 V)                POWERBANK DOS MOTORES (5 V)
          |                                      |
          +--> ESP32                             +--> TB6612 VM
          +--> ESP32-CAM                         +--> DRV8833 VCC
          +--> Relé 5 V                          +--> motores
          |                                      |
          +---------------- GND COMUM ------------+
```

- Os positivos dos dois powerbanks **não devem ser unidos**.
- Os GNDs precisam ser comuns para que os sinais da ESP32 tenham a mesma referência dos drivers.
- O caminho de corrente dos motores não deve passar pela ESP32 nem pelos trilhos finos da protoboard.
- O cabo modificado que veio com o PN-951 não deve ser usado até a polaridade ser medida; as cores não são prova de polaridade.

## 11. Motores e estratégia 4×4

Os quatro motores são do tipo:

> Motor DC 3–6 V, redutor amarelo tipo TT/130, roda de 65 mm para Arduino Smart Car.

Distribuição segura planejada:

| Driver | Canal | Motor |
|---|---|---|
| TB6612 | A | Motor 1 |
| TB6612 | B | Motor 2 |
| DRV8833 ou substituto | 1 | Motor 3 |
| DRV8833 ou substituto | 2 | Motor 4 |

Não foi autorizada a ligação de dois motores em paralelo em um único canal porque a corrente de travamento ainda não foi medida. Dois motores travados podem ultrapassar o limite do canal e danificar o driver.

## 12. Firmware e significado dos sinais

Arquivo principal: `firmware/src/main.cpp`.

Pinagem atual:

```cpp
LEFT_IN1   = 18;
LEFT_IN2   = 19;
LEFT_PWM   = 23;
RIGHT_IN1  = 16;
RIGHT_IN2  = 17;
RIGHT_PWM  = 22;
RELAY_PUMP = 25;
RELAY_SOUND = 26;
EMERGENCY_BUTTON = 32;
```

### 12.1 Exemplo de sentido e PWM

```text
IN1=HIGH, IN2=LOW,  PWM=60% -> motor gira em um sentido
IN1=LOW,  IN2=HIGH, PWM=60% -> motor gira no sentido oposto
IN1=LOW,  IN2=LOW,  PWM=0%  -> motor parado
```

`PWM` significa modulação por largura de pulso. O driver liga e desliga a alimentação rapidamente; a proporção de tempo ligado define a potência média e, portanto, a velocidade aproximada.

### 12.2 Situação do firmware físico

- O projeto compila com PlatformIO.
- A correção de partida segura dos relés está no arquivo local.
- A placa física recebeu essa versão em 24/09/2026 pela porta `/dev/ttyACM0`.
- Bootloader, tabela de partições, `boot_app0` e firmware tiveram os hashes verificados durante a gravação.
- O monitor serial confirmou repetidamente: `L=0`, `R=0`, `safety=ON`, `pump=OFF` e `sound=OFF`.
- O firmware ainda usa `Wokwi-GUEST` e `host.wokwi.internal`; será necessário configurar a rede real e o IP do servidor.
- Um cabo apenas de alimentação acende o LED, mas não permite gravar código.

## 13. O que aconteceu durante os testes

### 13.1 Primeiro teste do relé

Com o relé ligado a `VIN`, `GND`, GPIO25 e GPIO26:

- duas luzes do módulo acenderam;
- foram ouvidos dois cliques;
- os relés pararam de clicar;
- `COM`, `NO` e `NC` estavam vazios.

O comportamento foi associado ao pulso de inicialização das GPIOs antes de o firmware definir o estado desligado. Por isso, o código foi alterado para `OUTPUT_OPEN_DRAIN` com estado inicial alto.

### 13.2 Aquecimento e queda de alimentação

Em uma ligação posterior:

- somente as luzes do relé apareceram;
- o LED da ESP32 não permaneceu aceso;
- a região próxima ao micro-USB ficou bastante quente;
- após retirar o `VCC` do relé, o LED vermelho da ESP32 acendeu rapidamente e apagou.

Isso é compatível com curto-circuito ou sobrecorrente em algum circuito externo.

### 13.3 Isolamento realizado

Foram removidos todos os jumpers da ESP32. Depois:

1. a ESP32 foi testada sozinha fora da protoboard;
2. o LED vermelho permaneceu aceso;
3. a placa não aqueceu;
4. a ESP32 foi recolocada nas duas protoboards sem jumpers;
5. novamente permaneceu ligada e fria.

Conclusão disponível até este ponto:

- a ESP32 não apresentou falha quando isolada;
- o encaixe da ESP32 nas protoboards não causou aquecimento quando estava sem fios;
- em 24/09, o multímetro VC830L foi validado pelo teste sonoro entre as próprias pontas;
- não houve bip de continuidade entre `VCC` e `GND` do TB6612;
- não houve bip de continuidade entre `VM` e `GND` do TB6612;
- não foi encontrado curto direto nessas duas alimentações;
- a hipótese principal passa a ser uma ligação incorreta ou contato acidental na montagem anterior, mas a causa exata ainda não foi comprovada.

## 14. Por que a montagem precisou ser desmontada

A desmontagem foi uma medida de proteção, não o abandono do esquema.

Motivos:

1. a ESP32 aqueceu de maneira anormal;
2. o LED apagou, indicando queda ou proteção da alimentação;
3. continuar energizando poderia queimar a ESP32, a porta USB do notebook ou o driver;
4. havia muitas ligações simultâneas, impossibilitando identificar o ramo defeituoso;
5. as soldas do TB6612 precisam ser verificadas contra pontes entre pinos;
6. não havia multímetro para comprovar ausência de curto;
7. o firmware corrigido ainda não tinha sido gravado.

Ao remontar um fio por vez, cada etapa terá um resultado observável. Se o problema retornar, será possível identificar exatamente qual ligação o introduziu.

## 15. Glossário rápido

| Termo | Explicação |
|---|---|
| ESP32 | Microcontrolador principal do robô. |
| ESP32-CAM | ESP32 com câmera, responsável por fornecer imagens. |
| GPIO | Pino digital configurável da ESP32. |
| `D25` | Nome de placa para GPIO25. |
| `VIN` | Entrada/linha de aproximadamente 5 V da placa. |
| `3V3` | Alimentação regulada de 3,3 V. |
| `VCC` | Alimentação da parte lógica de um módulo. O valor depende do módulo. |
| `VM` | Alimentação dos motores no TB6612. |
| `GND` | Terra ou referência de zero volt. |
| PWM | Sinal pulsado usado para controlar potência/velocidade. |
| Ponte H | Circuito que permite inverter o sentido de um motor DC. |
| Driver | Módulo que fornece a corrente exigida pelo motor conforme o comando lógico. |
| Active-low | Dispositivo acionado quando a entrada vai para nível baixo/0 V. |
| Open-drain | Saída que puxa o sinal para GND, mas não injeta tensão alta no módulo. |
| Continuidade | Teste que identifica ligação elétrica ou curto entre dois pontos. |
| Corrente de travamento | Maior corrente do motor, medida quando o eixo não consegue girar. |
| Terra comum | GND compartilhado entre controladores e drivers com fontes separadas. |
| NO | Contato normalmente aberto de um relé. |
| NC | Contato normalmente fechado de um relé. |
| COM | Contato comum de um relé. |

## 16. Materiais necessários para a retomada

Essenciais:

- cabo micro-USB comprovadamente capaz de transferir dados;
- multímetro digital com tensão DC, resistência e continuidade sonora;
- fita ou etiquetas para identificar as duas pontas de cada jumper;
- rodas suspensas durante todos os primeiros testes;
- fotos nítidas das duas faces do TB6612 e das soldas.

Recomendados:

- adaptador USB macho com borne de parafuso e indicação `+5V/GND`;
- fios mais grossos para corrente dos motores;
- borne/distribuidor para a alimentação de potência;
- fusível na linha dos motores;
- segundo driver novo ou DRV8833 reparado profissionalmente;
- capacitores de supressão nos motores após os ensaios de ruído.

## 17. Checklist para continuar amanhã

### Fase A — confirmar comunicação

- [x] Manter todos os módulos externos desconectados.
- [x] Ligar apenas a ESP32 pelo cabo de dados.
- [x] Confirmar que aparece `/dev/ttyUSB0` ou `/dev/ttyACM0`.
- [x] Gravar o firmware corrigido.
- [ ] Reiniciar a placa e verificar que permanece fria.

### Fase B — medir antes de alimentar

- [ ] TB6612 totalmente desconectado.
- [ ] Inspecionar soldas e remover pontes visíveis.
- [x] Medir continuidade/resistência entre `VCC` e `GND`: sem bip.
- [x] Medir continuidade/resistência entre `VM` e `GND`: sem bip.
- [ ] Confirmar 5 V e polaridade dos cabos dos powerbanks.
- [ ] Não prosseguir se houver bip contínuo ou resistência próxima de zero.

### Fase C — reconstruir a lógica

- [ ] Conectar somente o GND do TB6612.
- [ ] Conectar VCC de 3,3 V e observar consumo/aquecimento.
- [ ] Conectar STBY.
- [ ] Conectar um GPIO por vez, seguindo a tabela de cores.
- [ ] Testar canal A sem motor.
- [ ] Testar canal B sem motor.
- [ ] Conectar o relé sozinho e confirmar partida sem cliques.
- [ ] Acionar IN1 e IN2 separadamente pelo firmware.

### Fase D — potência e motores

- [ ] Manter o positivo do powerbank dos motores separado do positivo lógico.
- [ ] Unir apenas os GNDs.
- [ ] Confirmar 5 V em VM.
- [ ] Testar um motor por vez, com roda suspensa e PWM baixo.
- [ ] Medir corrente sem carga e corrente de travamento.
- [ ] Verificar aquecimento antes de adicionar o próximo motor.
- [ ] Não ligar dois motores no mesmo canal sem confirmar corrente admissível.

### Fase E — bomba e som

- [ ] Identificar se S1 ou S2 aciona a bomba.
- [ ] Verificar o comportamento da MS-129BT quando a alimentação retorna.
- [ ] Usar COM/NO como contato isolado, sem alimentar as cargas pela GPIO.
- [ ] Confirmar limite de três segundos para a bomba.

## 18. Estado seguro para guardar a bancada

Ao interromper o trabalho:

- USB desconectado;
- dois powerbanks desconectados;
- ESP32 sem jumpers externos;
- TB6612 sem alimentação;
- DRV8833 separado e identificado como “não energizar”;
- motores, bomba e caixa sem ligação aos relés/drivers;
- pontas metálicas dos jumpers separadas para não se tocarem.

Esse é o ponto correto para retomar com medições e reconstrução controlada.

## 19. Inventário das placas ESP32

### ESP 01 — “ESP do Ikki”

Esta é a ESP32 DevKit de 30 pinos usada nos primeiros testes da bancada.

Diagnóstico registrado em 25/09/2026:

- chip ESP32-D0WD-V3 identificado corretamente;
- endereço MAC: `d4:e9:f4:a2:9f:2c`;
- memória flash de 4 MB identificada e gravável;
- bootloader e conversor USB–serial funcionam;
- firmware mínimo, sem Wi‑Fi, executa continuamente;
- ao ativar Wi‑Fi, a placa reinicia repetidamente por queda de alimentação (*brownout*);
- a porta USB desaparece e reaparece durante esses resets;
- a placa havia aquecido anteriormente perto da porta Micro‑USB.

Conclusão: a placa não está totalmente morta, mas **não deve ser usada no robô final
sem reparo da alimentação de 3,3 V**. As opções são substituir o regulador da
placa, usar um regulador externo de 3,3 V com pelo menos 500 mA, ou substituir a
placa inteira. Não alimentar simultaneamente `VIN/5V` e `3V3`.

### Nova placa — “ESP32-C6” (duas USB)

Uma segunda placa foi obtida, identificada provisoriamente pelo usuário como
`ESP-C6-32`. Ela possui duas portas USB. O modelo exato, a pinagem e a função de
cada USB ainda precisam ser confirmados pela serigrafia e pelo verso da placa.

Regras antes de conectá-la:

1. não reutilizar o mapa físico da ESP32 clássica de 30 pinos;
2. fotografar frente e verso, incluindo todos os nomes dos pinos;
3. identificar qual USB é alimentação/dados e qual é USB nativo ou USB–serial;
4. testar a placa sozinha, sem TB6612, relés ou motores;
5. só depois criar um novo mapa de protoboard e atualizar o firmware para a
   pinagem do ESP32-C6.

#### Identificação visual e pinagem provisória

As fotos confirmam uma placa **ESP32-DevKit-C6** da QSZNTEC, compatível
visualmente com o layout ESP32-C6-DevKitC-1. Ela possui duas USB-C:

- `UART`: ligada à ponte USB–UART, indicada para programação e monitor serial;
- `USB`: USB nativa do ESP32-C6, usada para programação, comunicação e JTAG.

Teste inicial no notebook do servidor (26/09/2026):

- porta detectada: `/dev/ttyACM1`;
- chip: ESP32-C6, revisão 0.2;
- MAC: `e8:f6:0a:ff:fe:f7:f0:64`;
- flash detectada: 4 MB;
- comunicação com o bootloader confirmada.

Com os conectores USB voltados para baixo, a pinagem observada é:

| Lado J1 (esquerdo, de cima para baixo) | Lado J3 (direito, de cima para baixo) |
|---|---|
| 3V3 | GND |
| RST | TX / GPIO16 |
| GPIO4 | RX / GPIO17 |
| GPIO5 | GPIO15 |
| GPIO6 | GPIO23 |
| GPIO7 | GPIO22 |
| GPIO0 | GPIO21 |
| GPIO1 | GPIO20 |
| GPIO8 (LED RGB) | GPIO19 |
| GPIO10 | GPIO18 |
| GPIO11 | GPIO9 |
| GPIO2 | GND |
| GPIO3 | GPIO13 / USB D+ |
| 5V | GPIO12 / USB D− |
| GND | GND |
| NC | NC |

Essa tabela deve ser conferida com uma foto nítida da serigrafia antes de ligar o
TB6612. O ESP32-C6 não pode reutilizar diretamente o mapa de GPIO da ESP32
clássica. Os GPIO8, GPIO9 e GPIO15 são pinos de configuração na inicialização;
evitar usá-los para cargas que alterem seu nível durante o reset.

Segundo a documentação oficial da Espressif, a placa pode ser alimentada pela
USB-UART, pela USB nativa, pelo pino `5V` ou pelo pino `3V3`; ao usar fonte
externa, nunca aplicar 5 V diretamente em `3V3`. A USB-UART é a opção inicial
recomendada para nosso teste. ([Guia oficial ESP32-C6-DevKitC-1](https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32c6/esp32-c6-devkitc-1/user_guide.html))

#### Correção da montagem na protoboard

O clone QSZNTEC fotografado possui espaçamento físico menor que o DevKitC-1
oficial: a fileira externa ocupa aproximadamente oito colunas. Portanto, a
orientação correta para manter pontos de ligação acessíveis é:

- USBs voltadas para baixo;
- fileira esquerda na coluna **B**;
- fileira direita na coluna **I**;
- mesmas linhas nos dois lados, por exemplo `B20–B35` e `I20–I35`;
- as colunas externas **A** e **J** ficam livres para jumpers.

Não usar `A–H`: embora os pinos possam encaixar, o corpo da placa bloqueia os
furos necessários para os jumpers. A recomendação anterior `A–J` estava errada
para esta placa específica e deve ser desconsiderada.

Com a montagem atual (3V3 em `P1-H48` e o último GND em `P1-H63`; fileira
direita iniciando em `P2-A48`), os GPIOs usados pelo TB6612 ficam:

| GPIO C6 | Coordenada física |
|---:|---|
| GPIO23 | `P2-A52` |
| GPIO22 | `P2-A53` |
| GPIO21 | `P2-A54` |
| GPIO20 | `P2-A55` |
| GPIO19 | `P2-A56` |
| GPIO18 | `P2-A57` |

Essas coordenadas pressupõem 16 pinos alinhados nas linhas 48–63 e devem ser
confirmadas pela serigrafia da placa antes de energizar.
