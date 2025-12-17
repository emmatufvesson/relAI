from fastapi import FastAPI, File, UploadFile
from fastapi.responses import JSONResponse
from PIL import Image
import io, os, time

from pycoral.utils.edgetpu import make_interpreter
from pycoral.adapters import common, detect

MODEL_PATH = os.getenv("MODEL_PATH", "/models/ssd_mobilenet_v2_coco_quant_postprocess_edgetpu.tflite")
SCORE_TH   = float(os.getenv("SCORE_TH", "0.4"))
TOPK       = int(os.getenv("TOPK", "10"))

app = FastAPI()
_interpreter = None

def get_interpreter():
    global _interpreter
    if _interpreter is None:
        _interpreter = make_interpreter(MODEL_PATH)
        _interpreter.allocate_tensors()
    return _interpreter

@app.get("/health")
def health():
    return {"ok": True, "model": os.path.basename(MODEL_PATH)}

@app.post("/infer")
async def infer(file: UploadFile = File(...)):
    it = get_interpreter()

    t0 = time.time()
    data = await file.read()
    img = Image.open(io.BytesIO(data)).convert("RGB")

    w,h = common.input_size(it)
    img = img.resize((w,h))
    common.set_input(it, img)
    t1 = time.time()
    it.invoke()
    t2 = time.time()

    objs = detect.get_objects(it, SCORE_TH)[:TOPK]
    dets = []
    for o in objs:
        dets.append({
            "id": int(o.id),
            "score": float(o.score),
            "bbox": {"xmin": int(o.bbox.xmin), "ymin": int(o.bbox.ymin),
                     "xmax": int(o.bbox.xmax), "ymax": int(o.bbox.ymax)}
        })

    return JSONResponse({
        "ok": True,
        "model": os.path.basename(MODEL_PATH),
        "pre_ms": round((t1 - t0) * 1000, 2),
        "invoke_ms": round((t2 - t1) * 1000, 2),
        "total_ms": round((t2 - t0) * 1000, 2),
        "detections": dets,
    })
