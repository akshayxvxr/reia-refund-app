# Reia — Cx Refund Obligations Tracker
### Flask Web App

---

## Quick Start (Local)

### 1. Install Python dependencies
```bash
cd reia_refund_app
pip install -r requirements.txt
```

### 2. Set up environment
```bash
cp .env.example .env
# Edit .env if needed (defaults work for local dev)
```

### 3. Run the app
```bash
python app.py
```

Open **http://localhost:5000** in your browser.

---

## Features

| Page | URL | What it does |
|------|-----|-------------|
| Tracker | `/tracker` | Live register — search, filter, click any row for details |
| New Entry | `/entry` | Form to log a new refund (net amount auto-calculates) |
| Detail | `/detail/<no>` | Full customer + bank info, update status |
| Summary | `/summary` | Breakdown by store, by reason, export to Google Sheets |

---

## Google Sheets Integration

### Step 1 — Enable APIs
1. Go to https://console.cloud.google.com
2. Create or select a project
3. Enable **Google Sheets API** and **Google Drive API**

### Step 2 — Create Service Account
1. Go to IAM & Admin → Service Accounts
2. Create a new service account
3. Download the JSON key → rename to `credentials.json`
4. Place `credentials.json` in the app root folder

### Step 3 — Share your sheet
1. Open your Google Sheet
2. Click Share → paste the service account email (from credentials.json)
3. Give it **Editor** access

### Step 4 — Configure .env
```bash
SPREADSHEET_ID=your_sheet_id_from_url
GOOGLE_CREDENTIALS_FILE=credentials.json
```

### Step 5 — Install Google packages
```bash
pip install google-auth google-auth-oauthlib google-api-python-client
```

Now every new entry auto-syncs, and you can do a full sync from the Summary page.

---

## Deploying to the Cloud

### Render (free tier, recommended)
1. Push this folder to a GitHub repo
2. Go to https://render.com → New Web Service
3. Connect your repo
4. Set Build Command: `pip install -r requirements.txt`
5. Set Start Command: `gunicorn app:app`
6. Add environment variables from your .env

```bash
pip install gunicorn  # add to requirements.txt
```

### Railway
1. Install Railway CLI: `npm i -g @railway/cli`
2. `railway login && railway init && railway up`

### Heroku
```bash
echo "web: gunicorn app:app" > Procfile
heroku create reia-refund-tracker
git push heroku main
```

---

## Project Structure
```
reia_refund_app/
├── app.py              # Flask routes + logic
├── google_sheets.py    # Google Sheets sync
├── requirements.txt    # Python dependencies
├── .env.example        # Environment config template
├── data/
│   └── refunds.json    # Local data store (auto-created)
└── templates/
    ├── base.html       # Layout, nav, styles
    ├── tracker.html    # Main register view
    ├── entry.html      # New entry form
    ├── detail.html     # Individual record + status update
    └── summary.html    # Reports + Google Sheets export
```

---

## API Endpoints
```
GET  /api/records          — Returns all records as JSON
PATCH /api/records/<no>    — Update fields on a specific record
```
