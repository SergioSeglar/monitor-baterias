import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

CHROMEDRIVER_PATH = "/usr/bin/chromedriver"  # Ruta estándar en Railway
BASE_URL = "http://87.106.124.228:3000"
COOKIE = {
    "name": "grafana_session",
    "value": "dd88454d575a37340ea2ae0ff9ec85b4",
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
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    service = Service(CHROMEDRIVER_PATH)
    driver = webdriver.Chrome(service=service, options=options)

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
    creds = ServiceAccountCredentials.from_json_keyfile_name("credenciales.json", scope)
    client = gspread.authorize(creds)

    sheet = client.open_by_key("1qe6aOpnrxwFDLoqwPJfcnzJRM4psbDrHG-h7fZk8RhA")
    worksheet = sheet.worksheet("Datos")

    encabezados = [["BATERÍA", "SOC (%)", "VOLTAJE", "AMPERAJE", "ÚLTIMA ACTUALIZACIÓN"]]
    nombres = [[nombre] for nombre, _ in baterias]
    worksheet.update("A1:E1", encabezados)
    worksheet.update("A2:A6", nombres)

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    valores = [[f"{soc}%", voltaje, f"{amperaje}A", timestamp] for soc, voltaje, amperaje in resultados]
    worksheet.update("B2:E6", valores)

if __name__ == "__main__":
    resultados = obtener_datos()
    enviar_a_google_sheets(resultados)
    print("Datos enviados correctamente.")
