from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import json, os, re
from datetime import date, datetime
from roadmap_data import ALL_SECTIONS

import psycopg2
from psycopg2.extras import RealDictCursor

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = FastAPI()
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

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

# ── database ───────────────────────────────────────────────────────────────────
def get_db():
    """Open a connection using the DATABASE_URL environment variable."""
    return psycopg2.connect(os.environ["DATABASE_URL"], cursor_factory=RealDictCursor)

def init_db():
    """Create the progress table if it doesn't exist yet."""
    with get_db() as conn:
        with conn.cursor() as cur:
            # Progress table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS progress (
                    id           TEXT PRIMARY KEY DEFAULT 'main',
                    checked      JSONB NOT NULL DEFAULT '{}',
                    streak_dates JSONB NOT NULL DEFAULT '[]',
                    last_check   TEXT
                )
            """)
            # Add new columns if they don't exist (migration)
            try:
                cur.execute("ALTER TABLE progress ADD COLUMN total_items INTEGER NOT NULL DEFAULT 0")
            except psycopg2.Error:
                pass  # Column already exists
            try:
                cur.execute("ALTER TABLE progress ADD COLUMN overall_pct FLOAT NOT NULL DEFAULT 0.0")
            except psycopg2.Error:
                pass  # Column already exists
            
            # Roadmap tables
            cur.execute("""
                CREATE TABLE IF NOT EXISTS sections (
                    id          TEXT PRIMARY KEY,
                    label       TEXT NOT NULL,
                    icon        TEXT NOT NULL,
                    color       TEXT NOT NULL,
                    sort_order  INTEGER NOT NULL DEFAULT 0
                )
            """)
            
            cur.execute("""
                CREATE TABLE IF NOT EXISTS phases (
                    id          TEXT PRIMARY KEY,
                    section_id  TEXT NOT NULL REFERENCES sections(id) ON DELETE CASCADE,
                    phase       TEXT NOT NULL,
                    title       TEXT NOT NULL,
                    icon        TEXT NOT NULL,
                    color       TEXT NOT NULL,
                    status      TEXT NOT NULL DEFAULT 'upcoming',
                    sort_order  INTEGER NOT NULL DEFAULT 0
                )
            """)
            
            cur.execute("""
                CREATE TABLE IF NOT EXISTS phase_sections (
                    id          SERIAL PRIMARY KEY,
                    phase_id    TEXT NOT NULL REFERENCES phases(id) ON DELETE CASCADE,
                    section_key TEXT NOT NULL,
                    UNIQUE(phase_id, section_key)
                )
            """)
            
            cur.execute("""
                CREATE TABLE IF NOT EXISTS items (
                    id          SERIAL PRIMARY KEY,
                    phase_section_id INTEGER NOT NULL REFERENCES phase_sections(id) ON DELETE CASCADE,
                    content     TEXT NOT NULL,
                    sort_order  INTEGER NOT NULL DEFAULT 0
                )
            """)
            
            # Ensure the single row exists
            cur.execute("""
                INSERT INTO progress (id) VALUES ('main')
                ON CONFLICT (id) DO NOTHING
            """)
        conn.commit()

# Run once when the server starts
init_db()

def calculate_total_items(sections=None):
    """Calculate the total number of items across all sections."""
    if sections is None:
        sections = get_all_sections()
    total = 0
    for section in sections:
        for phase in section["phases"]:
            for items in phase["sections"].values():
                total += len(items)
    return total

def get_all_sections_db():
    """Load all sections from database."""
    with get_db() as conn:
        with conn.cursor() as cur:
            # Get sections
            cur.execute("SELECT * FROM sections ORDER BY sort_order")
            sections = cur.fetchall()
            
            result = []
            for section in sections:
                section_id = section["id"]
                
                # Get phases for this section
                cur.execute("""
                    SELECT * FROM phases 
                    WHERE section_id = %s 
                    ORDER BY sort_order
                """, (section_id,))
                phases = cur.fetchall()
                
                phase_list = []
                for phase in phases:
                    phase_id = phase["id"]
                    
                    # Get phase sections
                    cur.execute("""
                        SELECT * FROM phase_sections 
                        WHERE phase_id = %s
                    """, (phase_id,))
                    phase_sections = cur.fetchall()
                    
                    sections_dict = {}
                    for ps in phase_sections:
                        ps_id = ps["id"]
                        section_key = ps["section_key"]
                        
                        # Get items for this phase section
                        cur.execute("""
                            SELECT id, content FROM items 
                            WHERE phase_section_id = %s 
                            ORDER BY sort_order
                        """, (ps_id,))
                        items = [{"id": row["id"], "content": row["content"]} for row in cur.fetchall()]
                        sections_dict[section_key] = items
                    
                    phase_list.append({
                        "id": phase_id,
                        "phase": phase["phase"],
                        "title": phase["title"],
                        "icon": phase["icon"],
                        "color": phase["color"],
                        "status": phase["status"],
                        "sections": sections_dict
                    })
                
                result.append({
                    "id": section["id"],
                    "label": section["label"],
                    "icon": section["icon"],
                    "color": section["color"],
                    "phases": phase_list
                })
            
            return result

def import_static_data():
    """Import the static data from roadmap_data.py into the database."""
    sections = get_all_sections()  # This loads from the static file
    
    with get_db() as conn:
        with conn.cursor() as cur:
            for i, section in enumerate(sections):
                # Insert section
                cur.execute("""
                    INSERT INTO sections (id, label, icon, color, sort_order)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO NOTHING
                """, (section["id"], section["label"], section["icon"], section["color"], i))
                
                for j, phase in enumerate(section["phases"]):
                    phase_id = phase["id"]
                    
                    # Insert phase
                    cur.execute("""
                        INSERT INTO phases (id, section_id, phase, title, icon, color, status, sort_order)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (id) DO NOTHING
                    """, (phase_id, section["id"], phase["phase"], phase["title"], 
                         phase["icon"], phase["color"], phase.get("status", "upcoming"), j))
                    
                    # Insert phase sections and items
                    for section_key, items in phase["sections"].items():
                        # Insert phase section
                        cur.execute("""
                            INSERT INTO phase_sections (phase_id, section_key)
                            VALUES (%s, %s)
                            ON CONFLICT (phase_id, section_key) DO NOTHING
                        """, (phase_id, section_key))
                        
                        # Get the phase_section_id
                        cur.execute("""
                            SELECT id FROM phase_sections 
                            WHERE phase_id = %s AND section_key = %s
                        """, (phase_id, section_key))
                        ps_row = cur.fetchone()
                        if ps_row:
                            ps_id = ps_row["id"]
                            
                            # Insert items
                            for k, item in enumerate(items):
                                cur.execute("""
                                    INSERT INTO items (phase_section_id, content, sort_order)
                                    VALUES (%s, %s, %s)
                                """, (ps_id, item, k))
            
            conn.commit()

def get_all_sections():
    """Get all sections - try database first, fall back to static data."""
    try:
        sections = get_all_sections_db()
        if not sections:  # If database is empty, import static data
            import_static_data()
            sections = get_all_sections_db()
        return sections
    except Exception:
        # Fall back to static data if database issues
        return [json.loads(json.dumps(s)) for s in ALL_SECTIONS]

def load_progress():
    with get_db() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute("SELECT checked, streak_dates, last_check, total_items, overall_pct FROM progress WHERE id = 'main'")
                row = cur.fetchone()
            except psycopg2.Error:
                # Fall back if columns don't exist yet
                cur.execute("SELECT checked, streak_dates, last_check FROM progress WHERE id = 'main'")
                row = cur.fetchone()
                if row:
                    return {
                        "checked": row["checked"] or {},
                        "streak": {
                            "dates":      row["streak_dates"] or [],
                            "last_check": row["last_check"],
                        },
                        "total_items": calculate_total_items(),
                        "overall_pct": 0.0,
                    }
    if not row:
        total_items = calculate_total_items()
        return {
            "checked": {},
            "streak": {"dates": [], "last_check": None},
            "total_items": total_items,
            "overall_pct": 0.0,
        }
    total_items = row["total_items"] or 0
    overall_pct = row["overall_pct"] or 0.0
    return {
        "checked": row["checked"] or {},
        "streak": {
            "dates":      row["streak_dates"] or [],
            "last_check": row["last_check"],
        },
        "total_items": total_items,
        "overall_pct": overall_pct,
    }

def save_progress(data):
    checked      = data.get("checked", {})
    streak_dates = data["streak"].get("dates", [])
    last_check   = data["streak"].get("last_check")
    
    # Calculate percentage
    total_items = calculate_total_items()
    done_items = len(checked)
    overall_pct = round(done_items / total_items * 100) if total_items else 0.0
    
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO progress (id, checked, streak_dates, last_check, total_items, overall_pct)
                VALUES ('main', %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE
                  SET checked      = EXCLUDED.checked,
                      streak_dates = EXCLUDED.streak_dates,
                      last_check   = EXCLUDED.last_check,
                      total_items  = EXCLUDED.total_items,
                      overall_pct  = EXCLUDED.overall_pct
            """, (json.dumps(checked), json.dumps(streak_dates), last_check, total_items, overall_pct))
        conn.commit()

