import logging
import os
import re
import subprocess
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

load_dotenv()

SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN")
SLACK_APP_TOKEN = os.environ.get("SLACK_APP_TOKEN")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.1:8b")
EDGE_TTS_SCRIPT = os.environ.get("EDGE_TTS_SCRIPT", "")
WHISPER_BIN = os.environ.get("WHISPER_BIN", "whisper")
OLLAMA_BIN = os.environ.get("OLLAMA_BIN", "ollama")
NODE_BIN = os.environ.get("NODE_BIN", "node")
TMP_DIR = Path(os.environ.get("TMP_DIR", "/tmp/c2e-app"))
TMP_RETENTION_HOURS = int(os.environ.get("TMP_RETENTION_HOURS", "24"))
LOG_DIR = Path(os.environ.get("LOG_DIR", str(Path(__file__).parent / "logs")))
LOG_FILE = LOG_DIR / os.environ.get("LOG_FILE", "c2e.log")
LOG_MAX_BYTES = int(os.environ.get("LOG_MAX_BYTES", str(5 * 1024 * 1024)))
LOG_BACKUP_COUNT = int(os.environ.get("LOG_BACKUP_COUNT", "5"))

TMP_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s:%(funcName)s: %(message)s"

root_logger = logging.getLogger()
root_logger.setLevel(LOG_LEVEL)

stream_handler = logging.StreamHandler()
stream_handler.setFormatter(logging.Formatter(LOG_FORMAT))
root_logger.addHandler(stream_handler)

file_handler = RotatingFileHandler(
    LOG_FILE,
    maxBytes=LOG_MAX_BYTES,
    backupCount=LOG_BACKUP_COUNT,
    encoding="utf-8",
)
file_handler.setFormatter(logging.Formatter(LOG_FORMAT))
root_logger.addHandler(file_handler)

app = App(token=SLACK_BOT_TOKEN)
logger = logging.getLogger("c2e")


def run_cmd(cmd: list[str]) -> str:
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.strip() or "command failed")
    return p.stdout.strip()


def cleanup_tmp_dir(retention_hours: int = TMP_RETENTION_HOURS):
    cutoff = time.time() - retention_hours * 3600
    removed = 0
    for p in TMP_DIR.glob("*"):
        try:
            if p.is_file() and p.stat().st_mtime < cutoff:
                p.unlink(missing_ok=True)
                removed += 1
        except Exception:
            logger.exception("Failed to clean temp file: %s", p)
    if removed:
        logger.info("Temp cleanup removed %s old files", removed)


def clean_ollama(text: str) -> str:
    # strip ANSI/control chars
    text = re.sub(r"\x1B\[[0-9;?]*[ -/]*[@-~]", "", text)
    text = re.sub(r"[\x00-\x1F\x7F]", "", text)
    return text.strip()


def translate_zh_to_en(chinese: str) -> str:
    prompt = (
        "Translate the following Chinese to English. "
        "Keep names, numbers, dates, and IDs exact. "
        "Do not add facts. Output only English text in natural style.\n\n"
        f"Chinese:\n{chinese}"
    )
    out = run_cmd([OLLAMA_BIN, "run", OLLAMA_MODEL, prompt])
    out = clean_ollama(out)
    return out or "(translation failed)"


def tts_edge(text: str, out_mp3: Path) -> Path:
    if not EDGE_TTS_SCRIPT:
        raise RuntimeError("EDGE_TTS_SCRIPT not configured")
    run_cmd([
        NODE_BIN,
        EDGE_TTS_SCRIPT,
        text,
        "--voice",
        "en-US-AriaNeural",
        "--output",
        str(out_mp3),
    ])
    return out_mp3


def find_recent_user_audio_file(channel_id: str, user_id: str) -> Optional[dict]:
    history = app.client.conversations_history(channel=channel_id, limit=15)
    for msg in history.get("messages", []):
        if msg.get("user") != user_id:
            continue
        for f in msg.get("files", []):
            if is_media_with_audio(f):
                return f
    return None


def transcribe_audio(audio_path: Path, task: str = "transcribe") -> str:
    run_cmd([
        WHISPER_BIN,
        str(audio_path),
        "--model",
        "turbo",
        "--task",
        task,
        "--output_format",
        "txt",
        "--output_dir",
        str(TMP_DIR),
    ])
    txt_path = TMP_DIR / f"{audio_path.stem}.txt"
    if not txt_path.exists():
        raise RuntimeError("transcript file not found")
    return txt_path.read_text(encoding="utf-8").strip()


def download_slack_file(url: str, out_path: Path):
    headers = {"Authorization": f"Bearer {SLACK_BOT_TOKEN}"}
    r = requests.get(url, headers=headers, timeout=60)
    r.raise_for_status()
    out_path.write_bytes(r.content)


