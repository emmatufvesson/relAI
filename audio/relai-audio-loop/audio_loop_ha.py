#!/usr/bin/env python3
import os, time, math, wave, audioop, tempfile, subprocess
from dataclasses import dataclass
import requests

@dataclass
class Config:
    alsa_device: str = "plughw:0,0"
    sample_rate: int = 48000
    channels: int = 2
    chunk_seconds: float = 1.0

    # Home Assistant
    ha_url: str = "http://127.0.0.1:8123"
    ha_token: str = ""
    entity_a: str = "sensor.voice_a"
    entity_b: str = "sensor.voice_b"

    timeout_seconds: float = 2.0
    dbfs_floor: float = -55.0
    dbfs_ceil: float = -15.0
    ema_alpha: float = 0.25
    baseline_alpha: float = 0.02
    print_every: int = 1

def run_ffmpeg_capture(cfg: Config, out_wav: str) -> None:
    cmd = [
        "ffmpeg","-hide_banner","-loglevel","error",
        "-f","alsa","-i",cfg.alsa_device,
        "-t",str(cfg.chunk_seconds),
        "-ac",str(cfg.channels),"-ar",str(cfg.sample_rate),
        "-acodec","pcm_s16le","-y",out_wav
    ]
    subprocess.run(cmd, check=True)

def wav_dbfs(path: str) -> float:
    with wave.open(path, "rb") as wf:
        sampwidth = wf.getsampwidth()
        frames = wf.readframes(wf.getnframes())
    rms = audioop.rms(frames, sampwidth)
    if rms <= 0:
        return -120.0
    full_scale = float(2 ** (8 * sampwidth - 1))
    return 20.0 * math.log10(rms / full_scale)

def clamp01(x: float) -> float:
    return 0.0 if x < 0.0 else (1.0 if x > 1.0 else x)

def map_dbfs_to_score(db: float, floor: float, ceil: float) -> float:
    return clamp01((db - floor) / (ceil - floor)) if ceil > floor else 0.0

def ha_post_state(cfg: Config, entity_id: str, state: float, attrs: dict) -> None:
    if not cfg.ha_token:
        raise RuntimeError("HA_TOKEN is missing")
    url = f"{cfg.ha_url.rstrip('/')}/api/states/{entity_id}"
    headers = {
        "Authorization": f"Bearer {cfg.ha_token}",
        "Content-Type": "application/json",
    }
    payload = {"state": f"{state:.3f}", "attributes": attrs}
    r = requests.post(url, headers=headers, json=payload, timeout=cfg.timeout_seconds)
    r.raise_for_status()

def main():
    cfg = Config(
        alsa_device=os.getenv("ALSA_DEVICE", "plughw:0,0"),
        ha_url=os.getenv("HA_URL", "http://127.0.0.1:8123"),
        ha_token=os.getenv("HA_TOKEN", ""),
        entity_a=os.getenv("HA_ENTITY_A", "sensor.voice_a"),
        entity_b=os.getenv("HA_ENTITY_B", "sensor.voice_b"),
    )

    print("Audio -> Home Assistant starting")
    print("ALSA_DEVICE =", cfg.alsa_device)
    print("HA_URL      =", cfg.ha_url)
    print("ENTITY_A    =", cfg.entity_a)
    print("ENTITY_B    =", cfg.entity_b)
    print("Ctrl+C to stop\n")

    ema = None
    base = None
    i = 0

    while True:
        i += 1
        with tempfile.TemporaryDirectory() as td:
            wav_path = os.path.join(td, "chunk.wav")

            try:
                run_ffmpeg_capture(cfg, wav_path)
            except subprocess.CalledProcessError as e:
                print(f"[{i}] ffmpeg capture failed: {e} (retrying)")
                time.sleep(0.5)
                continue

            db = wav_dbfs(wav_path)
            score = map_dbfs_to_score(db, cfg.dbfs_floor, cfg.dbfs_ceil)

            ema = score if ema is None else (cfg.ema_alpha * score + (1 - cfg.ema_alpha) * ema)
            base = ema if base is None else (cfg.baseline_alpha * ema + (1 - cfg.baseline_alpha) * base)

            attrs_a = {"unit_of_measurement":"score","friendly_name":"Voice A (EMA)","dbfs":round(db,1)}
            attrs_b = {"unit_of_measurement":"score","friendly_name":"Voice B (baseline)","dbfs":round(db,1)}

            try:
                ha_post_state(cfg, cfg.entity_a, ema, attrs_a)
                ha_post_state(cfg, cfg.entity_b, base, attrs_b)
            except Exception as e:
                print(f"[{i}] HA post failed: {e}")

            if cfg.print_every and (i % cfg.print_every == 0):
                print(f"[{i}] dBFS={db:6.1f} score={score:.3f} A={ema:.3f} B={base:.3f}")

if __name__ == "__main__":
    main()
