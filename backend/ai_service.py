"""Story text generation (Claude Sonnet 4.6). Illustrations are handled by fal_service (PuLID).
Face-similarity scoring is MOCKED for the MVP (no biometric model runs)."""
import os
import json
import hashlib
import random
import logging
from emergentintegrations.llm.chat import LlmChat, UserMessage

logger = logging.getLogger(__name__)

EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY")
TEXT_MODEL = ("anthropic", "claude-sonnet-4-6")

NUM_STORY_PAGES = 5  # story spreads (excluding the cover)

# Rough cost estimates (USD) for per-order AI cost tracking on the admin panel.
COST_PER_TEXT_GEN = 0.03
COST_PER_IMAGE = 0.05  # fal PuLID per illustration (approx)

LANG_NAMES = {"ar": "Arabic", "en": "English", "fr": "French"}
LEVEL_DESC = {"simple": "very simple words for a young child", "medium": "moderate vocabulary",
              "advanced": "richer vocabulary for an older child"}
STORY_TYPE_DESC = {
    "encouragement": "an encouraging, confidence-building adventure that celebrates the child",
    "behavior_correction": "a gentle behaviour-guidance story that teaches a positive lesson",
    "behavior": "a gentle behaviour-guidance story that teaches a positive lesson",
}


def _build_story_system_prompt(lang: str) -> str:
    lang_name = LANG_NAMES.get(lang, "Arabic")
    return (
        f"You are a master children's-book author who writes warm, age-appropriate picture-book stories "
        f"in {lang_name}. You return ONLY valid JSON. The story text must be written in {lang_name}. "
        f"Scene descriptions must always be written in ENGLISH (they generate illustrations)."
    )


async def generate_story(child_name: str, child_age: int, child_gender: str,
                         story_type: str, behavior_focus: str, language: str,
                         extra_context: str = "", level: str = "simple") -> dict:
    """Returns {'title': str, 'moral': str, 'pages': [{'text': str, 'scene': str}]}."""
    lang_name = LANG_NAMES.get(language, "Arabic")
    type_desc = STORY_TYPE_DESC.get(story_type, STORY_TYPE_DESC["encouragement"])
    focus_line = f"The specific focus/behaviour goal is: {behavior_focus}." if behavior_focus else ""
    ctx_line = f"Weave in these real details about the child's life: {extra_context}." if extra_context else ""
    level_line = LEVEL_DESC.get(level, LEVEL_DESC["simple"])

    prompt = (
        f"Write a personalised children's picture-book story in {lang_name} using {level_line}.\n"
        f"Main character: a {child_age}-year-old {child_gender} named {child_name}.\n"
        f"Story type: {type_desc}. {focus_line} {ctx_line}\n"
        f"The story must have exactly {NUM_STORY_PAGES} pages. Each page has 2-4 short sentences "
        f"suitable for a {child_age}-year-old. Use the child's name naturally.\n\n"
        f"Return ONLY this JSON (no markdown fences):\n"
        f'{{"title": "story title in {lang_name}", '
        f'"moral": "one gentle takeaway line in {lang_name}", '
        f'"pages": [{{"text": "page text in {lang_name}", '
        f'"scene": "vivid ENGLISH illustration description of this page featuring the child in a scene"}}]}}'
    )

    chat = LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=f"story-{child_name}-{random.randint(1000,9999)}",
        system_message=_build_story_system_prompt(language),
    ).with_model(*TEXT_MODEL).with_params(max_tokens=4000)

    resp = await chat.send_message(UserMessage(text=prompt))
    text = resp if isinstance(resp, str) else str(resp)
    data = _parse_json(text)
    return {
        "title": data.get("title", child_name),
        "moral": data.get("moral", ""),
        "pages": data.get("pages", [])[:NUM_STORY_PAGES],
    }


def _parse_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1] if text.count("```") >= 2 else text
        if text.startswith("json"):
            text = text[4:]
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1:
        text = text[start:end + 1]
    return json.loads(text)


def mock_face_similarity(seed_str: str) -> float:
    """MOCKED face-embedding similarity score in [0,1]. Deterministic. Real biometric matching
    is deferred; human review is the source of truth for now."""
    rng = random.Random(hashlib.sha256(seed_str.encode()).hexdigest())
    return round(rng.uniform(0.7, 0.95), 2)


SIMILARITY_THRESHOLD = 0.65
