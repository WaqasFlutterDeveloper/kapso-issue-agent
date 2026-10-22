"""WhatsApp note -> AI-drafted GitHub issue, created only after the user confirms."""
import json
import os

import httpx

from . import kapso, llm, store

ALLOWED_LABELS = {'bug', 'docs', 'idea', 'question'}
YES = {'yes', 'y', 'haan', 'ha', 'ok', 'confirm'}
NO = {'no', 'n', 'nahi', 'cancel'}

PROMPT = (
    'Turn the user note into a GitHub issue. Reply with JSON only, no code fences: '
    '{"title": string, "body": string, "labels": [string]}. '
    'Title under 70 characters. Body in markdown: what happened, what was expected, '
    'steps if given. Never invent facts that are not in the note. '
    'Labels only from: bug, docs, idea, question.'
)

HELP = (
    'Mujhe koi bhi rough note bhejein (bug, docs ki ghalti, idea). '
    'Main usse GitHub issue draft karunga. YES likhein to ban jayega, NO likhein to cancel.'
)


def parse_draft(text: str) -> dict:
    """Extract and validate the JSON draft from a model reply."""
    start, end = text.find('{'), text.rfind('}')
    if start == -1 or end == -1:
        raise ValueError('no JSON object in model reply')
    d = json.loads(text[start:end + 1])
    title = str(d.get('title', '')).strip()[:100]
    body = str(d.get('body', '')).strip()
    if not title or not body:
        raise ValueError('draft needs a title and a body')
    labels = [x for x in d.get('labels', []) if x in ALLOWED_LABELS]
    return {'title': title, 'body': body, 'labels': labels}


async def draft(note: str) -> dict:
    return parse_draft(await llm.chat(PROMPT, note))


async def create_issue(d: dict) -> str:
    repo = os.environ['GITHUB_REPO']
    headers = {
        'Authorization': 'Bearer ' + os.environ['GITHUB_TOKEN'],
        'Accept': 'application/vnd.github+json',
    }
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.post(
            f'https://api.github.com/repos/{repo}/issues',
            headers=headers,
            json={'title': d['title'], 'body': d['body'], 'labels': d['labels']},
        )
        r.raise_for_status()
        return r.json()['html_url']


def render_preview(d: dict) -> str:
    nl = chr(10)
    return (
        '*' + d['title'] + '*' + nl + nl + d['body'][:700]
        + nl + nl + 'Labels: ' + (', '.join(d['labels']) or 'none')
        + nl + nl + 'Reply YES to create this issue, or NO to cancel.'
    )


async def handle_text(phone_number_id: str, sender: str, text: str, message_id: str) -> None:
    t = text.strip().lower()
    try:
        if t in ('help', '/help', 'start'):
            reply = HELP
        elif t in YES:
            d = store.pop_pending(sender)
            reply = ('Issue ban gaya: ' + await create_issue(d)) if d else 'Kuch pending nahi hai. Pehle apna note bhejein.'
        elif t in NO:
            reply = 'Cancel kar diya.' if store.pop_pending(sender) else 'Kuch pending nahi hai.'
        else:
            d = await draft(text)
            store.set_pending(sender, d)
            reply = render_preview(d)
    except Exception as e:  # noqa: BLE001
        print('issue_agent error:', repr(e))
        reply = 'Sorry, kuch masla hua. Dobara try karein.'
    await kapso.send_text(phone_number_id, sender, reply[:4000], reply_to=message_id)
