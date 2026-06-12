from functools import wraps
from datetime import datetime, timezone
from collections import deque
from pathlib import Path
import re
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, Response, abort
import requests
import os
from dotenv import load_dotenv
from flask_wtf.csrf import CSRFError, CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_talisman import Talisman
from flask_caching import Cache

load_dotenv()

app = Flask(__name__)
BASE_DIR = Path(__file__).resolve().parent

# ==============================
# Config / Secrets
# ==============================
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-only-secret")

GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
PLACE_ID = os.environ.get("GOOGLE_PLACE_ID")
FLASK_ENV = os.environ.get("FLASK_ENV", "development")
ADMIN_API_TOKEN = os.environ.get("ADMIN_API_TOKEN")
SITE_URL = os.environ.get("SITE_URL", "https://360-epoxy.com").rstrip("/")
GHL_CONTACT_WEBHOOK_URL = os.environ.get("GHL_CONTACT_WEBHOOK_URL")
GHL_WEBHOOK_ENABLED = os.environ.get(
    "GHL_WEBHOOK_ENABLED",
    "true" if FLASK_ENV == "production" else "false",
).lower() == "true"
SMS_CONSENT_DISCLOSURE = (
    "I agree to receive conversational text messages from 360Epoxy about my estimate, "
    "appointments, and project. Message frequency varies. Message and data rates may apply. "
    "Reply STOP to opt out or HELP for help."
)
MARKETING_SMS_CONSENT_DISCLOSURE = (
    "I agree to receive occasional promotional text messages from 360Epoxy. Message frequency "
    "varies. Message and data rates may apply. Reply STOP to opt out or HELP for help."
)
PLACEHOLDER_CONVERSATIONAL_SMS = (
    "Hi {{contact.first_name}}, this is 360Epoxy. Thanks for requesting a free estimate. "
    "What type of space would you like coated? Reply STOP to opt out."
)
PLACEHOLDER_MARKETING_SMS = (
    "360Epoxy: Ready to transform your floor? Ask us about current coating options and "
    "availability. Reply STOP to opt out."
)
TEST_CONTACT_SUBMISSIONS = deque(maxlen=20)
PROJECT_TYPE_OPTIONS = {
    "garage_floor": "Garage Floor",
    "basement_floor": "Basement Floor",
    "patio_outdoor": "Patio / Outdoor",
    "commercial_space": "Commercial Space",
    "industrial_warehouse": "Industrial / Warehouse",
    "other": "Other",
}
TIMELINE_OPTIONS = {
    "as_soon_as_possible": "As Soon as Possible",
    "within_1_month": "Within 1 Month",
    "within_1_to_3_months": "Within 1-3 Months",
    "within_3_to_6_months": "Within 3-6 Months",
    "more_than_6_months": "More Than 6 Months",
    "exploring_options": "Just Exploring Options",
}
STATE_OPTIONS = {"Utah", "Arizona", "Colorado", "Idaho", "Nevada", "Wyoming", "Other"}

if FLASK_ENV == "production" and app.secret_key == "dev-only-secret":
    raise RuntimeError("FLASK_SECRET_KEY must be set in production.")

# ==============================
# Security settings
# ==============================
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SECURE"] = FLASK_ENV == "production"
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

# ==============================
# Cache
# ==============================
app.config["CACHE_TYPE"] = "SimpleCache"
app.config["CACHE_DEFAULT_TIMEOUT"] = 3600  # 1 hour
cache = Cache(app)

# ==============================
# Extensions
# ==============================
Talisman(
    app,
    content_security_policy={
        "default-src": ["'self'"],
        "script-src": ["'self'", "'unsafe-inline'", "https://cdn.jsdelivr.net"],
        "style-src": ["'self'", "'unsafe-inline'", "https://fonts.googleapis.com", "https://cdn.jsdelivr.net"],
        "font-src": ["'self'", "https://fonts.gstatic.com"],
        "img-src": ["'self'", "data:", "https:"],
        "connect-src": ["'self'"],
        "frame-ancestors": ["'self'"],
    },
    force_https=FLASK_ENV == "production",
    session_cookie_secure=FLASK_ENV == "production",
)

csrf = CSRFProtect(app)

limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"]
)

# ==============================
# Helpers
# ==============================
def is_valid_email(email: str) -> bool:
    if not email or "@" not in email or "." not in email:
        return False
    if len(email) > 120:
        return False
    return True


def clean_field(value, max_length):
    if value is None:
        return ""
    return value.strip()[:max_length]


def is_valid_phone(phone: str) -> bool:
    digits = "".join(character for character in phone if character.isdigit())
    return 10 <= len(digits) <= 15


