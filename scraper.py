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
# CONFIGURACION GENERAL
# =========================================================

app = Flask(__name__)

ZONA_HORARIA = timezone("Europe/Madrid")
INTERVALO_SEGUNDOS = 60

BASE_URL = "http://87.106.124.228:3000/login"

GRAFANA_USER = os.environ.get("GRAFANA_USER")
GRAFANA_PASSWORD = os.environ.get("GRAFANA_PASSWORD")

SPREADSHEET_ID = "1qe6aOpnrxwFDLoqwPJfcnzJRM4psbDrHG-h7fZk8RhA"
NOMBRE_HOJA = "Datos"

monitor_iniciado = False
monitor_lock = threading.Lock()


# =========================================================
# BATERIAS
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
    print("DIAG 0: Preparando Chromium y Selenium...", flush=True)

    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-background-networking")
    options.add_argument("--disable-renderer-backgrounding")
    options.add_argument("--window-size=1920,1080")

    options.binary_location = "/usr/bin/chromium"

    driver = webdriver.Chrome(options=options)

    # No esperar indefinidamente a que terminen de cargar todos los recursos.
    driver.set_page_load_timeout(90)
    driver.set_script_timeout(30)

    print("DIAG 0.1: Chromium iniciado correctamente.", flush=True)

    return driver



# =========================================================
# LOGIN GRAFANA: DIAGNOSTICOS
# =========================================================

def login(driver):
    if not GRAFANA_USER or not GRAFANA_PASSWORD:
        raise RuntimeError(
            "Faltan GRAFANA_USER o GRAFANA_PASSWORD "
            "en las variables de entorno."
        )

    print("DIAG 1: Inicio del login de Grafana.", flush=True)

    print("DIAG 2: Abriendo la página de login...", flush=True)

try:
    driver.get(BASE_URL)

except Exception as e:
    print(
        f"DIAG AVISO: La carga de Grafana tardó demasiado: "
        f"{type(e).__name__}: {e}",
        flush=True
    )

    # Comprobar si, pese al tiempo de espera, el navegador llegó a abrir
    # una página donde se pueda continuar con el inicio de sesión.
    try:
        print(
            f"DIAG URL después del aviso: {driver.current_url}",
            flush=True
        )

        print(
            f"DIAG Título después del aviso: {driver.title}",
            flush=True
        )

    except Exception as comprobacion:
        print(
            f"DIAG ERROR: Chromium no responde: {comprobacion}",
            flush=True
        )
        raise

    print(
        f"DIAG 3: Página abierta. URL actual: {driver.current_url}",
        flush=True
    )

    try:
        print(
            f"DIAG 3.1: Título de la página: {driver.title}",
            flush=True
        )
    except Exception:
        pass

    wait = WebDriverWait(driver, 45)

    print("DIAG 4: Esperando el campo de usuario...", flush=True)

    try:
        user = wait.until(
            EC.presence_of_element_located(
                (By.NAME, "username")
            )
        )

    except Exception as e:
        print(
            f"DIAG ERROR: No aparece el campo de usuario: "
            f"{type(e).__name__}: {e}",
            flush=True
        )
        print(
            f"DIAG URL actual: {driver.current_url}",
            flush=True
        )

        try:
            print(
                f"DIAG título actual: {driver.title}",
                flush=True
            )
        except Exception:
            pass

        raise

    print("DIAG 5: Campo de usuario encontrado.", flush=True)

    pwd = driver.find_element(
        By.NAME,
        "password"
    )

    user.send_keys(GRAFANA_USER)
    pwd.send_keys(GRAFANA_PASSWORD)

    print(
        "DIAG 6: Credenciales introducidas; enviando formulario.",
        flush=True
    )

    driver.find_element(
        By.XPATH,
        "//button[@type='submit']"
    ).click()

    print(
        "DIAG 7: Formulario enviado; esperando que termine el login...",
        flush=True
    )

    try:
        WebDriverWait(driver, 45).until(
            lambda d: "/login" not in d.current_url
        )

    except Exception as e:
        print(
            f"DIAG ERROR: Grafana no confirmó el login: "
            f"{type(e).__name__}: {e}",
            flush=True
        )

        print(
            f"DIAG URL después del login: {driver.current_url}",
            flush=True
        )

        try:
            print(
                f"DIAG título después del login: {driver.title}",
                flush=True
            )
        except Exception:
            pass

        raise

    print(
        f"DIAG 8: Sesión de Grafana iniciada. "
        f"URL: {driver.current_url}",
        flush=True
    )


