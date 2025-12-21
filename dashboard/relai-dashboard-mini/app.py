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
