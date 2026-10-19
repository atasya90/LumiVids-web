# Deploy LumiVids Web ke Render (Gratis)

## Yang perlu disiapkan
1. Akun Render (render.com) — daftar gratis, tanpa kartu kredit
2. Akun GitHub (untuk upload kode)
3. RH_API_KEY kamu (API key RunningHub)

## Langkah

### 1. Upload kode ke GitHub
- Buat repo baru di github.com (public/private bebas)
- Upload semua file dari folder `webapp/` ini:
  - `main.py`, `requirements.txt`
  - `backend/` (app.py, db.py)
  - `frontend/` (index.html, app.js)
- JANGAN upload folder `venv/`, `uploads/`, `__pycache__/`

### 2. Buat Web Service di Render
- render.com → New → Web Service → hubungkan repo GitHub
- Settings:
  - **Build Command:** `pip install -r requirements.txt`
  - **Start Command:** `python main.py`
  - **Instance Type:** Free

### 3. Set Environment Variables
Di dashboard Render → Environment:
- `RH_API_KEY` = (API key RunningHub kamu)
- `WEBAPP_ADMIN_USER` = admin
- `WEBAPP_ADMIN_PASS` = (password admin, ganti yang kuat!)

### 4. Deploy & buka
- Klik Deploy. Tunggu ~2 menit.
- Buka URL `https://namamu.onrender.com`
- Login sebagai admin, lalu daftar akun untuk user.

## Catatan
- Free tier Render tidur setelah 15 menit tidak dipakai (buka web ~1 menit untuk bangun).
- Kalau generate lagi jalan saat service tidur, job bisa terputus. Untuk produksi serius, upgrade ke Starter ($7/bln).
- File upload tersimpan sementara di server (hilang tiap redeploy) — hasil generate diambil dari URL RunningHub jadi aman.
