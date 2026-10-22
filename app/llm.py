"""LLM client for any OpenAI-compatible chat API (Groq, Gemini, OpenRouter, Ollama, OpenAI...).

Set LLM_BASE_URL, LLM_API_KEY and LLM_MODEL in the environment.
"""
import os

import httpx


async def chat(system: str, user: str) -> str:
    base = os.environ['LLM_BASE_URL'].rstrip('/')
    async with httpx.AsyncClient(timeout=40) as c:
        r = await c.post(
            base + '/chat/completions',
            headers={'Authorization': 'Bearer ' + os.environ['LLM_API_KEY']},
            json={
                'model': os.environ['LLM_MODEL'],
                'temperature': 0.2,
                'messages': [
                    {'role': 'system', 'content': system},
                    {'role': 'user', 'content': user},
                ],
            },
        )
        r.raise_for_status()
        return r.json()['choices'][0]['message']['content']