def load_legal_document(filename: str):
    lines = (BASE_DIR / filename).read_text(encoding="utf-8").splitlines()
    blocks = []

    for line in lines[1:]:
        text = line.strip()
        if not text:
            continue

        if text.lower().startswith("last updated:"):
            block_type = "updated"
        elif re.match(r"^\d+\.\s", text):
            block_type = "heading"
        elif text.isupper() and len(text) < 80:
            block_type = "callout"
        elif text.endswith(":") and len(text) < 100:
            block_type = "subheading"
        else:
            block_type = "paragraph"

        blocks.append({"type": block_type, "text": text})

    return blocks


def admin_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if not ADMIN_API_TOKEN:
            abort(404)

        token = request.headers.get("X-Admin-Token") or request.args.get("token")
        if token != ADMIN_API_TOKEN:
            abort(404)

        return view(*args, **kwargs)

    return wrapped_view


def google_get(url, params):
    response = requests.get(url, params=params, timeout=10)
    try:
        data = response.json()
    except ValueError:
        data = {"status": "INVALID_JSON", "raw_response": response.text[:500]}
    return response.status_code, data


def fetch_google_reviews():
    """
    Fetch reviews from Google Places API and return:
    (data_dict, status_code)
    """
    if not GOOGLE_API_KEY or not PLACE_ID:
        return {
            "error": "Reviews are not configured yet."
        }, 500

    url = "https://maps.googleapis.com/maps/api/place/details/json"
    params = {
        "place_id": PLACE_ID,
        "fields": "name,rating,reviews,formatted_address",
        "key": GOOGLE_API_KEY,
    }

    try:
        google_http_status, data = google_get(url, params)

        if data.get("status") != "OK":
            app.logger.error("Google Places API error: %s", data)
            return {
                "error": "Google reviews are currently unavailable."
            }, 502

        result = data.get("result", {})
        return {
            "name": result.get("name"),
            "rating": result.get("rating"),
            "formatted_address": result.get("formatted_address"),
            "reviews": result.get("reviews", [])
        }, 200

    except requests.RequestException as exc:
        app.logger.error("Google request exception: %s", exc)
        return {
            "error": "Unable to fetch reviews right now.",
            "debug": {
                "exception": str(exc)
            }
        }, 502


# ==============================
# Routes
# ==============================
@app.context_processor
def inject_site_metadata():
    return {
        "site_url": SITE_URL,
        "business_name": "360Epoxy",
        "business_phone": "+13855583495",
        "business_email": "360epoxyaz@gmail.com",
    }


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/mobile-preview")
def mobile_preview():
    if FLASK_ENV == "production":
        abort(404)

    return render_template("mobile_preview.html")


@app.route("/services")
def services():
    return render_template("services.html")


@app.route("/gallery")
def gallery():
    return render_template("gallery.html")

@app.route('/robots.txt')
@limiter.exempt
def robots():
    with open('static/robots.txt', 'r', encoding='utf-8') as f:
        text = f.read()
    return Response(text, mimetype='text/plain')


@app.route('/sitemap.xml')
@limiter.exempt
def sitemap():
    with open('static/sitemap.xml', 'r', encoding='utf-8') as f:
        xml = f.read()
    return Response(xml, mimetype='application/xml')

