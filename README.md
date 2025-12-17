# Vision service + Coral på Raspberry Pi 5 (Docker) — logg & status

Det här repo:t dokumenterar hur vi fick igång lokal bild-inferens på en **Raspberry Pi 5** med en **USB-webbkamera** och **Google Coral USB (EdgeTPU)**, där inferensen körs i **Docker** och exponeras via en liten **FastAPI**-tjänst.

Målet var att vara realistiska och verifiera allt i terminalen (ingen gissning, inga hittepåsiffror).

---

## Miljö (verifierat)

**Host:**
- Raspberry Pi 5 Model B Rev 1.0
- OS: Debian GNU/Linux 12 (bookworm)
- Kernel: `6.6.51+rpt-rpi-2712` (aarch64)
- RAM: 4.0 GiB
- Kamera: UGREEN Camera (UVC)
- Ljud: USB Audio från kameran

**Enheter:**
- Video-noder: `/dev/video0` och `/dev/video1` (UGREEN Camera)
- Audio capture: `card 0: Camera [UGREEN Camera], device 0: USB Audio`
- Coral USB syns i `lsusb` som:
  - `18d1:9302 Google Inc.` (EdgeTPU aktiv)

---

## Viktiga insikter vi bekräftade

### 1) Kameran fungerar för både bild och ljud
- `v4l2-ctl` visade att kameran stödjer MJPG 1080p upp till 30 fps.
- `arecord` kunde spela in en test-wav (16kHz mono).

### 2) EdgeTPU runtime finns på host
- `libedgetpu.so.1` finns i `/usr/lib/aarch64-linux-gnu/`.
- Vi såg att `load_delegate("libedgetpu.so.1")` fungerade med `sudo` först.
- Vi satte upp udev-regel + grupp så att delegate kunde laddas utan sudo.

### 3) Docker installerades och körs
- `docker run --rm hello-world` fungerade.
- `docker-compose` (v1) finns installerat.

### 4) PyCoral på Debian Bookworm + Python 3.11 i container är struligt
- Försök att installera `python3-pycoral` i en Bookworm/Python 3.11-container failade:
  - `python3-pycoral` kräver `python3 < 3.10` och en specifik `python3-tflite-runtime`.
- Lösningen blev att bygga en container baserad på **Debian bullseye-slim** (Python ~3.9 via apt),
  så att `python3-pycoral` och EdgeTPU runtime kan installeras via apt.

---

## Docker images vi använde

- `coral-test:py39`  
  En testimage där vi kunde köra TFLite + EdgeTPU och testa modeller.

- `vision-service:coral-apt`  
  En FastAPI-tjänst byggd på bullseye-slim + apt-install av `python3-pycoral` och `libedgetpu1-std`.

---

## Problem vi stötte på och hur de löstes

### A) FastAPI kraschade vid file upload
Fel:
- `Form data requires "python-multipart" to be installed.`

Fix:
- Installera `python-multipart` i imagen (pip i containern).

### B) "Empty reply from server" på /infer
Orsak:
- Tjänsten dog (segfault/exit 139) eller gav non-JSON.
- I vår pipeline var den vanligaste orsaken först att servern försökte mata in originalbildens storlek till modellen.

Fix:
- Resiza bilden till modellens input innan `common.set_input(...)`.
  (SSD Mobilenet v2 vill ha 300x300.)

### C) Input shape mismatch i pycoral
Fel:
- `ValueError: could not broadcast input array from shape (...) into shape (300,300,3)`

Fix:
- `w, h = common.input_size(interpreter)` och `img = img.resize((w,h))`

---

## Verifierat fungerande: /health + /infer

### Starta tjänsten
Kör i terminal 1:

```bash
docker run --rm -it \
  --name vision-service \
  -p 5052:5052 \
  --device /dev/bus/usb:/dev/bus/usb \
  -v ~/coral-test-data:/models:ro \
  -e MODEL_PATH=/models/ssd_mobilenet_v2_coco_quant_postprocess_edgetpu.tflite \
  vision-service:coral-apt
