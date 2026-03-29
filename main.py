from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import json, os, re
from datetime import date, datetime
from roadmap_data import ALL_SECTIONS

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

DATA_FILE      = "data/progress.json"
CUSTOM_FILE    = "data/custom.json"

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
    os.makedirs("data", exist_ok=True)
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

def load_custom():
    if not os.path.exists(CUSTOM_FILE):
        return {"sections": [], "phases": {}, "items": {}}
    with open(CUSTOM_FILE) as f:
        return json.load(f)

def save_custom(data):
    os.makedirs("data", exist_ok=True)
    with open(CUSTOM_FILE, "w") as f:
        json.dump(data, f, indent=2)

def get_all_sections():
    """Merge built-in sections with custom additions."""
    custom   = load_custom()
    sections = [json.loads(json.dumps(s)) for s in ALL_SECTIONS]   # deep copy

    # 1. Inject custom phases into existing sections
    for section in sections:
        sid = section["id"]
        for custom_phase in custom.get("phases", {}).get(sid, []):
            section["phases"].append(custom_phase)

    # 2. Inject custom items into phases
    custom_items = custom.get("items", {})
    for section in sections:
        for phase in section["phases"]:
            pid = phase["id"]
            for sec_key in DEFAULT_SECTION_KEYS:
                extras = custom_items.get(f"{pid}.{sec_key}", [])
                if extras:
                    if sec_key not in phase["sections"]:
                        phase["sections"][sec_key] = []
                    phase["sections"][sec_key] = list(phase["sections"][sec_key]) + extras

    # 3. Append fully custom sections
    for cs in custom.get("sections", []):
        cs_copy = json.loads(json.dumps(cs))
        # also inject any custom phases / items for this custom section
        sid = cs_copy["id"]
        for custom_phase in custom.get("phases", {}).get(sid, []):
            cs_copy["phases"].append(custom_phase)
        for phase in cs_copy["phases"]:
            pid = phase["id"]
            for sec_key in DEFAULT_SECTION_KEYS:
                extras = custom_items.get(f"{pid}.{sec_key}", [])
                if extras:
                    if sec_key not in phase["sections"]:
                        phase["sections"][sec_key] = []
                    phase["sections"][sec_key] = list(phase["sections"][sec_key]) + extras
        sections.append(cs_copy)

    return sections

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

# ── ADD ITEM ──────────────────────────────────────────────────────────────────
@app.post("/add-item", response_class=HTMLResponse)
async def add_item(
    request: Request,
    phase_id: str = Form(...),
    sec_key:  str = Form(...),
    text:     str = Form(...),
):
    text = text.strip()
    if not text:
        return HTMLResponse("", 200)

    custom = load_custom()
    key    = f"{phase_id}.{sec_key}"
    custom.setdefault("items", {}).setdefault(key, [])
    custom["items"][key].append(text)
    save_custom(custom)

    # Figure out the real index of the new item in the merged list
    sections = get_all_sections()
    color    = "#60a5fa"
    new_idx  = 0
    for section in sections:
        for phase in section["phases"]:
            if phase["id"] == phase_id:
                color   = phase["color"]
                new_idx = len(phase["sections"].get(sec_key, [])) - 1
                break

    item_key = f"{phase_id}.{sec_key}.{new_idx}"
    progress   = load_progress()
    stats      = build_stats(progress, sections)
    streak     = compute_streak(progress["streak"].get("dates", []))
    study_days = len(progress["streak"].get("dates", []))

    row_html   = _checkbox_row(item_key, text, False, color)
    stats_html = _stats_oob(stats, streak, study_days)
    return HTMLResponse(row_html + stats_html)

# ── REMOVE ITEM ───────────────────────────────────────────────────────────────
@app.post("/remove-item", response_class=HTMLResponse)
async def remove_item(
    request:  Request,
    key:      str = Form(...),   # e.g. "aiml_p0.topics.14"
):
    parts    = key.split(".")
    phase_id = parts[0]
    sec_key  = parts[1]
    item_idx = int(parts[2])

    # We only allow removing custom items.
    # Find how many built-in items exist for this phase+sec_key
    builtin_count = 0
    for s in ALL_SECTIONS:
        for p in s["phases"]:
            if p["id"] == phase_id:
                builtin_count = len(p["sections"].get(sec_key, []))
                break

    custom_key   = f"{phase_id}.{sec_key}"
    custom_index = item_idx - builtin_count   # index within the custom list

    if custom_index < 0:
        return HTMLResponse('<div class="remove-error">Built-in items cannot be removed.</div>', 200)

    custom = load_custom()
    items  = custom.get("items", {}).get(custom_key, [])
    if custom_index < len(items):
        items.pop(custom_index)
        custom["items"][custom_key] = items
        save_custom(custom)

    # Also remove from checked
    progress = load_progress()
    checked  = progress.get("checked", {})
    if key in checked:
        del checked[key]
        progress["checked"] = checked
        save_progress(progress)

    sections   = get_all_sections()
    stats      = build_stats(progress, sections)
    streak     = compute_streak(progress["streak"].get("dates", []))
    study_days = len(progress["streak"].get("dates", []))

    return HTMLResponse(_stats_oob(stats, streak, study_days))   # row just disappears

