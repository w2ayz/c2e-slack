# c2e — Chinese to English for Slack

A Slack bot that converts Chinese text or audio/video into English text + an English voice MP3, using a fully local AI pipeline.

## How it works

```
User input (text or audio/video)
  → Whisper  (local STT — transcription)
  → Ollama   (local LLM — translation)
  → Edge TTS (neural voice — English MP3)
  → Slack    (text + MP3 uploaded to channel)
```

No cloud AI APIs required. Everything runs locally.

## Usage

### Text input

```
/c2e 你好，今天天气怎么样？
```

Translates the Chinese text via Ollama and uploads an English voice MP3 + text reply.

### Audio / video input (standard)

```
/c2e
```

Upload your audio or video file first, then run `/c2e` with no arguments. Because Slack slash commands cannot carry binary files directly, the bot finds your most recent media file in the channel and runs the full pipeline:

```
Whisper (transcribe) → Ollama (translate) → Edge TTS → Slack
```

### Audio / video input (fast mode)

```
/c2e --fast
```

Upload your audio or video file first, then run `/c2e --fast`. Skips Ollama entirely — Whisper translates directly to English in one step:

```
Whisper (transcribe + translate) → Edge TTS → Slack
```

Faster, but translation quality is lower than the standard pipeline. Does not work with text input.

### Event-driven (automatic)

The bot also listens on `message` and `file_shared` events — upload audio/video to a channel the bot is in and it processes automatically using the standard pipeline (no slash command needed).

### Supported media

`.m4a` `.mp3` `.wav` `.mp4` `.mov` `.aac` `.ogg` `.webm` and any `audio/*` or `video/*` MIME type.

### Mode comparison

| | `/c2e <text>` | `/c2e` (audio) | `/c2e --fast` (audio) |
|---|---|---|---|
| Input | Chinese text | Audio / video | Audio / video |
| Transcription | — | Whisper | Whisper |
| Translation | Ollama LLM | Ollama LLM | Whisper built-in |
| Voice output | Edge TTS | Edge TTS | Edge TTS |
| Speed | Fast | Slower | Faster |
| Translation quality | High | High | Lower |

## Local stack

| Component | Tool | Default |
|-----------|------|---------|
| Transcription | [Whisper](https://github.com/openai/whisper) CLI | `--model turbo` |
| Translation | [Ollama](https://ollama.com) | `qwen2.5:7b-instruct` |
| Text-to-speech | [Edge TTS](https://github.com/rany2/edge-tts) via `node-edge-tts` | `en-US-AriaNeural` |

## Prerequisites

- Python 3.9+
- Node.js 18+
- [Whisper](https://github.com/openai/whisper) installed and on PATH
- [Ollama](https://ollama.com) running locally with a model pulled (e.g. `ollama pull qwen2.5:7b-instruct`)
- A Slack app with Socket Mode enabled (see [Slack setup](#slack-setup))

## Installation

```bash
git clone https://github.com/<your-username>/c2e-slack.git
cd c2e-slack

# Python bot
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Node TTS script
npm install
```

## Configuration

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

| Variable | Required | Description |
|----------|----------|-------------|
| `SLACK_BOT_TOKEN` | ✓ | Bot token (`xoxb-...`) |
| `SLACK_APP_TOKEN` | ✓ | App-level token for Socket Mode (`xapp-...`) |
| `EDGE_TTS_SCRIPT` | ✓ | Absolute path to `tts-converter.js` |
| `OLLAMA_MODEL` | | Ollama model name (default: `llama3.1:8b`) |
| `NODE_BIN` | | Path to `node` binary (default: `node`) |
| `WHISPER_BIN` | | Path to `whisper` binary (default: `whisper`) |
| `OLLAMA_BIN` | | Path to `ollama` binary (default: `ollama`) |
| `TMP_DIR` | | Temp file directory (default: `/tmp/c2e-app`) |
| `TMP_RETENTION_HOURS` | | Hours before temp files are pruned (default: `24`) |
| `LOG_DIR` | | Log directory (default: `./logs`) |
| `LOG_FILE` | | Log filename (default: `c2e.log`) |
| `LOG_LEVEL` | | Log level (default: `INFO`) |
| `LOG_MAX_BYTES` | | Max log file size in bytes (default: `5242880`) |
| `LOG_BACKUP_COUNT` | | Number of rotating log backups (default: `5`) |

## Running

```bash
source .venv/bin/activate
python app.py
```

The bot connects via Socket Mode — no public URL or ngrok needed.

## Slack setup

1. Go to [api.slack.com/apps](https://api.slack.com/apps) → Create New App → From manifest.
2. Use the manifest below (update `display_information` as needed).
3. Install the app to your workspace.
4. Copy the Bot Token and App Token into `.env`.

### Slack manifest

```yaml
display_information:
  name: c2e
features:
  bot_user:
    display_name: c2e
    always_online: false
oauth_config:
  scopes:
    bot:
      - chat:write
      - files:read
      - files:write
      - channels:history
      - groups:history
settings:
  event_subscriptions:
    bot_events:
      - message.channels
      - message.groups
      - file_shared
  interactivity:
    is_enabled: true
  socket_mode_enabled: true
  token_rotation_enabled: false
```

After adding or changing scopes, reinstall the app to your workspace.

### Slash command

In your Slack app settings → Slash Commands → Create New Command:

| Field | Value |
|-------|-------|
| Command | `/c2e` |
| Short Description | Convert Chinese text or audio to English |
| Usage Hint | `[Chinese text] [--fast]` |

## File structure

```
c2e-slack/
├── app.py              # Slack bot (Python, Slack Bolt)
├── tts-converter.js    # Edge TTS CLI wrapper (Node.js)
├── requirements.txt    # Python dependencies
├── package.json        # Node dependencies
├── .env.example        # Environment variable template
└── .gitignore
```

## Translation modes

The LLM prompt supports four modes (pass via future `/c2e --mode` flag or extend as needed):

| Mode | Description |
|------|-------------|
| `natural` | Natural English (default) |
| `literal` | Word-for-word translation |
| `polished` | Fluent, publication-ready English |
| `summary` | Condensed English summary |

## Troubleshooting

| Symptom | Check |
|---------|-------|
| Bot doesn't respond | Verify Socket Mode is enabled and `SLACK_APP_TOKEN` is an `xapp-` token |
| No MP3 uploaded | Check `EDGE_TTS_SCRIPT` path and that `node` is on PATH |
| Blank translation | Check Ollama is running: `ollama list` |
| Whisper not found | Check `WHISPER_BIN` env var or run `which whisper` |
| Scopes error | Reinstall Slack app after adding scopes |
