"""
Amazon Restock Bot
Monitorea productos de Amazon y envía alertas por WhatsApp via Twilio.
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

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
TWILIO_SID        = os.environ["TWILIO_ACCOUNT_SID"]
TWILIO_TOKEN      = os.environ["TWILIO_AUTH_TOKEN"]
TWILIO_WHATSAPP   = os.environ["TWILIO_WHATSAPP_FROM"]   # "whatsapp:+14155238886"
MY_WHATSAPP       = os.environ["MY_WHATSAPP_NUMBER"]     # "whatsapp:+521XXXXXXXXXX"

CHECK_INTERVAL    = int(os.getenv("CHECK_INTERVAL_SECONDS", "300"))   # 5 min default
PRODUCTS_FILE     = Path(os.getenv("PRODUCTS_FILE", "products.json"))

# User-Agents rotativos para evitar bloqueos
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
]

# ── Helpers ───────────────────────────────────────────────────────────────────

def load_products() -> list[dict]:
    """Carga la lista de productos desde products.json."""
    if not PRODUCTS_FILE.exists():
        log.warning("products.json no encontrado, creando ejemplo...")
        example = [
            {
                "name": "Ejemplo - Nintendo Switch",
                "url": "https://www.amazon.com.mx/dp/B07VGRJDFY",
                "last_status": None,
            }
        ]
        PRODUCTS_FILE.write_text(json.dumps(example, indent=2, ensure_ascii=False))
        return example
    return json.loads(PRODUCTS_FILE.read_text())


def save_products(products: list[dict]) -> None:
    PRODUCTS_FILE.write_text(json.dumps(products, indent=2, ensure_ascii=False))


def get_headers() -> dict:
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept-Language": "es-MX,es;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }


def check_availability(url: str) -> dict:
    """
    Revisa si un producto de Amazon está disponible.
    Retorna dict con keys: available (bool), title (str), price (str), error (str|None)
    """
    try:
        resp = requests.get(url, headers=get_headers(), timeout=15)
        resp.raise_for_status()
    except requests.RequestException as e:
        return {"available": False, "title": "?", "price": "?", "error": str(e)}

    soup = BeautifulSoup(resp.text, "html.parser")

    # Título
    title_el = soup.select_one("#productTitle")
    title = title_el.get_text(strip=True) if title_el else "Sin título"

    # Precio
    price_el = (
        soup.select_one(".a-price .a-offscreen") or
        soup.select_one("#priceblock_ourprice") or
        soup.select_one("#priceblock_dealprice")
    )
    price = price_el.get_text(strip=True) if price_el else "Precio no encontrado"

    # Disponibilidad — Amazon usa varios selectores
    availability_el = soup.select_one("#availability span")
    add_to_cart      = soup.select_one("#add-to-cart-button")
    buy_now          = soup.select_one("#buy-now-button")

    avail_text = availability_el.get_text(strip=True).lower() if availability_el else ""

    out_of_stock_keywords = [
        "no disponible", "agotado", "currently unavailable",
        "out of stock", "no está disponible", "temporalmente agotado",
    ]
    in_stock_keywords = [
        "en stock", "disponible", "in stock", "quedan", "en existencia",
    ]

    if add_to_cart or buy_now:
        available = True
    elif any(kw in avail_text for kw in in_stock_keywords):
        available = True
    elif any(kw in avail_text for kw in out_of_stock_keywords):
        available = False
    else:
        # Si no hay botón de compra y el texto es ambiguo → sin stock
        available = False

    return {"available": available, "title": title, "price": price, "error": None}


def send_whatsapp(message: str) -> None:
    """Envía mensaje de WhatsApp via Twilio."""
    client = Client(TWILIO_SID, TWILIO_TOKEN)
    client.messages.create(
        body=message,
        from_=TWILIO_WHATSAPP,
        to=MY_WHATSAPP,
    )
    log.info("✅ WhatsApp enviado.")


def format_alert(product: dict, info: dict, event: str) -> str:
    now = datetime.now().strftime("%d/%m/%Y %H:%M")
    if event == "restock":
        emoji = "🟢"
        header = "¡RESTOCK DETECTADO!"
    else:  # out_of_stock
        emoji = "🔴"
        header = "Producto AGOTADO"

    return (
        f"{emoji} *{header}*\n\n"
        f"📦 *Producto:* {product['name']}\n"
        f"💰 *Precio:* {info['price']}\n"
        f"🔗 {product['url']}\n\n"
        f"🕐 {now}"
    )


# ── Main loop ─────────────────────────────────────────────────────────────────

def run():
    log.info("🤖 Amazon Restock Bot iniciado.")
    send_whatsapp("🤖 *Amazon Restock Bot activado*\nMonitoreando tus productos...")

    while True:
        products = load_products()
        changed  = False

        for p in products:
            name = p.get("name", p["url"])
            log.info(f"Revisando: {name}")

            info          = check_availability(p["url"])
            prev_status   = p.get("last_status")      # True / False / None
            curr_status   = info["available"]

            if info["error"]:
                log.warning(f"  Error al revisar {name}: {info['error']}")
                continue

            log.info(f"  {'✅ En stock' if curr_status else '❌ Sin stock'} — {info['price']}")

            # Notificar solo cuando CAMBIA el estado
            if prev_status is False and curr_status is True:
                log.info(f"  🔔 RESTOCK detectado para {name}")
                msg = format_alert(p, info, "restock")
                send_whatsapp(msg)

            elif prev_status is True and curr_status is False:
                log.info(f"  📴 Se agotó {name}")
                msg = format_alert(p, info, "out_of_stock")
                send_whatsapp(msg)

            p["last_status"]   = curr_status
            p["last_checked"]  = datetime.now().isoformat()
            p["last_price"]    = info["price"]
            p["last_title"]    = info["title"]
            changed = True

            # Pausa entre productos para no saturar Amazon
            time.sleep(random.uniform(3, 7))

        if changed:
            save_products(products)

        log.info(f"⏳ Próxima revisión en {CHECK_INTERVAL // 60} min...\n")
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    run()
