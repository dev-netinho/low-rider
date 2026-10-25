# Simulação 3D no Webots

Esta é a simulação visual principal do projeto. Ela mostra o carro 4×4, as quatro rodas motorizadas de 65 mm, o ambiente com paredes, a câmera frontal e o jato da bomba. Não existe HC-SR04, lidar, GPS ou sensor de distância no algoritmo de navegação.

## O que é simulado

- Quatro `RotationalMotor`, um em cada roda.
- Rodas de 65 mm e chassi de aproximadamente 290 × 180 mm.
- Câmera monocular com resolução 320 × 240 e campo de visão próximo ao da ESP32-CAM.
- Estimativa de espaço à frente, à esquerda e à direita por segmentação da imagem e projeção no piso.
- Navegação autônoma centralizando o carro no corredor e escolhendo o lado mais livre.
- Controle manual vindo do Dashboard.
- Bomba com gotas azuis físicas e limite de acionamento de três segundos.
- Caixa MS-129BT representada no chassi e estado controlado pela API.
- Parada de emergência e parada por perda do servidor ou da câmera.

O uso da API `Supervisor` está limitado ao efeito visual da água. O controlador não consulta posição, colisões ou distância do mundo para navegar.

## Pré-requisitos

1. Webots R2025a.
2. Python 3 para o servidor local.

Download oficial: <https://github.com/cyberbotics/webots/releases/tag/R2025a>

## Executar

Na raiz do projeto, inicie a API e o Dashboard:

```sh
python3 server.py
```

Abra `http://127.0.0.1:8765/bancada` para ver a ESP32 na protoboard, os jumpers, a ponte H, o relé e os fios chegando aos motores e controlar os componentes. Em seguida, abra no Webots:

```text
simulation/webots/worlds/carro_4x4.wbt
```

Pressione **Play** no Webots.

Neste computador, o Webots validado também pode ser aberto diretamente por:

```sh
./simulation/webots/abrir_webots.sh
```

O script usa uma instalação normal do Webots quando disponível e reconhece a cópia local preparada no cache deste ambiente.

### Modo manual

1. Selecione **Manual** no Dashboard.
2. Use os botões, WASD ou setas.
3. Observe as quatro rodas girarem e o carro responder fisicamente.

O painel sobre a cena informa separadamente M1, M2, M3 e M4 em porcentagem, `rad/s` e `rpm`. A velocidade é calculada pelos quatro `PositionSensor` associados aos eixos das rodas.

A câmera continua calculando as distâncias visuais para telemetria, mas não altera a trajetória manual.

### Modo autônomo

Selecione **Autônomo**. A cada quadro, o controlador:

1. separa piso escuro e paredes claras;
2. encontra as bordas do corredor;
3. projeta essas bordas no plano do chão usando a calibração da câmera;
4. publica as distâncias visuais em `POST /api/vision`;
5. recebe da API os comandos dos dois bancos de motores.

Se a imagem ficar indisponível ou a confiança cair, os motores param.

### Bomba

Clique em **Dispersar água** no Dashboard. O Webots cria um jato de gotas azuis saindo do bico frontal. A API encerra o pulso automaticamente em até três segundos.

### Visualizar a câmera

A ESP32-CAM é a visão do robô, não a visão externa da simulação. Ela inicia oculta para deixar o carro visível. Para inspecionar a imagem, expanda `Carro 4x4 Grupo 2` na árvore, abra `ESP32-CAM (visao do robo - pode fechar)` ou use o menu de dispositivos de câmera. Fechar essa janela não remove a câmera do algoritmo.

## Calibração

Os valores usados pelo modelo estão em `monocular_vision.py`:

- altura óptica: `0.164 m`;
- inclinação para baixo: `0.22 rad`;
- campo de visão: lido diretamente do dispositivo da câmera.

Na montagem física, altura, inclinação, distorção da lente e escala devem ser recalibradas com imagens e medidas reais. Uma única câmera não mede distância absoluta sem hipóteses geométricas; neste projeto usamos altura conhecida, piso aproximadamente plano e largura/bordas visíveis do corredor.
