import os
import tempfile

import pytest

os.environ.update(
    KAPSO_API_KEY='test-key',
    WEBHOOK_SECRET='test-secret',
    ALLOWED_SENDERS='+923001234567',
    LLM_BASE_URL='http://llm.invalid/v1',
    LLM_API_KEY='x',
    LLM_MODEL='m',
    GITHUB_TOKEN='t',
    GITHUB_REPO='me/notes',
)


@pytest.fixture(autouse=True)
def fresh_db(monkeypatch):
    path = os.path.join(tempfile.mkdtemp(), 'test.db')
    monkeypatch.setenv('DB_PATH', path)
    yield
