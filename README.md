# Robô de Logística e Fuga — gêmeo digital

MVP digital do projeto de Robótica Móvel do Grupo 2. O repositório contém um Dashboard Web funcional, servidor local, simulação física 3D no Webots, percepção monocular, regras de segurança, API para integração e firmware da ESP32 principal preparado para PlatformIO e Wokwi.

## O que já funciona

- Controle manual 4×4 diferencial por botões, toque, setas ou WASD.
- Modo autônomo guiado exclusivamente pela imagem da câmera frontal.
- Mundo Webots com quatro rodas motorizadas, paredes, câmera e jato visual da bomba.
- Estimativa visual de espaço à frente, à esquerda e à direita, sem HC-SR04 ou outro sensor de distância.
- Telemetria de motores, enlace, bateria, posição e sensores.
- Acionamento temporizado da bomba e habilitação da caixa de som.
- Parada de emergência, timeout de comando, perda de enlace e bloqueio por obstáculo.
- Cenários de teste e registro de eventos.
- API consumida tanto pelo Dashboard quanto pelo firmware.
- Circuito Wokwi com ESP32, dois relés e LEDs representando os sinais da ponte H.

## Executar o Dashboard

Requer apenas Python 3:

```sh
python3 server.py
```

Abra `http://127.0.0.1:8765` no navegador.

### Troca rápida de rede e endereços

No painel principal, use o botão **Rede** para atualizar sem editar código:

- **URL da câmera**: endereço HTTP que fornece o vídeo (por exemplo, o `/video` do DroidCam).
- **URL do ESP32-C6**: IP atual ou `http://robo-c6.local` quando o nome mDNS resolver.
- **SSID e senha**: credenciais da rede de **2,4 GHz** para o C6.

Os dois endereços ficam salvos em `runtime_config.json` (sem senha). O hub mantém um único consumidor da câmera e troca o upstream quando a URL é salva. A senha é enviada somente ao endpoint `/wifi` do firmware de provisioning e é apagada do formulário após o envio.

O C6 precisa estar acessível pela rede atual para receber novas credenciais. Se ele estiver sem conexão, conecte o notebook temporariamente ao ponto de acesso `Robo-C6` criado pelo firmware, use `http://192.168.4.1` como URL do C6 no painel, envie a rede doméstica de 2,4 GHz e depois retorne o notebook à rede doméstica. O firmware do C6 não conecta a redes exclusivamente de 5 GHz; uma rede cujo nome termina em `5G` normalmente exige a variante 2,4 GHz do roteador.

### Provisionamento direto pela USB

O mesmo diálogo **Rede** possui a seção **USB da placa**. Em um navegador com Web Serial, clique em **Scan USB / selecionar ESP**, escolha a porta, confira a placa identificada e clique em **Enviar Wi‑Fi pela USB**. O comando é processado pelo firmware e salvo em `Preferences`; não é um upload de firmware e não depende de IP. A URL da câmera continua sendo salva separadamente no hub.

O protocolo serial é deliberadamente pequeno (`PING`, `WIFI<TAB>ssid<TAB>senha` e `STATUS`) e não imprime a senha. O upload de firmware continua sendo uma operação de manutenção separada, feita pelo procedimento de gravação da placa.

Para ver diretamente as conexões, os quatro motores e suas velocidades, abra:

```text
http://127.0.0.1:8765/bancada
```

A Bancada Virtual mostra a montagem física proposta em vista superior: ESP32 encaixada na protoboard, jumpers identificados por GPIO, ponte H L298N provisória, módulo relé e fios chegando aos quatro motores DC, à bomba e ao MS-129BT. Ela também anima os sinais e os atuadores; quando o Webots está executando, as velocidades em `rad/s` e `rpm` são medidas individualmente pelos encoders de cada roda.

Para acessar pelo celular ou por uma ESP32 na mesma rede:

```sh
python3 server.py --host 0.0.0.0
```

Depois abra `http://IP-DO-COMPUTADOR:8765`. O firewall do computador precisa permitir conexões na porta 8765.

