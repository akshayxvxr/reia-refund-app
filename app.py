from dotenv import load_dotenv
load_dotenv()

from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
import json
import os
from datetime import date, datetime
from google_sheets import GoogleSheetsSync

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "reia-refund-secret-2024")

DATA_FILE = "data/refunds.json"

# ── Google Sheets instance ────────────────────────────────────────────────────
gs = GoogleSheetsSync()

# ── helpers ───────────────────────────────────────────────────────────────────

def load_records():
    """Load from Google Sheets if configured, else fall back to local JSON."""
    if gs.is_configured():
        try:
            return gs.load_all_records()
        except Exception as e:
            print(f"Google Sheets load error: {e} — falling back to local JSON")
    return load_local()

def load_local():
    if not os.path.exists(DATA_FILE):
        return seed_data()
    with open(DATA_FILE) as f:
        return json.load(f)

def save_records(records):
    """Save to local JSON as backup cache."""
    os.makedirs("data", exist_ok=True)
    with open(DATA_FILE, "w") as f:
        json.dump(records, f, indent=2, default=str)

def seed_data():
    records = [
        {"no": 1, "name": "Chinmaya Joisa", "store": "Jayanagar", "email": "chinmayajoisa@gmail.com",
         "phone": "7019994254", "acc": "39600807015", "ifsc": "SBIN0014512", "bank": "SBI",
         "bankname": "Udaya Kumar Joisa", "date": "2026-04-22", "reason": "Excess payment made",
         "notes": "Paid excess amount instead of exchanging the product (cx was out of country)",
         "invoice": 74391, "received": 107250, "net": 32859, "approved_by": "",
         "refund_initiated": "", "days_out": 2, "actual_date": "", "status": "Pending"},
        {"no": 2, "name": "Jagadheeshwari", "store": "Cross Cut", "email": "",
         "phone": "9944454188", "acc": "26218100000325", "ifsc": "BARBOSAICOI", "bank": "Bank of Baroda",
         "bankname": "Jagatheswari K", "date": "2026-04-22", "reason": "Excess amount paid in Old gold",
         "notes": "", "invoice": 37940, "received": 49246, "net": 11306, "approved_by": "",
         "refund_initiated": "", "days_out": 2, "actual_date": "", "status": "Pending"},
        {"no": 3, "name": "Hema", "store": "Cross Cut", "email": "lema.ganesh456@gmail.com",
         "phone": "7708167293", "acc": "26218100000325", "ifsc": "BARBOSAICOI", "bank": "Bank of Baroda",
         "bankname": "Jagatheswari K", "date": "2026-04-22", "reason": "Excess amount paid in Old gold",
         "notes": "", "invoice": 18000, "received": 19455, "net": 1455, "approved_by": "",
         "refund_initiated": "", "days_out": 2, "actual_date": "", "status": "Pending"},
        {"no": 4, "name": "Vidhyavathi", "store": "Cross Cut", "email": "vidyapuru77@gmail.com",
         "phone": "9845561106", "acc": "", "ifsc": "", "bank": "", "bankname": "",
         "date": "2026-04-22", "reason": "Excess amount paid in Old gold",
         "notes": "", "invoice": 57291, "received": 60762, "net": 3471, "approved_by": "",
         "refund_initiated": "", "days_out": 2, "actual_date": "", "status": "Pending"},
        {"no": 5, "name": "Sangeetha", "store": "RS Puram", "email": "sangee@keeyes.com",
         "phone": "9600290909", "acc": "59119600290909", "ifsc": "HDFC0000445", "bank": "HDFC Bank",
         "bankname": "SANGEETHA N", "date": "2026-04-15", "reason": "Excess amount paid in Old gold",
         "notes": "", "invoice": 484000, "received": 539906, "net": 55906, "approved_by": "",
         "refund_initiated": "", "days_out": 9, "actual_date": "", "status": "Pending"},
    ]
    save_records(records)
    return records

def compute_days(record):
    if record.get("status") == "Completed":
        return 0
    if record.get("date"):
        try:
            d = datetime.strptime(str(record["date"]), "%Y-%m-%d").date()
            return (date.today() - d).days
        except:
            try:
                d = datetime.strptime(str(record["date"]), "%m/%d/%Y").date()
                return (date.today() - d).days
            except:
                pass
    return record.get("days_out", 0)

def next_record_no(records):
    if not records:
        return 1
    return max(r.get("no", 0) for r in records) + 1

# ── routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return redirect(url_for("tracker"))

@app.route("/tracker")
def tracker():
    records = load_records()
    for r in records:
        r["days_out"] = compute_days(r)

    status_filter = request.args.get("status", "")
    search        = request.args.get("search", "").lower()
    filtered      = records

    if status_filter:
        filtered = [r for r in filtered if r["status"] == status_filter]
    if search:
        filtered = [r for r in filtered if
                    search in r["name"].lower() or
                    search in r["store"].lower() or
                    search in (r.get("bank") or "").lower()]

    total       = len(records)
    pending     = sum(1 for r in records if r["status"] == "Pending")
    completed   = sum(1 for r in records if r["status"] == "Completed")
    outstanding = sum(r["net"] for r in records if r["status"] != "Completed")

    return render_template("tracker.html", records=filtered, total=total,
                           pending=pending, completed=completed,
                           outstanding=outstanding, status_filter=status_filter,
                           search=search)

