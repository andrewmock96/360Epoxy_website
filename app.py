from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
import requests # type: ignore


app = Flask(__name__)
app.secret_key = "360EpoxySecretKey"

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
def contact():
    if request.method == "POST":
        name = request.form.get("name")
        email = request.form.get("email")
        phone = request.form.get("phone")
        message = request.form.get("message")
        print(f"New submission: {name}, {email}, {phone}, {message}")
        flash("Thank you! Your message has been sent.", "success")
        return redirect(url_for("contact"))
    return render_template("contact.html")

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)



# GOOGLE REVIEWS API SETTINGS
API_KEY = "YOUR_GOOGLE_API_KEY"  # replace with your Google API Key
PLACE_ID = "YOUR_PLACE_ID"        # replace with your verified business Place ID

@app.route("/api/reviews")
def get_reviews():
    url = f"https://maps.googleapis.com/maps/api/place/details/json?place_id={PLACE_ID}&fields=name,rating,reviews&key={API_KEY}"
    response = requests.get(url)
    data = response.json()
    
    reviews = data.get("result", {}).get("reviews", [])
    
    # Simplify the data to send to frontend
    simplified_reviews = [
        {
            "author_name": r.get("author_name"),
            "rating": r.get("rating"),
            "text": r.get("text")
        } for r in reviews
    ]
    
    return jsonify(simplified_reviews)