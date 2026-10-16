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


# =========================================================
# CONFIGURACIÓN GENERAL
# =========================================================

app = Flask(__name__)

ZONA_HORARIA = timezone("Europe/Madrid")

# Objetivo: iniciar un ciclo aproximadamente cada 60 segundos.
INTERVALO_SEGUNDOS = 60

BASE_URL = "http://87.106.124.228:3000/login"

GRAFANA_USER = os.environ.get("GRAFANA_USER")
GRAFANA_PASSWORD = os.environ.get("GRAFANA_PASSWORD")

SPREADSHEET_ID = "1qe6aOpnrxwFDLoqwPJfcnzJRM4psbDrHG-h7fZk8RhA"
NOMBRE_HOJA = "Datos"

# Evita que se inicien dos monitores dentro del mismo proceso.
monitor_iniciado = False
monitor_lock = threading.Lock()


# =========================================================
# BATERÍAS
# =========================================================

baterias = [
    (
        "BATERÍA 10",
        "http://87.106.124.228:3000/d/U_0RUIJnz/lgv-10-em0522000366001-48v-gprs_s_439?orgId=121&refresh=1m"
    ),
    (
        "BATERÍA 9",
        "http://87.106.124.228:3000/d/hssJ_tY4k/lgv-9-em1423001154001-48v-315ah-gprs_s_23205?orgId=121&refresh=1m"
    ),
    (
        "BATERÍA 8",
        "http://87.106.124.228:3000/d/mpPEGXkSk/lgv-8-em3223002731001-48v-315ah-gprs_s_23597?orgId=121&refresh=1m"
    ),
    (
        "BATERÍA 7",
        "http://87.106.124.228:3000/d/5zlPqHZSz/lgv-7-em3223002713001-48v-315ah-gprs_s_23473?orgId=121&refresh=1m"
    ),
    (
        "BATERÍA 6",
        "http://87.106.124.228:3000/d/FjZH7jL4k/lgv-6-em1423001156001-48v-315ah-gprs_s_23177?orgId=121&refresh=1m"
    ),
    (
        "BATERÍA 1",
        "http://87.106.124.228:3000/d/VXjh1AADz/lgv-1-em1926001340001-48v-315ah-disp-tfts-3557-gprs_w_4g_25678?orgId=121&refresh=1m"
    ),
]


# =========================================================
# CHROME
# =========================================================

def crear_driver():
    options = Options()

    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")

    options.binary_location = "/usr/bin/chromium"

    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(45)

    return driver


# =========================================================
# LOGIN GRAFANA
# =========================================================

def login(driver):
    if not GRAFANA_USER or not GRAFANA_PASSWORD:
        raise RuntimeError(
            "Faltan GRAFANA_USER o GRAFANA_PASSWORD en las variables de entorno."
        )

    print("🔐 Iniciando sesión en Grafana...", flush=True)

    driver.get(BASE_URL)

    wait = WebDriverWait(driver, 45)

    user = wait.until(
        EC.presence_of_element_located((By.NAME, "username"))
    )

    pwd = driver.find_element(By.NAME, "password")

    user.send_keys(GRAFANA_USER)
    pwd.send_keys(GRAFANA_PASSWORD)

    driver.find_element(
        By.XPATH,
        "//button[@type='submit']"
    ).click()

    WebDriverWait(driver, 45).until(
        lambda d: "/login" not in d.current_url
    )

    print("✅ Sesión de Grafana iniciada.", flush=True)


# =========================================================
# ESPERA DEL DASHBOARD
# =========================================================

def esperar_dashboard(driver):
    WebDriverWait(driver, 45).until(
        lambda d: d.execute_script(
            "return document.readyState"
        ) == "complete"
    )

    # Pequeña espera para que se representen los valores.
    time.sleep(2)


# =========================================================
# LECTURA DE LAS SEIS BATERÍAS
# =========================================================

def obtener_datos():
    driver = None
    resultados = []

    try:
        driver = crear_driver()

        login(driver)

        for nombre, url in baterias:
            print(f"📡 Consultando {nombre}...", flush=True)

            try:
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

                print(
                    f"Valores encontrados en {nombre}: {valores}",
                    flush=True
                )

                soc = next(
                    (v for v in valores if "%" in v),
                    "N/A"
                )

                volt = next(
                    (v for v in valores if "V" in v),
                    "N/A"
                )

                amp = next(
                    (v for v in valores if "A" in v),
                    "N/A"
                )

                resultados.append((soc, volt, amp))

                print(
                    f"✅ {nombre}: {soc} | {volt} | {amp}",
                    flush=True
                )

            except Exception as e:
                # Un fallo en una batería no impide intentar las siguientes.
                print(
                    f"❌ Error consultando {nombre}: {e}",
                    flush=True
                )

                resultados.append(("N/A", "N/A", "N/A"))

    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass

    return resultados


