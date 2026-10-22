"""FastAPI webhook receiver for Kapso WhatsApp events."""
import hashlib
import hmac
import json
import os

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request

from . import issue_agent, kapso, store

app = FastAPI(title='kapso-issue-agent')


def valid_signature(raw: bytes, signature: str | None) -> bool:
    """HMAC-SHA256 (hex) of the RAW request body, keyed with the webhook secret."""
    secret = os.environ.get('WEBHOOK_SECRET', '')
    if not signature or not secret:
        return False
    signature = signature.removeprefix('sha256=')
    expected = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, expected)


def _norm(number: str) -> str:
    return ''.join(ch for ch in str(number) if ch.isdigit())


def allowed(sender: str) -> bool:
    """Only phone numbers listed in ALLOWED_SENDERS may talk to the bot (it can create issues)."""
    allow = {_norm(x) for x in os.getenv('ALLOWED_SENDERS', '').split(',') if x.strip()}
    return _norm(sender) in allow


def extract(ev: dict) -> dict | None:
    """Pull the fields we need out of a Kapso whatsapp.message.received payload."""
    msg = ev.get('message') or {}
    text = msg.get('content') or (msg.get('text') or {}).get('body')
    out = {
        'id': msg.get('id'),
        'sender': msg.get('from'),
        'text': text,
        'phone_number_id': ev.get('phone_number_id'),
    }
    return out if all(out.values()) else None


@app.get('/health')
def health():
    return {'ok': True}


@app.post('/webhooks/whatsapp')
async def webhook(req: Request, bg: BackgroundTasks):
    raw = await req.body()  # verify against the raw bytes, never re-serialized JSON
    if not valid_signature(raw, req.headers.get('x-webhook-signature')):
        raise HTTPException(status_code=401, detail='invalid signature')
    if req.headers.get('x-webhook-event') != 'whatsapp.message.received':
        return {'ok': True}
    body = json.loads(raw)
    if os.getenv('LOG_PAYLOADS') == '1':
        print('PAYLOAD:', json.dumps(body)[:2000])
    events = body['data'] if body.get('batch') else [body]  # buffered webhooks arrive as a batch
    for ev in events:
        bg.add_task(handle, ev)
    return {'ok': True}  # answer 200 fast; Kapso retries otherwise


async def handle(ev: dict) -> None:
    m = extract(ev)
    if not m:
        return  # non-text message or unknown shape
    if store.seen(m['id']):
        return  # duplicate delivery
    if not allowed(m['sender']):
        print('ignored message from a number not in ALLOWED_SENDERS')
        return
    await kapso.typing(m['phone_number_id'], m['id'])
    await issue_agent.handle_text(m['phone_number_id'], m['sender'], m['text'], m['id'])