def process_slack_audio_file(slack_file: dict, channel: str, thread_ts: Optional[str] = None, fast: bool = False):
    if not is_media_with_audio(slack_file):
        return False

    cleanup_tmp_dir()

    file_id = slack_file.get("id", "unknown")
    file_name = slack_file.get("name", file_id)
    mode_label = "transcribe → English voice (fast)" if fast else "transcribe → translate → English voice"
    logger.info("Processing file id=%s name=%s channel=%s fast=%s", file_id, file_name, channel, fast)

    post_kwargs = {
        "channel": channel,
        "text": f"Got it — processing `{file_name}` now ({mode_label})...",
    }
    if thread_ts:
        post_kwargs["thread_ts"] = thread_ts
    app.client.chat_postMessage(**post_kwargs)

    local_audio = TMP_DIR / f"{file_id}{media_extension(slack_file)}"
    download_slack_file(slack_file["url_private_download"], local_audio)
    logger.info("Downloaded source media to %s", local_audio)

    if fast:
        en = transcribe_audio(local_audio, task="translate")
    else:
        zh = transcribe_audio(local_audio, task="transcribe")
        en = translate_zh_to_en(zh)

    out_mp3 = TMP_DIR / f"{file_id}_en.mp3"
    tts_edge(en, out_mp3)

    upload_kwargs = {
        "channel": channel,
        "file": str(out_mp3),
        "title": "C2E English Voice",
        "initial_comment": f"English text:\n{en}",
    }
    if thread_ts:
        upload_kwargs["thread_ts"] = thread_ts
    app.client.files_upload_v2(**upload_kwargs)

    logger.info("Uploaded English voice file for id=%s to channel=%s fast=%s", file_id, channel, fast)
    return True


def is_media_with_audio(slack_file: dict) -> bool:
    """Accept true audio files and common video containers that carry audio tracks."""
    mimetype = (slack_file.get("mimetype") or "").lower()
    if mimetype.startswith("audio/"):
        return True
    if mimetype.startswith("video/"):
        return True

    name = (slack_file.get("name") or "").lower()
    ext = Path(name).suffix
    return ext in {".m4a", ".mp3", ".wav", ".mp4", ".mov", ".aac", ".ogg", ".webm"}


def media_extension(slack_file: dict) -> str:
    name = (slack_file.get("name") or "").lower()
    ext = Path(name).suffix
    if ext:
        return ext
    # fallback for Slack audio/video payloads without filename extension
    mimetype = (slack_file.get("mimetype") or "").lower()
    if "mpeg" in mimetype:
        return ".mp3"
    if "wav" in mimetype:
        return ".wav"
    if "ogg" in mimetype:
        return ".ogg"
    if mimetype.startswith("video/"):
        return ".mp4"
    return ".m4a"


@app.event("message")
def handle_dm_messages(body, say):
    event = body.get("event", {})

    # Only handle DMs; ignore bot messages and message edits
    if event.get("channel_type") != "im":
        return
    if event.get("bot_id") or event.get("subtype"):
        return

    channel = event.get("channel")
    thread_ts = event.get("ts")
    user = event.get("user", "unknown")

    # Audio/video file uploaded in DM
    files = event.get("files", [])
    if files:
        for f in files:
            try:
                handled = process_slack_audio_file(f, channel=channel, thread_ts=thread_ts)
                if not handled:
                    continue
            except Exception as e:
                logger.exception("DM audio processing failed")
                say(f"C2E failed: {e}", thread_ts=thread_ts)
        return

    # Plain text message in DM
    zh = (event.get("text") or "").strip()
    if not zh:
        return

    logger.info("DM text from user=%s channel=%s", user, channel)
    try:
        en = translate_zh_to_en(zh)
        out_mp3 = TMP_DIR / f"dm_{user}_{thread_ts.replace('.', '_')}.mp3"
        tts_edge(en, out_mp3)
        app.client.files_upload_v2(
            channel=channel,
            file=str(out_mp3),
            title="C2E English Voice",
            initial_comment=f"English text:\n{en}",
        )
    except Exception as e:
        logger.exception("DM text processing failed")
        say(f"C2E failed: {e}")


@app.command("/c2e")
def c2e_command(ack, respond, command):
    ack()
    raw = (command.get("text") or "").strip()

    # Parse --fast flag
    fast = "--fast" in raw
    zh = raw.replace("--fast", "").strip()

    logger.info("/c2e invoked by user=%s channel=%s fast=%s has_text=%s",
                command.get("user_id"), command.get("channel_id"), fast, bool(zh))
    try:
        if not zh:
            # Slash commands cannot directly carry binary file uploads.
            # Fallback: grab the user's most recent audio/video file in channel.
            f = find_recent_user_audio_file(command["channel_id"], command["user_id"])
            if not f:
                respond("No recent audio/video file found. Upload a file, then run `/c2e` again (or use `/c2e <Chinese text>`).")
                return
            process_slack_audio_file(f, channel=command["channel_id"], thread_ts=None, fast=fast)
            return

        if fast:
            respond("`--fast` requires audio input — Whisper can only translate audio, not text. Use `/c2e <Chinese text>` (without `--fast`) for text input.")
            return

        en = translate_zh_to_en(zh)
        out_mp3 = TMP_DIR / f"c2e_{command['trigger_id'].replace('.', '_')}.mp3"
        tts_edge(en, out_mp3)
        app.client.files_upload_v2(
            channel=command["channel_id"],
            file=str(out_mp3),
            title="C2E English Voice",
            initial_comment=f"English text:\n{en}",
        )
    except Exception as e:
        respond(f"C2E failed: {e}")



if __name__ == "__main__":
    if not SLACK_BOT_TOKEN or not SLACK_APP_TOKEN:
        raise SystemExit("Missing SLACK_BOT_TOKEN or SLACK_APP_TOKEN")
    cleanup_tmp_dir()
    logger.info(
        "Starting c2e Slack app (tmp_dir=%s, retention=%sh, log_file=%s)",
        TMP_DIR,
        TMP_RETENTION_HOURS,
        LOG_FILE,
    )
    SocketModeHandler(app, SLACK_APP_TOKEN).start()
