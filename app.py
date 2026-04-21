from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
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
    content_security_policy=None,
    force_https=FLASK_ENV == "production"
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


def fetch_google_reviews():
    """
    Fetch reviews from Google Places API and return:
    (data_dict, status_code)
    """
    if not GOOGLE_API_KEY or not PLACE_ID:
        return {
            "error": "Server configuration is incomplete.",
            "debug": {
                "GOOGLE_API_KEY_set": bool(GOOGLE_API_KEY),
                "GOOGLE_PLACE_ID_set": bool(PLACE_ID),
                "GOOGLE_PLACE_ID_value": PLACE_ID
            }
        }, 500

    url = "https://maps.googleapis.com/maps/api/place/findplacefromtext/json"
    params = {
        "place_id": PLACE_ID,
        "fields": "name,rating,reviews,formatted_address",
        "key": GOOGLE_API_KEY,
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        data = response.json()

        # Helpful while debugging
        if data.get("status") != "OK":
            app.logger.error("Google Places API error: %s", data)
            return {
                "error": "Google Places request failed.",
                "debug": {
                    "google_http_status": response.status_code,
                    "google_response": data,
                    "place_id_used": PLACE_ID
                }
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
@app.route("/")
def home():
    return render_template("index.html")


@app.route("/services")
def services():
    return render_template("services.html")


@app.route("/gallery")
def gallery():
    return render_template("gallery.html")


@app.route("/contact", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def contact():
    if request.method == "POST":
        name = clean_field(request.form.get("name"), 100)
        email = clean_field(request.form.get("email"), 120)
        phone = clean_field(request.form.get("phone"), 25)
        message = clean_field(request.form.get("message"), 2000)

        if not name or not email or not message:
            flash("Please fill out all required fields.", "error")
            return redirect(url_for("contact"))

        if not is_valid_email(email):
            flash("Please enter a valid email address.", "error")
            return redirect(url_for("contact"))

        if len(message) < 5:
            flash("Message is too short.", "error")
            return redirect(url_for("contact"))

        app.logger.info("New contact form submission received.")
        flash("Thank you! Your message has been sent.", "success")
        return redirect(url_for("contact"))

    return render_template("contact.html")


@app.route("/api/reviews")
@limiter.limit("20 per minute")
@cache.cached(timeout=3600)
def get_reviews():
    data, status_code = fetch_google_reviews()
    return jsonify(data), status_code


@app.route("/api/reviews-debug")
@limiter.limit("10 per minute")
def reviews_debug():
    """
    Temporary debug route:
    Use this to see exactly what Google is returning.
    Do not leave this public forever.
    """
    if not GOOGLE_API_KEY or not PLACE_ID:
        return jsonify({
            "error": "Missing config",
            "GOOGLE_API_KEY_set": bool(GOOGLE_API_KEY),
            "GOOGLE_PLACE_ID_set": bool(PLACE_ID),
            "GOOGLE_PLACE_ID_value": PLACE_ID
        }), 500

    url = "https://maps.googleapis.com/maps/api/place/details/json"
    params = {
        "place_id": PLACE_ID,
        "fields": "name,rating,reviews",
        "key": GOOGLE_API_KEY,
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        return jsonify({
            "request_url": response.url,
            "google_http_status": response.status_code,
            "google_response": response.json()
        }), response.status_code
    except requests.RequestException as exc:
        return jsonify({
            "error": "Request failed",
            "details": str(exc)
        }), 502


@app.route("/api/clear-reviews-cache", methods=["POST"])
def clear_reviews_cache():
    cache.clear()
    return jsonify({"message": "Reviews cache cleared."}), 200


@app.errorhandler(429)
def ratelimit_handler(e):
    return jsonify({"error": "Too many requests. Please try again later."}), 429

@app.route("/api/find-place")
def find_place():
    query = request.args.get("q", "360Epoxy").strip()

    url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
    params = {
        "query": query,
        "region": "us",
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

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)