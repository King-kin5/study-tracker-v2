# Lekan's Master Study Tracker

**1,156 items** across 4 sections, 27 modules.

## Stack
FastAPI · HTMX · Vanilla CSS · JSON persistence

## Setup

```bash
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Open: **http://localhost:8000**

## Sections

| Section | Modules | Items |
|---------|---------|-------|
| 🤖 AI / ML | 5 phases | 210 |
| ⚙️ Backend Engineering | 9 modules | 390 |
| ∑ Mathematics | 9 modules | 368 |
| ⚛️ Physics | 4 modules | 188 |
| **Total** | **27** | **1,156** |

## Features
- ✅ Check off Topics, Papers to Read, Papers to Implement, Experiments, Projects
- 📊 Dashboard with per-section and per-phase breakdowns
- 🔥 Streak tracker — logs every day you complete an item
- 💾 Progress saved to `data/progress.json` (commit to keep forever)
- ⚡ HTMX — instant checkbox updates, zero page reloads
- 🧭 Sidebar navigation + phase jump nav

## File Structure
```
study-tracker-v2/
├── main.py              # FastAPI app
├── roadmap_data.py      # All 1,156 items
├── requirements.txt
├── data/progress.json   # Auto-created on first run
├── templates/
│   ├── index.html
│   ├── section.html
│   ├── dashboard.html
│   └── partials/
│       ├── sidebar.html
│       └── topbar.html
└── static/
    ├── css/base.css
    └── js/app.js
```