@app.route("/contact", methods=["GET", "POST"])
@limiter.limit("5 per minute", methods=["POST"])
def contact():
    form_data = {}

    if request.method == "POST":
        form_data = {
            "first_name": clean_field(request.form.get("first_name"), 50),
            "last_name": clean_field(request.form.get("last_name"), 50),
            "email": clean_field(request.form.get("email"), 120),
            "phone": clean_field(request.form.get("phone"), 25),
            "project_type": clean_field(request.form.get("project_type"), 50),
            "square_feet": clean_field(request.form.get("square_feet"), 10),
            "desired_timeline": clean_field(request.form.get("desired_timeline"), 50),
            "street_address": clean_field(request.form.get("street_address"), 150),
            "city": clean_field(request.form.get("city"), 80),
            "state": clean_field(request.form.get("state"), 50),
            "zip_code": clean_field(request.form.get("zip_code"), 10),
            "additional_details": clean_field(request.form.get("additional_details"), 2000),
            "minimum_project_acknowledged": request.form.get("minimum_project_acknowledged") == "yes",
            "sms_consent": request.form.get("sms_consent") == "yes",
            "marketing_sms_consent": request.form.get("marketing_sms_consent") == "yes",
        }

        if not all(
            form_data[field]
            for field in (
                "first_name", "last_name", "email", "phone", "project_type",
                "square_feet", "street_address", "city", "state", "zip_code",
            )
        ):
            flash("Please fill out all required fields.", "error")
            return render_template("contact.html", form_data=form_data), 400

        if form_data["project_type"] not in PROJECT_TYPE_OPTIONS:
            flash("Please select your project type.", "error")
            return render_template("contact.html", form_data=form_data), 400

        if form_data["desired_timeline"] and form_data["desired_timeline"] not in TIMELINE_OPTIONS:
            flash("Please select a valid project timeline.", "error")
            return render_template("contact.html", form_data=form_data), 400

        if form_data["state"] not in STATE_OPTIONS:
            flash("Please select a valid state.", "error")
            return render_template("contact.html", form_data=form_data), 400

        if not form_data["square_feet"].isdigit() or int(form_data["square_feet"]) < 1:
            flash("Please enter a valid approximate square footage.", "error")
            return render_template("contact.html", form_data=form_data), 400

        if not re.match(r"^\d{5}(?:-\d{4})?$", form_data["zip_code"]):
            flash("Please enter a valid ZIP code.", "error")
            return render_template("contact.html", form_data=form_data), 400

        if not form_data["minimum_project_acknowledged"]:
            flash("Please acknowledge the $1,999 minimum project investment.", "error")
            return render_template("contact.html", form_data=form_data), 400

        if not is_valid_email(form_data["email"]):
            flash("Please enter a valid email address.", "error")
            return render_template("contact.html", form_data=form_data), 400

        if not is_valid_phone(form_data["phone"]):
            flash("Please enter a valid phone number.", "error")
            return render_template("contact.html", form_data=form_data), 400

        submitted_at = datetime.now(timezone.utc).isoformat()
        has_sms_consent = form_data["sms_consent"] or form_data["marketing_sms_consent"]
        payload = {
            **form_data,
            "name": f"{form_data['first_name']} {form_data['last_name']}",
            "message": form_data["additional_details"],
            "project_type_label": PROJECT_TYPE_OPTIONS[form_data["project_type"]],
            "desired_timeline_label": TIMELINE_OPTIONS.get(form_data["desired_timeline"], ""),
            "source": "360Epoxy website contact form",
            "source_url": request.url,
            "submitted_at_utc": submitted_at,
            "ip_address": request.remote_addr if has_sms_consent else None,
            "user_agent": request.user_agent.string if has_sms_consent else None,
            "ip_address_collected_for_consent_evidence": has_sms_consent,
            "consent_disclosure_version": "2026-06-11",
            "sms_consent_disclosure": SMS_CONSENT_DISCLOSURE,
            "marketing_sms_consent_disclosure": MARKETING_SMS_CONSENT_DISCLOSURE,
            "consent_is_not_condition_of_purchase": True,
            "sms_consent_status": "opted_in" if form_data["sms_consent"] else "not_opted_in",
            "marketing_sms_consent_status": "opted_in" if form_data["marketing_sms_consent"] else "not_opted_in",
            "sms_consent_timestamp_utc": submitted_at if form_data["sms_consent"] else None,
            "marketing_sms_consent_timestamp_utc": submitted_at if form_data["marketing_sms_consent"] else None,
            "placeholder_conversational_sms": PLACEHOLDER_CONVERSATIONAL_SMS,
            "placeholder_marketing_sms": PLACEHOLDER_MARKETING_SMS,
        }

        if not GHL_WEBHOOK_ENABLED:
            TEST_CONTACT_SUBMISSIONS.appendleft(payload)
            app.logger.info("Contact form test submission accepted; LeadConnector webhook is disabled.")
            flash(
                "Test successful! Your request was validated and saved in the local test inbox, "
                "but it was not sent to the CRM.",
                "success",
            )
            return redirect(url_for("contact"))

        if not GHL_CONTACT_WEBHOOK_URL:
            app.logger.error("GHL_CONTACT_WEBHOOK_URL is not configured.")
            flash("We could not send your request right now. Please call or email us.", "error")
            return render_template("contact.html", form_data=form_data), 503

        try:
            response = requests.post(GHL_CONTACT_WEBHOOK_URL, json=payload, timeout=10)
            response.raise_for_status()
        except requests.RequestException:
            app.logger.error("LeadConnector contact webhook request failed.")
            flash("We could not send your request right now. Please call or email us.", "error")
            return render_template("contact.html", form_data=form_data), 502

        app.logger.info("Contact form submission delivered to LeadConnector.")
        flash("Thank you! We received your request and will be in touch soon.", "success")
        return redirect(url_for("contact"))

    return render_template("contact.html", form_data=form_data)


@app.route("/privacy")
def privacy():
    return render_template("privacy.html", legal_blocks=load_legal_document("privacy_policy.txt"))


@app.route("/terms")
def terms():
    return render_template("terms.html", legal_blocks=load_legal_document("terms_of_service.txt"))


@app.route("/api/reviews")
@limiter.limit("20 per minute")
@cache.cached(timeout=3600)
def get_reviews():
    data, status_code = fetch_google_reviews()
    return jsonify(data), status_code


