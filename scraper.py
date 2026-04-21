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

USERNAME = os.environ.get("GRAFANA_USER")
PASSWORD = os.environ.get("GRAFANA_PASSWORD")

baterias = [
    ("BATERÍA 10", "http://87.106.124.228:3000/d/U_0RUIJnz/lgv-10-em0522000366001-48v-gprs_s_439?orgId=121&refresh=1m"),
    ("BATERÍA 9", "http://87.106.124.228:3000/d/hssJ_tY4k/lgv-9-em1423001154001-48v-315ah-gprs_s_23205?orgId=121&refresh=1m"),
    ("BATERÍA 8", "http://87.106.124.228:3000/d/mpPEGXkSk/lgv-8-em3223002731001-48v-315ah-gprs_s_23597?refresh=1m"),
    ("BATERÍA 7", "http://87.106.124.228:3000/d/5zlPqHZSz/lgv-7-em3223002713001-48v-315ah-gprs_s_23473?orgId=121&refresh=1m"),
    ("BATERÍA 6", "http://87.106.124.228:3000/d/FjZH7jL4k/lgv-6-em1423001156001-48v-315ah-gprs_s_23177?orgId=121&refresh=1m"),
]

def crear_driver():
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.binary_location = "/usr/bin/chromium"

    return webdriver.Chrome(options=options)

def limpiar_valor(valor):
    return float(valor.replace('%', '').replace('V', '').replace('A', '').replace(',', '.').strip())

def login(driver):
    print("🔐 Haciendo login...")

    driver.get(BASE_URL)

    WebDriverWait(driver, 20).until(
        EC.presence_of_element_located((By.NAME, "username"))
    )

    driver.find_element(By.NAME, "username").send_keys(USERNAME)
    driver.find_element(By.NAME, "password").send_keys(PASSWORD)

    driver.find_element(By.XPATH, "//button").click()

    # esperar a salir del login
    WebDriverWait(driver, 20).until(
        lambda d: "/login" not in d.current_url
    )

    print("✅ Login correcto")

def esperar_datos(driver):
    try:
        WebDriverWait(driver, 30).until(
            lambda d: len(d.find_elements(By.CLASS_NAME, "flot-temp-elem")) >= 3
        )
        return True
    except:
        return False

def obtener_datos():
    driver = crear_driver()

    login(driver)

    resultados = []

    for nombre, url in baterias:
        print(f"\n📡 {nombre}")
        driver.get(url)

        if not esperar_datos(driver):
            print("⚠️ Reintentando carga...")
            driver.refresh()
            time.sleep(5)

        elements = driver.find_elements(By.CLASS_NAME, "flot-temp-elem")

        try:
            if len(elements) >= 6:
                textos = [e.text for e in elements]

                soc = limpiar_valor(textos[0])
                voltaje = textos[1]
                amperaje = limpiar_valor(textos[5])

                print(f"✅ SOC: {soc}% | VOLT: {voltaje} | AMP: {amperaje}")
                resultados.append((soc, voltaje, amperaje))
            else:
                raise Exception("Datos insuficientes")

        except Exception as e:
            print(f"❌ Error: {e}")
            resultados.append(("N/A", "N/A", "N/A"))

        time.sleep(2)

    driver.quit()
    return resultados

def enviar_a_google_sheets(resultados):
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
    ]

    creds_dict = json.loads(os.environ["GOOGLE_CREDENTIALS_JSON"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)

    sheet = client.open_by_key("1qe6aOpnrxwFDLoqwPJfcnzJRM4psbDrHG-h7fZk8RhA")
    ws = sheet.worksheet("Datos")

    ws.update("A1:E1", [["BATERÍA", "SOC (%)", "VOLTAJE", "AMPERAJE", "ÚLTIMA ACTUALIZACIÓN"]])
    ws.update("A2:A6", [[nombre] for nombre, _ in baterias])

    timestamp = datetime.now(timezone("Europe/Madrid")).strftime("%Y-%m-%d %H:%M:%S")

    valores = [[f"{soc}%", voltaje, f"{amp}A", timestamp] for soc, voltaje, amp in resultados]

    ws.update("B2:E6", valores)

def bucle():
    while True:
        ahora = datetime.now(timezone("Europe/Madrid"))
        hora = ahora.hour
        dia = ahora.weekday()

        ejecutar = (
            (dia in range(0, 5) and hora >= 22) or
            (dia in range(1, 6) and hora < 6)
        )

        if ejecutar:
            print(f"\n⏱ Ejecutando... {ahora.strftime('%H:%M:%S')}")
            datos = obtener_datos()
            enviar_a_google_sheets(datos)
        else:
            print(f"😴 Fuera de horario {ahora.strftime('%H:%M:%S')}")

        time.sleep(600)

@app.route("/")
def home():
    return "OK - Monitor activo"

if __name__ == "__main__":
    threading.Thread(target=bucle).start()
    app.run(host="0.0.0.0", port=10000)
