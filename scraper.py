import os
import json
import time
import threading
from datetime import datetime

from flask import Flask

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

import gspread
from oauth2client.service_account import ServiceAccountCredentials
from pytz import timezone

# -------------------------
# FLASK
# -------------------------
app = Flask(__name__)
port = int(os.environ.get("PORT", 10000))

# -------------------------
# MEMORIA GLOBAL (WEB)
# -------------------------
datos_globales = []
lock = threading.Lock()

# -------------------------
# CONFIG
# -------------------------
BASE_URL = "http://87.106.124.228:3000/login"

GRAFANA_USER = os.environ.get("GRAFANA_USER")
GRAFANA_PASSWORD = os.environ.get("GRAFANA_PASSWORD")

baterias = [
    ("BATERÍA 10", "http://87.106.124.228:3000/d/U_0RUIJnz/lgv-10-em0522000366001-48v-gprs_s_439?orgId=121&refresh=1m"),
    ("BATERÍA 9", "http://87.106.124.228:3000/d/hssJ_tY4k/lgv-9-em1423001154001-48v-315ah-gprs_s_23205?orgId=121&refresh=1m"),
    ("BATERÍA 8", "http://87.106.124.228:3000/d/mpPEGXkSk/lgv-8-em3223002731001-48v-315ah-gprs_s_23597?orgId=121&refresh=1m"),
    ("BATERÍA 7", "http://87.106.124.228:3000/d/5zlPqHZSz/lgv-7-em3223002713001-48v-315ah-gprs_s_23473?orgId=121&refresh=1m"),
    ("BATERÍA 6", "http://87.106.124.228:3000/d/FjZH7jL4k/lgv-6-em1423001156001-48v-315ah-gprs_s_23177?orgId=121&refresh=1m"),
]

# -------------------------
# HORARIO
# -------------------------
def dentro_de_horario():
    ahora = datetime.now(timezone("Europe/Madrid"))
    h = ahora.hour
    d = ahora.weekday()

    return (d in range(7) and h >= 22) or (d in range(5) and h < 6)

# -------------------------
# CHROME
# -------------------------
def crear_driver():
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.binary_location = "/usr/bin/chromium"

    return webdriver.Chrome(options=options)

# -------------------------
# LOGIN
# -------------------------
def login(driver):
    driver.get(BASE_URL)

    time.sleep(3)

    driver.find_element(By.NAME, "username").send_keys(GRAFANA_USER)
    driver.find_element(By.NAME, "password").send_keys(GRAFANA_PASSWORD)

    driver.find_element(By.XPATH, "//button[@type='submit']").click()

    time.sleep(5)

# -------------------------
# SCRAPER SEGURO (FIX STALE)
# -------------------------
def obtener_datos():
    driver = crear_driver()
    resultados = []

    try:
        login(driver)

        for nombre, url in baterias:
            driver.get(url)
            time.sleep(8)

            elements = driver.find_elements(By.CSS_SELECTOR, "span.flot-temp-elem")

            valores = []

            # 🔥 FIX REAL: evitar stale element
            for e in elements:
                try:
                    txt = e.get_attribute("textContent").strip()
                    if txt:
                        valores.append(txt)
                except:
                    continue

            soc = next((v for v in valores if "%" in v), "N/A")
            volt = next((v for v in valores if "V" in v), "N/A")
            amp = next((v for v in valores if "A" in v), "N/A")

            resultados.append((soc, volt, amp))

            time.sleep(2)

    finally:
        driver.quit()

    return resultados

# -------------------------
# GOOGLE SHEETS
# -------------------------
def enviar_a_google_sheets(resultados):
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ]

    creds_dict = json.loads(os.environ["GOOGLE_CREDENTIALS_JSON"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)

    client = gspread.authorize(creds)

    sheet = client.open_by_key("1qe6aOpnrxwFDLoqwPJfcnzJRM4psbDrHG-h7fZk8RhA")
    ws = sheet.worksheet("Datos")

    ts = datetime.now(timezone("Europe/Madrid")).strftime("%Y-%m-%d %H:%M:%S")

    ws.update(values=[["BATERÍA","SOC","VOLTAJE","AMPERAJE","FECHA"]], range_name="A1:E1")
    ws.update(values=[[n] for n,_ in baterias], range_name="A2:A6")
    ws.update(values=[[s,v,a,ts] for s,v,a in resultados], range_name="B2:E6")

# -------------------------
# LOOP BACKGROUND (NO BLOQUEA FLASK)
# -------------------------
def loop():
    global datos_globales

    while True:
        try:
            if dentro_de_horario():
                datos = obtener_datos()

                with lock:
                    datos_globales = [
                        {
                            "nombre": baterias[i][0],
                            "soc": datos[i][0],
                            "volt": datos[i][1],
                            "amp": datos[i][2],
                            "hora": datetime.now().strftime("%H:%M:%S")
                        }
                        for i in range(len(datos))
                    ]

                enviar_a_google_sheets(datos)

        except Exception as e:
            print("ERROR LOOP:", e)

        time.sleep(600)

# -------------------------
# PANEL WEB
# -------------------------
@app.route("/")
def home():
    with lock:
        data = datos_globales.copy()

    html = """
    <html>
    <head>
        <meta http-equiv="refresh" content="10">
        <style>
            body { font-family: Arial; background:#0f0f0f; color:white; }
            .grid { display:flex; flex-wrap:wrap; gap:10px; }
            .card { background:#1e1e1e; padding:15px; border-radius:10px; width:200px; }
            h1 { color:#00ffcc; }
        </style>
    </head>
    <body>
        <h1>🔋 Monitor Baterías</h1>
        <div class="grid">
    """

    for d in data:
        html += f"""
        <div class="card">
            <h3>{d['nombre']}</h3>
            <p>SOC: {d['soc']}</p>
            <p>Volt: {d['volt']}</p>
            <p>Amp: {d['amp']}</p>
            <p>🕒 {d['hora']}</p>
        </div>
        """

    html += "</div></body></html>"
    return html

# -------------------------
# STARTUP (IMPORTANTE RENDER)
# -------------------------
if __name__ == "__main__":
    print("🚀 SISTEMA INICIADO")

    threading.Thread(target=loop, daemon=True).start()

    app.run(host="0.0.0.0", port=port)
