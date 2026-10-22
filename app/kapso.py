"""Thin client for Kapso's WhatsApp send API (Meta proxy)."""
import os

import httpx

BASE = 'https://api.kapso.ai/meta/whatsapp/v24.0'


def _headers() -> dict:
    return {'X-API-Key': os.environ['KAPSO_API_KEY']}


async def _post(phone_number_id: str, payload: dict) -> dict:
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.post(f'{BASE}/{phone_number_id}/messages', headers=_headers(), json=payload)
        r.raise_for_status()
        return r.json()


async def send_text(phone_number_id: str, to: str, body: str, reply_to: str | None = None) -> dict:
    payload = {
        'messaging_product': 'whatsapp',
        'recipient_type': 'individual',
        'to': to,
        'type': 'text',
        'text': {'preview_url': False, 'body': body},
    }
    if reply_to:
        payload['context'] = {'message_id': reply_to}
    return await _post(phone_number_id, payload)


async def typing(phone_number_id: str, message_id: str) -> None:
    """Mark as read and show the typing indicator. Best effort only."""
    try:
        await _post(phone_number_id, {
            'messaging_product': 'whatsapp',
            'status': 'read',
            'message_id': message_id,
            'typing_indicator': {'type': 'text'},
        })
    except Exception as e:  # noqa: BLE001
        print('typing indicator failed:', e)
