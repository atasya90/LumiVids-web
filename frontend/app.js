const API = "";
let token = localStorage.getItem("lv_token") || "";
let prices = {mc:1000, seed:500, image:200};
let selPkg = 0;
const PKGS = [5000,10000,25000,50000,100000];

const $ = id => document.getElementById(id);
const rp = n => "Rp" + n.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ".");

async function api(path, opts={}) {
  opts.headers = opts.headers || {};
  if (token) opts.headers["Authorization"] = "Bearer " + token;
  const r = await fetch(API + path, opts);
  const d = await r.json().catch(()=>({}));
  if (!r.ok) throw new Error(d.detail || ("Error " + r.status));
  return d;
}
function msg(el, text, cls) {
  const e = $(el); e.className = "status " + cls; e.textContent = text; e.classList.remove("hidden");
}
function hide(el){ $(el).classList.add("hidden"); }

async function refreshMe() {
  try {
    const me = await api("/api/me");
    $("saldoBadge").textContent = rp(me.balance);
    $("saldoBadge").classList.remove("hidden");
    $("saldoBig").textContent = rp(me.balance);
    if (me.is_admin) { $("tabAdmin").classList.remove("hidden"); loadTopups(); }
    return me;
  } catch(e) { logout(); }
}
function logout(){ token=""; localStorage.removeItem("lv_token");
  $("appView").classList.add("hidden"); $("authView").classList.remove("hidden");
  $("saldoBadge").classList.add("hidden"); $("btnLogout").classList.add("hidden"); }

$("btnLogin").onclick = async () => {
  try {
    const fd = new FormData();
    fd.append("username", $("username").value.trim());
    fd.append("password", $("password").value);
    const d = await api("/api/login", {method:"POST", body:fd});
    token = d.token; localStorage.setItem("lv_token", token);
    enter();
  } catch(e){ msg("authMsg", e.message, "err"); }
};
$("btnRegister").onclick = async () => {
  try {
    const fd = new FormData();
    fd.append("username", $("username").value.trim());
    fd.append("password", $("password").value);
    const d = await api("/api/register", {method:"POST", body:fd});
    token = d.token; localStorage.setItem("lv_token", token);
    enter();
  } catch(e){ msg("authMsg", e.message, "err"); }
};
$("btnLogout").onclick = logout;

async function enter(){
  $("authView").classList.add("hidden"); $("appView").classList.remove("hidden");
  $("btnLogout").classList.remove("hidden");
  try { prices = await api("/api/prices"); } catch(e){}
  $("priceMc").textContent = rp(prices.mc);
  $("priceSeed").textContent = rp(prices.seed);
  $("priceImg").textContent = rp(prices.image);
  $("pkgList").innerHTML = PKGS.map(p=>`<button data-p="${p}">${rp(p)}</button>`).join("");
  document.querySelectorAll("#pkgList button").forEach(b=>b.onclick=()=>{
    document.querySelectorAll("#pkgList button").forEach(x=>x.classList.remove("sel"));
    b.classList.add("sel"); selPkg = +b.dataset.p;
  });
  await refreshMe(); loadJobs();
}

document.querySelectorAll("nav button[data-tab]").forEach(b=>b.onclick=()=>{
  document.querySelectorAll("nav button").forEach(x=>x.classList.remove("active"));
  b.classList.add("active");
  ["mc","seed","img","saldo","riwayat","admin"].forEach(t=>$("tab-"+t).classList.toggle("hidden", t!==b.dataset.tab));
  if (b.dataset.tab==="riwayat") loadJobs();
  if (b.dataset.tab==="saldo") refreshMe();
});

async function pollJob(jobId, statusEl, isVideo) {
  for (let i=0;i<120;i++) {
    await new Promise(r=>setTimeout(r,10000));
    try {
      const j = await api("/api/job/"+jobId);
      if (j.status==="done") {
        msg(statusEl, "✅ Jadi!", "ok");
        const media = isVideo ? `<video src="${j.result_url}" controls></video>`
                              : `<img src="${j.result_url}">`;
        $(statusEl).insertAdjacentHTML("afterend", `<div class="job">${media}<br><a href="${j.result_url}" target="_blank">🔗 Download</a></div>`);
        refreshMe(); loadJobs(); return;
      }
      if (j.status==="failed") { msg(statusEl, "❌ Gagal: "+(j.result_url||""), "err"); refreshMe(); return; }
      msg(statusEl, "⏳ Diproses... ("+j.status+")", "info");
    } catch(e){}
  }
  msg(statusEl, "⏳ Masih diproses, cek di Riwayat.", "info");
}

