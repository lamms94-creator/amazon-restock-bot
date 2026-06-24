"""
Amazon Restock Bot - v5
- Usa ScraperAPI para evitar bloqueos de Amazon
- Maneja limite de mensajes de Twilio sin caerse
- No manda alertas falsas si el producto ya se agotó
"""

import time
import json
import logging
import os
import random
from datetime import datetime, date
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],
)
log = logging.getLogger(__name__)

TWILIO_SID     = os.environ["TWILIO_ACCOUNT_SID"]
TWILIO_TOKEN   = os.environ["TWILIO_AUTH_TOKEN"]
TWILIO_WA      = os.environ["TWILIO_WHATSAPP_FROM"]
MY_WA          = os.environ["MY_WHATSAPP_NUMBER"]
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL_SECONDS", "600"))
PRODUCTS_FILE  = Path(os.getenv("PRODUCTS_FILE", "products.json"))
SCRAPER_KEY    = os.environ["SCRAPER_API_KEY"]
SCRAPER_URL    = "https://api.scraperapi.com"

messages_blocked_today = False
blocked_date = None

def load_products():
    if not PRODUCTS_FILE.exists():
        PRODUCTS_FILE.write_text(json.dumps([], indent=2))
        return []
    return json.loads(PRODUCTS_FILE.read_text())

def save_products(products):
    PRODUCTS_FILE.write_text(json.dumps(products, indent=2, ensure_ascii=False))

def extract_asin(url: str) -> str:
    import re
    match = re.search(r'/(?:dp|gp/product)/([A-Z0-9]{10})', url)
    return match.group(1) if match else ""

def check_availability(url: str) -> dict:
    asin = extract_asin(url)
    clean_url = f"https://www.amazon.com.mx/dp/{asin}" if asin else url

    params = {
        "api_key": SCRAPER_KEY,
        "url": clean_url,
        "country_code": "mx",
        "device_type": "desktop",
    }

    try:
        resp = requests.get(SCRAPER_URL, params=params, timeout=60)
        resp.raise_for_status()
    except requests.RequestException as e:
        return {"available": False, "title": "?", "price": "?", "error": str(e)}

    if len(resp.text) < 3000:
        return {"available": False, "title": "?", "price": "?", "error": "Respuesta muy corta"}

    soup = BeautifulSoup(resp.text, "html.parser")

    title_el = soup.select_one("#productTitle")
    title = title_el.get_text(strip=True)[:80] if title_el else "Sin título"

    price = None
    for sel in [
        ".a-price .a-offscreen",
        "#priceblock_ourprice",
        "#priceblock_dealprice",
        "#corePrice_desktop .a-offscreen",
        "#apex_desktop .a-price .a-offscreen",
    ]:
        el = soup.select_one(sel)
        if el:
            price = el.get_text(strip=True)
            break
    price = price or "Precio no encontrado"

    add_cart   = soup.select_one("#add-to-cart-button")
    buy_now    = soup.select_one("#buy-now-button")
    avail_el   = soup.select_one("#availability span")
    avail_text = avail_el.get_text(strip=True).lower() if avail_el else ""

    out_kw = ["no disponible", "agotado", "unavailable", "out of stock", "temporalmente"]
    in_kw  = ["en stock", "disponible", "in stock", "quedan", "en existencia"]

    if add_cart or buy_now:
        available = True
    elif any(k in avail_text for k in in_kw):
        available = True
    elif any(k in avail_text for k in out_kw):
        available = False
    else:
        available = price != "Precio no encontrado"

    return {"available": available, "title": title, "price": price, "error": None}

def send_whatsapp(message: str) -> bool:
    global messages_blocked_today, blocked_date

    if messages_blocked_today and blocked_date == date.today():
        return False

    try:
        client = Client(TWILIO_SID, TWILIO_TOKEN)
        client.messages.create(body=message, from_=TWILIO_WA, to=MY_WA)
        log.info("✅ WhatsApp enviado.")
        messages_blocked_today = False
        return True

    except TwilioRestException as e:
        if "63038" in str(e) or "daily messages limit" in str(e).lower() or "429" in str(e):
            log.warning("⚠️ Límite diario de Twilio alcanzado. Se reintentará mañana.")
            messages_blocked_today = True
            blocked_date = date.today()
            return False
        else:
            log.error(f"Error de Twilio: {e}")
            return False

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

def run():
    global messages_blocked_today, blocked_date

    log.info("🤖 Amazon Restock Bot v5 iniciado.")
    send_whatsapp("🤖 *Amazon Restock Bot v5 activo*\n✅ Listo para monitorear tus productos Pokémon TCG")

    while True:
        # Resetear bloqueo si cambió el día
        if blocked_date and blocked_date != date.today():
            log.info("🌅 Nuevo día — límite de Twilio reiniciado")
            messages_blocked_today = False
            blocked_date = None

        products = load_products()
        changed = False

        for p in products:
            name = p.get("name", p["url"])
            log.info(f"Revisando: {name}")

            info        = check_availability(p["url"])
            prev_status = p.get("last_status")
            curr_status = info["available"]

            if info["error"]:
                log.warning(f"  Error: {info['error']}")
                continue

            status_str = "✅ En stock" if curr_status else "❌ Sin stock"
            log.info(f"  {status_str} — {info['price']}")

            # Solo notificar si HAY stock en este momento
            # Si el límite de Twilio está activo, marcar como pendiente en el producto
            if prev_status is False and curr_status is True:
                log.info(f"  🔔 RESTOCK detectado: {name}")
                sent = send_whatsapp(format_alert(p, info, "restock"))
                if not sent:
                    # Guardar que tiene alerta pendiente
                    p["pending_alert"] = "restock"
                    log.warning(f"  📋 Alerta guardada — se verificará stock antes de enviar mañana")
                else:
                    p.pop("pending_alert", None)

            elif prev_status is True and curr_status is False:
                log.info(f"  📴 Se agotó: {name}")
                p.pop("pending_alert", None)  # Cancelar alerta pendiente si ya se agotó
                send_whatsapp(format_alert(p, info, "out_of_stock"))

            else:
                # Verificar si hay alerta pendiente del día anterior
                if p.get("pending_alert") == "restock" and curr_status is True:
                    log.info(f"  📤 Enviando alerta pendiente de restock: {name}")
                    sent = send_whatsapp(format_alert(p, info, "restock"))
                    if sent:
                        p.pop("pending_alert", None)
                elif p.get("pending_alert") == "restock" and curr_status is False:
                    log.info(f"  ❌ Alerta pendiente cancelada — ya no hay stock: {name}")
                    p.pop("pending_alert", None)

            p["last_status"]  = curr_status
            p["last_checked"] = datetime.now().isoformat()
            p["last_price"]   = info["price"]
            p["last_title"]   = info["title"]
            changed = True

            time.sleep(random.uniform(3, 6))

        if changed:
            save_products(products)

        log.info(f"⏳ Próxima revisión en {CHECK_INTERVAL // 60} min...\n")
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    run()
