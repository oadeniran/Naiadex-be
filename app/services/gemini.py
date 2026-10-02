import json
import logging

from app.ai_client import VertexAIClient

logger = logging.getLogger("uvicorn")

# One client for the whole app (don't re-init per request)
_client = VertexAIClient()


def _extract_json(raw) -> dict:
    # your chat_completion returns {"error": ...} on failure; guard for it
    if isinstance(raw, dict):
        raise RuntimeError(raw.get("error", "LLM generation failed"))
    if not raw:
        raise RuntimeError("Empty response from model")
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end == -1:
        raise RuntimeError("No JSON object found in model response")
    return json.loads(raw[start : end + 1])


def json_from_image(image_bytes: bytes, mime_type: str, prompt: str) -> dict:
    raw = _client.generate_structured_from_image(
        image_bytes=image_bytes, prompt=prompt, mime_type=mime_type, model="gemini-3.1-pro-preview"
    )
    return _extract_json(raw)

def json_from_labeled_images(labeled_images, prompt: str) -> dict:
    raw = _client.generate_structured_from_images(labeled_images, prompt)
    return _extract_json(raw)


def json_from_text(prompt: str) -> dict:
    raw = _client.chat_completion(
        messages=[{"role": "user", "content": prompt}],
        response_mime_type="application/json",
    )
    return _extract_json(raw)

def text_from_prompt(prompt: str) -> str:
    raw = _client.chat_completion(
        messages=[{"role": "user", "content": prompt}],
        response_mime_type="text/plain",
    )
    if isinstance(raw, dict):  # your client's error fallback
        raise RuntimeError(raw.get("error", "LLM generation failed"))
    return (raw or "").strip()