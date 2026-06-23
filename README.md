# 🤖 Amazon Restock Bot — WhatsApp Alerts

Bot que monitorea productos de Amazon y te avisa por **WhatsApp** cuando hay restock o cuando se agotan.

---

## ¿Cómo funciona?

```
products.json  →  bot.py revisa cada 5 min  →  Amazon cambia estado  →  WhatsApp alert 🔔
```

- Cada X minutos, el bot visita las URLs de Amazon que configuraste
- Detecta si un producto pasó de "sin stock" → "en stock" (RESTOCK) o viceversa
- Te manda un mensaje de WhatsApp al instante con nombre, precio y link

---

## Setup en 4 pasos

### Paso 1 — Crear cuenta en Twilio (gratis)

1. Ve a [https://www.twilio.com](https://www.twilio.com) y crea una cuenta gratuita
2. En el dashboard, copia tu **Account SID** y **Auth Token**
3. Ve a **Messaging → Try it out → Send a WhatsApp message**
4. Sigue las instrucciones para activar el **Sandbox de WhatsApp**:
   - Envía `join <palabra>` al número `+1 415 523 8886` desde tu WhatsApp
5. ¡Listo! Twilio Sandbox es **gratis** y perfecto para uso personal

### Paso 2 — Configurar las variables de entorno

Copia `.env.example` a `.env` y llena los valores:

```bash
cp .env.example .env
```

Edita `.env`:
```env
TWILIO_ACCOUNT_SID=ACxxxxxx...
TWILIO_AUTH_TOKEN=xxxxxx...
TWILIO_WHATSAPP_FROM=whatsapp:+14155238886
MY_WHATSAPP_NUMBER=whatsapp:+521XXXXXXXXXX   # tu número con +52
CHECK_INTERVAL_SECONDS=300
```

### Paso 3 — Agregar productos a monitorear

Edita `products.json` con las URLs que quieras rastrear:

```json
[
  {
    "name": "Nintendo Switch OLED Blanca",
    "url": "https://www.amazon.com.mx/dp/B098RL6SBJ",
    "last_status": null
  },
  {
    "name": "Tarjeta GPU RTX 4070",
    "url": "https://www.amazon.com.mx/dp/XXXXXXXXX",
    "last_status": null
  }
]
```

> 💡 **Tip:** Agrega tantos productos como quieras. El bot los revisa todos en cada ciclo.

### Paso 4 — Desplegar en Railway (recomendado — gratis)

Railway es la opción más sencilla para que corra 24/7 en la nube:

1. Ve a [https://railway.app](https://railway.app) y crea una cuenta (con GitHub)
2. Crea un **New Project → Deploy from GitHub**
3. Sube este repositorio a GitHub y selecciónalo
4. En Railway, ve a **Variables** y agrega todas las del `.env`
5. Railway detecta el `Dockerfile` automáticamente y despliega el bot

**Alternativas:**
- **Render.com** — también tiene plan gratuito, igual de fácil
- **VPS propio** — DigitalOcean / Linode (~$6/mes), mayor control

---

## Correr localmente (para pruebas)

```bash
# Instalar dependencias
pip install -r requirements.txt

# Cargar variables de entorno y correr
export $(cat .env | xargs)
python bot.py
```

---

## Estructura del proyecto

```
amazon-restock-bot/
├── bot.py            # 🤖 Lógica principal del bot
├── products.json     # 📋 Lista de productos a monitorear
├── requirements.txt  # 📦 Dependencias Python
├── Dockerfile        # 🐳 Para desplegar en la nube
├── railway.toml      # 🚂 Config para Railway
└── .env.example      # 🔑 Plantilla de variables de entorno
```

---

## Ejemplos de alertas que recibirás

**Restock detectado:**
```
🟢 ¡RESTOCK DETECTADO!

📦 Producto: Nintendo Switch OLED
💰 Precio: $7,999.00
🔗 https://www.amazon.com.mx/dp/B098RL6SBJ

🕐 15/06/2025 14:32
```

**Producto agotado:**
```
🔴 Producto AGOTADO

📦 Producto: PS5 Consola
💰 Precio no encontrado
🔗 https://www.amazon.com.mx/dp/B09KVSV3BX

🕐 15/06/2025 18:05
```

---

## Notas importantes

- **Amazon México** (`amazon.com.mx`) funciona de forma nativa
- Amazon puede **bloquear scraping** ocasionalmente; el bot rota User-Agents para reducir esto
- Si ves muchos errores, aumenta `CHECK_INTERVAL_SECONDS` a `600` (10 min)
- El archivo `products.json` se actualiza automáticamente con el último estado y precio
- Los logs se guardan en `bot.log`

---

## ¿Quieres más productos o más canales?

Puedes agregar **notificaciones por email** (con smtplib), **Telegram** (python-telegram-bot),
o conectar con **Google Sheets** como base de productos. ¡Solo pídelo!
