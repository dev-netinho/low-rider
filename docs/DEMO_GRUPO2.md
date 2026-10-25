# Demonstração física — Grupo 2

## O que é real e o que é simulado

- **Imagem real:** o hub recebe o vídeo do S23/DroidCam em `CAMERA_STREAM_URL` e publica apenas o JPEG mais recente em `/api/camera/stream`.
- **Detecção real:** `vision_autonomy.py` decodifica esse JPEG com OpenCV, procura o maior alvo de uma cor forte e produz `LEFT`, `RIGHT`, `FORWARD` ou `STOP`.
- **Controle físico:** quando iniciado com `--robot-url`, `C6HttpBridge` envia `GET /drive?left=...&right=...` ao ESP32-C6. O C6 tem watchdog próprio de 800 ms.
- **Ainda simulado:** pose, bateria, RSSI padrão do painel e as distâncias em centímetros do corredor. A detecção por cor não inventa distância; ela expõe `vision_distance_valid=false`.
- **Hardware não confirmado pelo código:** fios, alimentação, ponte H e motores só podem ser confirmados visualmente/por teste com rodas suspensas. O servidor só marca `ESP32-C6 conectado` após resposta HTTP/telemetria.

## Modos e parada

`MANUAL`, `AUTONOMO` e `PARADO` são controlados pela máquina de estados em `server.py`. Emergência, perda de enlace, ausência de quadro recente e confiança baixa têm prioridade e zeram os motores. O ESP32-C6 também para após 800 ms sem `/drive`.

O detector consome somente a sequência mais recente do hub. Alvo ausente, JPEG inválido, frame envelhecido ou erro de comunicação resulta em `STOP`.

## Inicialização na faculdade

1. Ative o hotspot **2,4 GHz** do S23 e deixe o DroidCam transmitindo. Conecte notebook e ESP32-C6 ao mesmo hotspot.
2. Descubra os endereços em tempo de execução (lista DHCP do hotspot/roteador ou varredura local). Não reutilize IP de casa. Confirme `http://<IP_DO_C6>/` e o endpoint `/drive` com rodas suspensas.
3. No notebook, inicie:

   ```text
   python3 server.py --host 0.0.0.0 --port 8765 \
     --camera-url http://<IP_DO_S23>:4747/video \
     --robot-url http://<IP_DO_C6> --vision-color red
   ```

4. Abra `http://<IP_DO_NOTEBOOK>:8765/`. Primeiro selecione **Manual**, confirme `STOP` e teste só com rodas suspensas. Depois selecione **Autônomo**.
5. Se o hotspot falhar, use uma rede local própria (roteador portátil) com os três dispositivos; mantenha a mesma descoberta dinâmica de IP.

O firmware atual do C6 contém credenciais de uma rede anterior e pode precisar ser configurado para a rede da apresentação; isso não é resolvido pelo hub e não deve ser mascarado como hardware conectado.
