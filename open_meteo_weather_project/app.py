from flask import Flask, render_template, request
from models import Weather, db
import requests
from datetime import datetime

app = Flask(__name__)

GEO_URL = "https://geocoding-api.open-meteo.com/v1/search"
WEATHER_URL = "https://api.open-meteo.com/v1/forecast"

WEATHER_CODES = {
    0: "صاف",
    1: "عمدتاً صاف",
    2: "نیمه‌ابری",
    3: "ابری",
    45: "مه",
    48: "مه یخ‌زده",
    51: "نم‌نم باران سبک",
    53: "نم‌نم باران",
    55: "نم‌نم باران شدید",
    61: "باران سبک",
    63: "باران",
    65: "باران شدید",
    71: "برف سبک",
    73: "برف",
    75: "برف شدید",
    80: "رگبار سبک",
    81: "رگبار",
    82: "رگبار شدید",
    95: "رعد و برق",
    96: "رعد و برق همراه تگرگ",
    99: "رعد و برق شدید همراه تگرگ"
}


def get_city_location(city_name):
    response = requests.get(
        GEO_URL,
        params={"name": city_name, "count": 1, "language": "fa"},
        timeout=10
    )
    response.raise_for_status()
    results = response.json().get("results", [])

    if not results:
        return None

    return results[0]


def get_weather(latitude, longitude):
    response = requests.get(
        WEATHER_URL,
        params={
            "latitude": latitude,
            "longitude": longitude,
            "current": "temperature_2m,relative_humidity_2m,weather_code,pressure_msl",
            "timezone": "auto"
        },
        timeout=10
    )
    response.raise_for_status()

    current = response.json().get("current", {})
    code = current.get("weather_code")

    return {
        "temp": current.get("temperature_2m"),
        "humidity": current.get("relative_humidity_2m"),
        "pressure": current.get("pressure_msl"),
        "description": WEATHER_CODES.get(code, "نامشخص"),
        "icon": str(code) if code is not None else ""
    }


@app.before_request
def open_database():
    if db.is_closed():
        db.connect()


@app.teardown_appcontext
def close_database(error):
    if not db.is_closed():
        db.close()


@app.route("/", methods=["GET", "POST"])
def index():
    result = None
    error = None

    if request.method == "POST":
        city_name = request.form.get("city", "").strip()

        if city_name:
            try:
                location = get_city_location(city_name)

                if location is None:
                    error = "شهر پیدا نشد."
                else:
                    weather = get_weather(
                        location["latitude"],
                        location["longitude"]
                    )

                    city = location["name"]

                    Weather.create(
                        city=city,
                        date=datetime.now(),
                        **weather
                    )

                    result = {
                        "city": city,
                        **weather
                    }

            except requests.RequestException:
                error = "ارتباط با سرویس Open-Meteo برقرار نشد."

    history = Weather.select().order_by(Weather.date.desc()).limit(20)

    return render_template(
        "index.html",
        result=result,
        error=error,
        history=history
    )


if __name__ == "__main__":
    app.run(debug=True)