# =========================================================
# ESPERA DEL DASHBOARD
# =========================================================

def esperar_dashboard(driver):
    WebDriverWait(driver, 45).until(
        lambda d: d.execute_script(
            "return document.readyState"
        ) == "complete"
    )

    time.sleep(2)


# =========================================================
# LECTURA DE LAS SEIS BATERIAS
# =========================================================

def obtener_datos():
    driver = None
    resultados = []

    try:
        driver = crear_driver()

        login(driver)

        for nombre, url in baterias:
            print(
                f"Consultando {nombre}...",
                flush=True
            )

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

                resultados.append(
                    (soc, volt, amp)
                )

                print(
                    f"{nombre}: {soc} | {volt} | {amp}",
                    flush=True
                )

            except Exception as e:
                print(
                    f"ERROR consultando {nombre}: "
                    f"{type(e).__name__}: {e}",
                    flush=True
                )

                resultados.append(
                    ("N/A", "N/A", "N/A")
                )

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
            "Falta GOOGLE_CREDENTIALS_JSON "
            "en las variables de entorno."
        )

    creds_dict = json.loads(
        credenciales_json
    )

    creds = ServiceAccountCredentials.from_json_keyfile_dict(
        creds_dict,
        scope
    )

    client = gspread.authorize(
        creds
    )

    sheet = client.open_by_key(
        SPREADSHEET_ID
    )

    ws = sheet.worksheet(
        NOMBRE_HOJA
    )

    ts = datetime.now(
        ZONA_HORARIA
    ).strftime("%Y-%m-%d %H:%M:%S")

    # Actualiza la tabla A1:E7.
    # No añade una fila histórica por cada ciclo.
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
        values=[
            [nombre]
            for nombre, _ in baterias
        ],
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
        f"Google Sheets actualizado: {ts}",
        flush=True
    )


# =========================================================
# MONITOR CONTINUO 24/7
# =========================================================

def loop():
    print(
        "Monitor continuo iniciado: seis baterías, 24/7.",
        flush=True
    )

    while True:
        inicio = time.monotonic()

        try:
            hora = datetime.now(
                ZONA_HORARIA
            ).strftime("%Y-%m-%d %H:%M:%S")

            print(
                f"\nNuevo ciclo: {hora}",
                flush=True
            )

            datos = obtener_datos()

            print(
                f"Resultado del ciclo: {datos}",
                flush=True
            )

            enviar_a_google_sheets(
                datos
            )

            print(
                "Ciclo completado correctamente.",
                flush=True
            )

        except Exception as e:
            print(
                f"ERROR en el ciclo: "
                f"{type(e).__name__}: {e}",
                flush=True
            )

        duracion = time.monotonic() - inicio

        espera = max(
            5,
            INTERVALO_SEGUNDOS - duracion
        )

        print(
            f"Duración del ciclo: {duracion:.1f} s. "
            f"Próximo ciclo en {espera:.1f} s.",
            flush=True
        )

        time.sleep(
            espera
        )


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
        "Iniciando aplicación de monitorización...",
        flush=True
    )

    iniciar_monitor()

    puerto = int(
        os.environ.get("PORT", 10000)
    )

    app.run(
        host="0.0.0.0",
        port=puerto,
        threaded=True
    )
