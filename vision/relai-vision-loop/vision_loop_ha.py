#!/usr/bin/env python3
import os, time, json, tempfile, subprocess
from collections import Counter
import requests

def load_labels(path: str) -> dict[int, str]:
    labels = {}
    if not path or not os.path.exists(path):
        return labels
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split(maxsplit=1)
            if len(parts) == 2 and parts[0].isdigit():
                labels[int(parts[0])] = parts[1].strip()
            else:
                labels[len(labels)] = line
    return labels

def run_ffmpeg(cmd: list[str]) -> None:
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        msg = (e.stderr or e.stdout or str(e)).strip()
        raise RuntimeError(msg)

def snap_jpeg(video_devs: list[str], out_path: str, width: int, height: int, fps: int, input_formats: list[str]) -> tuple[str, str]:
    """
    Returns (used_dev, used_format). input_formats may include "" meaning 'no -input_format'.
    """
    last_err = ""
    for dev in video_devs:
        for fmt in input_formats:
            cmd = [
                "ffmpeg", "-hide_banner", "-loglevel", "error",
                "-f", "v4l2",
                "-framerate", str(fps),
            ]
            if fmt:
                cmd += ["-input_format", fmt]
            cmd += [
                "-video_size", f"{width}x{height}",
                "-i", dev,
                "-frames:v", "1",
                "-q:v", "4",
                "-y",
                out_path
            ]
            try:
                run_ffmpeg(cmd)
                return dev, (fmt or "auto")
            except Exception as e:
                last_err = str(e)
                # Busy? prova nästa device/format
                if "Device or resource busy" in last_err:
                    continue
                # V4L2 EINVAL? prova nästa format
                if "Invalid argument" in last_err or "VIDIOC_REQBUFS" in last_err:
                    continue
                # annat fel -> prova ändå nästa, men spara felet
                continue
    raise RuntimeError(f"Could not grab frame. Last error: {last_err}")

def infer(vision_url: str, jpg_path: str) -> dict:
    with open(jpg_path, "rb") as f:
        r = requests.post(f"{vision_url.rstrip('/')}/infer", files={"file": f}, timeout=10)
    r.raise_for_status()
    return r.json()

def ha_set_state(ha_url: str, token: str, entity_id: str, state, attributes: dict | None = None) -> None:
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {"state": str(state), "attributes": (attributes or {})}
    r = requests.post(f"{ha_url.rstrip('/')}/api/states/{entity_id}", headers=headers, data=json.dumps(payload), timeout=10)
    r.raise_for_status()

def main():
    ha_url      = os.getenv("HA_URL", "http://127.0.0.1:8123")
    ha_token    = os.getenv("HA_TOKEN", "")
    vision_url  = os.getenv("VISION_URL", "http://127.0.0.1:5052")

    video_devs  = os.getenv("VIDEO_DEVS", os.getenv("VIDEO_DEV", "/dev/video0"))
    video_devs  = [v.strip() for v in video_devs.split(",") if v.strip()]

    labels_path = os.getenv("LABELS_PATH", "")
    interval_s  = float(os.getenv("INTERVAL_S", "2.0"))
    width       = int(os.getenv("SNAP_W", "640"))
    height      = int(os.getenv("SNAP_H", "480"))
    fps         = int(os.getenv("SNAP_FPS", "10"))
    min_score   = float(os.getenv("MIN_SCORE", "0.40"))

    # Om du sätter SNAP_INPUT_FORMAT=mjpeg så kör vi den först,
    # annars testar vi auto -> mjpeg som fallback.
    fmt_env = os.getenv("SNAP_INPUT_FORMAT", "").strip()
    if fmt_env:
        input_formats = [fmt_env, ""]  # tvingad först, sen auto
    else:
        input_formats = ["", "mjpeg"]  # auto först, sen mjpeg

    if not ha_token:
        raise RuntimeError("HA_TOKEN is missing")

    labels = load_labels(labels_path)

    def label_for(i: int) -> str:
        return labels.get(i, f"id_{i}")

    print("Vision loop starting")
    print("HA_URL       =", ha_url)
    print("VISION_URL   =", vision_url)
    print("VIDEO_DEVS   =", ",".join(video_devs))
    print("LABELS_PATH  =", labels_path or "(none)")
    print("INTERVAL_S   =", interval_s)
    print("SNAP_FPS     =", fps)
    print("TRY_FORMATS  =", ",".join([f or "auto" for f in input_formats]))
    print("Ctrl+C to stop\n")

    while True:
        t0 = time.time()
        jpg_path = None
        try:
            fd, jpg_path = tempfile.mkstemp(suffix=".jpg")
            os.close(fd)

            used_dev, used_fmt = snap_jpeg(video_devs, jpg_path, width=width, height=height, fps=fps, input_formats=input_formats)
            data = infer(vision_url, jpg_path)

            dets = data.get("detections", []) or []
            dets_f = [d for d in dets if float(d.get("score", 0.0)) >= min_score]

            ids = [int(d.get("id", -1)) for d in dets_f if "id" in d]
            counts = Counter(ids)

            top_label = "none"
            top_score = 0.0
            if dets_f:
                best = max(dets_f, key=lambda d: float(d.get("score", 0.0)))
                top_label = label_for(int(best.get("id", -1)))
                top_score = float(best.get("score", 0.0))

            person_count = 0
            if labels:
                for i, c in counts.items():
                    if label_for(i).lower() == "person":
                        person_count += c
            else:
                person_count = counts.get(0, 0)

            attrs_common = {
                "model": data.get("model"),
                "pre_ms": data.get("pre_ms"),
                "invoke_ms": data.get("invoke_ms"),
                "total_ms": data.get("total_ms"),
                "min_score": min_score,
                "video_dev_used": used_dev,
                "snap_format_used": used_fmt,
                "counts": {label_for(i): c for i, c in counts.items()},
            }

            attrs_dets = []
            for d in dets_f[:10]:
                i = int(d.get("id", -1))
                attrs_dets.append({"label": label_for(i), "score": float(d.get("score", 0.0)), "bbox": d.get("bbox", {})})
            attrs_common["top_detections"] = attrs_dets

            ha_set_state(ha_url, ha_token, "sensor.vision_top_label", top_label, attrs_common)
            ha_set_state(ha_url, ha_token, "sensor.vision_top_score", round(top_score, 3), attrs_common)
            ha_set_state(ha_url, ha_token, "sensor.vision_person_count", person_count, attrs_common)
            ha_set_state(ha_url, ha_token, "sensor.vision_total_ms", round(float(data.get("total_ms", 0.0)), 2), attrs_common)

        except Exception as e:
            print("vision loop error:", e)
            time.sleep(1.0)
        finally:
            if jpg_path and os.path.exists(jpg_path):
                try: os.remove(jpg_path)
                except: pass

        dt = time.time() - t0
        time.sleep(max(0.0, interval_s - dt))

if __name__ == "__main__":
    main()