## Operação

1. Confirme que o indicador mostra **Simulador local conectado**.
2. Selecione **Manual**.
3. Use WASD, setas ou o controle direcional.
4. Solte o comando para interromper imediatamente os motores.
5. Use **Dispersar água** para um pulso com limite rígido de três segundos.
6. Use **Caixa de som** para alternar o segundo canal do relé.
7. Altere a estimativa da câmera sintética, interrompa o enlace ou escolha um cenário para validar as proteções.

A barra laranja de parada permanece disponível no topo em desktop e celular. Quando acionada, ela desliga movimento, bomba e som e retorna o sistema ao modo parado.

## Testes automatizados

```sh
python3 -m unittest discover -s tests -v
```

Os testes cobrem partida segura, mistura diferencial, parada ao soltar o comando, timeout, emergência, perda de enlace, navegação visual, perda da câmera, geometria monocular e limite da bomba.

## Simulação visual 3D

O Wokwi não possui motor DC escovado nem simulação de câmera adequada para este caso. Para visualizar o comportamento físico, use o projeto Webots:

```text
simulation/webots/worlds/carro_4x4.wbt
```

Inicie antes o `server.py`, abra o mundo no Webots R2025a e pressione **Play**. O carro recebe os comandos da Bancada ou do Dashboard, movimenta quatro rodas físicas e cria gotas azuis quando a bomba é acionada. A visão principal abre seguindo o carro; a janela da ESP32-CAM fica oculta para não cobrir a cena.

Neste computador, abra o simulador diretamente com:

```sh
./simulation/webots/abrir_webots.sh
```

O controlador não lê distância, posição ou colisão do Webots para navegar. Ele segmenta a imagem da câmera e projeta as bordas do corredor no chão. Consulte [`simulation/webots/README.md`](simulation/webots/README.md).

No canto superior da cena 3D, o Webots mostra o comando e a velocidade medida de M1, M2, M3 e M4, além dos estados da bomba, som e visão.

## Firmware ESP32 e Wokwi

O diretório [`firmware`](firmware/) é um projeto PlatformIO:

```sh
platformio run -d firmware
```

Depois, abra o diretório no VS Code com as extensões PlatformIO e Wokwi e execute **Wokwi: Start Simulator**. O `diagram.json` usa:

- LEDs verdes/amarelos: sentido de cada banco de motores.
- LEDs azuis: PWM esquerdo e direito.
- Dois relés: bomba e caixa de som.
- Botão vermelho: parada de emergência local.

No Wokwi para VS Code, o firmware usa `http://host.wokwi.internal:8765`. Para uma placa física, substitua `API_BASE_URL` no `platformio.ini` pelo IP do computador e configure SSID e senha reais.

## Organização

```text
dashboard/            interface visual
firmware/             firmware e circuito Wokwi da ESP32 principal
simulation/webots/    carro, mundo 3D, câmera e bomba visível
tests/                testes da máquina de estados
docs/ARQUITETURA.md   arquitetura, API e integração física
docs/PLANO_DE_TESTES.md roteiro digital, Wokwi e bancada física
docs/RELATORIO_BANCADA_FISICA.md registro da montagem, pinagem e incidente elétrico
server.py             API HTTP e gêmeo digital
PRODUCT.md            requisitos consolidados
DESIGN.md             sistema visual do Dashboard
```

## Limitações conhecidas

- Quando o Webots não está conectado, o feed visual, bateria, RSSI e confiança são sintéticos.
- O Wokwi não calcula torque, corrente de partida, aquecimento ou autonomia.
- A ponte H física permanece aberta até conhecermos a corrente de travamento dos motores.
- A tensão da bomba reaproveitada e o comportamento de alimentação da MS-129BT ainda precisam ser medidos em bancada.
- A calibração monocular do Webots deverá ser repetida com a ESP32-CAM física e o ambiente real.

O software digital valida lógica, estados e integração; ele não substitui o dimensionamento elétrico antes da montagem física.