# ── helpers ────────────────────────────────────────────────────────────────────
def get_all_sections():
    return [json.loads(json.dumps(s)) for s in ALL_SECTIONS]

def slugify(text):
    return re.sub(r"[^a-z0-9_]", "_", text.lower().strip())[:40]

# ── streak ─────────────────────────────────────────────────────────────────────
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

# ── stats ──────────────────────────────────────────────────────────────────────
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

# ── routes ─────────────────────────────────────────────────────────────────────
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

@app.get("/manage", response_class=HTMLResponse)
async def manage(request: Request):
    sections = get_all_sections()
    return templates.TemplateResponse("manage.html", {
        "request": request,
        "sections": sections,
    })

# ── toggle ─────────────────────────────────────────────────────────────────────
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

# ── Management API ─────────────────────────────────────────────────────────────

# Sections
@app.post("/api/sections", response_class=JSONResponse)
async def create_section(request: Request):
    data = await request.json()
    section_id = slugify(data["label"])
    
    with get_db() as conn:
        with conn.cursor() as cur:
            # Get max sort order
            cur.execute("SELECT COALESCE(MAX(sort_order), 0) + 1 FROM sections")
            sort_order = cur.fetchone()[0]
            
            cur.execute("""
                INSERT INTO sections (id, label, icon, color, sort_order)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
            """, (section_id, data["label"], data["icon"], data["color"], sort_order))
            conn.commit()
            return {"id": cur.fetchone()[0]}

