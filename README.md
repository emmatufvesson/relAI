# relAI på Raspberry Pi 5 — nuläge (körbart) + statuslogg (video+audio+HA)

Det här repot dokumenterar vårt faktiska “nu-läge” på Raspberry Pi 5 och hur man får igång ett minimalt, verifierbart system:

- **Home Assistant** i Docker (framtida dashboard/automationer/Assist i mobilen)
- **Vision inference** (Google Coral / EdgeTPU) i Docker (`vision-service`)
- **Vision loop → Home Assistant-sensorer** (snapshot → `/infer` → postar sensorer i HA)
- **Audio loop** (webbkamera-mic → enkel realtids-score → HTTP/HA)
- En **minimal FastAPI “dashboard”** användes som testmottagare för att bevisa att audio kan skicka live

Målet är att bygga upp systemet **stegvis**, med tydliga kommandon och så lite gissning som möjligt.

---

## Status (senast verifierat)

✅ `vision-service` svarar på `http://127.0.0.1:5052/health`  
✅ Kamera-snapshot via `ffmpeg` fungerar (`/dev/video0 → /tmp/frame.jpg`)  
✅ `infer`-endpoint fungerar (`/infer` tar emot bild och svarar JSON)  
✅ `relai-audio-loop.service` kör (systemd)  
✅ `relai-dashboard-mini.service` kör (systemd)  
🟡 `relai-vision-loop.service` finns och körs via systemd, men kameradrivrutinen kan kräva format-tvingning (se “Felsökning: V4L2 Invalid argument”)

### Senaste snabbtest (2025-12-30)
- `curl http://127.0.0.1:5052/health` → `{"ok":true,"model":"ssdlite_mobiledet_coco_qat_postprocess_edgetpu.tflite"}`
- `ffmpeg ... /dev/video0 ... /tmp/frame.jpg` → skapade fil (~55K)
- `curl -F file=@/tmp/frame.jpg http://127.0.0.1:5052/infer` → fungerade (men kunde ge `detections: []` beroende på bildinnehåll)

---

## Miljö (host)

- **Raspberry Pi 5 Model B**
- **OS**: Debian GNU/Linux 12 (bookworm), **aarch64**
- **Kamera**: UGREEN UVC + USB Audio (mic)
- **Coral**: EdgeTPU USB (syns som `18d1:9302` i `lsusb`)

### Audio-enhet (UGREEN Camera)
`arecord -l` (exempel):
- `card 0: Camera [UGREEN Camera], device 0: USB Audio [USB Audio]`

`arecord --dump-hw-params` visar typiskt:
- FORMAT: `S16_LE`
- CHANNELS: `2`
- RATE: `8000–48000`

---

## Repo & mappar (lokalt på Pi)

Exempel (kan variera):
- `~/vision_service_bookworm/` – vision/Coral-relaterat repo (detta repo)
- `~/coral-test-data/` – modeller/testdata (på hosten)
- `~/homeassistant/config/` – Home Assistant config-volym (på hosten)

I repot:
- `vision/relai-vision-loop/` – **Vision loop → HA** (Python)

---

## 1) Home Assistant (Docker)

### Starta container
```bash
mkdir -p ~/homeassistant/config

docker run -d \
  --name homeassistant \
  --restart unless-stopped \
  --network host \
  -e TZ="Europe/Stockholm" \
  -v ~/homeassistant/config:/config \
  ghcr.io/home-assistant/home-assistant:stable
```

### Öppna UI
```bash
hostname -I
```
Öppna:
- `http://<PI-IP>:8123`

### Bluetooth (valfritt)
Om du behöver Bluetooth:
- installera `bluez` på host
- skapa om containern med cap-add + dbus mount

```bash
sudo apt update
sudo apt install -y bluez

docker stop homeassistant
docker rm homeassistant

docker run -d \
  --name homeassistant \
  --restart unless-stopped \
  --network host \
  --cap-add=NET_ADMIN \
  --cap-add=NET_RAW \
  -v /run/dbus:/run/dbus:ro \
  -e TZ="Europe/Stockholm" \
  -v ~/homeassistant/config:/config \
  ghcr.io/home-assistant/home-assistant:stable
```

---

## 2) Vision-service (Docker + Coral)

> PyCoral på Bookworm + Python 3.11 är ofta struligt. Vi kör därför inference i container där EdgeTPU-runtime + pycoral kommer via apt (bullseye/py39-baserat upplägg).

### Health-check
```bash
curl -sS http://127.0.0.1:5052/health ; echo
```

### Snapshot → infer (snabb verifiering)
```bash
rm -f /tmp/frame.jpg
ffmpeg -hide_banner -loglevel error -f v4l2 -video_size 640x480 -i /dev/video0 -frames:v 1 -q:v 4 -y /tmp/frame.jpg
ls -lh /tmp/frame.jpg

curl -sS -F "file=@/tmp/frame.jpg" http://127.0.0.1:5052/infer | head -c 400; echo
```

**Obs:** `detections: []` betyder bara att modellen inte ser något den klassar över tröskeln i just den bilden.

---

## 3) Vision loop → Home Assistant (sensorer)

Vision-loopen tar snapshots, skickar dem till `vision-service` och postar resultat som sensorer i Home Assistant.

### Sensornamn i Home Assistant
- `sensor.vision_top_label`
- `sensor.vision_top_score`
- `sensor.vision_person_count`
- `sensor.vision_total_ms`

### Labels-fil (COCO)
För att få “person” istället för bara id, använd en labels-fil (ex):
- `/home/tuff/coral-test-data/coco_labels.txt`

