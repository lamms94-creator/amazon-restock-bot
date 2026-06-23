FROM python:3.12-slim

WORKDIR /app

# Instalar dependencias del sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copiar e instalar dependencias Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código y archivos
COPY bot.py .
COPY products.json .

# Crear volumen para persistir el estado de productos
VOLUME ["/app"]

CMD ["python", "bot.py"]
