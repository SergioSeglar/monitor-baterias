import os
import json
import time
from datetime import datetime
from flask import Flask
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from pytz import timezone
import logging

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# Configuración
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

def limpiar_valor(valor):
    return float(valor.replace('%', '').replace('V', '').replace('A', '').replace(',', '.').strip())

def obtener_datos():
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    driver = webdriver.Chrome(options=chrome_options)

    driver.get(BASE_URL)
    time.sleep(2)
    driver.add_cookie(COOKIE)

    resultados = []
    for _, url in baterias:
        driver.get(url)
        time.sleep(7)
        elements = driver.find_elements(By.CLASS_NAME, "flot-temp-elem")
        if len(elements) >= 6:
            soc = limpiar_valor(elements[0].text)
            voltaje = elements[1].text
            amperaje = limpiar_valor(elements[5].text)
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

    worksheet.update("A1:E1", [["BATERÍA", "SOC (%)", "VOLTAJE", "AMPERAJE", "ÚLTIMA ACTUALIZACIÓN"]])
    worksheet.update("A2:A6", [[nombre] for nombre, _ in baterias])

    timestamp = datetime.now(timezone("Europe/Madrid")).strftime("%Y-%m-%d %H:%M:%S")
    valores = [[f"{soc}%", voltaje, f"{amperaje}A", timestamp] for soc, voltaje, amperaje in resultados]
    worksheet.update("B2:E6", valores)

def ejecutar_monitoreo():
    hora = datetime.now(timezone("Europe/Madrid")).hour
    if hora >= 22 or hora < 6:
        logging.info("Ejecutando monitoreo de baterías...")
        datos = obtener_datos()
        enviar_a_google_sheets(datos)
        logging.info("Monitoreo completado.")
    else:
        logging.info("Fuera del horario (22:00 - 6:00). No se ejecuta el monitoreo.")

@app.route("/")
def home():
    logging.info("Llamada desde cron-job recibida, ejecutando monitoreo...")
    ejecutar_monitoreo()
    return "✅ Monitoreo de baterías ejecutado correctamente."

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
