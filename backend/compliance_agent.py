import asyncio
import json
import logging
import os
import re
import time

import httpx
from fastapi import HTTPException
from playwright.async_api import async_playwright

from code_index import ProjectIndex, build_project_index

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

COMPLIANCE_CHECKER_URL = (
    "https://artificialintelligenceact.eu/assessment/eu-ai-act-compliance-checker/embedded/"
)
LLM_API_URL = "https://api.mistral.ai/v1/chat/completions"
LLM_MODEL = os.environ.get("MISTRAL_MODEL", "mistral-small-latest")
MAX_ITERATIONS = 30
NAVIGATION_TIMEOUT_MS = 60000
DOM_SETTLE_TIMEOUT_MS = 500

_http_client: httpx.AsyncClient | None = None


def _get_http_client() -> httpx.AsyncClient:
    # Reused across every LLM call in the process instead of one AsyncClient
    # per call, so httpx's connection pool can keep the TLS/TCP connection to
    # the LLM API alive between questions instead of renegotiating it every time.
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(timeout=120)
    return _http_client

# Returns every currently visible question on the page (radio/checkbox groups and
# text/email/textarea inputs), together with the question text scraped from the
# nearest preceding rich-text block. New questions appear as earlier ones are
# answered, since the form hides/reveals sections with plain CSS (offsetParent
# is the only reliable "really visible" check, display:none on an ancestor
# doesn't show up on the element's own computed style).
GET_VISIBLE_FIELDS_JS = """
() => {
    function extractQuestion(el) {
        if (['text', 'textarea'].includes(el.dataset.type)) {
            const label = el.querySelector('label');
            if (label) return label.innerText.trim();
        }
        // Some questions are split into several sibling checkbox/radio groups
        // sharing ONE heading above all of them (e.g. Annex I "Section A" /
        // "Section B" checklists under a single "High-risk AI system" question).
        // Skip over sibling answer fields we haven't collected a heading from
        // yet; only stop once we've found at least one heading and then hit
        // another answer field (that one belongs to a genuinely earlier
        // question). Bounded by steps, not by how many fields we pass, since a
        // shared heading can sit several fields back.
        const parts = [];
        let node = el.previousElementSibling;
        let collected = 0;
        let steps = 0;
        while (node && collected < 3 && steps < 12) {
            if (node.dataset && node.dataset.type === 'texteditor') {
                parts.unshift(node.innerText.trim());
                collected++;
            } else if (
                collected > 0 &&
                node.dataset &&
                ['radio', 'checkbox', 'text', 'textarea'].includes(node.dataset.type)
            ) {
                break;
            }
            node = node.previousElementSibling;
            steps++;
        }
        return parts.join('\\n');
    }

    const results = [];
    document.querySelectorAll('.wsf-field-wrapper').forEach(el => {
        const type = el.dataset.type;
        // "email" is excluded on purpose: the only email-type field on this page
        // is the "email me my results" opt-in near the bottom, unrelated to the
        // AI Act questionnaire itself — scanning it produced a bogus unresolved
        // "question" with no real text (discovered via live testing 2026-09-26).
        if (!['radio', 'checkbox', 'text', 'textarea'].includes(type)) return;
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
    api_key = os.environ.get("MISTRAL_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="MISTRAL_API_KEY n’est pas configurée sur le serveur")

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

    try:
        client = _get_http_client()
        response = await client.post(
            LLM_API_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": LLM_MODEL,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
    except httpx.TimeoutException as error:
        raise HTTPException(
            status_code=504,
            detail="Le modèle a mis trop de temps à répondre",
        ) from error
    except httpx.RequestError as error:
        raise HTTPException(
            status_code=502,
            detail=f"Impossible de contacter le modèle ({error})",
        ) from error

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


def _human_answer_to_field_answer(field: dict, value: str | list[str]) -> dict:
    if field["type"] in ("radio", "checkbox"):
        selected = value if isinstance(value, list) else [value]
        return {"selected": selected, "confidence": "human", "reasoning": "Réponse fournie par l’utilisateur"}
    return {"text": value if isinstance(value, str) else "", "confidence": "human", "reasoning": "Réponse fournie par l’utilisateur"}


def _describe_unresolved_field(field: dict, answer: dict, reasoning_override: str | None = None) -> dict:
    described = {
        "field_id": field["id"],
        "type": field["type"],
        "question": _strip_html(field["question"]),
        "reasoning": reasoning_override or answer.get("reasoning", ""),
    }
    if field["type"] in ("radio", "checkbox"):
        described["options"] = [_strip_html(option["value"]) for option in field["options"]]
    return described


CLICK_TIMEOUT_MS = 5000


async def _apply_answer(page, field: dict, answer: dict) -> bool:
    """Returns False if nothing could actually be clicked/filled.

    A failure here is ambiguous by itself: it might mean the option became
    moot (the form's branching logic hid it because it no longer applies —
    fine, nothing lost) or it might mean a genuinely required answer silently
    didn't register (not fine — the form will stay incomplete with no clue
    why). We can't tell which from here, so the caller treats a False return
    as "unresolved" only if the form is still incomplete once the whole loop
    ends (see run_compliance_check_with_index) — if it turns out to have been
    moot, the form completes anyway and the human is never bothered about it.
    """
    if field["type"] in ("radio", "checkbox"):
        selected = {value.strip().lower() for value in answer.get("selected", [])}
        applied = False
        for option in field["options"]:
            if _strip_html(option["value"]).strip().lower() in selected:
                try:
                    await page.click(f"#{option['id']}", timeout=CLICK_TIMEOUT_MS)
                    applied = True
                except Exception:
                    logger.warning(
                        "Could not click option %s for field %s (no longer visible?)",
                        option["id"], field["id"],
                    )
        return applied
    else:
        text = answer.get("text", "")
        if text and field.get("inputId"):
            try:
                await page.fill(f"#{field['inputId']}", text, timeout=CLICK_TIMEOUT_MS)
                return True
            except Exception:
                logger.warning("Could not fill field %s (no longer visible?)", field["id"])
                return False
        return True


async def run_compliance_check(
    code_context: str,
    system_name: str | None = None,
    extra_context: str | None = None,
) -> tuple[dict, ProjectIndex]:
    """Builds a fresh ProjectIndex from code_context, then runs the check.

    Returns (result, project_index) so the caller (main.py) can cache the index
    for a later resume round via run_compliance_check_with_index — rebuilding it
    from scratch on every human-answer round would re-pay the indexing cost
    spec 002's research.md already measured as significant for large projects.
    """
    index_start = time.monotonic()
    project_index = await asyncio.to_thread(build_project_index, code_context)
    logger.info("Building the code index took %.2fs", time.monotonic() - index_start)
    result = await run_compliance_check_with_index(project_index, system_name, extra_context)
    return result, project_index


async def run_compliance_check_with_index(
    project_index: ProjectIndex,
    system_name: str | None = None,
    extra_context: str | None = None,
    human_answers: dict[str, str | list[str]] | None = None,
) -> dict:
    context_parts = []
    if system_name:
        context_parts.append(f"AI system name: {system_name}")
    if extra_context:
        context_parts.append(extra_context)
    combined_extra_context = "\n\n".join(context_parts)

    processed: dict[str, dict] = {}
    unresolved: list[dict] = []
    unresolved_ids: set[str] = set()
    apply_failed: dict[str, tuple[dict, dict]] = {}
    run_start = time.monotonic()

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            nav_start = time.monotonic()
            await page.goto(
                COMPLIANCE_CHECKER_URL, wait_until="domcontentloaded", timeout=NAVIGATION_TIMEOUT_MS
            )
            logger.info("Navigation to checker page took %.2fs", time.monotonic() - nav_start)

            try:
                await page.get_by_text("Accept", exact=False).first.click(timeout=3000)
            except Exception:
                pass

            for iteration in range(MAX_ITERATIONS):
                fields = await page.evaluate(GET_VISIBLE_FIELDS_JS)
                new_fields = [field for field in fields if field["id"] not in processed]
                if not new_fields:
                    break

                for field in new_fields:
                    field_start = time.monotonic()
                    human_value = human_answers.get(field["id"]) if human_answers else None
                    if human_value is not None:
                        answer = _human_answer_to_field_answer(field, human_value)
                        source = "human"
                    else:
                        question_text = _strip_html(field["question"])
                        retrieved = await asyncio.to_thread(project_index.query, question_text)
                        answer = await _ask_llm_for_answer(
                            field, retrieved.as_prompt_text(), combined_extra_context
                        )
                        source = "llm"
                    logger.info(
                        "[iter %d] field %s (%s, %s) took %.2fs",
                        iteration, field["id"], field["type"], source, time.monotonic() - field_start,
                    )
                    processed[field["id"]] = answer
                    if answer.get("confidence") == "low" or (
                        field["type"] in ("radio", "checkbox") and not answer.get("selected")
                    ):
                        unresolved.append(_describe_unresolved_field(field, answer))
                        unresolved_ids.add(field["id"])
                    applied = await _apply_answer(page, field, answer)
                    if not applied:
                        apply_failed[field["id"]] = (field, answer)

                await page.wait_for_timeout(DOM_SETTLE_TIMEOUT_MS)

            body_text = await page.inner_text("body")
            results_text = _extract_results_section(body_text)
            is_complete = "not yet completed" not in results_text.lower() and \
                "incomplete" not in results_text.lower()

            if not is_complete:
                # A click/fill failure is ambiguous on its own (see _apply_answer's
                # docstring) — but if the form is STILL incomplete once we're done,
                # any answer that never actually registered is a real candidate for
                # why, and the human deserves a lead rather than a dead end (observed
                # live 2026-09-26: the loop found no new fields, returned
                # needs_human_input: [], yet the checker still said "Incomplete" with
                # nothing for the user to act on).
                for field_id, (field, answer) in apply_failed.items():
                    if field_id not in unresolved_ids:
                        unresolved.append(_describe_unresolved_field(
                            field, answer,
                            reasoning_override="An answer was chosen but couldn't be "
                            "applied to the form (the option may have stopped being "
                            "available) — please answer this one directly.",
                        ))
                        unresolved_ids.add(field_id)
        finally:
            await browser.close()

    logger.info(
        "run_compliance_check_with_index total: %.2fs (%d fields processed)",
        time.monotonic() - run_start, len(processed),
    )

    return {
        "is_complete": is_complete,
        "results_text": results_text,
        "questions_answered": len(processed),
        "needs_human_input": unresolved,
    }
