# Video Transcriber

Eine lokale Web-App zum Transkribieren von Instagram Reels, TikTok-Videos und YouTube-Videos per KI (OpenAI Whisper).

## Voraussetzungen

- Python 3.11+
- ffmpeg (`sudo apt install ffmpeg`)

## Installation

```bash
# Abhängigkeiten installieren
sudo pip3 install yt-dlp openai-whisper flask

# App starten
cd transcriber
python3.11 app.py
```

Dann im Browser öffnen: **http://localhost:7860**

## Verwendung

1. Link von Instagram, TikTok oder YouTube einfügen
2. Optional: Sprache auswählen (oder „Auto" für automatische Erkennung)
3. Auf **Transkribieren** klicken
4. Transkript wird angezeigt und kann kopiert werden

## Cookies für Login-geschützte Videos

Instagram, TikTok und YouTube blockieren Downloads ohne Anmeldung. So geht's:

1. Browser-Extension **[Get cookies.txt LOCALLY](https://chrome.google.com/webstore/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc)** installieren
2. Auf der jeweiligen Plattform einloggen
3. Extension öffnen → „Export cookies.txt" klicken
4. In der App: Cookies-Panel öffnen → Datei hochladen

Die Cookies werden lokal in `cookies.txt` gespeichert und automatisch für alle Downloads verwendet.

## Features

- **Plattformen**: Instagram Reels, TikTok, YouTube (und viele weitere via yt-dlp)
- **Sprachen**: Automatische Erkennung oder manuelle Auswahl (50+ Sprachen)
- **Zeitstempel**: Segmentierte Transkription mit Start/End-Zeiten
- **Verlauf**: Letzte 10 Transkriptionen werden lokal gespeichert
- **Privat**: Alles läuft lokal, keine Daten werden an externe Server gesendet

## Technologie

| Komponente | Technologie |
|---|---|
| Video-Download | yt-dlp |
| Audio-Transkription | OpenAI Whisper (base model) |
| Backend | Flask (Python) |
| Frontend | Vanilla HTML/CSS/JS |
