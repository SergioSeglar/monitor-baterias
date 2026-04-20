import os
import json
import time
import threading
import traceback
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

# ================= FLASK =================

app = Flask(__name__)

@app.route("/")
def home():
    print("[WEB] / ping recibido")
    return "OK"

@app.route("/health")
def health():
    print("[WEB] /health ping recibido")
    return "alive"

# ================= CONFIG =================

BASE_URL = "http://87.106.124.228:3000/login"

GRAFANA_USER = os.environ.get("GRAFANA_USER")
GRAFANA_PASSWORD = os.environ.get("GRAFANA_PASSWORD")

baterias = [
    ("BATERÍA 10", "http://87.106.124.228:3000/d/U_0RUIJnz/lgv-10-em0522000366001-48v-gprs_s_439?orgId=121&refresh=1m"),
    ("BATERÍA 9", "http://87.106.124.228:3000/d/hssJ_tY4k/lgv-9-em1423001154001-48v-315ah-gprs_s_23205?orgId=121&refresh=1m"),
    ("BATERÍA 8", "http://87.106.124.228:3000/d/mpPEGXkSk/lgv-8-em3223002731001-48v-315ah-gprs_s_23597?refresh=1m"),
    ("BATERÍA 7", "http://87.106.124.228:3000/d/5zlPqHZSz/lgv-7-em3223002713001-48v-315ah-gprs_s_23473?orgId=121&refresh=1m"),
    ("BATERÍA 6", "http://87.106.124.228:3000/d/FjZH7jL4k/lgv-6-em1423001156001-48v-315ah-gprs_s_23177?orgId=121&refresh=1m"),
]

driver = None
contador = 0

# ================= LOG =================

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

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

# ================= DRIVER =================

def crear_driver():
    log("Creando Chrome driver...")

    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")

    driver = webdriver.Chrome(options=options)

    log("Chrome driver creado correctamente")
    return driver

# ================= LOGIN =================

def login(driver):
    try:
        log("Entrando a login Grafana...")
        driver.get(BASE_URL)

        wait = WebDriverWait(driver, 15)

        user = wait.until(EC.presence_of_element_located((By.NAME, "user")))
        password = driver.find_element(By.NAME, "password")

        user.send_keys(GRAFANA_USER)
        password.send_keys(GRAFANA_PASSWORD)

        driver.find_element(By.XPATH, "//button").click()

        time.sleep(2)

        log("Login correcto")

    except Exception as e:
        log("ERROR LOGIN")
        log(str(e))
        log(traceback.format_exc())
        raise

# ================= DRIVER CONTROL =================

def get_driver():
    global driver

    if driver is None:
        driver = crear_driver()
        login(driver)

    return driver

def reset_driver():
    global driver

    log("Reseteando driver...")

    try:
        if driver:
            driver.quit()
    except:
        pass

    driver = None

# ================= SCRAPING =================

def obtener_datos():
    driver = get_driver()
    resultados = []

    log("Iniciando scraping de baterías...")

    for nombre, url in baterias:
        try:
            log(f"Accediendo a {nombre}")

            driver.get(url)

            if "login" in driver.current_url:
                log("Sesión expirada → relogin")
                reset_driver()
                driver = get_driver()
                driver.get(url)

            elements = WebDriverWait(driver, 15).until(
                EC.presence_of_all_elements_located((By.CLASS_NAME, "flot-temp-elem"))
            )

            log(f"{nombre} elementos detectados: {len(elements)}")

            if len(elements) < 6:
                resultados.append(("N/A", "N/A", "N/A"))
                continue

            soc = limpiar_valor(elements[0].text)
            voltaje = elements[1].text
            amperaje = limpiar_valor(elements[5].text)

            log(f"{nombre} → SOC:{soc} V:{voltaje} A:{amperaje}")

            resultados.append((soc, voltaje, amperaje))

        except Exception as e:
            log(f"ERROR en {nombre}")
            log(str(e))
            log(traceback.format_exc())

            resultados.append(("N/A", "N/A", "N/A"))

    return resultados

# ================= GOOGLE SHEETS =================

def enviar_sheets(resultados):
    try:
        log("Enviando a Google Sheets...")

        scope = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive"
        ]

        creds = json.loads(os.environ["GOOGLE_CREDENTIALS_JSON"])

        client = gspread.authorize(
            ServiceAccountCredentials.from_json_keyfile_dict(creds, scope)
        )

        sheet = client.open_by_key("1qe6aOpnrxwFDLoqwPJfcnzJRM4psbDrHG-h7fZk8RhA")
        ws = sheet.worksheet("Datos")

        timestamp = datetime.now(timezone("Europe/Madrid")).strftime("%Y-%m-%d %H:%M:%S")

        data = [["BATERÍA", "SOC (%)", "VOLTAJE", "AMPERAJE", "HORA"]]

        for i, (nombre, _) in enumerate(baterias):
            soc, voltaje, amperaje = resultados[i]

            data.append([
                nombre,
                f"{soc}%" if soc is not None else "N/A",
                voltaje,
                f"{amperaje}A" if amperaje is not None else "N/A",
                timestamp
            ])

        ws.update("A1:E6", data)

        log("Google Sheets actualizado")

    except Exception as e:
        log("ERROR GOOGLE SHEETS")
        log(str(e))
        log(traceback.format_exc())

# ================= HORARIO =================

def dentro_horario():
    ahora = datetime.now(timezone("Europe/Madrid"))
    h = ahora.hour
    d = ahora.weekday()

    return (d in range(0, 5) and h >= 22) or (d in range(1, 6) and h < 6)

# ================= LOOP =================

def ciclo():
    global contador

    while True:
        contador += 1

        log(f"===== CICLO {contador} =====")

        try:
            if dentro_horario():
                log("Dentro de horario → ejecutando")

                datos = obtener_datos()
                enviar_sheets(datos)

            else:
                log("Fuera de horario")

        except Exception as e:
            log("ERROR GLOBAL")
            log(str(e))
            log(traceback.format_exc())

            reset_driver()

        if contador >= 30:
            log("Reinicio preventivo driver")
            reset_driver()
            contador = 0

        time.sleep(540)

# ================= MAIN =================

if __name__ == "__main__":
    log("SERVICIO INICIADO")

    threading.Thread(target=ciclo, daemon=True).start()

    app.run(host="0.0.0.0", port=10000)