# ── ADD PHASE ─────────────────────────────────────────────────────────────────
@app.post("/add-phase")
async def add_phase(
    request:    Request,
    section_id: str = Form(...),
    title:      str = Form(...),
    icon:       str = Form("📌"),
    color:      str = Form("#60a5fa"),
):
    title = title.strip()
    if not title:
        return JSONResponse({"ok": False, "error": "Title required"}, 400)

    custom = load_custom()
    # Count existing custom phases for this section to number them
    existing = custom.setdefault("phases", {}).setdefault(section_id, [])
    phase_num = len(existing) + 1
    phase_id  = f"{section_id}_custom_{slugify(title)}_{phase_num}"

    # Count total phases already in this section for phase label
    all_secs = get_all_sections()
    sec      = next((s for s in all_secs if s["id"] == section_id), None)
    phase_label = f"Phase {len(sec['phases']) + 1}" if sec else f"Phase {phase_num}"

    new_phase = {
        "id":      phase_id,
        "phase":   phase_label,
        "title":   title,
        "icon":    icon,
        "color":   color,
        "status":  "upcoming",
        "sections": {k: [] for k in DEFAULT_SECTION_KEYS},
    }
    existing.append(new_phase)
    save_custom(custom)
    return JSONResponse({"ok": True, "phase_id": phase_id, "redirect": f"/section/{section_id}"})

# ── REMOVE PHASE ──────────────────────────────────────────────────────────────
@app.post("/remove-phase")
async def remove_phase(
    request:    Request,
    section_id: str = Form(...),
    phase_id:   str = Form(...),
):
    # Only custom phases can be deleted
    if "_custom_" not in phase_id:
        return JSONResponse({"ok": False, "error": "Built-in phases cannot be removed."}, 400)

    custom = load_custom()
    phases = custom.get("phases", {}).get(section_id, [])
    custom["phases"][section_id] = [p for p in phases if p["id"] != phase_id]

    # Also remove all items belonging to this phase
    to_del = [k for k in custom.get("items", {}) if k.startswith(phase_id + ".")]
    for k in to_del:
        del custom["items"][k]
    save_custom(custom)

    # Remove checked state
    progress = load_progress()
    checked  = {k: v for k, v in progress["checked"].items() if not k.startswith(phase_id + ".")}
    progress["checked"] = checked
    save_progress(progress)

    return JSONResponse({"ok": True})

# ── ADD SECTION ───────────────────────────────────────────────────────────────
@app.post("/add-section")
async def add_section(
    request: Request,
    label:   str = Form(...),
    icon:    str = Form("📁"),
    color:   str = Form("#60a5fa"),
):
    label = label.strip()
    if not label:
        return JSONResponse({"ok": False, "error": "Label required"}, 400)

    custom = load_custom()
    section_id = f"custom_{slugify(label)}_{len(custom.get('sections', [])) + 1}"
    new_section = {
        "id":     section_id,
        "label":  label,
        "icon":   icon,
        "color":  color,
        "phases": [],
    }
    custom.setdefault("sections", []).append(new_section)
    save_custom(custom)
    return JSONResponse({"ok": True, "section_id": section_id, "redirect": f"/section/{section_id}"})

# ── REMOVE SECTION ────────────────────────────────────────────────────────────
@app.post("/remove-section")
async def remove_section(
    request:    Request,
    section_id: str = Form(...),
):
    if not section_id.startswith("custom_"):
        return JSONResponse({"ok": False, "error": "Built-in sections cannot be removed."}, 400)

    custom = load_custom()
    custom["sections"] = [s for s in custom.get("sections", []) if s["id"] != section_id]

    # Remove all phases & items belonging to this section
    custom.get("phases", {}).pop(section_id, None)
    to_del = [k for k in custom.get("items", {}) if k.startswith(section_id)]
    for k in to_del:
        del custom["items"][k]
    save_custom(custom)

    progress = load_progress()
    checked  = {k: v for k, v in progress["checked"].items() if not k.startswith(section_id)}
    progress["checked"] = checked
    save_progress(progress)

    return JSONResponse({"ok": True})

# ── HTML fragment helpers ─────────────────────────────────────────────────────
def _checkbox_row(key, text, done, color):
    cls      = "checked" if done else ""
    mark     = "✓" if done else ""
    safe_key = key.replace(".", "-")
    # Only custom items (index >= builtin count — handled client-side) show delete
    return f"""<div class="item-row {cls}" id="item-{safe_key}"
     hx-post="/toggle" hx-vals='{{"key":"{key}"}}'
     hx-target="#item-{safe_key}" hx-swap="outerHTML">
  <div class="checkbox" style="--pc:{color}">{mark}</div>
  <span class="item-text">{text}</span>
  <button class="item-del" title="Remove item"
          hx-post="/remove-item" hx-vals='{{"key":"{key}"}}'
          hx-target="#item-{safe_key}" hx-swap="outerHTML"
          hx-confirm="Remove this item?"
          onclick="event.stopPropagation()">×</button>
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