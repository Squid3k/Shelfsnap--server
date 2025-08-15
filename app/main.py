
from fastapi import FastAPI, UploadFile, File, Form, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import uuid, os, shutil, subprocess, glob

ROOT = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(ROOT, "..", "uploads")
TMP_DIR = os.path.join(ROOT, "..", "tmp")
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(TMP_DIR, exist_ok=True)

app = FastAPI(title="ShelfSnap API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class StartScanResponse(BaseModel):
    scan_id: str

class InventoryItem(BaseModel):
    name: str
    confidence: float
    include: Optional[bool] = True

class ScanResult(BaseModel):
    scan_id: str
    inventory: List[InventoryItem]
    recipes: list
    gaps: list
    frames_extracted: int

def ffmpeg_available() -> bool:
    try:
        subprocess.run(["ffmpeg", "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        return True
    except FileNotFoundError:
        return False

@app.post("/v1/scan/start", response_model=StartScanResponse)
def start_scan():
    scan_id = str(uuid.uuid4())
    return StartScanResponse(scan_id=scan_id)

@app.post("/v1/scan/upload")
async def upload_frames(scan_id: str = Form(...), files: List[UploadFile] = File(default=[])):
    if not files:
        raise HTTPException(status_code=400, detail="No file provided")
    video_file = files[0]
    scan_dir = os.path.join(UPLOAD_DIR, scan_id)
    os.makedirs(scan_dir, exist_ok=True)
    save_path = os.path.join(scan_dir, "scan.mp4")
    with open(save_path, "wb") as f:
        content = await video_file.read()
        f.write(content)
    return {"ok": True, "frames_received": 1}

@app.post("/v1/scan/complete", response_model=ScanResult)
async def complete_scan(scan_id: str = Form(...), background_tasks: BackgroundTasks = None):
    scan_dir = os.path.join(UPLOAD_DIR, scan_id)
    video_path = os.path.join(scan_dir, "scan.mp4")
    if not os.path.exists(video_path):
        raise HTTPException(status_code=404, detail="Scan not found or video missing")

    frames_dir = os.path.join(TMP_DIR, scan_id)
    if os.path.exists(frames_dir):
        shutil.rmtree(frames_dir)
    os.makedirs(frames_dir, exist_ok=True)

    if not ffmpeg_available():
        frames_count = 0
    else:
        cmd = ["ffmpeg", "-i", video_path, "-vf", "fps=4", os.path.join(frames_dir, "frame_%03d.jpg"), "-hide_banner", "-loglevel", "error"]
        try:
            subprocess.run(cmd, check=True)
        except subprocess.CalledProcessError:
            frames_count = 0
        frames = glob.glob(os.path.join(frames_dir, "frame_*.jpg"))
        frames_count = len(frames)

    inventory = [
        {"name": "milk 2%", "confidence": 0.92},
        {"name": "eggs", "confidence": 0.88},
        {"name": "tortillas", "confidence": 0.83},
    ]

    return ScanResult(scan_id=scan_id, inventory=inventory, recipes=[], gaps=[], frames_extracted=frames_count)

@app.get("/healthz")
def health():
    return {"status": "ok", "ffmpeg": ffmpeg_available()}
@app.get("/")
def home():
    return {"message": "ShelfSnap API is live!"}