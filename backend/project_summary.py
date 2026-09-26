import json
import logging
import os
import re

import httpx
from fastapi import HTTPException

from compliance_agent import LLM_API_URL, LLM_MODEL, _get_http_client

logger = logging.getLogger(__name__)

MAX_CODE_CONTEXT_CHARS = 40000
SUMMARY_TIMEOUT_SECONDS = 120

PROMPT_TEMPLATE = """You are analyzing a codebase to prepare it for the EU AI Act \
Compliance Checker (a form covering things like: what the system does, whether it's an \
AI system, who operates it, whether it's placed on the EU market, whether it falls under \
high-risk categories, biometric/subliminal/manipulative uses, etc.).

Write:
1. A coherent, factual summary (a few paragraphs) of what this system does, based only \
on the code and context below. Do not invent facts not supported by the material.
2. A list of information gaps: specific categories of information the compliance form \
is likely to need that this code/context does NOT tell you.

The real compliance form is itself multiple-choice wherever possible — match that. For \
each gap, if the answer space is naturally small (yes/no, a short enumerable list, "not \
sure"), give 3-5 short concrete answer options a non-expert user could just click, \
instead of making them write a paragraph. Only omit options (empty list) when the answer \
is genuinely open-ended free text (e.g. "describe the system's intended purpose in your \
own words", "list the EU member states you operate in"). Prefer options over free text \
whenever a reasonable person could answer by picking one of a handful of choices — this \
is the default, free text is the exception.

Each gap needs: a short stable id (lowercase, hyphens), a human-readable description \
explaining what's missing and why it matters for the AI Act assessment, and an "options" \
array (may be empty per the rule above; include "Not sure" as one of the options whenever \
useful).

Extra context about the company/system (may be empty):
{extra_context}

Codebase representation (may be truncated):
{code_context}

Respond with ONLY a JSON object of this exact shape, no other text:
{{"summary": "...", "gaps": [{{"id": "...", "description": "...", "options": ["...", "..."]}}]}}
If there are no real gaps, reply with an empty gaps array."""


async def generate_project_summary(code_context: str, extra_context: str) -> dict:
    api_key = os.environ.get("MISTRAL_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="MISTRAL_API_KEY n’est pas configurée sur le serveur")

    prompt = PROMPT_TEMPLATE.format(
        extra_context=extra_context or "(none provided)",
        code_context=code_context[:MAX_CODE_CONTEXT_CHARS],
    )

    try:
        client = _get_http_client()
        response = await client.post(
            LLM_API_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json={"model": LLM_MODEL, "messages": [{"role": "user", "content": prompt}]},
            timeout=SUMMARY_TIMEOUT_SECONDS,
        )
    except httpx.TimeoutException as error:
        raise HTTPException(
            status_code=504, detail="Le modèle a mis trop de temps à générer le résumé"
        ) from error
    except httpx.RequestError as error:
        raise HTTPException(
            status_code=502, detail=f"Impossible de contacter le modèle ({error})"
        ) from error

    if response.status_code != 200:
        raise HTTPException(
            status_code=502, detail=f"L’appel au modèle a échoué ({response.status_code})"
        )

    content = response.json()["choices"][0]["message"]["content"]
    match = re.search(r"\{.*\}", content, re.DOTALL)
    if not match:
        logger.warning("Unreadable summary response: %r", content[:500])
        return {"summary": "", "gaps": []}

    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        logger.warning("Unparsable summary JSON: %r", content[:500])
        return {"summary": "", "gaps": []}

    return {
        "summary": parsed.get("summary", ""),
        "gaps": parsed.get("gaps", []),
    }
