from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, Response, abort
import requests
import os
from dotenv import load_dotenv
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_talisman import Talisman
from flask_caching import Cache

load_dotenv()

app = Flask(__name__)

# ==============================
# Config / Secrets
# ==============================
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-only-secret")

GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
PLACE_ID = os.environ.get("GOOGLE_PLACE_ID")
FLASK_ENV = os.environ.get("FLASK_ENV", "development")
ADMIN_API_TOKEN = os.environ.get("ADMIN_API_TOKEN")
SITE_URL = os.environ.get("SITE_URL", "https://360-epoxy.com").rstrip("/")

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

# Local contact page is paused while Contact Us routes to the external funnel.
# @app.route("/contact", methods=["GET", "POST"])
# @limiter.limit("5 per minute", methods=["POST"])
# def contact():
#     if request.method == "POST":
#         name = clean_field(request.form.get("name"), 100)
#         email = clean_field(request.form.get("email"), 120)
#         phone = clean_field(request.form.get("phone"), 25)
#         message = clean_field(request.form.get("message"), 2000)
#
#         if not name or not email or not message:
#             flash("Please fill out all required fields.", "error")
#             return redirect(url_for("contact"))
#
#         if not is_valid_email(email):
#             flash("Please enter a valid email address.", "error")
#             return redirect(url_for("contact"))
#
#         if len(message) < 5:
#             flash("Message is too short.", "error")
#             return redirect(url_for("contact"))
#
#         app.logger.info("New contact form submission received.")
#         flash("Thank you! Your message has been sent.", "success")
#         return redirect(url_for("contact"))
#
#     return render_template("contact.html")


@app.route("/api/reviews")
@limiter.limit("20 per minute")
@cache.cached(timeout=3600)
def get_reviews():
    data, status_code = fetch_google_reviews()
    return jsonify(data), status_code


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
