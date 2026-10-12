"""
Gemini AI Opinion & Creative Summary Module (Rule #2 Compliant):
- NEVER generates numbers, trends, prices, ad counts, view counts, or scores.
- Only classifies or summarizes real visible product inputs (title, description, category, supplier cost).
- All outputs are explicitly labelled 'AI opinion (not data)' with method='ai_opinion'.
- If GEMINI_API_KEY is not configured or fails, returns None (null) with reason — zero fake fallback scores.
"""
import os
import json
import requests
from pathlib import Path
from typing import Dict, Any, Optional
from winning_engine.data_models import now_iso, RUNTIME_DATA_DIR, REPO_DATA_DIR

GEMINI_CACHE_FILE = RUNTIME_DATA_DIR / "gemini_cache.json"
REPO_GEMINI_CACHE_FILE = REPO_DATA_DIR / "gemini_cache.json"
_GEMINI_MEM_CACHE: Dict[str, Any] = {"mtime": 0.0, "data": None}


def _load_gemini_cache() -> Dict[str, Any]:
    merged: Dict[str, Any] = {}
    max_mtime = 0.0
    for target in (REPO_GEMINI_CACHE_FILE, GEMINI_CACHE_FILE):
        if target.exists():
            try:
                max_mtime = max(max_mtime, target.stat().st_mtime)
            except Exception:
                pass
    if _GEMINI_MEM_CACHE["data"] is not None and _GEMINI_MEM_CACHE["mtime"] == max_mtime:
        return _GEMINI_MEM_CACHE["data"]
    for target in (REPO_GEMINI_CACHE_FILE, GEMINI_CACHE_FILE):
        if target.exists():
            try:
                with open(target, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    merged.update(data)
            except Exception:
                pass
    _GEMINI_MEM_CACHE["mtime"] = max_mtime
    _GEMINI_MEM_CACHE["data"] = merged
    return merged


def _save_gemini_cache(cache: Dict[str, Any]) -> None:
    for target in (GEMINI_CACHE_FILE, REPO_GEMINI_CACHE_FILE):
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            with open(target, "w", encoding="utf-8") as f:
                json.dump(cache, f, indent=2, ensure_ascii=False)
            _GEMINI_MEM_CACHE["mtime"] = target.stat().st_mtime
            _GEMINI_MEM_CACHE["data"] = cache
        except Exception:
            pass


def _get_api_key() -> str:
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if key:
        return key
    env_file = Path(__file__).resolve().parent.parent.parent / ".env"
    if env_file.exists():
        try:
            with open(env_file, "r", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("GEMINI_API_KEY="):
                        return line.split("=", 1)[1].strip()
        except Exception:
            pass
    return ""


def analyze_with_gemini(
    product_title: str,
    niche: str,
    wholesale_price: float,
    selling_price: float,
    description: str = "",
    handle: str = "",
    fetch_live: bool = False
) -> Dict[str, Any]:
    """
    Summarizes real product attributes and evaluates Pain/Wow rating (1-5) and 3-Second Demo rating (1-5)
    explicitly marked as 'AI opinion (not data)' using Gemini 3.5 Flash Lite / 3.8 Flash.
    Never generates fake market statistics, view counts, ad counts, or sales numbers.
    """
    cache_key = (handle or product_title[:50]).strip().lower()
    cache = _load_gemini_cache()
    if cache_key in cache and not fetch_live:
        cached = cache[cache_key]
        if cached.get("gemini_powered"):
            return cached

    api_key = _get_api_key()
    if not api_key or not fetch_live:
        return cache.get(cache_key) or {
            "label": "AI opinion (not data)",
            "ai_verdict": None,
            "viral_hook_hinglish": None,
            "target_audience": None,
            "suggested_pain_wow_rating_1_to_5": None,
            "suggested_demo_3s_rating_1_to_5": None,
            "gemini_powered": False,
            "source": "Google Gemini API (AI opinion)",
            "source_url": "https://ai.google.dev/",
            "fetched_at": None,
            "method": "ai_opinion",
            "null_reason": "Data not available: GEMINI_API_KEY not configured" if not api_key else "Cached AI research pending"
        }

    models = ["gemini-3.5-flash-lite", "gemini-3.8-flash", "gemini-3.1-flash-lite"]
    prompt = f"""You are reviewing real supplier catalog inputs for an Indian dropshipping product.
Do NOT invent any market statistics, view counts, ad counts, or sales numbers. Only evaluate the visible product attributes below:
- Title: {product_title}
- Category: {niche}
- Supplier Cost: Rs. {wholesale_price}
- Planned Selling Price: Rs. {selling_price}
- Description: {description[:250]}

Return ONLY valid JSON with these exact keys:
1. "ai_verdict": 1 concise sentence summarizing what problem this product solves or its visual appeal in India (labelled AI opinion).
2. "viral_hook_hinglish": 1 catchy 3-second Hinglish hook line for a Reel demonstration.
3. "target_audience": Suggested Indian buyer persona based on product utility.
4. "suggested_pain_wow_rating_1_to_5": Integer 1 to 5 rating for Pain-Solving or Visual Wow factor.
5. "suggested_demo_3s_rating_1_to_5": Integer 1 to 5 rating for how clearly this item can be visually demonstrated in 3 seconds."""

    for model in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": 600}
        }
        try:
            res = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=12)
            if res.status_code == 200:
                parts = res.json()["candidates"][0]["content"]["parts"]
                text = ""
                for p in parts:
                    if "text" in p and p["text"].strip():
                        text = p["text"].strip()
                if text.startswith("```"):
                    text = text.strip("`")
                    if text.startswith("json"):
                        text = text[4:]
                parsed = json.loads(text.strip())
                ts = now_iso()
                result = {
                    "label": "AI opinion (not data)",
                    "ai_verdict": parsed.get("ai_verdict"),
                    "viral_hook_hinglish": parsed.get("viral_hook_hinglish"),
                    "target_audience": parsed.get("target_audience"),
                    "suggested_pain_wow_rating_1_to_5": int(parsed.get("suggested_pain_wow_rating_1_to_5") or 4),
                    "suggested_demo_3s_rating_1_to_5": int(parsed.get("suggested_demo_3s_rating_1_to_5") or 4),
                    "gemini_powered": True,
                    "source": f"Google Gemini API ({model}) — AI opinion",
                    "source_url": "https://ai.google.dev/",
                    "fetched_at": ts,
                    "method": "ai_opinion",
                    "null_reason": None
                }
                cache[cache_key] = result
                _save_gemini_cache(cache)
                return result
        except Exception:
            continue

    return {
        "label": "AI opinion (not data)",
        "ai_verdict": None,
        "viral_hook_hinglish": None,
        "target_audience": None,
        "suggested_pain_wow_rating_1_to_5": None,
        "suggested_demo_3s_rating_1_to_5": None,
        "gemini_powered": False,
        "source": "Google Gemini API (AI opinion)",
        "source_url": "https://ai.google.dev/",
        "fetched_at": None,
        "method": "ai_opinion",
        "null_reason": "AI opinion unavailable: Gemini API request failed or timed out"
    }


