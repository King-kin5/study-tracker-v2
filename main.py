from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import json, os, re
from datetime import date, datetime
from roadmap_data import ALL_SECTIONS

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

app = FastAPI()
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

DATA_FILE   = os.path.join(DATA_DIR, "progress.json")

SECTION_META = {
    "topics":           ("📚", "Topics"),
    "papers_read":      ("📄", "Papers to Read"),
    "papers_implement": ("🔬", "Papers to Implement"),
    "experiments":      ("⚗️",  "Experiments"),
    "projects":         ("🛠️", "Projects"),
}

DEFAULT_SECTION_KEYS = ["topics", "papers_read", "papers_implement", "experiments", "projects"]

PALETTE = [
    "#60a5fa","#4ade80","#f472b6","#fb923c","#a78bfa",
    "#34d399","#fbbf24","#f87171","#38bdf8","#c084fc",
]

# ── persistence ───────────────────────────────────────────────────────────────
def load_progress():
    if not os.path.exists(DATA_FILE):
        return {"checked": {}, "streak": {"dates": [], "last_check": None}}
    with open(DATA_FILE) as f:
        return json.load(f)

def save_progress(data):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

def get_all_sections():
    return [json.loads(json.dumps(s)) for s in ALL_SECTIONS]

def slugify(text):
    return re.sub(r"[^a-z0-9_]", "_", text.lower().strip())[:40]

# ── streak ────────────────────────────────────────────────────────────────────
def update_streak(progress):
    today = str(date.today())
    dates = set(progress["streak"].get("dates", []))
    dates.add(today)
    progress["streak"]["dates"]      = sorted(dates)
    progress["streak"]["last_check"] = today
    return progress

def compute_streak(dates):
    if not dates:
        return 0
    sorted_dates = sorted(
        [datetime.strptime(d, "%Y-%m-%d").date() for d in dates], reverse=True
    )
    today = date.today()
    if (today - sorted_dates[0]).days > 1:
        return 0
    streak = 1
    for i in range(len(sorted_dates) - 1):
        if (sorted_dates[i] - sorted_dates[i + 1]).days == 1:
            streak += 1
        else:
            break
    return streak

# ── stats ─────────────────────────────────────────────────────────────────────
def build_stats(progress, sections=None):
    if sections is None:
        sections = get_all_sections()
    checked = progress.get("checked", {})
    grand_total = grand_done = 0
    sections_stats = []

    for section in sections:
        s_total = s_done = 0
        phase_stats = []
        for phase in section["phases"]:
            p_total = p_done = 0
            sec_stats = {}
            for sec_key, items in phase["sections"].items():
                st = len(items)
                sd = sum(1 for i in range(st)
                         if checked.get(f"{phase['id']}.{sec_key}.{i}"))
                sec_stats[sec_key] = {"total": st, "done": sd}
                p_total += st
                p_done  += sd
            pct = round(p_done / p_total * 100) if p_total else 0
            phase_stats.append({
                "id": phase["id"], "title": phase["title"],
                "icon": phase["icon"], "color": phase["color"],
                "phase": phase["phase"],
                "total": p_total, "done": p_done, "pct": pct,
                "section_stats": sec_stats,
            })
            s_total += p_total
            s_done  += p_done

        s_pct = round(s_done / s_total * 100) if s_total else 0
        sections_stats.append({
            "id": section["id"], "label": section["label"],
            "icon": section["icon"], "color": section["color"],
            "total": s_total, "done": s_done, "pct": s_pct,
            "phases": phase_stats,
        })
        grand_total += s_total
        grand_done  += s_done

    return {
        "sections": sections_stats,
        "total": grand_total,
        "done":  grand_done,
        "overall_pct": round(grand_done / grand_total * 100) if grand_total else 0,
    }

# ── routes ────────────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    progress = load_progress()
    sections = get_all_sections()
    stats    = build_stats(progress, sections)
    streak   = compute_streak(progress["streak"].get("dates", []))
    study_days = len(progress["streak"].get("dates", []))
    return templates.TemplateResponse("index.html", {
        "request": request,
        "sections": sections,
        "checked": progress.get("checked", {}),
        "stats": stats,
        "streak": streak,
        "study_days": study_days,
        "section_meta": SECTION_META,
    })

