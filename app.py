import os
import uuid
import threading
import time
import hashlib
import secrets
import requests as http_requests
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory, session, redirect
import yt_dlp
import whisper

# Deno für YouTube JS-Runtime verfügbar machen (lokal)
os.environ["PATH"] = "/home/ubuntu/.deno/bin:/usr/local/bin:" + os.environ.get("PATH", "")

app = Flask(__name__, static_folder="static")
app.secret_key = os.environ.get("FLASK_SECRET_KEY", secrets.token_hex(32))

DOWNLOAD_DIR = Path(os.environ.get("DOWNLOAD_DIR", "/tmp/transcriber_downloads"))
DOWNLOAD_DIR.mkdir(exist_ok=True, parents=True)

# Supadata API Key
SUPADATA_API_KEY = "sd_8e4855c8561793a566320b077616d7be"
SUPADATA_BASE_URL = "https://api.supadata.ai/v1"

# ── Nutzer-Datenbank (gehashte Passwörter) ────────────────────────────────────
def _hash(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()

USERS = {
    "Geldgeldgeld1210998": _hash("X9!vQ7#Lm2@rT8$zP4&kY1%u"),
}

# Globaler Whisper-Model-Cache
_whisper_model = None
_model_lock = threading.Lock()


def get_whisper_model():
    global _whisper_model
    with _model_lock:
        if _whisper_model is None:
            print("Lade Whisper-Modell (base)...")
            _whisper_model = whisper.load_model("base")
            print("Whisper-Modell geladen.")
    return _whisper_model


def require_login(f):
    """Decorator: Gibt 401 zurück wenn nicht eingeloggt."""
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return jsonify({"error": "Nicht autorisiert.", "login_required": True}), 401
        return f(*args, **kwargs)
    return decorated


def detect_platform(url: str) -> str:
    url_lower = url.lower()
    if "instagram.com" in url_lower:
        return "instagram"
    elif "tiktok.com" in url_lower or "vm.tiktok.com" in url_lower:
        return "tiktok"
    elif "youtube.com" in url_lower or "youtu.be" in url_lower:
        return "youtube"
    elif "twitter.com" in url_lower or "x.com" in url_lower:
        return "twitter"
    elif "facebook.com" in url_lower or "fb.watch" in url_lower:
        return "facebook"
    else:
        return "other"


def transcribe_via_supadata(url: str, language: str = None) -> dict:
    params = {"url": url}
    if language:
        params["lang"] = language

    resp = http_requests.get(
        f"{SUPADATA_BASE_URL}/transcript",
        params=params,
        headers={"x-api-key": SUPADATA_API_KEY},
        timeout=60
    )

    if resp.status_code == 429:
        raise Exception("supadata_rate_limit")
    if resp.status_code == 402:
        raise Exception("supadata_quota_exceeded")
    if resp.status_code == 404:
        raise Exception("supadata_not_found")
    if resp.status_code != 200:
        try:
            err = resp.json()
            raise Exception(f"supadata_error:{err.get('message', resp.text[:100])}")
        except Exception as e:
            if "supadata_" in str(e):
                raise
            raise Exception(f"supadata_error:{resp.text[:100]}")

    data = resp.json()
    content = data.get("content", [])
    if not content:
        raise Exception("supadata_no_content")

    full_text = " ".join(item["text"] for item in content).strip()
    segments = [
        {
            "start": round(item.get("offset", 0) / 1000, 2),
            "end": round((item.get("offset", 0) + item.get("duration", 0)) / 1000, 2),
            "text": item["text"].strip(),
        }
        for item in content
    ]

    return {
        "text": full_text,
        "language": data.get("lang", "unknown"),
        "segments": segments,
        "method": "supadata",
    }


def download_audio(url: str, job_id: str) -> str:
    output_path = DOWNLOAD_DIR / job_id
    platform = detect_platform(url)

    extractor_args = {}
    if platform == "youtube":
        extractor_args["youtube"] = {"player_client": ["mweb"]}
    elif platform == "tiktok":
        extractor_args["tiktok"] = {"webpage_download": ["1"]}

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": str(output_path) + ".%(ext)s",
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "128",
        }],
        "quiet": True,
        "no_warnings": True,
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
        },
        "extractor_args": extractor_args,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    for f in DOWNLOAD_DIR.glob(f"{job_id}.*"):
        return str(f)
    raise FileNotFoundError(f"Audio-Datei für Job {job_id} nicht gefunden.")