@app.route("/api/test-contact-submissions")
@admin_required
@limiter.limit("20 per minute")
def test_contact_submissions():
    if FLASK_ENV == "production":
        abort(404)

    return jsonify({
        "webhook_enabled": GHL_WEBHOOK_ENABLED,
        "submission_count": len(TEST_CONTACT_SUBMISSIONS),
        "submissions": list(TEST_CONTACT_SUBMISSIONS),
    }), 200


@app.route("/api/clear-reviews-cache", methods=["POST"])
@csrf.exempt
@admin_required
@limiter.limit("5 per minute")
def clear_reviews_cache():
    cache.clear()
    return jsonify({"message": "Reviews cache cleared."}), 200


@app.errorhandler(429)
def ratelimit_handler(e):
    return jsonify({"error": "Too many requests. Please try again later."}), 429


@app.errorhandler(CSRFError)
def csrf_error_handler(e):
    if request.path == "/contact":
        flash("Your form session expired. Please review your information and submit again.", "error")
        return redirect(url_for("contact"))
    return "Bad request.", 400


@app.errorhandler(404)
def not_found_handler(e):
    if request.path.startswith("/api/"):
        return jsonify({"error": "Not found."}), 404
    return "Not found.", 404


@app.route("/api/place-diagnostics")
@admin_required
@limiter.limit("10 per minute")
def place_diagnostics():
    query = clean_field(request.args.get("q"), 120) or "360 Epoxy Salt Lake City"
    phone_query = "+13855583495"

    if not GOOGLE_API_KEY:
        return jsonify({
            "error": "GOOGLE_API_KEY is not configured.",
            "checks": {
                "google_api_key_set": False,
                "google_place_id_set": bool(PLACE_ID),
            }
        }), 500

    diagnostics = {
        "checks": {
            "google_api_key_set": True,
            "google_place_id_set": bool(PLACE_ID),
            "site_url": SITE_URL,
        },
        "stored_place_id_check": None,
        "find_place_results": [],
        "notes": [
            "If stored_place_id_check.status is NOT_FOUND, the saved Place ID is probably obsolete.",
            "If responses show REQUEST_DENIED, check Google Cloud billing, Places API enablement, and API key restrictions.",
            "If searches do not return 360Epoxy, verify the Google Business Profile name, service area, category, and phone number."
        ]
    }

    details_url = "https://maps.googleapis.com/maps/api/place/details/json"
    find_url = "https://maps.googleapis.com/maps/api/place/findplacefromtext/json"

    try:
        if PLACE_ID:
            status_code, data = google_get(details_url, {
                "place_id": PLACE_ID,
                "fields": "place_id,name,business_status,rating,user_ratings_total,formatted_address",
                "key": GOOGLE_API_KEY,
            })
            diagnostics["stored_place_id_check"] = {
                "google_http_status": status_code,
                "status": data.get("status"),
                "error_message": data.get("error_message"),
                "result": data.get("result"),
            }

        for search_query in (query, phone_query):
            status_code, data = google_get(find_url, {
                "input": search_query,
                "inputtype": "textquery",
                "fields": "place_id,name,formatted_address,business_status,rating,user_ratings_total",
                "locationbias": "circle:50000@40.2349254,-111.740896",
                "key": GOOGLE_API_KEY,
            })
            diagnostics["find_place_results"].append({
                "query_used": search_query,
                "google_http_status": status_code,
                "status": data.get("status"),
                "error_message": data.get("error_message"),
                "candidates": data.get("candidates", []),
            })

        return jsonify(diagnostics), 200

    except requests.RequestException as exc:
        app.logger.error("Google diagnostics request failed: %s", exc)
        return jsonify({
            "error": "Google diagnostics request failed.",
            "details": str(exc)
        }), 502


@app.route("/api/find-place")
@admin_required
@limiter.limit("10 per minute")
def find_place():
    query = request.args.get("q", "360 Epoxy Salt Lake City").strip()

    url = "https://maps.googleapis.com/maps/api/place/findplacefromtext/json"
    params = {
        "input": query,
        "inputtype": "textquery",
        "fields": "place_id,name,formatted_address,business_status,rating,user_ratings_total",
        "key": GOOGLE_API_KEY,
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        return jsonify({
            "query_used": query,
            "google_response": response.json()
        }), response.status_code
    except requests.RequestException as exc:
        return jsonify({
            "error": "Request failed",
            "details": str(exc)
        }), 502
    
@app.route("/api/nearby-place")
@admin_required
@limiter.limit("10 per minute")
def nearby_place():
    url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
    params = {
        "location": "40.2349254,-111.740896",
        "radius": 50000,
        "keyword": "epoxy",
        "key": GOOGLE_API_KEY,
    }

    response = requests.get(url, params=params, timeout=10)
    return jsonify(response.json()), response.status_code

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
