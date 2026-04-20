from __future__ import annotations

from pathlib import Path
import json
from typing import Any

import ollama

from app.config import (
    PROJECT_ROOT,
    VISION_ENABLED,
    VISION_MODEL_NAME,
    VISION_GENERATE_SUMMARY,
    VISION_GENERATE_JSON,
)

VISION_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "visual_summary": {
            "type": "string",
            "description": "A concise 2-4 sentence summary of what is visually present in the image."
        },
        "vision_json": {
            "type": "object",
            "description": "Structured visual findings from the image.",
            "properties": {
                "scene_type": {"type": ["string", "null"]},
                "people": {"type": "array", "items": {"type": "string"}},
                "objects": {"type": "array", "items": {"type": "string"}},
                "text_visible": {"type": "array", "items": {"type": "string"}},
                "activities": {"type": "array", "items": {"type": "string"}},
                "document_type": {"type": ["string", "null"]},
                "brand_names": {"type": "array", "items": {"type": "string"}},
                "locations": {"type": "array", "items": {"type": "string"}},
                "safety_flags": {"type": "array", "items": {"type": "string"}},
                "confidence": {"type": ["number", "null"]},
            },
            "required": [
                "scene_type",
                "people",
                "objects",
                "text_visible",
                "activities",
                "document_type",
                "brand_names",
                "locations",
                "safety_flags",
                "confidence",
            ],
            "additionalProperties": True,
        },
    },
    "required": ["visual_summary", "vision_json"],
    "additionalProperties": False,
}


def _safe_json_loads(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value)
        if isinstance(parsed, dict):
            return parsed
        return {"raw_response": parsed}
    except json.JSONDecodeError:
        return {"raw_response": value}


def analyze_image_with_vision_model(image_path: str | Path) -> tuple[str | None, str | None]:
    """
    Analyze an image with Ollama Gemma 4 and return:
      - visual_summary: plain text summary
      - vision_json: JSON string for DB storage
    """
    if not VISION_ENABLED:
        return None, None

    path = Path(image_path)
    if not path.exists():
        path = PROJECT_ROOT / path

    prompt = """
Analyze this image for a personal document / knowledge pipeline.

Return:
- visual_summary: a concise 2-4 sentence summary of what is visually present
- vision_json:     
    Focus on useful extraction such as:
    {
        - scene type
        - people
        - visible objects
        - visible text
        - activities
        - document type
        - brand names
        - locations
        - safety-sensitive content if relevant
        - Tags - A list that co-respond with the image (e.g: Baby, image, ID, CV, bill, Desktop, etc')
        - overall confidence
    }

Be accurate and do not guess details that are not visible.
"""

    response = ollama.chat(
        model=VISION_MODEL_NAME,
        messages=[
            {
                "role": "user",
                "content": prompt,
                "images": [str(path)],
            }
        ],
        format=VISION_RESPONSE_SCHEMA,
    )

    content = response["message"]["content"]
    parsed = _safe_json_loads(content)

    visual_summary: str | None = None
    vision_json: str | None = None

    if VISION_GENERATE_SUMMARY:
        summary_value = parsed.get("visual_summary")
        if isinstance(summary_value, str) and summary_value.strip():
            visual_summary = summary_value.strip()

    if VISION_GENERATE_JSON:
        vision_value = parsed.get("vision_json")
        if isinstance(vision_value, dict):
            vision_json = json.dumps(vision_value, ensure_ascii=False)
        elif vision_value is not None:
            vision_json = json.dumps({"value": vision_value}, ensure_ascii=False)

    return visual_summary, vision_json
