# relAI på Raspberry Pi 5 — statuslogg & körbart nuläge (video+audio+HA)

Det här repo:t dokumenterar vårt faktiska “nu-läge” på Raspberry Pi 5:
- **Video-inferens med Google Coral (EdgeTPU)** i Docker (pycoral/apt på bullseye pga kompatibilitet).
- **Audio capture från webbkamera (UGREEN USB Audio)** → enkel realtids-score (dBFS/energi) → skickas till en HTTP-endpoint.
- **Home Assistant** körs som Docker-container (för framtida dashboard/automationer/Assist i mobilen).
- En superminimal **dashboard-endpoint** (FastAPI mini) användes för att verifiera att ljudloopen kan skicka A/B live.

Målet är att bygga upp systemet stegvis, med verifierbara terminalkommandon och så lite gissning som möjligt.

---

## Miljö (verifierat)

**Host:**
- Raspberry Pi 5 Model B
- OS: Debian GNU/Linux 12 (bookworm)
- CPU/arch: aarch64
- Kamera: UGREEN UVC + USB Audio (mic)

**Audio (UGREEN Camera)**
- `arecord -l`:
  - `card 0: Camera [UGREEN Camera], device 0: USB Audio [USB Audio]`
- `--dump-hw-params` visar:
  - FORMAT: `S16_LE`
  - CHANNELS: `2`
  - RATE: `[8000 48000]`

**Coral**
- syns som `18d1:9302` i `lsusb` (EdgeTPU aktiv)

---

## Repo-mappar (lokalt på Pi)

Exempelstruktur (kan variera lite):
- `~/vision_service/` eller `~/vision_service_bookworm/` – vision/Coral-relaterat
- `~/coral-test-data/` – modeller/testdata
- `~/relai-audio-loop/` – audio loop (ffmpeg → dBFS-score → /set)
- `~/relai-dashboard-mini/` – minimal FastAPI endpoint för att ta emot /set (användes för test)
- `~/homeassistant/config/` – Home Assistant config-volym

---

## 1) Home Assistant (Docker) — igång

### Starta Home Assistant container
```bash
mkdir -p ~/homeassistant/config

docker run -d \
  --name homeassistant \
  --restart=unless-stopped \
  --network=host \
  -e TZ="Europe/Stockholm" \
  -v ~/homeassistant/config:/config \
  ghcr.io/home-assistant/home-assistant:stable
(Valfritt) Om du vill ha Bluetooth-stöd i HA-container
Du kan skapa om containern med:

--cap-add=NET_ADMIN --cap-add=NET_RAW

och mount av dbus: -v /run/dbus:/run/dbus:ro

Exempel:

bash
Kopiera kod
sudo apt update
sudo apt install -y bluez

docker stop homeassistant
docker rm homeassistant

docker run -d \
  --name homeassistant \
  --restart=unless-stopped \
  --network=host \
  --cap-add=NET_ADMIN \
  --cap-add=NET_RAW \
  -v /run/dbus:/run/dbus:ro \
  -e TZ="Europe/Stockholm" \
  -v ~/homeassistant/config:/config \
  ghcr.io/home-assistant/home-assistant:stable
Öppna HA UI
Ta Pi-IP:

bash
Kopiera kod
hostname -I
Öppna i webbläsare (mobil/dator på samma nät):

http://<PI-IP>:8123

Röst (nivå 2)
Installera Home Assistant Companion App på mobilen.

Logga in mot http://<PI-IP>:8123.

Använd Assist i appen för röstkommandon.

2) Audio loop (webbkamera-mic → score → HTTP)
Förutsättningar
bash
Kopiera kod
sudo apt update
sudo apt install -y ffmpeg python3-venv
Verifiera ljud-enheten
bash
Kopiera kod
arecord -l
arecord -D hw:0,0 --dump-hw-params -d 1 /dev/null
Testa inspelning (uppspelning är valfritt)
bash
Kopiera kod
arecord -D hw:0,0 -f S16_LE -c 2 -r 48000 -d 3 test.wav
ls -lh test.wav
Obs: aplay kan faila om Pi saknar playback-enhet. Det påverkar inte inspelning.

Audio loop-körning
Audio-loopen använder ffmpeg + ALSA och skickar A/B till /set:

bash
Kopiera kod
cd ~/relai-audio-loop
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install requests

ALSA_DEVICE="plughw:0,0" \
DASHBOARD_SET_URL="http://127.0.0.1:8000/set" \
python ./audio_loop_webcam.py
Förväntat:

Terminal acknowledges dBFS/score kontinuerligt.

Inga “Connection refused” om mottagaren är igång.

3) Minimal “dashboard-endpoint” (FastAPI) — testmottagare för /set
Detta är inte Home Assistant-dashboards, utan ett enkelt sätt att bevisa att ljudloopen kan skicka data live.

Skapa och starta mini-dashboard
bash
Kopiera kod
mkdir -p ~/relai-dashboard-mini
cd ~/relai-dashboard-mini
python3 -m venv .venv
source .venv/bin/activate
pip install fastapi uvicorn

cat > app.py <<'PY'
from fastapi import FastAPI
from fastapi.responses import JSONResponse

app = FastAPI()
state = {"A": 0.0, "B": 0.0}

@app.get("/health")
def health():
    return {"ok": True, "state": state}

@app.get("/set")
def set_values(A: float = 0.0, B: float = 0.0):
    state["A"] = float(A)
    state["B"] = float(B)
    return JSONResponse({"ok": True, "state": state})
PY

uvicorn app:app --host 0.0.0.0 --port 8000
Test:

bash
Kopiera kod
curl "http://127.0.0.1:8000/health"
curl "http://127.0.0.1:8000/set?A=0.5&B=0.2"
4) Vision + Coral (Docker) — riktning
PyCoral i Bookworm + Python 3.11 i container är struligt.
Vi har därför kört en bullseye/py39-baserad container där pycoral och edgetpu-runtime installeras via apt.

Grundprinciper som redan verifierats tidigare:

Resiza alltid input till modellens input_size innan set_input(...) (t.ex. 300x300 för SSD Mobilenet v2).

Kör container med --device /dev/bus/usb:/dev/bus/usb så EdgeTPU är synlig.

(Detaljer ligger i vision_service-mapparna och tidigare logg.)

Kända “gotchas”
aplay fungerar inte
Om Pi saknar playback-device får du fel, men inspelning + analys fungerar ändå.

Bluetooth-varningar i HA logs
Om du inte behöver Bluetooth: ignorera.
Om du behöver Bluetooth: återskapa containern med NET_ADMIN/NET_RAW + dbus mount och installera bluez på host.

Nästa steg (plan)
Flytta A/B-score från mini-dashboard till Home Assistant som sensor (REST/command_line/MQTT).

Bygga HA-dashboard som kan visas på mobil/dator (och senare kiosk på skärm).

Skapa todo/workflow: Assist (mobil) → HA automation → todo/shopping list.

Integrera vision-events (EdgeTPU detections) som HA-sensorer/events.