$("btnMc").onclick = async () => {
  const ph = $("mcPhoto").files[0], vd = $("mcVideo").files[0];
  if (!ph || !vd) { msg("mcStatus","Pilih foto dan video dulu.","err"); return; }
  if (vd.size > 20*1024*1024) { msg("mcStatus","Video maks 20 MB.","err"); return; }
  const fd = new FormData();
  fd.append("photo", ph); fd.append("video", vd);
  fd.append("prompt", $("mcPrompt").value);
  $("btnMc").disabled = true; msg("mcStatus","⏳ Upload...","info");
  try {
    const d = await api("/api/generate/mc", {method:"POST", body:fd});
    msg("mcStatus","⏳ Menunggu hasil...","info");
    pollJob(d.job_id, "mcStatus", true);
  } catch(e){ msg("mcStatus", e.message, "err"); }
  $("btnMc").disabled = false;
};

$("btnSeed").onclick = async () => {
  const p = $("seedPrompt").value.trim();
  if (p.length<5||p.length>5000) { msg("seedStatus","Prompt 5–5000 karakter.","err"); return; }
  const fd = new FormData(); fd.append("prompt", p);
  const rf = $("seedRef").files[0];
  if (rf) {
    if (rf.size > 20*1024*1024) { msg("seedStatus","File maks 20 MB.","err"); return; }
    fd.append("ref", rf);
  }
  $("btnSeed").disabled = true; msg("seedStatus","⏳ Upload...","info");
  try {
    const d = await api("/api/generate/seedance", {method:"POST", body:fd});
    msg("seedStatus","⏳ Menunggu hasil...","info");
    pollJob(d.job_id, "seedStatus", true);
  } catch(e){ msg("seedStatus", e.message, "err"); }
  $("btnSeed").disabled = false;
};

const SIZES = {"916":[[720,1280],[1152,2048]], "169":[[1280,720],[2048,1152]]};
$("btnImg").onclick = async () => {
  const p = $("imgPrompt").value.trim();
  if (p.length<5||p.length>5000) { msg("imgStatus","Prompt 5–5000 karakter.","err"); return; }
  const [w,h] = SIZES[$("imgAspect").value][+$("imgRes").value];
  const fd = new FormData(); fd.append("prompt", p);
  fd.append("width", w); fd.append("height", h);
  const rf = $("imgRef").files[0];
  if (rf) fd.append("ref", rf);
  $("btnImg").disabled = true; msg("imgStatus","⏳ Upload...","info");
  try {
    const d = await api("/api/generate/image", {method:"POST", body:fd});
    msg("imgStatus","⏳ Menunggu hasil...","info");
    pollJob(d.job_id, "imgStatus", false);
  } catch(e){ msg("imgStatus", e.message, "err"); }
  $("btnImg").disabled = false;
};

$("btnTopup").onclick = async () => {
  if (!selPkg) { msg("topupStatus","Pilih nominal dulu.","err"); return; }
  const pf = $("topupProof").files[0];
  if (!pf) { msg("topupStatus","Lampirkan foto bukti transfer.","err"); return; }
  const fd = new FormData(); fd.append("amount", selPkg); fd.append("proof", pf);
  msg("topupStatus","⏳ Mengirim...","info");
  try {
    await api("/api/topup", {method:"POST", body:fd});
    msg("topupStatus","✅ Bukti terkirim, menunggu verifikasi admin.","ok");
  } catch(e){ msg("topupStatus", e.message, "err"); }
};

async function loadJobs(){
  try {
    const jobs = await api("/api/jobs");
    $("jobList").innerHTML = jobs.length ? jobs.map(j=>{
      const media = j.status==="done" ?
        (j.job_type==="image" ? `<img src="${j.result_url}">` : `<video src="${j.result_url}" controls></video>`) : "";
      return `<div class="job"><b>${j.job_type}</b> <span class="badge">${j.status}</span><br>
        <span style="color:#64748b">${j.prompt||""}</span>${media}</div>`;
    }).join("") : "<p style='color:#64748b'>Belum ada.</p>";
  } catch(e){}
}

async function loadTopups(){
  try {
    const rows = await api("/api/admin/topups");
    $("topupList").innerHTML = rows.length ? rows.map(r=>
      `<div class="job"><b>${r[5]}</b> (${r[1]}) — <b>${rp(r[2])}</b><br>
      <button class="ghost" onclick="decideTopup(${r[0]},'approve')">✅ Setujui</button>
      <button class="ghost" onclick="decideTopup(${r[0]},'reject')">❌ Tolak</button></div>`
    ).join("") : "<p style='color:#64748b'>Tidak ada pending.</p>";
  } catch(e){}
}
async function decideTopup(id, action){
  try { await api(`/api/admin/topup/${id}/${action}`, {method:"POST"}); loadTopups(); }
  catch(e){ alert(e.message); }
}

if (token) enter();
