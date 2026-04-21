import json
import time
from datetime import datetime

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# =========================
# CONFIG
# =========================

LOGIN_URL = "http://87.106.124.228:3000/login"

USER = "Porcelanosa"
PASSWORD = "J.Porcelanosa2022"

DATA_FILE = "data.json"

baterias = [
    ("BATERÍA 10", "http://87.106.124.228:3000/d/U_0RUIJnz/lgv-10-em0522000366001-48v-gprs_s_439?orgId=121&refresh=1m"),
    ("BATERÍA 9", "http://87.106.124.228:3000/d/hssJ_tY4k/lgv-9-em1423001154001-48v-315ah-gprs_s_23205?orgId=121&refresh=1m"),
    ("BATERÍA 8", "http://87.106.124.228:3000/d/mpPEGXkSk/lgv-8-em3223002731001-48v-315ah-gprs_s_23597?orgId=121&refresh=1m"),
    ("BATERÍA 7", "http://87.106.124.228:3000/d/5zlPqHZSz/lgv-7-em3223002713001-48v-315ah-gprs_s_23473?orgId=121&refresh=1m"),
    ("BATERÍA 6", "http://87.106.124.228:3000/d/FjZH7jL4k/lgv-6-em1423001156001-48v-315ah-gprs_s_23177?orgId=121&refresh=1m"),
]

# =========================
# DRIVER
# =========================

def driver_init():
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    return webdriver.Chrome(options=options)

# =========================
# LOG
# =========================

def log(msg):
    print(f"[SCRAPER] {msg}")

# =========================
# LOGIN
# =========================

def login(driver):
    log("LOGIN Grafana...")

    driver.get(LOGIN_URL)

    WebDriverWait(driver, 20).until(
        EC.presence_of_element_located((By.NAME, "username"))
    )

    driver.find_element(By.NAME, "username").send_keys(USER)
    pwd = driver.find_element(By.NAME, "password")
    pwd.send_keys(PASSWORD)
    pwd.send_keys("\n")

    WebDriverWait(driver, 20).until(
        lambda d: "login" not in d.current_url
    )

    log("LOGIN OK")

# =========================
# EXTRACCIÓN REAL
# =========================

def extract_values(driver):
    WebDriverWait(driver, 20).until(
        EC.presence_of_all_elements_located((By.CSS_SELECTOR, "span.flot-temp-elem"))
    )

    elems = driver.find_elements(By.CSS_SELECTOR, "span.flot-temp-elem")

    values = [e.text.strip() for e in elems if e.text.strip()]

    soc = next((v for v in values if "%" in v), None)
    volt = next((v for v in values if "V" in v), None)
    amp = next((v for v in values if "A" in v), None)

    return soc, volt, amp

# =========================
# GUARDAR JSON
# =========================

def save(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

# =========================
# FUNCIÓN PRINCIPAL (CRON JOB)
# =========================

def run_scraper_once():
    log("INICIO SCRAPER")

    driver = driver_init()

    try:
        login(driver)

        results = []
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        for nombre, url in baterias:

            try:
                log(f"📡 {nombre}")

                driver.get(url)

                soc, volt, amp = extract_values(driver)

                log(f"{nombre} → SOC:{soc} | VOLT:{volt} | AMP:{amp}")

                results.append({
                    "nombre": nombre,
                    "soc": soc,
                    "volt": volt,
                    "amp": amp,
                    "time": now
                })

            except Exception as e:
                log(f"❌ ERROR {nombre}")
                log(str(e))

                results.append({
                    "nombre": nombre,
                    "soc": None,
                    "volt": None,
                    "amp": None,
                    "time": now
                })

        save({
            "updated": now,
            "data": results
        })

        log("FIN OK")

    except Exception as e:
        log("❌ ERROR GLOBAL")
        log(str(e))

    finally:
        driver.quit()