@app.put("/api/sections/{section_id}", response_class=JSONResponse)
async def update_section(section_id: str, request: Request):
    data = await request.json()
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE sections 
                SET label = %s, icon = %s, color = %s
                WHERE id = %s
            """, (data["label"], data["icon"], data["color"], section_id))
            conn.commit()
    return {"success": True}

@app.delete("/api/sections/{section_id}", response_class=JSONResponse)
async def delete_section(section_id: str):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM sections WHERE id = %s", (section_id,))
            conn.commit()
    return {"success": True}

# Phases
@app.post("/api/sections/{section_id}/phases", response_class=JSONResponse)
async def create_phase(section_id: str, request: Request):
    data = await request.json()
    phase_id = f"{section_id}_{slugify(data['title'])}"
    
    with get_db() as conn:
        with conn.cursor() as cur:
            # Get max sort order
            cur.execute("SELECT COALESCE(MAX(sort_order), 0) + 1 FROM phases WHERE section_id = %s", (section_id,))
            sort_order = cur.fetchone()[0]
            
            cur.execute("""
                INSERT INTO phases (id, section_id, phase, title, icon, color, status, sort_order)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (phase_id, section_id, data["phase"], data["title"], data["icon"], 
                 data["color"], data.get("status", "upcoming"), sort_order))
            conn.commit()
            return {"id": cur.fetchone()[0]}

@app.put("/api/phases/{phase_id}", response_class=JSONResponse)
async def update_phase(phase_id: str, request: Request):
    data = await request.json()
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE phases 
                SET phase = %s, title = %s, icon = %s, color = %s, status = %s
                WHERE id = %s
            """, (data["phase"], data["title"], data["icon"], data["color"], 
                 data.get("status", "upcoming"), phase_id))
            conn.commit()
    return {"success": True}

@app.delete("/api/phases/{phase_id}", response_class=JSONResponse)
async def delete_phase(phase_id: str):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM phases WHERE id = %s", (phase_id,))
            conn.commit()
    return {"success": True}

# Items
@app.post("/api/phases/{phase_id}/sections/{section_key}/items", response_class=JSONResponse)
async def create_item(phase_id: str, section_key: str, request: Request):
    data = await request.json()
    
    with get_db() as conn:
        with conn.cursor() as cur:
            # Get or create phase_section
            cur.execute("""
                INSERT INTO phase_sections (phase_id, section_key)
                VALUES (%s, %s)
                ON CONFLICT (phase_id, section_key) DO NOTHING
            """, (phase_id, section_key))
            
            cur.execute("""
                SELECT id FROM phase_sections 
                WHERE phase_id = %s AND section_key = %s
            """, (phase_id, section_key))
            ps_id = cur.fetchone()[0]
            
            # Get max sort order
            cur.execute("SELECT COALESCE(MAX(sort_order), 0) + 1 FROM items WHERE phase_section_id = %s", (ps_id,))
            sort_order = cur.fetchone()[0]
            
            cur.execute("""
                INSERT INTO items (phase_section_id, content, sort_order)
                VALUES (%s, %s, %s)
                RETURNING id
            """, (ps_id, data["content"], sort_order))
            conn.commit()
            return {"id": cur.fetchone()[0]}

@app.put("/api/items/{item_id}", response_class=JSONResponse)
async def update_item(item_id: int, request: Request):
    data = await request.json()
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE items 
                SET content = %s
                WHERE id = %s
            """, (data["content"], item_id))
            conn.commit()
    return {"success": True}

@app.delete("/api/items/{item_id}", response_class=JSONResponse)
async def delete_item(item_id: int):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM items WHERE id = %s", (item_id,))
            conn.commit()
    return {"success": True}

# ── HTML fragment helpers ──────────────────────────────────────────────────────
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