from flask import Flask, jsonify
import json
from scraper import run_scraper_once

app = Flask(__name__)

DATA_FILE = "data.json"

def load():
    try:
        with open(DATA_FILE) as f:
            return json.load(f)
    except:
        return {"data": []}

@app.route("/")
def home():
    return "OK - sistema activo"

@app.route("/run")
def run():
    run_scraper_once()
    return {"status": "ok"}

@app.route("/data")
def data():
    return jsonify(load())

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)