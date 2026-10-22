import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient

from app import issue_agent, kapso, store
from app.main import app, extract, valid_signature

client = TestClient(app)
EVENT = {'x-webhook-event': 'whatsapp.message.received'}
SENDER = '923001234567'


def sign(raw: bytes) -> str:
    return hmac.new(b'test-secret', raw, hashlib.sha256).hexdigest()


def payload(text, msg_id='wamid.1', sender=SENDER):
    return {'message': {'id': msg_id, 'from': sender, 'content': text}, 'phone_number_id': 'pn1'}


def post(body, headers=None, signature=None):
    raw = json.dumps(body).encode()
    h = {**EVENT, 'x-webhook-signature': signature or sign(raw), **(headers or {})}
    return client.post('/webhooks/whatsapp', content=raw, headers=h)


@pytest.fixture
def sent(monkeypatch):
    """Capture outgoing WhatsApp messages and stub the LLM and GitHub."""
    out = []

    async def fake_send(pnid, to, body, reply_to=None):
        out.append(body)

    async def fake_typing(pnid, mid):
        return None

    async def fake_chat(system, user):
        return 'Sure! ' + json.dumps({'title': 'Docs: header name is wrong', 'body': 'Docs say X.', 'labels': ['docs', 'nonsense']})

    async def fake_issue(d):
        return 'https://github.com/me/notes/issues/1'

    monkeypatch.setattr(kapso, 'send_text', fake_send)
    monkeypatch.setattr(kapso, 'typing', fake_typing)
    monkeypatch.setattr(issue_agent.llm, 'chat', fake_chat)
    monkeypatch.setattr(issue_agent, 'create_issue', fake_issue)
    return out


# ---- signature -------------------------------------------------------------

def test_valid_signature_accepts_hex_and_prefixed():
    raw = b'{"a":1}'
    assert valid_signature(raw, sign(raw))
    assert valid_signature(raw, 'sha256=' + sign(raw))


def test_invalid_or_missing_signature_rejected():
    assert not valid_signature(b'{}', 'bad')
    assert not valid_signature(b'{}', None)


def test_webhook_rejects_bad_signature():
    r = client.post('/webhooks/whatsapp', content=b'{}', headers={**EVENT, 'x-webhook-signature': 'bad'})
    assert r.status_code == 401


def test_webhook_ignores_other_events(sent):
    r = post(payload('hi'), headers={'x-webhook-event': 'whatsapp.message.delivered'})
    assert r.status_code == 200 and sent == []


# ---- payload parsing -------------------------------------------------------

def test_extract_handles_both_text_shapes():
    assert extract(payload('hello'))['text'] == 'hello'
    ev = {'message': {'id': 'a', 'from': 'b', 'text': {'body': 'hey'}}, 'phone_number_id': 'p'}
    assert extract(ev)['text'] == 'hey'


def test_extract_returns_none_for_non_text():
    assert extract({'message': {'id': 'a', 'from': 'b', 'type': 'image'}, 'phone_number_id': 'p'}) is None


# ---- full flow -------------------------------------------------------------

def test_note_then_yes_creates_issue(sent):
    assert post(payload('docs header name is wrong', 'wamid.1')).status_code == 200
    assert 'Reply YES' in sent[0] and 'Docs: header name is wrong' in sent[0]
    assert 'nonsense' not in sent[0]  # invalid labels are dropped

    assert post(payload('YES', 'wamid.2')).status_code == 200
    assert 'github.com/me/notes/issues/1' in sent[1]
    assert store.pop_pending(SENDER) is None  # draft consumed


def test_no_cancels(sent):
    post(payload('some idea', 'wamid.1'))
    post(payload('no', 'wamid.2'))
    assert sent[-1].startswith('Cancel')
    assert store.pop_pending(SENDER) is None


def test_yes_without_pending(sent):
    post(payload('yes'))
    assert 'Kuch pending nahi' in sent[0]


def test_duplicate_delivery_processed_once(sent):
    post(payload('a note', 'wamid.same'))
    post(payload('a note', 'wamid.same'))
    assert len(sent) == 1


def test_batched_webhook(sent):
    body = {'batch': True, 'data': [payload('first', 'w1'), payload('second', 'w2')]}
    assert post(body).status_code == 200
    assert len(sent) == 2


def test_unknown_sender_is_ignored(sent):
    post(payload('hi', 'w9', sender='15550000000'))
    assert sent == []


def test_llm_failure_gives_friendly_reply(sent, monkeypatch):
    async def boom(system, user):
        raise RuntimeError('llm down')

    monkeypatch.setattr(issue_agent.llm, 'chat', boom)
    post(payload('a note'))
    assert 'Sorry' in sent[0]


# ---- draft parsing ---------------------------------------------------------

def test_parse_draft_strips_fences_and_trims_title():
    d = issue_agent.parse_draft('```json\n{"title": "  T  ", "body": "B", "labels": ["bug"]}\n```')
    assert d == {'title': 'T', 'body': 'B', 'labels': ['bug']}


@pytest.mark.parametrize('bad', ['no json here', '{"title": "", "body": "x"}', '{"title": "x"}'])
def test_parse_draft_rejects_bad_output(bad):
    with pytest.raises(ValueError):
        issue_agent.parse_draft(bad)