# =========================================================
# GOOGLE SHEETS
# =========================================================

def enviar_a_google_sheets(resultados):
    if len(resultados) != len(baterias):
        raise RuntimeError(
            f"Se esperaban {len(baterias)} resultados, "
            f"pero se recibieron {len(resultados)}."
        )

    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ]

    credenciales_json = os.environ.get(
        "GOOGLE_CREDENTIALS_JSON"
    )

    if not credenciales_json:
        raise RuntimeError(
            "Falta GOOGLE_CREDENTIALS_JSON en las variables de entorno."
        )

    creds_dict = json.loads(credenciales_json)

    creds = ServiceAccountCredentials.from_json_keyfile_dict(
        creds_dict,
        scope
    )

    client = gspread.authorize(creds)

    sheet = client.open_by_key(SPREADSHEET_ID)
    ws = sheet.worksheet(NOMBRE_HOJA)

    ts = datetime.now(ZONA_HORARIA).strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    # Se conserva la estructura original A:E.
    ws.update(
        values=[[
            "BATERÍA",
            "SOC",
            "VOLTAJE",
            "AMPERAJE",
            "FECHA"
        ]],
        range_name="A1:E1"
    )

    ws.update(
        values=[[nombre] for nombre, _ in baterias],
        range_name="A2:A7"
    )

    filas = [
        [soc, volt, amp, ts]
        for soc, volt, amp in resultados
    ]

    ws.update(
        values=filas,
        range_name="B2:E7"
    )

    print(
        f"📊 Google Sheets actualizado: {ts}",
        flush=True
    )


# =========================================================
# MONITOR CONTINUO 24/7
# =========================================================

def loop():
    print(
        "🚀 Monitor continuo iniciado: seis baterías, 24/7.",
        flush=True
    )

    while True:
        inicio = time.monotonic()

        try:
            hora = datetime.now(
                ZONA_HORARIA
            ).strftime("%Y-%m-%d %H:%M:%S")

            print(
                f"\n🔄 Nuevo ciclo: {hora}",
                flush=True
            )

            datos = obtener_datos()

            print(
                f"📋 Resultado del ciclo: {datos}",
                flush=True
            )

            enviar_a_google_sheets(datos)

            print(
                "✅ Ciclo completado correctamente.",
                flush=True
            )

        except Exception as e:
            print(
                f"❌ Error en el ciclo: {e}",
                flush=True
            )

        # Intentar mantener el inicio de los ciclos cerca de 60 s.
        # Si el ciclo tarda más de un minuto, espera 5 s antes
        # del siguiente intento para no crear un bucle sin pausa.
        duracion = time.monotonic() - inicio
        espera = max(5, INTERVALO_SEGUNDOS - duracion)

        print(
            f"⏳ Duración del ciclo: {duracion:.1f} s. "
            f"Próximo ciclo en {espera:.1f} s.",
            flush=True
        )

        time.sleep(espera)


# =========================================================
# FLASK
# =========================================================

@app.route("/")
def home():
    return "OK monitor activo 24/7", 200


@app.route("/health")
def health():
    return {
        "status": "ok",
        "monitor": "baterias",
        "timestamp": datetime.now(
            ZONA_HORARIA
        ).strftime("%Y-%m-%d %H:%M:%S")
    }, 200


# =========================================================
# ARRANQUE
# =========================================================

def iniciar_monitor():
    global monitor_iniciado

    with monitor_lock:
        if monitor_iniciado:
            return

        monitor_iniciado = True

    hilo = threading.Thread(
        target=loop,
        daemon=True,
        name="monitor-baterias"
    )

    hilo.start()


if __name__ == "__main__":
    print(
        "🚀 Iniciando aplicación de monitorización...",
        flush=True
    )

    iniciar_monitor()

    puerto = int(os.environ.get("PORT", 10000))

    app.run(
        host="0.0.0.0",
        port=puerto,
        threaded=True
    )
```
