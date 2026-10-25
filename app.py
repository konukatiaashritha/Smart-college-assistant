"""
app.py — Flask backend for Smart College Assistant.

Routes:
  GET  /                          → main chat page (index.html)
  GET  /api/history               → return session chat history (JSON)
  POST /api/chat                  → process question, return answer (JSON)
  POST /api/feedback              → save feedback rating + comment (JSON)
  GET  /api/faqs                  → return all FAQs (JSON, for FAQ view)
  GET  /admin/login               → admin login page
  POST /admin/login               → process login
  POST /admin/logout              → log out
  GET  /admin                     → FAQ dashboard (auth required)
  POST /admin/faqs                → add FAQ
  POST /admin/faqs/<id>/edit      → edit FAQ
  POST /admin/faqs/<id>/delete    → delete FAQ
"""

import os
import uuid
import hmac
from functools import wraps

from flask import (
    Flask, jsonify, redirect, render_template,
    request, session, url_for, flash,
)

import database as db
from chatbot import get_response

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("FLASK_SECRET_KEY", "dev-secret-change-in-production")
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")

with app.app_context():
    db.init_db()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _session_id() -> str:
    if "session_id" not in session:
        session["session_id"] = str(uuid.uuid4())
    return session["session_id"]


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("admin_logged_in"):
            flash("Please log in to access the admin panel.", "warning")
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return decorated


def _validate_faq(data: dict) -> list:
    errs = []
    if not data.get("question", "").strip():
        errs.append("Question is required.")
    elif len(data["question"]) > 500:
        errs.append("Question must be ≤ 500 characters.")
    if not data.get("answer", "").strip():
        errs.append("Answer is required.")
    elif len(data["answer"]) > 2000:
        errs.append("Answer must be ≤ 2000 characters.")
    if not data.get("category", "").strip():
        errs.append("Category is required.")
    elif len(data["category"]) > 100:
        errs.append("Category must be ≤ 100 characters.")
    if len(data.get("keywords", "")) > 500:
        errs.append("Keywords must be ≤ 500 characters.")
    return errs


# ---------------------------------------------------------------------------
# Student routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/chat", methods=["POST"])
def api_chat():
    if not request.is_json:
        return jsonify({"error": "Content-Type must be application/json"}), 400
    data = request.get_json(silent=True)
    if data is None:
        return jsonify({"error": "Invalid JSON"}), 400

    message = data.get("message", "")
    if not isinstance(message, str):
        return jsonify({"error": "message must be a string"}), 400
    message = message.strip()
    if not message:
        return jsonify({"error": "Message cannot be empty"}), 400
    if len(message) > 500:
        return jsonify({"error": "Message must be ≤ 500 characters"}), 400

    result = get_response(message)
    sid    = _session_id()
    db.save_chat(sid, message, result["answer"], result.get("faq_id"))

    return jsonify({
        "answer":     result["answer"],
        "faq_id":     result.get("faq_id"),
        "category":   result.get("category"),
        "matched":    result.get("matched", False),
        "confidence": result.get("confidence", 0),
    })


@app.route("/api/history")
def api_history():
    sid   = _session_id()
    items = db.get_chat_history(sid)
    return jsonify({"history": items})


@app.route("/api/feedback", methods=["POST"])
def api_feedback():
    if not request.is_json:
        return jsonify({"error": "Content-Type must be application/json"}), 400
    data = request.get_json(silent=True)
    if data is None:
        return jsonify({"error": "Invalid JSON"}), 400

    rating = data.get("rating")
    if rating not in (0, 1):
        return jsonify({"error": "rating must be 0 or 1"}), 400

    faq_id  = data.get("faq_id")
    comment = str(data.get("comment", ""))[:500]

    if faq_id is not None:
        if not isinstance(faq_id, int):
            return jsonify({"error": "faq_id must be integer or null"}), 400
        if db.get_faq_by_id(faq_id) is None:
            faq_id = None

    sid = _session_id()
    db.save_feedback(sid, faq_id, rating, comment)
    return jsonify({"success": True})


@app.route("/api/faqs")
def api_faqs():
    category = request.args.get("category", "").strip()
    if category:
        faqs = db.get_faqs_by_category(category)
    else:
        faqs = db.get_all_faqs()
    return jsonify({"faqs": faqs})


# ---------------------------------------------------------------------------
# Admin routes
# ---------------------------------------------------------------------------

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if session.get("admin_logged_in"):
        return redirect(url_for("admin_dashboard"))
    if request.method == "POST":
        u = request.form.get("username", "").strip()
        p = request.form.get("password", "")
        if hmac.compare_digest(u, ADMIN_USERNAME) and hmac.compare_digest(p, ADMIN_PASSWORD):
            session["admin_logged_in"] = True
            session.permanent = False
            flash("Welcome back!", "success")
            return redirect(url_for("admin_dashboard"))
        flash("Invalid credentials. Please try again.", "danger")
    return render_template("admin_login.html")


@app.route("/admin/logout", methods=["POST"])
@login_required
def admin_logout():
    session.pop("admin_logged_in", None)
    flash("You have been logged out.", "info")
    return redirect(url_for("admin_login"))


@app.route("/admin")
@login_required
def admin_dashboard():
    return redirect(url_for("index"))


@app.route("/admin/faqs", methods=["POST"])
@login_required
def admin_add_faq():
    data = {k: request.form.get(k, "") for k in ("question", "answer", "category", "keywords")}
    errs = _validate_faq(data)
    if errs:
        [flash(e, "danger") for e in errs]
        return redirect(url_for("admin_dashboard"))
    db.add_faq(data["question"], data["answer"], data["category"], data["keywords"])
    flash("FAQ added successfully.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/faqs/<int:faq_id>/edit", methods=["POST"])
@login_required
def admin_edit_faq(faq_id: int):
    if not db.get_faq_by_id(faq_id):
        flash("FAQ not found.", "danger")
        return redirect(url_for("admin_dashboard"))
    data = {k: request.form.get(k, "") for k in ("question", "answer", "category", "keywords")}
    errs = _validate_faq(data)
    if errs:
        [flash(e, "danger") for e in errs]
        return redirect(url_for("admin_dashboard"))
    db.update_faq(faq_id, data["question"], data["answer"], data["category"], data["keywords"])
    flash("FAQ updated successfully.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/faqs/<int:faq_id>/delete", methods=["POST"])
@login_required
def admin_delete_faq(faq_id: int):
    if not db.get_faq_by_id(faq_id):
        flash("FAQ not found.", "danger")
        return redirect(url_for("admin_dashboard"))
    db.delete_faq(faq_id)
    flash("FAQ deleted.", "success")
    return redirect(url_for("admin_dashboard"))


# ---------------------------------------------------------------------------
# Error handlers
# ---------------------------------------------------------------------------

@app.errorhandler(404)
def not_found(e):
    if request.path.startswith("/api/"):
        return jsonify({"error": "Not found"}), 404
    return render_template("index.html"), 404


@app.errorhandler(405)
def method_not_allowed(e):
    if request.path.startswith("/api/"):
        return jsonify({"error": "Method not allowed"}), 405
    return redirect(url_for("index"))


@app.errorhandler(500)
def server_error(e):
    if request.path.startswith("/api/"):
        return jsonify({"error": "Internal server error"}), 500
    return render_template("index.html"), 500


if __name__ == "__main__":
    app.run(debug=True)
