"""Web UI backend — API untuk generate video/gambar via RunningHub + saldo/topup."""
import asyncio
import os
import sys
import time

sys.path.insert(0, "/home/hatch/workspace/telebot")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from runninghub import RunningHubClient, RunningHubError, sanitize_proxy_env

from fastapi import FastAPI, UploadFile, File, Form, Header, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import db

sanitize_proxy_env()

# --- konfigurasi (sama seperti bot Telegram) ---
RH_API_KEY = os.environ.get("RH_API_KEY", "").strip()
ADMIN_USER = os.environ.get("WEBAPP_ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("WEBAPP_ADMIN_PASS", "admin123")

MC_WORKFLOW = "2084137643265724417"
MC_NODE_IMG = ("30", "image")
MC_NODE_VID = ("33", "video")
MC_NODE_TXT = ("3", "text")

SEED_WORKFLOW = "2095487980718022657"
SEED_NODE_IMG = ("1", "image")
SEED_NODE_VID = ("4", "video")
SEED_NODE_PROMPT = ("10", "prompt")

IMG_WORKFLOW = "2076546569814867970"
IMG_NODE_PROMPT = ("5", "prompt")
I2I_WORKFLOW = "2100136607797329922"
I2I_NODE_IMG = ("1", "image")
I2I_NODE_TXT = ("3", "text")
I2I_NODE_SIZE = ("4", "width")

PRICE_MC = 1000
PRICE_SEED = 500
PRICE_IMAGE = 200

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = FastAPI(title="LumiVids Web")

# buat admin default kalau belum ada
if not db.verify_user(ADMIN_USER, ADMIN_PASS):
    db.create_user(ADMIN_USER, ADMIN_PASS, is_admin=True)


def _auth(authorization: str = Header("")):
    token = authorization.replace("Bearer ", "").strip()
    user = db.get_user_by_token(token) if token else None
    if not user:
        raise HTTPException(401, "Login dulu")
    return user


def _rh():
    if not RH_API_KEY:
        raise HTTPException(500, "RH_API_KEY belum diset di server")
    return RunningHubClient(api_key=RH_API_KEY)


@app.post("/api/register")
def register(username: str = Form(...), password: str = Form(...)):
    if len(username) < 3 or len(password) < 4:
        raise HTTPException(400, "Username min 3, password min 4 karakter")
    uid = db.create_user(username, password)
    if not uid:
        raise HTTPException(400, "Username sudah dipakai")
    token = db.create_session(uid)
    return {"token": token, "username": username}


@app.post("/api/login")
def login(username: str = Form(...), password: str = Form(...)):
    user = db.verify_user(username, password)
    if not user:
        raise HTTPException(401, "Username/password salah")
    token = db.create_session(user["id"])
    return {"token": token, "username": username, "is_admin": user["is_admin"]}


@app.get("/api/me")
def me(authorization: str = Header("")):
    user = _auth(authorization)
    return {"username": user["username"], "is_admin": user["is_admin"],
            "balance": db.get_balance(user["id"])}


@app.get("/api/prices")
def prices():
    return {"mc": PRICE_MC, "seed": PRICE_SEED, "image": PRICE_IMAGE}


async def _run_generate(job_id, node_info, wf_id, cost, desc):
    """Background: submit -> poll -> simpan hasil -> potong saldo."""
    job = db.get_job(job_id)
    if not job:
        return
    uid = job["user_id"]
    try:
        client = _rh()
        task_id = await client.submit_workflow(wf_id, node_info)
        results = await client.poll_until_done(task_id, interval_s=10.0, timeout_s=1800.0)
        urls = RunningHubClient.result_urls(results)
        if not urls:
            raise RunningHubError("tidak ada URL hasil")
        db.update_job(job_id, "done", urls[0])
        # potong saldo setelah sukses (admin gratis)
        user = db.get_user_by_token("")  # dummy, cek admin via job
        import sqlite3
        conn = sqlite3.connect(db.DB_PATH)
        is_admin = conn.execute(
            "SELECT is_admin FROM users WHERE id = ?", (uid,)
        ).fetchone()[0]
        conn.close()
        if not is_admin:
            db.deduct_balance(uid, cost, desc)
    except Exception as e:
        db.update_job(job_id, "failed", str(e)[:300])


def _check_funds(user, price):
    if user["is_admin"]:
        return
    if db.get_balance(user["id"]) < price:
        raise HTTPException(402, f"Saldo kurang (butuh {db.format_rp(price)}). Top up dulu.")


@app.post("/api/generate/mc")
async def gen_mc(authorization: str = Header(""),
                 photo: UploadFile = File(...), video: UploadFile = File(...),
                 prompt: str = Form("")):
    user = _auth(authorization)
    _check_funds(user, PRICE_MC)
    if len(prompt) > 5000:
        raise HTTPException(400, "Prompt maks 5000 karakter")
    ts = int(time.time())
    p1 = os.path.join(UPLOAD_DIR, f"{user['id']}_{ts}_photo.jpg")
    p2 = os.path.join(UPLOAD_DIR, f"{user['id']}_{ts}_video.mp4")
    with open(p1, "wb") as f:
        f.write(await photo.read())
    with open(p2, "wb") as f:
        f.write(await video.read())
    client = _rh()
    img_url = await client.upload_file(p1)
    vid_url = await client.upload_file(p2)
    node_info = [
        {"nodeId": MC_NODE_IMG[0], "fieldName": MC_NODE_IMG[1], "fieldValue": img_url},
        {"nodeId": MC_NODE_VID[0], "fieldName": MC_NODE_VID[1], "fieldValue": vid_url},
    ]
    if prompt.strip():
        node_info.append({"nodeId": MC_NODE_TXT[0], "fieldName": MC_NODE_TXT[1],
                          "fieldValue": prompt.strip()})
    job_id = db.create_job(user["id"], "mc", prompt[:200], PRICE_MC)
    asyncio.create_task(_run_generate(job_id, node_info, MC_WORKFLOW, PRICE_MC, "🎬 MC RH"))
    return {"job_id": job_id}


@app.post("/api/generate/seedance")
async def gen_seed(authorization: str = Header(""),
                   ref: UploadFile = File(None), prompt: str = Form(...)):
    user = _auth(authorization)
    _check_funds(user, PRICE_SEED)
    prompt = prompt.strip()
    if len(prompt) < 5 or len(prompt) > 5000:
        raise HTTPException(400, "Prompt harus 5–5000 karakter")
    node_info = [{"nodeId": SEED_NODE_PROMPT[0], "fieldName": SEED_NODE_PROMPT[1],
                  "fieldValue": prompt}]
    if ref:
        ts = int(time.time())
        ext = ".mp4" if (ref.content_type or "").startswith("video") else ".jpg"
        p = os.path.join(UPLOAD_DIR, f"{user['id']}_{ts}_ref{ext}")
        with open(p, "wb") as f:
            f.write(await ref.read())
        client = _rh()
        ref_url = await client.upload_file(p)
        if ext == ".mp4":
            node_info.append({"nodeId": SEED_NODE_VID[0], "fieldName": SEED_NODE_VID[1],
                              "fieldValue": ref_url})
        else:
            node_info.append({"nodeId": SEED_NODE_IMG[0], "fieldName": SEED_NODE_IMG[1],
                              "fieldValue": ref_url})
    job_id = db.create_job(user["id"], "seedance", prompt[:200], PRICE_SEED)
    asyncio.create_task(_run_generate(job_id, node_info, SEED_WORKFLOW, PRICE_SEED, "🎞️ Seedance"))
    return {"job_id": job_id}


@app.post("/api/generate/image")
async def gen_image(authorization: str = Header(""),
                    ref: UploadFile = File(None), prompt: str = Form(...),
                    width: int = Form(720), height: int = Form(1280)):
    user = _auth(authorization)
    _check_funds(user, PRICE_IMAGE)
    prompt = prompt.strip()
    if len(prompt) < 5 or len(prompt) > 5000:
        raise HTTPException(400, "Prompt harus 5–5000 karakter")
    client = _rh()
    if ref:
        ts = int(time.time())
        p = os.path.join(UPLOAD_DIR, f"{user['id']}_{ts}_imgref.jpg")
        with open(p, "wb") as f:
            f.write(await ref.read())
        ref_url = await client.upload_file(p)
        node_info = [
            {"nodeId": I2I_NODE_IMG[0], "fieldName": I2I_NODE_IMG[1], "fieldValue": ref_url},
            {"nodeId": I2I_NODE_TXT[0], "fieldName": I2I_NODE_TXT[1], "fieldValue": prompt},
            {"nodeId": I2I_NODE_SIZE[0], "fieldName": "width", "fieldValue": str(width)},
            {"nodeId": I2I_NODE_SIZE[0], "fieldName": "height", "fieldValue": str(height)},
        ]
        wf = I2I_WORKFLOW
    else:
        node_info = [
            {"nodeId": IMG_NODE_PROMPT[0], "fieldName": IMG_NODE_PROMPT[1], "fieldValue": prompt},
            {"nodeId": IMG_NODE_PROMPT[0], "fieldName": "width", "fieldValue": str(width)},
            {"nodeId": IMG_NODE_PROMPT[0], "fieldName": "height", "fieldValue": str(height)},
        ]
        wf = IMG_WORKFLOW
    job_id = db.create_job(user["id"], "image", prompt[:200], PRICE_IMAGE)
    asyncio.create_task(_run_generate(job_id, node_info, wf, PRICE_IMAGE, "🎨 Image"))
    return {"job_id": job_id}


@app.get("/api/job/{job_id}")
def job_status(job_id: int, authorization: str = Header("")):
    user = _auth(authorization)
    job = db.get_job(job_id)
    if not job or (job["user_id"] != user["id"] and not user["is_admin"]):
        raise HTTPException(404, "Job tidak ditemukan")
    return job


@app.get("/api/jobs")
def my_jobs(authorization: str = Header("")):
    user = _auth(authorization)
    return db.user_jobs(user["id"])


@app.post("/api/topup")
async def topup_request(authorization: str = Header(""),
                        amount: int = Form(...), proof: UploadFile = File(...)):
    user = _auth(authorization)
    if amount not in (5000, 10000, 25000, 50000, 100000):
        raise HTTPException(400, "Nominal tidak valid")
    ts = int(time.time())
    p = os.path.join(UPLOAD_DIR, f"topup_{user['id']}_{ts}.jpg")
    with open(p, "wb") as f:
        f.write(await proof.read())
    req_id = db.create_topup(user["id"], amount, p)
    return {"request_id": req_id, "status": "pending"}


@app.get("/api/admin/topups")
def admin_topups(authorization: str = Header("")):
    user = _auth(authorization)
    if not user["is_admin"]:
        raise HTTPException(403, "Admin only")
    return db.pending_topups()


@app.post("/api/admin/topup/{req_id}/{action}")
def admin_topup_action(req_id: int, action: str, authorization: str = Header("")):
    user = _auth(authorization)
    if not user["is_admin"]:
        raise HTTPException(403, "Admin only")
    req = db.get_topup(req_id)
    if not req or req["status"] != "pending":
        raise HTTPException(400, "Sudah diproses")
    if action == "approve":
        db.set_topup_status(req_id, "approved")
        new_bal = db.add_balance(req["user_id"], req["amount"], "Top up disetujui admin")
        return {"ok": True, "new_balance": new_bal}
    elif action == "reject":
        db.set_topup_status(req_id, "rejected")
        return {"ok": True}
    raise HTTPException(400, "Action tidak valid")


# frontend statis
FRONT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend")
app.mount("/", StaticFiles(directory=FRONT, html=True), name="frontend")
