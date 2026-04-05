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

### Behavior by context

**DM with c2e app — no command needed:**

| Input | Trigger | Response |
|-------|---------|----------|
| Send Chinese text | Automatic | English text + voice MP3 in Chat |
| Upload voice/audio file | Automatic | English text + voice MP3 in Chat |

**In a channel:**

| Input | Trigger | Response |
|-------|---------|----------|
| Upload voice/audio file | `/c2e` after upload | Processes most recent audio file |
| Upload voice/audio file | `/c2e --fast` after upload | Same, skips Ollama (faster) |
| Chinese text | `/c2e <text>` | English text + voice MP3 |

### `/c2e <Chinese text>` — text input

```
/c2e 你好，今天天气怎么样？
```

Translates Chinese text via Ollama and replies with English text + voice MP3.

### `/c2e` — audio input (standard)

Upload your audio or video file first, then run `/c2e`. The bot finds your most recent media file in the channel:

```
Whisper (transcribe) → Ollama (translate) → Edge TTS → Slack
```

### `/c2e --fast` — audio input (fast mode)

```
/c2e --fast
```

Skips Ollama — Whisper translates directly to English in one step:

```
Whisper (transcribe + translate) → Edge TTS → Slack
```

Faster but lower translation quality. Does not work with text input.

### Supported media

`.m4a` `.mp3` `.wav` `.mp4` `.mov` `.aac` `.ogg` `.webm` and any `audio/*` or `video/*` MIME type.

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
      - im:history
settings:
  event_subscriptions:
    bot_events:
      - message.channels
      - message.groups
      - message.im
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

## Changelog

### v1.2.0
- Add `_processing` dedup set — prevents duplicate Slack events from racing two Whisper processes
- Add `_whisper_lock` — serializes Whisper calls to prevent CPU/RAM overload
- Whisper logs exit code, stdout, stderr for easier debugging
- `find_recent_user_audio_file` returns `(file, msg_ts)` tuple — `/c2e` reply now threads under the original upload
- DM handler: dual check (`channel_type` + `D`-prefix), explicit `file_share` subtype allow, `break` after first audio file
- `handle_file_shared_events` explicit noop stub — no Slack Bolt unhandled-event warnings
- `logger.exception` in all error paths — full tracebacks written to log file

### v1.1.0
- DM auto-trigger: text and audio processed automatically, no command needed
- DM responses post to Chat tab via legacy `files.upload`
- Channels: require `/c2e` or `/c2e --fast` to trigger (no auto-processing)
- Added `--fast` mode: Whisper `--task translate` skips Ollama
- Fixed DM detection via channel ID `D`-prefix
- Fixed `file_share` subtype filter (iOS voice memos previously missed)

### v1.0.1
- Added full usage instructions and mode comparison table to README
- Updated slash command usage hint to include `--fast`

### v1.0.0
- Initial release: `/c2e` slash command, audio file processing, `--fast` mode
- Local pipeline: Whisper → Ollama → Edge TTS
- Socket Mode — no public URL required
