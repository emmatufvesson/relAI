# relAI på Raspberry Pi 5 — nuläge (körbart) + statuslogg

Det här repot dokumenterar vårt faktiska “nu-läge” på Raspberry Pi 5 och hur man får igång ett minimalt, verifierbart system:

- **Home Assistant** i Docker (framtida dashboard/automationer/Assist i mobilen)
- **Vision inference** (Google Coral / EdgeTPU) i Docker (`vision-service`)
- **Vision loop → Home Assistant-sensorer** (snapshot → /infer → postar sensorer i HA)
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
🟡 `relai-vision-loop.service` finns och körs via systemd, men **kameradrivrutinen kan kräva format-tvingning** (se “Felsökning: V4L2 Invalid argument”)


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

## 1) Home Assistant (Docker) — igång

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