Hitta den:
```bash
find ~/coral-test-data -maxdepth 2 -type f \( -iname "*label*txt" -o -iname "*coco*txt" \)
```

### Manuell körning (för test)
```bash
cd ~/vision_service_bookworm/vision/relai-vision-loop
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# token hämtas säkert från secrets:
set -a
source /home/tuff/.relai_secrets
set +a

HA_URL="http://127.0.0.1:8123" \
VISION_URL="http://127.0.0.1:5052" \
VIDEO_DEV="/dev/video0" \
LABELS_PATH="/home/tuff/coral-test-data/coco_labels.txt" \
INTERVAL_S="2.0" \
python ./vision_loop_ha.py
```

### Systemd (kör alltid)
Secrets (lokalt, aldrig i git):
- `/home/tuff/.relai_secrets` innehåller:
  - `HA_TOKEN=...`

Loggar:
```bash
journalctl -u relai-vision-loop.service -f
```

---

## 4) Audio loop (webbkamera-mic → score → HTTP)

> Audio-loopen analyserar mikrofonen och skickar A/B-score till en endpoint. Ursprungligen testades detta mot mini-dashboard (`/set`).

Installera förutsättningar:
```bash
sudo apt update
sudo apt install -y ffmpeg python3-venv
```

Verifiera ljud-enhet:
```bash
arecord -l
arecord -D hw:0,0 --dump-hw-params -d 1 /dev/null
```

Testa inspelning:
```bash
arecord -D hw:0,0 -f S16_LE -c 2 -r 48000 -d 3 test.wav
ls -lh test.wav
```

Kör audio-loop (exempel):
```bash
cd ~/relai-audio-loop
python3 -m venv .venv
source .venv/bin/activate
pip install requests

ALSA_DEVICE="plughw:0,0" \
DASHBOARD_SET_URL="http://127.0.0.1:8000/set" \
python ./audio_loop_webcam.py
```

**Obs:** `aplay` kan faila om Pi saknar playback-enhet – det påverkar inte inspelning/analys.

---

## 5) Mini-dashboard (FastAPI) — testmottagare för /set

Detta är inte Home Assistant-dashboard, utan en minimal mottagare för att bevisa “audio kan skicka live”.

Skapa och starta:
```bash
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
```

Test:
```bash
curl "http://127.0.0.1:8000/health"
curl "http://127.0.0.1:8000/set?A=0.5&B=0.2"
```

---

## Felsökning

### Kamera upptagen (Device or resource busy)
Någon annan process håller kameran:
```bash
sudo fuser -v /dev/video0 /dev/video1
sudo lsof /dev/video0
sudo lsof /dev/video1
```

### V4L2 “Invalid argument” (VIDIOC_REQBUFS)
Vissa UVC-kameror behöver att man tvingar format (oftast `mjpeg`) och/eller använder rätt video-node.
- Testa `/dev/video1`
- Testa `mjpeg` i ffmpeg:

```bash
ffmpeg -hide_banner -loglevel error \
  -f v4l2 -input_format mjpeg -video_size 640x480 -i /dev/video0 \
  -frames:v 1 -q:v 4 -y /tmp/frame.jpg
```

Om detta funkar men systemd-loop failar:
- sätt `SNAP_INPUT_FORMAT=mjpeg` i `relai-vision-loop.service`
- och/eller `VIDEO_DEVS=/dev/video0,/dev/video1`

---

## Säkerhet / “Push-säkert”
Filer som **aldrig** ska in i git:
- `.venv/`
- `.relai_secrets`

Lägg i `.gitignore`:
```gitignore
.venv/
.relai_secrets
__pycache__/
*.pyc
```

---

## 2DO (nästa steg)

### Stabilitet & drift
- [ ] Säkerställ att `relai-vision-loop.service` är stabil (mjpeg + ev `/dev/video1`)
- [ ] Lägg in “single instance”-lås (flock) i vision-loop service om inte redan gjort
- [ ] Lägg in bättre loggning/metrics (t.ex. “snap_format_used”, “video_dev_used” i HA-attribut)

### Home Assistant (nytta)
- [ ] Byt audio-output från mini-dashboard → **HA-sensorer** (REST API states eller MQTT)
- [ ] Skapa en “Live”-dashboard i HA med:
  - `vision_top_label`, `top_score`, `person_count`, `total_ms`
  - audio-score (A/B) som graf eller gauge
- [ ] Skapa automation: “person i bild” → notifiering / logg / assist

### Produktifiera repot
- [ ] Dokumentera exakt hur `vision-service` byggs/körs (Dockerfile/compose)
- [ ] Lägg in “Quickstart”-script (makefile eller `./scripts/`)
- [ ] Lägg in “known-good” versions (Debian, container-tag, modellfilnamn, osv)

### Nästa delprojekt (valfritt)
- [ ] Speaker ID (separat modell + enrollment) → `sensor.speaker` + `sensor.speaker_confidence`
- [ ] Privacy & samtycke: tydlig policy/README-sektion om vad som lagras, vad som inte lagras

---

## Snabbkommandon (bra att ha)

```bash
# vision-service health
curl -sS http://127.0.0.1:5052/health ; echo

# snapshot
ffmpeg -hide_banner -loglevel error -f v4l2 -video_size 640x480 -i /dev/video0 -frames:v 1 -q:v 4 -y /tmp/frame.jpg

# infer
curl -sS -F "file=@/tmp/frame.jpg" http://127.0.0.1:5052/infer | head -c 400; echo

# vision-loop logg
journalctl -u relai-vision-loop.service -f

# audio-loop logg
journalctl -u relai-audio-loop.service -f
```