def generate_creative_direction(product_title: str, category: str, description: str = "", price: int = 499) -> Dict[str, Any]:
    """
    Generates creative direction (AI opinion / copywriting assistance) for UGC video production.
    Explicitly marked as AI opinion / template copy, never presented as market data.
    """
    models = ["gemini-3.5-flash-lite", "gemini-3.8-flash", "gemini-3.1-flash-lite"]
    api_key = _get_api_key()

    prompt = f"""Summarize creative video production ideas (AI opinion) for this product:
Product: {product_title}
Category: {category}
Selling Price: Rs. {price}
Context: {description[:300]}

Return valid JSON with keys:
"storyboard_setting", "storyboard_atmosphere", "video_style", "voiceover_script", "sound_effects", "camera_movements", "lighting_setup", "creator_secret_tip"."""

    if api_key:
        for model in models:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.4, "maxOutputTokens": 900}
            }
            try:
                res = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=12)
                if res.status_code == 200:
                    parts = res.json()["candidates"][0]["content"]["parts"]
                    text = ""
                    for p in parts:
                        if "text" in p and p["text"].strip():
                            text = p["text"].strip()
                    if text.startswith("```"):
                        text = text.strip("`")
                        if text.startswith("json"):
                            text = text[4:]
                    parsed = json.loads(text.strip())
                    parsed["ai_generated"] = True
                    parsed["label"] = "AI opinion (creative suggestion)"
                    parsed["model_used"] = model
                    return parsed
            except Exception:
                continue

    return {
        "storyboard_setting": f"Clean indoor setting highlighting {product_title}",
        "storyboard_atmosphere": "Natural diffused lighting, clear focus on product demonstration",
        "video_style": "3-Second Visual Problem/Solution Demonstration (Template Suggestion)",
        "voiceover_script": f"Dekhiye kaise yeh {product_title[:35]} aapka kaam aasaan banata hai.",
        "sound_effects": "[0s] Visual hook action, [3s] Product operation sound",
        "camera_movements": "Scene 1: Close-up on problem/action; Scene 2: Clear product usage; Scene 3: Full result",
        "lighting_setup": "Warm indoor ambient light + key diffuser",
        "creator_secret_tip": "Show the physical result in the first 3 seconds without text clutter (Rule-based tip).",
        "ai_generated": False,
        "label": "Template suggestion (not data)",
        "model_used": "rule-template"
    }
