FROM python:3.11-slim

# System-Abhängigkeiten
RUN apt-get update && apt-get install -y \
    ffmpeg \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python-Pakete installieren
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Whisper-Modell vorab herunterladen (spart Zeit beim ersten Start)
RUN python3 -c "import whisper; whisper.load_model('base')"

# App-Dateien kopieren
COPY . .

# Downloads-Verzeichnis erstellen
RUN mkdir -p downloads

EXPOSE 8080

CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--timeout", "300", "--workers", "1", "app:app"]
