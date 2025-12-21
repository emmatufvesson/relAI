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
    dashboard_set_url: str = "http://127.0.0.1:8000/set"
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

def send_to_dashboard(cfg: Config, a: float, b: float) -> None:
    r = requests.get(cfg.dashboard_set_url, params={"A": f"{a:.3f}", "B": f"{b:.3f}"}, timeout=cfg.timeout_seconds)
    r.raise_for_status()

def main():
    cfg = Config(
        alsa_device=os.getenv("ALSA_DEVICE", "plughw:0,0"),
        dashboard_set_url=os.getenv("DASHBOARD_SET_URL", "http://127.0.0.1:8000/set"),
    )

    print("Audio loop starting")
    print("ALSA_DEVICE      =", cfg.alsa_device)
    print("DASHBOARD_SET_URL=", cfg.dashboard_set_url)
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

            try:
                send_to_dashboard(cfg, a=ema, b=base)
            except Exception as e:
                print(f"[{i}] dashboard send failed: {e}")

            if cfg.print_every and (i % cfg.print_every == 0):
                print(f"[{i}] dBFS={db:6.1f} score={score:.3f} A={ema:.3f} B={base:.3f}")

if __name__ == "__main__":
    main()
