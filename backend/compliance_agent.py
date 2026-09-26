import asyncio
import json
import os
import re

import httpx
from fastapi import HTTPException
from playwright.async_api import async_playwright

from code_index import build_project_index

COMPLIANCE_CHECKER_URL = (
    "https://artificialintelligenceact.eu/assessment/eu-ai-act-compliance-checker/embedded/"
)
LLM_API_URL = "https://api.z.ai/api/paas/v4/chat/completions"
LLM_MODEL = os.environ.get("ZAI_MODEL", "glm-4.6")
MAX_ITERATIONS = 30
NAVIGATION_TIMEOUT_MS = 60000
DOM_SETTLE_TIMEOUT_MS = 500

# Returns every currently visible question on the page (radio/checkbox groups and
# text/email/textarea inputs), together with the question text scraped from the
# nearest preceding rich-text block. New questions appear as earlier ones are
# answered, since the form hides/reveals sections with plain CSS (offsetParent
# is the only reliable "really visible" check, display:none on an ancestor
# doesn't show up on the element's own computed style).
GET_VISIBLE_FIELDS_JS = """
() => {
    function extractQuestion(el) {
        if (['text', 'textarea', 'email'].includes(el.dataset.type)) {
            const label = el.querySelector('label');
            if (label) return label.innerText.trim();
        }
        const parts = [];
        let node = el.previousElementSibling;
        let collected = 0;
        while (node && collected < 3) {
            if (node.dataset && node.dataset.type === 'texteditor') {
                parts.unshift(node.innerText.trim());
                collected++;
            } else if (node.dataset && ['radio', 'checkbox', 'text', 'textarea', 'email'].includes(node.dataset.type)) {
                break;
            }
            node = node.previousElementSibling;
        }
        return parts.join('\\n');
    }

    const results = [];
    document.querySelectorAll('.wsf-field-wrapper').forEach(el => {
        const type = el.dataset.type;
        if (!['radio', 'checkbox', 'text', 'textarea', 'email'].includes(type)) return;
        if (el.offsetParent === null) return;

        const question = extractQuestion(el);
        if (type === 'radio' || type === 'checkbox') {
            const options = Array.from(el.querySelectorAll('input')).map(i => ({
                id: i.id, value: i.value, checked: i.checked,
            }));
            results.push({ id: el.id, type, question, options });
        } else {
            const input = el.querySelector('input, textarea');
            results.push({
                id: el.id, type, question,
                inputId: input ? input.id : null,
                value: input ? input.value : '',
            });
        }
    });
    return results;
}
"""


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip()


def _extract_results_section(body_text: str) -> str:
    start = body_text.find("Your results")
    if start == -1:
        return body_text
    end = body_text.find("Save your results", start)
    section = body_text[start : end if end != -1 else None]
    return section.strip()


async def _ask_llm_for_answer(field: dict, retrieved_code_text: str, extra_context: str) -> dict:
    api_key = os.environ.get("ZAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="ZAI_API_KEY n’est pas configurée sur le serveur")

    question = _strip_html(field["question"])
    if field["type"] in ("radio", "checkbox"):
        options = [_strip_html(o["value"]) for o in field["options"]]
        options_block = "\n".join(f"- {option}" for option in options)
        answer_instructions = (
            "Reply with a JSON object of the form "
            '{"selected": ["<one or more of the options above, copied exactly>"], '
            '"confidence": "high"|"medium"|"low", "reasoning": "<one sentence>"}. '
            'If the code/context gives no basis to answer, reply '
            '{"selected": [], "confidence": "low", "reasoning": "<why not>"}.'
        )
    else:
        options_block = "(free text field)"
        answer_instructions = (
            "Reply with a JSON object of the form "
            '{"text": "<answer>", "confidence": "high"|"medium"|"low", "reasoning": "<one sentence>"}. '
            'If nothing in the code/context answers this, reply {"text": "", "confidence": "low", "reasoning": "<why not>"}.'
        )

    prompt = (
        "You are filling out the official EU AI Act Compliance Checker form on behalf of a "
        "development team, using only the facts in their submitted codebase and any extra "
        "context provided below. Do not guess beyond what the material supports; when unsure, "
        "say so via low confidence rather than inventing facts.\n\n"
        f"Question:\n{question}\n\nOptions:\n{options_block}\n\n"
        f"Extra context about the company/system (may be empty):\n{extra_context or '(none provided)'}\n\n"
        f"Codebase excerpts relevant to this question:\n{retrieved_code_text}\n\n"
        f"{answer_instructions}\nRespond with ONLY the JSON object, no other text."
    )

    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            LLM_API_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": LLM_MODEL,
                "messages": [{"role": "user", "content": prompt}],
            },
        )

    if response.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"L’appel au modèle a échoué ({response.status_code})",
        )

    content = response.json()["choices"][0]["message"]["content"]
    match = re.search(r"\{.*\}", content, re.DOTALL)
    if not match:
        return {"selected": [], "text": "", "confidence": "low", "reasoning": "Réponse du modèle illisible"}

    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return {"selected": [], "text": "", "confidence": "low", "reasoning": "Réponse du modèle illisible"}


async def _apply_answer(page, field: dict, answer: dict) -> None:
    if field["type"] in ("radio", "checkbox"):
        selected = {value.strip().lower() for value in answer.get("selected", [])}
        for option in field["options"]:
            if _strip_html(option["value"]).strip().lower() in selected:
                await page.click(f"#{option['id']}")
    else:
        text = answer.get("text", "")
        if text and field.get("inputId"):
            await page.fill(f"#{field['inputId']}", text)


async def run_compliance_check(
    code_context: str,
    system_name: str | None = None,
    extra_context: str | None = None,
) -> dict:
    context_parts = []
    if system_name:
        context_parts.append(f"AI system name: {system_name}")
    if extra_context:
        context_parts.append(extra_context)
    combined_extra_context = "\n\n".join(context_parts)

    processed: dict[str, dict] = {}
    unresolved: list[dict] = []
    project_index = await asyncio.to_thread(build_project_index, code_context)

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            await page.goto(
                COMPLIANCE_CHECKER_URL, wait_until="networkidle", timeout=NAVIGATION_TIMEOUT_MS
            )

            try:
                await page.get_by_text("Accept", exact=False).first.click(timeout=3000)
            except Exception:
                pass

            for _ in range(MAX_ITERATIONS):
                fields = await page.evaluate(GET_VISIBLE_FIELDS_JS)
                new_fields = [field for field in fields if field["id"] not in processed]
                if not new_fields:
                    break

                for field in new_fields:
                    question_text = _strip_html(field["question"])
                    retrieved = await asyncio.to_thread(project_index.query, question_text)
                    answer = await _ask_llm_for_answer(
                        field, retrieved.as_prompt_text(), combined_extra_context
                    )
                    processed[field["id"]] = answer
                    if answer.get("confidence") == "low" or (
                        field["type"] in ("radio", "checkbox") and not answer.get("selected")
                    ):
                        unresolved.append(
                            {
                                "question": _strip_html(field["question"]),
                                "reasoning": answer.get("reasoning", ""),
                            }
                        )
                    await _apply_answer(page, field, answer)

                await page.wait_for_timeout(DOM_SETTLE_TIMEOUT_MS)

            body_text = await page.inner_text("body")
            results_text = _extract_results_section(body_text)
            is_complete = "not yet completed" not in results_text.lower() and \
                "incomplete" not in results_text.lower()
        finally:
            await browser.close()

    return {
        "is_complete": is_complete,
        "results_text": results_text,
        "questions_answered": len(processed),
        "needs_human_input": unresolved,
    }