@app.get("/section/{section_id}", response_class=HTMLResponse)
async def section_view(request: Request, section_id: str):
    sections = get_all_sections()
    section  = next((s for s in sections if s["id"] == section_id), None)
    if not section:
        return HTMLResponse("Not found", 404)
    progress   = load_progress()
    stats      = build_stats(progress, sections)
    streak     = compute_streak(progress["streak"].get("dates", []))
    study_days = len(progress["streak"].get("dates", []))
    sec_stats  = next(s for s in stats["sections"] if s["id"] == section_id)
    return templates.TemplateResponse("section.html", {
        "request": request,
        "section": section,
        "sec_stats": sec_stats,
        "all_sections": sections,
        "checked": progress.get("checked", {}),
        "stats": stats,
        "streak": streak,
        "study_days": study_days,
        "section_meta": SECTION_META,
        "palette": PALETTE,
    })

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    progress   = load_progress()
    sections   = get_all_sections()
    stats      = build_stats(progress, sections)
    streak     = compute_streak(progress["streak"].get("dates", []))
    study_days = len(progress["streak"].get("dates", []))
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "stats": stats,
        "streak": streak,
        "study_days": study_days,
        "all_sections": sections,
    })

# ── toggle ────────────────────────────────────────────────────────────────────
@app.post("/toggle", response_class=HTMLResponse)
async def toggle(request: Request, key: str = Form(...)):
    progress = load_progress()
    checked  = progress.get("checked", {})
    if key in checked:
        del checked[key]
    else:
        checked[key] = True
    progress["checked"] = checked
    progress = update_streak(progress)
    save_progress(progress)

    parts    = key.split(".")
    phase_id = parts[0]
    sec_key  = parts[1]
    item_idx = int(parts[2])
    is_done  = key in checked

    sections  = get_all_sections()
    color     = "#60a5fa"
    item_text = ""
    for section in sections:
        for phase in section["phases"]:
            if phase["id"] == phase_id and sec_key in phase["sections"]:
                items = phase["sections"][sec_key]
                if item_idx < len(items):
                    color     = phase["color"]
                    item_text = items[item_idx]
                break

    stats      = build_stats(progress, sections)
    streak     = compute_streak(progress["streak"].get("dates", []))
    study_days = len(progress["streak"].get("dates", []))

    checkbox_html = _checkbox_row(key, item_text, is_done, color)
    stats_html    = _stats_oob(stats, streak, study_days)
    return HTMLResponse(checkbox_html + stats_html)

# ── HTML fragment helpers ─────────────────────────────────────────────────────
def _checkbox_row(key, text, done, color):
    cls      = "checked" if done else ""
    mark     = "✓" if done else ""
    safe_key = key.replace(".", "-")
    return f"""<div class=\"item-row {cls}\" id=\"item-{safe_key}\"
     hx-post=\"/toggle\" hx-vals='{{"key":"{key}"}}'
     hx-target=\"#item-{safe_key}\" hx-swap=\"outerHTML\">
  <div class=\"checkbox\" style=\"--pc:{color}\">{mark}</div>
  <span class=\"item-text\">{text}</span>
</div>"""

def _stats_oob(stats, streak, study_days):
    sec_pills = "".join(
        f'<div class="sb-sec" style="--c:{s["color"]}">'
        f'<span>{s["icon"]}</span>'
        f'<div class="sb-bar-wrap"><div class="sb-bar" style="width:{s["pct"]}%;background:{s["color"]}"></div></div>'
        f'<span class="sb-pct">{s["pct"]}%</span></div>'
        for s in stats["sections"]
    )
    return f"""<div id="stats-bar" hx-swap-oob="true">
  <div class="sb-pills">
    <div class="sb-pill"><span style="color:#fbbf24;font-weight:700">🔥{streak}</span><span class="sb-label">streak</span></div>
    <div class="sb-pill"><span style="color:#60a5fa;font-weight:700">{study_days}</span><span class="sb-label">days</span></div>
    <div class="sb-pill"><span style="color:#4ade80;font-weight:700">{stats["done"]}/{stats["total"]}</span><span class="sb-label">done</span></div>
    <div class="sb-pill"><span style="color:#f472b6;font-weight:700">{stats["overall_pct"]}%</span><span class="sb-label">total</span></div>
  </div>
  <div class="sb-sections">{sec_pills}</div>
</div>"""