def transcribe_audio_whisper(audio_path: str, language: str = None) -> dict:
    model = get_whisper_model()
    options = {}
    if language:
        options["language"] = language
    result = model.transcribe(audio_path, **options)
    return {
        "text": result["text"].strip(),
        "language": result.get("language", "unknown"),
        "segments": [
            {
                "start": round(seg["start"], 2),
                "end": round(seg["end"], 2),
                "text": seg["text"].strip(),
            }
            for seg in result.get("segments", [])
        ],
        "method": "whisper",
    }


def cleanup_file(path: str, delay: int = 300):
    def _delete():
        time.sleep(delay)
        try:
            os.remove(path)
        except Exception:
            pass
    threading.Thread(target=_delete, daemon=True).start()


# ─── Auth Endpunkte ───────────────────────────────────────────────────────────

@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json(force=True)
    username = (data.get("username") or "").strip()
    password = (data.get("password") or "")

    stored_hash = USERS.get(username)
    if not stored_hash or stored_hash != _hash(password):
        time.sleep(1)  # Brute-Force-Schutz
        return jsonify({"error": "Falscher Benutzername oder Passwort."}), 401

    session["logged_in"] = True
    session["username"] = username
    session.permanent = True
    return jsonify({"success": True, "username": username})


@app.route("/api/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"success": True})


@app.route("/api/auth-status", methods=["GET"])
def auth_status():
    return jsonify({
        "logged_in": bool(session.get("logged_in")),
        "username": session.get("username", ""),
    })


# ─── Transcribe Endpunkt (geschützt) ─────────────────────────────────────────

@app.route("/api/transcribe", methods=["POST"])
@require_login
def transcribe():
    data = request.get_json(force=True)
    url = (data.get("url") or "").strip()
    language = data.get("language") or None

    if not url:
        return jsonify({"error": "Kein URL angegeben."}), 400

    platform = detect_platform(url)
    job_id = str(uuid.uuid4())

    # Supadata (primär)
    supadata_error = None
    try:
        result = transcribe_via_supadata(url, language=language)
        return jsonify({
            "platform": platform,
            "url": url,
            "language": result["language"],
            "text": result["text"],
            "segments": result["segments"],
            "method": "supadata",
        })
    except Exception as e:
        supadata_error = str(e)
        if "supadata_rate_limit" in supadata_error:
            return jsonify({"error": "Zu viele Anfragen. Bitte warte kurz."}), 429
        if "supadata_quota_exceeded" in supadata_error:
            return jsonify({"error": "Monatliches Limit erreicht. Upgrade auf supadata.ai erforderlich."}), 402
        print(f"Supadata fehlgeschlagen ({supadata_error}), versuche Whisper-Fallback...")

    # Whisper Fallback
    try:
        audio_path = download_audio(url, job_id)
    except Exception as e:
        err_msg = str(e)
        err_lower = err_msg.lower()
        if any(k in err_lower for k in ["login required", "sign in", "cookies", "login page", "rate-limit reached or login"]):
            return jsonify({"error": "Dieses Video erfordert eine Anmeldung."}), 401
        if "rate-limit" in err_lower or "too many requests" in err_lower:
            return jsonify({"error": "Rate-Limit erreicht. Bitte warte kurz."}), 429
        if any(k in err_lower for k in ["not available", "private", "removed", "does not exist"]):
            return jsonify({"error": "Dieses Video ist nicht öffentlich verfügbar oder wurde entfernt."}), 403
        if "unsupported url" in err_lower:
            return jsonify({"error": "Diese URL wird nicht unterstützt."}), 400
        return jsonify({"error": f"Transkription fehlgeschlagen: {err_msg}"}), 500

    try:
        result = transcribe_audio_whisper(audio_path, language=language)
    except Exception as e:
        cleanup_file(audio_path, delay=0)
        return jsonify({"error": f"Transkription fehlgeschlagen: {str(e)}"}), 500

    cleanup_file(audio_path)

    return jsonify({
        "platform": platform,
        "url": url,
        "language": result["language"],
        "text": result["text"],
        "segments": result["segments"],
        "method": "whisper",
    })


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "supadata": True,
        "whisper_loaded": _whisper_model is not None,
    })


@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve_static(path):
    static_dir = app.static_folder
    if path and (Path(static_dir) / path).exists():
        return send_from_directory(static_dir, path)
    return send_from_directory(static_dir, "index.html")


if __name__ == "__main__":
    threading.Thread(target=get_whisper_model, daemon=True).start()
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)
