import os
import json
import time
import threading
from datetime import datetime

from flask import Flask

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

import gspread
from oauth2client.service_account import ServiceAccountCredentials
from pytz import timezone

app = Flask(__name__)

BASE_URL = "http://87.106.124.228:3000/login"

GRAFANA_USER = os.environ.get("GRAFANA_USER")
GRAFANA_PASSWORD = os.environ.get("GRAFANA_PASSWORD")

# -------------------------
# HORARIO DE FUNCIONAMIENTO
# -------------------------
def dentro_de_horario():
    ahora = datetime.now(timezone("Europe/Madrid"))

    hora = ahora.hour
    dia = ahora.weekday()  # 0=lunes ... 6=domingo

    # 🌙 domingo a jueves desde 22:00
    if dia in [6, 0, 1, 2, 3] and hora >= 22:
        return True

    # 🌅 lunes a viernes hasta 06:00
    if dia in [0, 1, 2, 3, 4] and hora < 6:
        return True

    return False


# -------------------------
# BATERÍAS (URLS COMPLETAS)
# -------------------------
baterias = [
    ("BATERÍA 10", "http://87.106.124.228:3000/d/U_0RUIJnz/lgv-10-em0522000366001-48v-gprs_s_439?orgId=121&refresh=1m"),
    ("BATERÍA 9", "http://87.106.124.228:3000/d/hssJ_tY4k/lgv-9-em1423001154001-48v-315ah-gprs_s_23205?orgId=121&refresh=1m"),
    ("BATERÍA 8", "http://87.106.124.228:3000/d/mpPEGXkSk/lgv-8-em3223002731001-48v-315ah-gprs_s_23597?orgId=121&refresh=1m"),
    ("BATERÍA 7", "http://87.106.124.228:3000/d/5zlPqHZSz/lgv-7-em3223002713001-48v-315ah-gprs_s_23473?orgId=121&refresh=1m"),
    ("BATERÍA 6", "http://87.106.124.228:3000/d/FjZH7jL4k/lgv-6-em1423001156001-48v-315ah-gprs_s_23177?orgId=121&refresh=1m"),
]


# -------------------------
# CHROME (RENDER FIX)
# -------------------------
def crear_driver():
    options = Options()

    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")

    options.binary_location = "/usr/bin/chromium"

    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(90)

    return driver


# -------------------------
# LOGIN GRAFANA
# -------------------------
def login(driver):
    print("🔐 LOGIN...")

    driver.get(BASE_URL)
    wait = WebDriverWait(driver, 60)

    user = wait.until(EC.presence_of_element_located((By.NAME, "username")))
    pwd = driver.find_element(By.NAME, "password")

    user.send_keys(GRAFANA_USER)
    pwd.send_keys(GRAFANA_PASSWORD)

    driver.find_element(By.XPATH, "//button[@type='submit']").click()

    WebDriverWait(driver, 60).until(
        lambda d: "/login" not in d.current_url
    )

    print("✅ LOGIN OK")


# -------------------------
# ESPERA DASHBOARD REAL
# -------------------------
def esperar_dashboard(driver):
    WebDriverWait(driver, 90).until(
        lambda d: d.execute_script("return document.readyState") == "complete"
    )
    time.sleep(7)


# -------------------------
# SCRAPER
# -------------------------
def obtener_datos():
    driver = crear_driver()
    resultados = []

    try:
        login(driver)

        for nombre, url in baterias:
            print(f"\n📡 {nombre}")

            driver.get(url)
            esperar_dashboard(driver)

            elements = driver.find_elements(
                By.CSS_SELECTOR,
                "span.flot-temp-elem"
            )

            valores = [
                e.text.strip()
                for e in elements
                if e.is_displayed() and e.text.strip()
            ]

            print("RAW:", valores)

            soc = next((v for v in valores if "%" in v), "N/A")
            volt = next((v for v in valores if "V" in v), "N/A")
            amp = next((v for v in valores if "A" in v), "N/A")

            resultados.append((soc, volt, amp))

            print(f"OK → {soc} | {volt} | {amp}")

            time.sleep(3)

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
    ws.update(values=[[soc, volt, amp, ts] for soc, volt, amp in resultados], range_name="B2:E6")


# -------------------------
# LOOP CON HORARIO
# -------------------------
def loop():
    while True:
        try:
            if dentro_de_horario():
                print("\n🚀 CICLO (EN HORARIO)")
                datos = obtener_datos()
                print("📊 RESULTADO:", datos)

                enviar_a_google_sheets(datos)
                print("📤 ENVIADO OK")
            else:
                print("⏱️ Fuera de horario")

        except Exception as e:
            print("❌ ERROR LOOP:", e)

        time.sleep(600)


# -------------------------
# FLASK
# -------------------------
@app.route("/")
def home():
    return "OK monitor activo"


# -------------------------
# STARTUP
# -------------------------
if __name__ == "__main__":
    print("🚀 INICIANDO SISTEMA")

    # 🔥 primera ejecución solo si toca horario
    try:
        if dentro_de_horario():
            datos = obtener_datos()
            print("📊 PRIMERA LECTURA:", datos)
            enviar_a_google_sheets(datos)
            print("📤 PRIMERA SUBIDA OK")
        else:
            print("⏱️ Inicio fuera de horario")
    except Exception as e:
        print("❌ ERROR INICIAL:", e)

    t = threading.Thread(target=loop, daemon=True)
    t.start()

    app.run(host="0.0.0.0", port=10000)
