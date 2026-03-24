import os
import json
import time
import threading
from datetime import datetime
from flask import Flask
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from pytz import timezone

# --- FLASK SOLO PARA CRON-JOB ---
app = Flask(__name__)

# --- CONFIGURACIÓN ---
BASE_URL = "http://87.106.124.228:3000"
COOKIE = {
    "name": "grafana_session",
    "value": os.environ.get("GRAFANA_SESSION", ""),
    "domain": "87.106.124.228",
    "path": "/",
}

baterias = [
    ("BATERÍA 10", "http://87.106.124.228:3000/d/U_0RUIJnz/lgv-10-em0522000366001-48v-gprs_s_439?orgId=121&refresh=1m"),
    ("BATERÍA 9", "http://87.106.124.228:3000/d/hssJ_tY4k/lgv-9-em1423001154001-48v-315ah-gprs_s_23205?orgId=121&refresh=1m"),
    ("BATERÍA 8", "http://87.106.124.228:3000/d/mpPEGXkSk/lgv-8-em3223002731001-48v-315ah-gprs_s_23597?refresh=1m"),
    ("BATERÍA 7", "http://87.106.124.228:3000/d/5zlPqHZSz/lgv-7-em3223002713001-48v-315ah-gprs_s_23473?orgId=121&refresh=1m"),
    ("BATERÍA 6", "http://87.106.124.228:3000/d/FjZH7jL4k/lgv-6-em1423001156001-48v-315ah-gprs_s_23177?orgId=121&refresh=1m"),
]

# --- FUNCIONES ---
def limpiar_valor(valor):
    """Convierte un valor a float si es posible, devuelve None si no hay valor válido"""
    if not valor:
        return None
    valor = valor.replace('%', '').replace('V', '').replace('A', '').replace(',', '.').strip()
    if valor in ['N/', 'N/A', '-', '']:
        return None
    try:
        return float(valor)
    except:
        return None

def crear_driver():
    options = Options()
    options.binary_location = "/usr/bin/chromium"  # Path en Render
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    service = Service("/usr/bin/chromedriver")
    return webdriver.Chrome(service=service, options=options)

def obtener_datos():
    driver = crear_driver()
    driver.get(BASE_URL)
    time.sleep(2)
    driver.add_cookie(COOKIE)

    resultados = []
    for nombre, url in baterias:
        driver.get(url)
        time.sleep(4)
        elements = driver.find_elements(By.CLASS_NAME, "flot-temp-elem")
        if len(elements) >= 6:
            soc = limpiar_valor(elements[0].text) or "N/A"
            voltaje = elements[1].text
            amperaje = limpiar_valor(elements[5].text) or "N/A"
            resultados.append((soc, voltaje, amperaje))
        else:
            resultados.append(("N/A", "N/A", "N/A"))

    driver.quit()
    return resultados

def enviar_a_google_sheets(resultados):
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = json.loads(os.environ["GOOGLE_CREDENTIALS_JSON"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)

    sheet = client.open_by_key("1qe6aOpnrxwFDLoqwPJfcnzJRM4psbDrHG-h7fZk8RhA")
    worksheet = sheet.worksheet("Datos")

    timestamp = datetime.now(timezone("Europe/Madrid")).strftime("%Y-%m-%d %H:%M:%S")

    valores = [
        [
            nombre,
            f"{soc}%" if soc != "N/A" else "N/A",
            voltaje,
            f"{amperaje}A" if amperaje != "N/A" else "N/A",
            timestamp
        ]
        for (nombre, _), (soc, voltaje, amperaje) in zip(baterias, resultados)
    ]

    worksheet.update("A1:E6", [["BATERÍA","SOC (%)","VOLTAJE","AMPERAJE","ÚLTIMA ACTUALIZACIÓN"]] + valores)

def bucle():
    while True:
        try:
            ahora = datetime.now(timezone("Europe/Madrid"))
            hora = ahora.hour
            dia_semana = ahora.weekday()  # lunes=0

            ejecutar = (dia_semana in range(0,5) and hora >= 21) or (dia_semana in range(1,6) and hora < 6)

            if ejecutar:
                print(f"[INFO] Ejecutando monitoreo... ({ahora.strftime('%H:%M:%S')})")
                datos = obtener_datos()
                enviar_a_google_sheets(datos)
            else:
                print(f"[INFO] Fuera del horario permitido ({ahora.strftime('%H:%M:%S')})")
        except Exception as e:
            print(f"[ERROR] {e}")

        time.sleep(600)  # 10 minutos

# --- RUTA PARA CRON-JOB ---
@app.route("/")
def home():
    return "Monitoreo de baterías activo."

# --- INICIO ---
if __name__ == "__main__":
    threading.Thread(target=bucle, daemon=True).start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