@app.route("/entry", methods=["GET", "POST"])
def entry():
    if request.method == "POST":
        records  = load_records()
        next_no  = next_record_no(records)
        invoice  = float(request.form.get("invoice", 0) or 0)
        received = float(request.form.get("received", 0) or 0)
        net      = max(0, received - invoice)

        record = {
            "no":               next_no,
            "name":             request.form.get("name", "").strip(),
            "store":            request.form.get("store", "").strip(),
            "email":            request.form.get("email", "").strip(),
            "phone":            request.form.get("phone", "").strip(),
            "acc":              request.form.get("acc", "").strip(),
            "ifsc":             request.form.get("ifsc", "").strip(),
            "bank":             request.form.get("bank", "").strip(),
            "bankname":         request.form.get("bankname", "").strip(),
            "date":             request.form.get("date", str(date.today())),
            "reason":           request.form.get("reason", ""),
            "notes":            request.form.get("notes", "").strip(),
            "invoice":          invoice,
            "received":         received,
            "net":              net,
            "approved_by":      request.form.get("approved_by", "").strip(),
            "refund_initiated": "",
            "days_out":         0,
            "actual_date":      "",
            "status":           "Pending",
        }

        # Save to Google Sheets (primary)
        if gs.is_configured():
            try:
                gs.append_row(record)
            except Exception as e:
                print(f"Google Sheets append error: {e}")

        # Also save locally as backup
        records.append(record)
        save_records(records)

        flash("Refund entry saved successfully!", "success")
        return redirect(url_for("tracker"))

    return render_template("entry.html", today=str(date.today()))

@app.route("/detail/<int:no>")
def detail(no):
    records = load_records()
    record  = next((r for r in records if r["no"] == no), None)
    if not record:
        flash("Record not found.", "error")
        return redirect(url_for("tracker"))
    record["days_out"] = compute_days(record)
    return render_template("detail.html", r=record)

@app.route("/update_status/<int:no>", methods=["POST"])
def update_status(no):
    records = load_records()
    for r in records:
        if r["no"] == no:
            r["status"] = request.form.get("status", r["status"])
            if r["status"] == "Completed" and not r.get("actual_date"):
                r["actual_date"] = str(date.today())
            approved_by = request.form.get("approved_by", "").strip()
            if approved_by:
                r["approved_by"] = approved_by
            r["days_out"] = compute_days(r)

            # Update in Google Sheets
            if gs.is_configured():
                try:
                    gs.update_record(r)
                except Exception as e:
                    print(f"Google Sheets update error: {e}")

            # Update local backup
            save_records(records)
            break

    flash("Status updated successfully.", "success")
    return redirect(url_for("detail", no=no))

@app.route("/delete/<int:no>", methods=["POST"])
def delete_record(no):
    records          = load_records()
    record_to_delete = next((r for r in records if r["no"] == no), None)

    if not record_to_delete:
        flash("Record not found.", "error")
        return redirect(url_for("tracker"))

    # Delete from Google Sheets
    if gs.is_configured():
        try:
            gs.delete_row(no)
        except Exception as e:
            print(f"Google Sheets delete error: {e}")

    # Delete from local backup
    records = [r for r in records if r["no"] != no]
    save_records(records)

    flash(f"Entry #{no} ({record_to_delete['name']}) deleted successfully.", "success")
    return redirect(url_for("tracker"))

@app.route("/summary")
def summary():
    records = load_records()
    stores  = {}
    for r in records:
        s = r["store"]
        if s not in stores:
            stores[s] = {"count": 0, "invoice": 0, "net": 0, "pending": 0, "completed": 0}
        stores[s]["count"]   += 1
        stores[s]["invoice"] += r["invoice"]
        stores[s]["net"]     += r["net"]
        if r["status"] in ("Pending", "In Progress"):
            stores[s]["pending"] += 1
        if r["status"] == "Completed":
            stores[s]["completed"] += 1

    total_outstanding = sum(r["net"] for r in records if r["status"] != "Completed")
    total_refunded    = sum(r["net"] for r in records if r["status"] == "Completed")
    rate = round(len([r for r in records if r["status"] == "Completed"]) / len(records) * 100) if records else 0
    reasons = {}
    for r in records:
        reasons[r["reason"]] = reasons.get(r["reason"], 0) + r["net"]

    return render_template("summary.html", stores=stores,
                           total_outstanding=total_outstanding,
                           total_refunded=total_refunded,
                           rate=rate, reasons=reasons)

@app.route("/export/google-sheets", methods=["POST"])
def export_google_sheets():
    if not gs.is_configured():
        flash("Google Sheets not configured.", "error")
        return redirect(url_for("summary"))
    try:
        records = load_records()
        url     = gs.full_sync(records)
        flash(f"Synced to Google Sheets! {url}", "success")
    except Exception as e:
        flash(f"Export failed: {str(e)}", "error")
    return redirect(url_for("summary"))

# ── API ───────────────────────────────────────────────────────────────────────

@app.route("/api/records")
def api_records():
    return jsonify(load_records())

@app.route("/api/records/<int:no>", methods=["PATCH"])
def api_update(no):
    records = load_records()
    data    = request.get_json()
    for r in records:
        if r["no"] == no:
            r.update(data)
            if gs.is_configured():
                try:
                    gs.update_record(r)
                except Exception as e:
                    print(f"Google Sheets update error: {e}")
            save_records(records)
            return jsonify({"ok": True, "record": r})
    return jsonify({"ok": False, "error": "Not found"}), 404

@app.route("/api/records/<int:no>", methods=["DELETE"])
def api_delete(no):
    records          = load_records()
    record_to_delete = next((r for r in records if r["no"] == no), None)
    if not record_to_delete:
        return jsonify({"ok": False, "error": "Not found"}), 404
    if gs.is_configured():
        try:
            gs.delete_row(no)
        except Exception as e:
            print(f"Google Sheets delete error: {e}")
    records = [r for r in records if r["no"] != no]
    save_records(records)
    return jsonify({"ok": True, "deleted": no})

if __name__ == "__main__":
    app.run(debug=True, port=5000)
