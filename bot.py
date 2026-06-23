"""
Amazon Restock Bot - v2
Monitorea productos de Amazon y envía alertas por WhatsApp via Twilio.
Usa requests-html con mejor evasión de detección.
"""

import time
import json
import logging
import os
import random
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from twilio.rest import Client

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],
)
log = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
TWILIO_SID      = os.environ["TWILIO_ACCOUNT_SID"]
TWILIO_TOKEN    = os.environ["TWILIO_AUTH_TOKEN"]
TWILIO_WA       = os.environ["TWILIO_WHATSAPP_FROM"]
MY_WA           = os.environ["MY_WHATSAPP_NUMBER"]
CHECK_INTERVAL  = int(os.getenv("CHECK_INTERVAL_SECONDS", "600"))  # 10 min
PRODUCTS_FILE   = Path(os.getenv("PRODUCTS_FILE", "products.json"))

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]

# ── Helpers ───────────────────────────────────────────────────────────────────

def load_products():
    if not PRODUCTS_FILE.exists():
        PRODUCTS_FILE.write_text(json.dumps([], indent=2))
        return []
    return json.loads(PRODUCTS_FILE.read_text())

def save_products(products):
    PRODUCTS_FILE.write_text(json.dumps(products, indent=2, ensure_ascii=False))

def get_session():
    session = requests.Session()
    ua = random.choice(USER_AGENTS)
    session.headers.update({
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "es-MX,es;q=0.8,en-US;q=0.5,en;q=0.3",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Cache-Control": "max-age=0",
    })
    return session

def extract_asin(url: str) -> str:
    """Extrae el ASIN de una URL de Amazon."""
    import re
    match = re.search(r'/(?:dp|gp/product)/([A-Z0-9]{10})', url)
    return match.group(1) if match else ""

def check_availability(url: str) -> dict:
    asin = extract_asin(url)
    # Usar URL limpia con el ASIN para evitar parámetros de tracking
    clean_url = f"https://www.amazon.com.mx/dp/{asin}" if asin else url

    session = get_session()

    # Primero visitar la home de Amazon para parecer un navegador real
    try:
        session.get("https://www.amazon.com.mx", timeout=10)
        time.sleep(random.uniform(2, 4))
    except Exception:
        pass

    try:
        resp = session.get(clean_url, timeout=20)
        resp.raise_for_status()
    except requests.RequestException as e:
        return {"available": False, "title": "?", "price": "?", "error": str(e)}

    # Detectar si Amazon nos bloqueó (CAPTCHA)
    if "robot" in resp.text.lower() or "captcha" in resp.text.lower() or len(resp.text) < 5000:
        log.warning("  ⚠️ Posible bloqueo/CAPTCHA detectado")
        return {"available": False, "title": "?", "price": "?", "error": "CAPTCHA/blocked"}

    soup = BeautifulSoup(resp.text, "html.parser")

    # Título
    title_el = soup.select_one("#productTitle")
    title = title_el.get_text(strip=True)[:80] if title_el else "Sin título"

    # Precio — múltiples selectores
    price = None
    for sel in [
        ".a-price .a-offscreen",
        "#priceblock_ourprice",
        "#priceblock_dealprice",
        ".a-price-whole",
        "#apex_desktop .a-price .a-offscreen",
        "#corePrice_desktop .a-offscreen",
    ]:
        el = soup.select_one(sel)
        if el:
            price = el.get_text(strip=True)
            break
    price = price or "Precio no encontrado"

    # Disponibilidad
    add_cart   = soup.select_one("#add-to-cart-button")
    buy_now    = soup.select_one("#buy-now-button")
    avail_el   = soup.select_one("#availability span, #outOfStock")
    avail_text = avail_el.get_text(strip=True).lower() if avail_el else ""

    out_keywords = ["no disponible", "agotado", "unavailable", "out of stock",
                    "temporalmente", "no está disponible"]
    in_keywords  = ["en stock", "disponible", "in stock", "quedan", "en existencia",
                    "solo queda", "en camino"]

    if add_cart or buy_now:
        available = True
    elif any(k in avail_text for k in in_keywords):
        available = True
    elif any(k in avail_text for k in out_keywords):
        available = False
    else:
        # Si no hay botón pero tampoco dice "agotado", verificar si hay precio
        available = price != "Precio no encontrado"

    return {"available": available, "title": title, "price": price, "error": None}

def send_whatsapp(message: str):
    client = Client(TWILIO_SID, TWILIO_TOKEN)
    client.messages.create(body=message, from_=TWILIO_WA, to=MY_WA)
    log.info("✅ WhatsApp enviado.")

def format_alert(product, info, event):
    now = datetime.now().strftime("%d/%m/%Y %H:%M")
    if event == "restock":
        return (f"🟢 *¡RESTOCK DETECTADO!*\n\n"
                f"📦 *{product['name']}*\n"
                f"💰 {info['price']}\n"
                f"🔗 {product['url']}\n\n🕐 {now}")
    else:
        return (f"🔴 *Producto AGOTADO*\n\n"
                f"📦 *{product['name']}*\n"
                f"🔗 {product['url']}\n\n🕐 {now}")

# ── Main loop ─────────────────────────────────────────────────────────────────

def run():
    log.info("🤖 Amazon Restock Bot v2 iniciado.")
    send_whatsapp("🤖 *Amazon Restock Bot v2 activado*\nMonitoreando tus productos Pokémon TCG...")

    while True:
        products = load_products()
        changed = False

        for p in products:
            name = p.get("name", p["url"])
            log.info(f"Revisando: {name}")

            info        = check_availability(p["url"])
            prev_status = p.get("last_status")
            curr_status = info["available"]

            if info["error"] == "CAPTCHA/blocked":
                log.warning(f"  Bloqueado por Amazon, esperando más tiempo...")
                time.sleep(random.uniform(30, 60))
                continue

            if info["error"]:
                log.warning(f"  Error: {info['error']}")
                continue

            status_str = "✅ En stock" if curr_status else "❌ Sin stock"
            log.info(f"  {status_str} — {info['price']}")

            if prev_status is False and curr_status is True:
                log.info(f"  🔔 RESTOCK: {name}")
                send_whatsapp(format_alert(p, info, "restock"))
            elif prev_status is True and curr_status is False:
                log.info(f"  📴 AGOTADO: {name}")
                send_whatsapp(format_alert(p, info, "out_of_stock"))

            p["last_status"]  = curr_status
            p["last_checked"] = datetime.now().isoformat()
            p["last_price"]   = info["price"]
            p["last_title"]   = info["title"]
            changed = True

            # Pausa más larga entre productos para no ser detectado
            time.sleep(random.uniform(8, 15))

        if changed:
            save_products(products)

        log.info(f"⏳ Próxima revisión en {CHECK_INTERVAL // 60} min...\n")
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    run()
