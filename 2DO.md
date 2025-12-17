2-DO LIST (komplett)
A. Stabilitet & reproducibilitet

 Lägg in server.py i ett rent skick (inga trasiga heredocs / klippfel).

 Lägg in en minimal Dockerfile som alltid bygger samma image (vision-service:coral-apt).

 Dokumentera exakt vilka env vars som stöds: MODEL_PATH, SCORE_TH, TOPK, ev. LABELS_PATH.

 Lägg till tydlig logging i servern:

start-logg med modellnamn

logga inputstorlek och inference-tid

fånga exceptions och returnera JSON-fel (inte “empty reply”)

B. Modellhantering

 Skapa endpoint /models som listar modeller i /models.

 Skapa endpoint /reload?model=... (eller kräver restart) för att byta modell kontrollerat.

 Benchmark-script som kör 20–50 inference och skriver median/p95 för invoke_ms.

C. Video-pipeline (från webbkamera)

 Bestäm ingest-strategi:

Frame-by-frame via OpenCV (CPU) eller GStreamer

MJPG decode-kostnad vs YUYV

 Sätt en rimlig profil: t.ex. 640x480 @ 10–15 fps som start.

 Implementera “sample rate” (inferera t.ex. var 5:e frame).

 Lägg in en ringbuffer/queue så att inferens inte backar upp video-capture.

D. Audio-pipeline (lokalt)

 Skapa en separat audio_service (om ni vill hålla microservices)

 Bestäm vad ni analyserar:

VAD (enklare event-detection: “tyst”, “tal”, “högt ljud”) vs full STT

 Sätt upp en stabil capture med ALSA (arecord) eller PyAudio.

 Implementera chunking (t.ex. 1–2 sek per chunk) och enkel feature extraction (RMS/energi).

E. Docker/Compose

 Skapa docker-compose.yml för:

vision-service (5052)

ev. dashboard (senare)

volumes + devices

 Lås image-taggar, och dokumentera hur man rebuildar.

F. Kvalitet & säkerhet

 Begränsa filstorlek på upload (för att undvika minnesproblem)

 Inputvalidering (bildformat, storlek)

 Timeout på inferens (så API inte låser sig)

 Notera att TPU access kräver rätt device-mapping; dokumentera det tydligt.

G. “Definition of done” för MVP

 /health svarar alltid

 /infer returnerar alltid JSON (ok eller error)

 Minst 1 modell fungerar stabilt (SSD Mobilenet v2 postprocess)

 Dokumenterad start/stop + test via curl

 Enkel benchmark så ni kan välja modell på data
