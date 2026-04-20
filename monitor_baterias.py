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

# ================= CONFIG =================

app = Flask(__name__)

BASE_URL = "http://87.106.124.228:3000/login"

GRAFANA_USER = os.environ.get("GRAFANA_USER")
GRAFANA_PASSWORD = os.environ.get("GRAFANA_PASSWORD")

baterias = [
    ("BATERÍA 10", "http://87.106.124.228:3000/d/U_0RUIJnz/lgv-10"),
    ("BATERÍA 9", "http://87.106.124.228:3000/d/hssJ_tY4k/lgv-9"),
    ("BATERÍA 8", "http://87.106.124.228:3000/d/mpPEGXkSk/lgv-8"),
    ("BATERÍA 7", "http://87.106.124.228:3000/d/5zlPqHZSz/lgv-7"),
    ("BATERÍA 6", "http://87.106.124.228:3000/d/FjZH7jL4k/lgv-6"),
]

driver = None

# ================= UTIL =================

def limpiar_valor(valor):
    try:
        return float(
            valor.replace('%', '')
            .replace('V', '')
            .replace('A', '')
            .replace(',', '.')
            .strip()
        )
    except:
        return None

# ================= LOGIN =================

def hacer_login(driver):
    print("[INFO] Haciendo login en Grafana...")

    driver.get(BASE_URL)

    wait = WebDriverWait(driver, 15)

    try:
        user_input = wait.until(EC.presence_of_element_located((By.NAME, "user")))
        pass_input = driver.find_element(By.NAME, "password")
        login_button = driver.find_element(By.XPATH, "//button")

        user_input.send_keys(GRAFANA_USER)
        pass_input.send_keys(GRAFANA_PASSWORD)
        login_button.click()

        # Esperar a que desaparezca login (o cargue dashboard)
        wait.until(EC.url_contains("/"))

        print("[INFO] Login correcto")

    except Exception as e:
        print(f"[ERROR] Login fallido: {e}")
        raise

# ================= DRIVER =================

def obtener_driver():
    global driver

    if driver is None:
        chrome_options = Options()
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")

        driver = webdriver.Chrome(options=chrome_options)

        hacer_login(driver)

    return driver

# ================= SCRAPING =================

def obtener_datos():
    global driver

    driver = obtener_driver()
    resultados = []

    for _, url in baterias:
        try:
            driver.get(url)

            # Detectar si nos ha devuelto al login (sesión expirada)
            if "login" in driver.current_url:
                print("[WARN] Sesión expirada, re-logueando...")
                hacer_login(driver)
                driver.get(url)

            elements = WebDriverWait(driver, 15).until(
                EC.presence_of_all_elements_located((By.CLASS_NAME, "flot-temp-elem"))
            )

            if len(elements) < 6:
                resultados.append(("N/A", "N/A", "N/A"))
                continue

            soc = limpiar_valor(elements[0].text)
            voltaje = elements[1].text
            amperaje = limpiar_valor(elements[5].text)

            resultados.append((soc, voltaje, amperaje))

        except Exception as e:
            print(f"[ERROR] Scraping: {e}")
            resultados.append(("N/A", "N/A", "N/A"))

    return resultados

# ================= GOOGLE SHEETS =================

def enviar_a_google_sheets(resultados):
    try:
        scope = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive"
        ]

        creds_dict = json.loads(os.environ["GOOGLE_CREDENTIALS_JSON"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)

        sheet = client.open_by_key("1qe6aOpnrxwFDLoqwPJfcnzJRM4psbDrHG-h7fZk8RhA")
        worksheet = sheet.worksheet("Datos")

        timestamp = datetime.now(timezone("Europe/Madrid")).strftime("%Y-%m-%d %H:%M:%S")

        data = [["BATERÍA", "SOC (%)", "VOLTAJE", "AMPERAJE", "ÚLTIMA ACTUALIZACIÓN"]]

        for i, (nombre, _) in enumerate(baterias):
            soc, voltaje, amperaje = resultados[i]
            data.append([
                nombre,
                f"{soc}%" if soc is not None else "N/A",
                voltaje,
                f"{amperaje}A" if amperaje is not None else "N/A",
                timestamp
            ])

        worksheet.update("A1:E6", data)

    except Exception as e:
        print(f"[ERROR] Google Sheets: {e}")

# ================= BUCLE =================

def dentro_de_horario():
    ahora = datetime.now(timezone("Europe/Madrid"))
    hora = ahora.hour
    dia = ahora.weekday()

    return (
        (dia in range(0, 5) and hora >= 22) or
        (dia in range(1, 6) and hora < 6)
    )

def bucle():
    global driver

    while True:
        ahora = datetime.now(timezone("Europe/Madrid")).strftime("%H:%M:%S")

        if dentro_de_horario():
            print(f"[INFO] Ejecutando monitoreo ({ahora})")

            try:
                datos = obtener_datos()
                enviar_a_google_sheets(datos)

            except Exception as e:
                print(f"[ERROR] Ciclo: {e}")

                if driver:
                    driver.quit()
                    driver = None  # fuerza relogin

        else:
            print(f"[INFO] Fuera de horario ({ahora})")

        time.sleep(600)

# ================= FLASK =================

@app.route("/")
def home():
    return "Monitoreo activo con login automático."

# ================= MAIN =================

if __name__ == "__main__":
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        threading.Thread(target=bucle, daemon=True).start()

    app.run(host="0.0.0.0", port=10000)
