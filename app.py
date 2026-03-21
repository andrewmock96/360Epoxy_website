from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
import requests
import os
from dotenv import load_dotenv
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_talisman import Talisman

load_dotenv()

app = Flask(__name__)

# Secrets / config
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-only-secret")
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
PLACE_ID = os.environ.get("GOOGLE_PLACE_ID")

# Secure cookie settings
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("FLASK_ENV") == "production"
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

# Security headers / HTTPS protection
# For Render or other reverse proxies, this is usually fine.
Talisman(app, content_security_policy=None)

# CSRF protection
csrf = CSRFProtect(app)

# Rate limiting
limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"]
)


def is_valid_email(email: str) -> bool:
    """Basic email validation without extra dependencies in route logic."""
    if not email or "@" not in email or "." not in email:
        return False
    if len(email) > 120:
        return False
    return True


def clean_field(value, max_length):
    """Trim whitespace and cap size safely."""
    if value is None:
        return ""
    value = value.strip()
    return value[:max_length]


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

        # Required fields
        if not name or not email or not message:
            flash("Please fill out all required fields.", "error")
            return redirect(url_for("contact"))

        # Basic validation
        if not is_valid_email(email):
            flash("Please enter a valid email address.", "error")
            return redirect(url_for("contact"))

        if len(message) < 5:
            flash("Message is too short.", "error")
            return redirect(url_for("contact"))

        # Minimal logging only — do not log personal details
        app.logger.info("New contact form submission received.")

        # Future: send email or save to database here

        flash("Thank you! Your message has been sent.", "success")
        return redirect(url_for("contact"))

    return render_template("contact.html")


@app.route("/api/reviews")
@limiter.limit("20 per minute")
def get_reviews():
    if not GOOGLE_API_KEY or not PLACE_ID:
        app.logger.error("Google Places configuration missing.")
        return jsonify({"error": "Server configuration is incomplete."}), 500

    url = "https://maps.googleapis.com/maps/api/place/details/json"
    params = {
        "place_id": PLACE_ID,
        "fields": "name,rating,reviews",
        "key": GOOGLE_API_KEY,
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        if data.get("status") != "OK":
            app.logger.error(
                "Google Places request failed. Status=%s Message=%s",
                data.get("status"),
                data.get("error_message"),
            )
            return jsonify({"error": "Unable to load reviews right now."}), 502

        result = data.get("result", {})
        return jsonify({
            "name": result.get("name"),
            "rating": result.get("rating"),
            "reviews": result.get("reviews", [])
        })

    except requests.RequestException as exc:
        app.logger.error("Reviews request exception: %s", exc)
        return jsonify({"error": "Unable to fetch reviews right now."}), 502


@app.errorhandler(429)
def ratelimit_handler(e):
    return jsonify({"error": "Too many requests. Please try again later."}), 429


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)