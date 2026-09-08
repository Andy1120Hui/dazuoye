from __future__ import annotations

import json

import httpx


LABELS = {
    "zh": ("适合日常使用", "设计简洁实用", "规格信息清晰", "便于跨境展示", "多场景可用", "这款{title}以实用设计满足日常需求。{spec}"),
    "en": ("Made for everyday use", "Practical, clean design", "Clear product specifications", "Ready for global shoppers", "Useful in multiple settings", "The {title} combines practical design with everyday convenience. {spec}"),
    "de": ("Für den Alltag geeignet", "Praktisches, klares Design", "Klare Produktspezifikationen", "Für internationale Kunden", "Vielseitig einsetzbar", "{title} verbindet praktisches Design mit Komfort im Alltag. {spec}"),
    "es": ("Ideal para el uso diario", "Diseño práctico y sencillo", "Especificaciones claras", "Pensado para clientes internacionales", "Útil en distintos entornos", "{title} combina un diseño práctico con comodidad diaria. {spec}"),
}


def template_copy(product, language: str, style: str) -> dict:
    labels = LABELS[language]
    style_prefix = {"concise": "", "professional": "Premium ", "lively": "Fresh "}.get(style, "") if language == "en" else ""
    title = f"{style_prefix}{product.title}"[:120]
    spec = product.specification or ""
    bullets = [labels[i] + (f" — {spec}" if i == 2 and spec else "") for i in range(5)]
    return {"title": title, "selling_points": bullets, "description": labels[5].format(title=product.title, spec=spec)}


async def generate_copy(product, language: str, style: str, settings) -> tuple[dict, str, str | None]:
    if not (settings.llm_base_url and settings.llm_api_key and settings.llm_model):
        return template_copy(product, language, style), "template", "llm_not_configured"
    prompt = (
        "Return JSON with title, selling_points (exactly 5 strings), description. Use only these facts; "
        f"do not invent sales, certifications or performance. Language={language}; style={style}; "
        f"title={product.title}; specification={product.specification or 'unknown'}"
    )
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(15, connect=3)) as client:
            response = await client.post(
                settings.llm_base_url.rstrip("/") + "/chat/completions",
                headers={"Authorization": f"Bearer {settings.llm_api_key}"},
                json={"model": settings.llm_model, "messages": [{"role": "user", "content": prompt}], "response_format": {"type": "json_object"}},
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            result = json.loads(content)
            if not isinstance(result.get("selling_points"), list) or len(result["selling_points"]) != 5:
                raise ValueError("invalid selling_points")
            if not all(isinstance(result.get(key), str) for key in ("title", "description")):
                raise ValueError("invalid copy fields")
            return result, "llm", None
    except (httpx.HTTPError, KeyError, ValueError, json.JSONDecodeError):
        return template_copy(product, language, style), "template", "llm_request_or_response_error"
