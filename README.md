# kapso-issue-agent

Text a rough note to a WhatsApp number and get a clean GitHub issue back. An LLM drafts the title, body and labels, shows you the draft, and **only creates the issue after you reply YES**.

Built on [Kapso](https://kapso.com) (WhatsApp webhooks + send API) with FastAPI. About 270 lines of Python, 17 offline tests.

## Demo

An example conversation (text only, the bot never acts without your confirmation):

```
You:  login page par crash hota hai jab password galat ho

Bot:  *App crashes on login with wrong password*

      The login page crashes when an incorrect password is entered.

      Expected: an error message is shown.
      Actual: the app crashes.

      Labels: bug

      Reply YES to create this issue, or NO to cancel.

You:  YES

Bot:  Issue ban gaya: https://github.com/<you>/<repo>/issues/2
```

Also understood: `NO` / `cancel` to drop the draft, `help` for usage. Notes can be written in any language the LLM understands.

## How it works

```
WhatsApp -> Kapso -> POST /webhooks/whatsapp -> verify HMAC -> 200 OK (fast)
                                                  |
                                          background task
                                                  |
        dedup -> allow-list -> LLM draft -> preview -> YES -> GitHub issue -> reply with link
```

| File | Responsibility |
| --- | --- |
| `app/main.py` | Webhook endpoint, HMAC verification, payload parsing, dedup and allow-list checks |
| `app/issue_agent.py` | Conversation flow (note, preview, YES/NO), draft validation, GitHub issue creation |
| `app/llm.py` | Minimal client for any OpenAI-compatible chat API |
| `app/kapso.py` | Send text, mark as read and typing indicator through Kapso's WhatsApp API |
| `app/store.py` | SQLite: processed message ids and one pending draft per sender |
| `tests/` | Signature, payload shapes, batching, dedup, allow-list, YES/NO flow, LLM failure |

## Design decisions

- **Signature check on the raw body.** HMAC-SHA256 over the exact bytes received (`X-Webhook-Signature`), compared in constant time. Re-serialised JSON would not match.
- **Answer 200 first, work later.** Kapso retries when it does not get a fast 200, so the LLM and GitHub calls run in a background task.
- **Idempotency.** Retries and duplicate deliveries are dropped by message id.
- **Batched webhooks.** Buffered deliveries (`batch: true`) are unpacked and handled one by one.
- **Human in the loop.** An AI draft never becomes an issue without an explicit YES from the sender.
- **Allow-list.** The bot can write to a repository, so only numbers in `ALLOWED_SENDERS` can use it. Phone numbers are normalised to digits before comparing, because the UI shows `+92...` while the webhook sends `92...`.
- **Validated model output.** The LLM reply is parsed defensively (code fences and chatter are tolerated), the title is capped, and only labels from a fixed set (`bug`, `docs`, `idea`, `question`) are kept.
- **Provider-agnostic LLM.** Groq, Gemini, OpenRouter, Ollama, OpenAI: anything that speaks `/chat/completions`.
- **Least privilege.** Use a fine-grained GitHub token with only *Issues: read and write* on a single repository.

## Setup

Requires Python 3.10+.

### 1. Install

```bash
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                 # Windows: copy .env.example .env
```

### 2. Configure `.env`

| Variable | Required | Description |
| --- | --- | --- |
| `KAPSO_API_KEY` | yes | Kapso API key used to send replies |
| `WEBHOOK_SECRET` | yes | Secret you set when registering the webhook in Kapso. Requests without a valid signature get 401 |
| `ALLOWED_SENDERS` | yes | Comma-separated phone numbers allowed to use the bot, e.g. `+923001234567` |
| `LLM_BASE_URL` | yes | OpenAI-compatible base URL, e.g. `https://api.groq.com/openai/v1` |
| `LLM_API_KEY` | yes | Key for that provider |
| `LLM_MODEL` | yes | Model name from your provider's model list |
| `GITHUB_TOKEN` | yes | Fine-grained token, Issues: read and write on the target repo |
| `GITHUB_REPO` | yes | `owner/repo` where issues are created |
| `DB_PATH` | no | SQLite file, default `bot.db` |
| `LOG_PAYLOADS` | no | Set to `1` to print incoming payloads while you confirm field names. Turn it off afterwards, it logs phone numbers |

Put comments on their own line. Inline `# comments` after a value are not stripped by every loader (the Windows `start.ps1` launcher keeps them as part of the value), which breaks secrets.

### 3. Run

```bash
set -a; source .env; set +a          # bash. On Windows use: .\start.ps1
uvicorn app.main:app --reload
```

On Windows, `.\start.ps1` activates the venv, loads `.env` and starts the server.

Docker:

```bash
docker build -t kapso-issue-agent .
docker run --env-file .env -p 8000:8000 kapso-issue-agent
```

### 4. Expose it and register the webhook

```bash
ngrok http 8000                                  # or: cloudflared tunnel --url http://localhost:8000
```

In Kapso, connect the **sandbox** number (send the activation code from your phone to it once), then add a webhook:

- URL: `https://<your-tunnel>/webhooks/whatsapp`
- Event: `whatsapp.message.received`
- Secret: the same value as `WEBHOOK_SECRET`

Send a note from an allowed phone and reply `YES`. Tunnel URLs change on restart, so update the webhook URL when they do.

## Tests

```bash
python -m pytest -q
```

17 tests, no network and no API keys: they stub the LLM, GitHub and Kapso calls.

## Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| `401 invalid signature` | `WEBHOOK_SECRET` is empty, differs from Kapso's secret, or has trailing comment text from `.env`. Restart the server after editing `.env` |
| Nothing in the server log | Wrong tunnel URL in Kapso, tunnel not running, or sandbox not activated |
| `ignored message from a number not in ALLOWED_SENDERS` | Your number is missing from `ALLOWED_SENDERS` |
| Bot replies `Sorry, kuch masla hua` | See the `issue_agent error:` line in the log: bad LLM key or model, or GitHub token/repo problem |
| GitHub returns 404 on a private repo | The token has no access to that repo (GitHub reports missing access as 404) |

## Known limitations / next steps

- Text messages only (no media yet).
- WhatsApp's 24-hour window: free-form replies only work within 24h of the user's last message; a template fallback is the next step.
- One pending draft per sender: a new note replaces an unconfirmed one.
- The WhatsApp preview shows the first 700 characters of the body; the GitHub issue gets the full text.
- SQLite is fine for one instance; use Postgres plus a queue for scale.
- Replies are plain text; interactive YES/NO buttons would be a nicer UX.

See [`NOTES.md`](NOTES.md) for what I found while building on Kapso.