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

baterias = [
    ("BATERÍA 10", "http://87.106.124.228:3000/d/U_0RUIJnz/..."),
    ("BATERÍA 9", "http://87.106.124.228:3000/d/hssJ_tY4k/..."),
    ("BATERÍA 8", "http://87.106.124.228:3000/d/mpPEGXkSk/..."),
    ("BATERÍA 7", "http://87.106.124.228:3000/d/5zlPqHZSz/..."),
    ("BATERÍA 6", "http://87.106.124.228:3000/d/FjZH7jL4k/..."),
]

# -------------------------
# CHROME RENDER
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
    print("🔐 Login...")

    driver.get(BASE_URL)
    wait = WebDriverWait(driver, 60)

    user = wait.until(EC.presence_of_element_located((By.NAME, "username")))
    pwd = driver.find_element(By.NAME, "password")

    user.clear()
    user.send_keys(GRAFANA_USER)

    pwd.clear()
    pwd.send_keys(GRAFANA_PASSWORD)

    btn = driver.find_element(By.XPATH, "//button[@type='submit']")
    driver.execute_script("arguments[0].click();", btn)

    WebDriverWait(driver, 60).until(
        lambda d: "/login" not in d.current_url
    )

    print("✅ Login OK")


# -------------------------
# ESPERA DATOS
# -------------------------
def esperar_datos(driver):
    try:
        WebDriverWait(driver, 60).until(
            lambda d: len(d.find_elements(By.CLASS_NAME, "flot-temp-elem")) > 0
        )
        return True
    except:
        return False


# -------------------------
# SCRAPING
# -------------------------
def obtener_datos():
    driver = crear_driver()

    resultados = []

    try:
        login(driver)

        for nombre, url in baterias:
            print(f"\n📡 {nombre}")
            driver.get(url)

            if not esperar_datos(driver):
                print("⚠️ Reintentando...")
                time.sleep(5)
                driver.refresh()

            elements = driver.find_elements(By.CLASS_NAME, "flot-temp-elem")

            print(f"🔎 elementos: {len(elements)}")

            try:
                textos = [e.text for e in elements]

                if len(textos) >= 6:
                    soc = float(textos[0].replace('%',''))
                    volt = textos[1]
                    amp = float(textos[5].replace('A',''))

                    print(f"SOC {soc} | VOLT {volt} | AMP {amp}")

                    resultados.append((soc, volt, amp))
                else:
                    resultados.append(("N/A","N/A","N/A"))

            except Exception as e:
                print("❌ error:", e)
                resultados.append(("N/A","N/A","N/A"))

            time.sleep(3)

    finally:
        driver.quit()

    return resultados


# -------------------------
# GOOGLE SHEETS (FIXED)
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

    # HEADER (FIXED)
    ws.update(
        values=[["BATERÍA","SOC (%)","VOLTAJE","AMPERAJE","FECHA"]],
        range_name="A1:E1"
    )

    ws.update(
        values=[[nombre] for nombre,_ in baterias],
        range_name="A2:A6"
    )

    timestamp = datetime.now(timezone("Europe/Madrid")).strftime("%Y-%m-%d %H:%M:%S")

    valores = [[f"{soc}%", volt, f"{amp}A", timestamp] for soc, volt, amp in resultados]

    ws.update(
        values=valores,
        range_name="B2:E6"
    )


# -------------------------
# LOOP
# -------------------------
def loop():
    while True:
        print("\n🚀 CICLO")
        datos = obtener_datos()
        enviar_a_google_sheets(datos)
        print("💤 esperando 10 min")
        time.sleep(600)


# -------------------------
# FLASK
# -------------------------
@app.route("/")
def home():
    return "OK monitor activo"


if __name__ == "__main__":
    print("🚀 INICIANDO SISTEMA")

    t = threading.Thread(target=loop, daemon=True)
    t.start()

    app.run(host="0.0.0.0", port=10000)
def loop():
    while True:
        try:
            print("\n🚀 CICLO INICIADO")
            datos = obtener_datos()
            print("📊 datos:", datos)

            enviar_a_google_sheets(datos)
            print("📤 enviado a sheets")

        except Exception as e:
            print("❌ ERROR LOOP:", e)

        time.sleep(600)    
