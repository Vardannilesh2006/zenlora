"""
Zenlora AI SEO Engine (Gemini Powered & Deterministic Fallback)
==============================================================
Generates high-converting, viral Google Search Title Tags and Meta Descriptions
strictly adhering to user & search-engine character constraints:
- SEO Title Tag: Strictly Maximum 60 characters (High-CTR commercial click magnet).
- SEO Meta Description: Strictly Maximum 160 characters (SERP snippet with problem solved, price, COD & Free Delivery).
- Powered by Google Gemini API with smart persistent caching and deterministic instant fallbacks.
"""

import html
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
SEO_CACHE_FILE = DATA_DIR / "seo_cache.json"

_SEO_MEM_CACHE: Dict[str, Any] = {"mtime": 0.0, "data": None}


def _get_api_key() -> str:
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if key:
        return key
    env_file = ROOT_DIR / ".env"
    if env_file.exists():
        try:
            with open(env_file, "r", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("GEMINI_API_KEY="):
                        val = line.split("=", 1)[1].strip().strip('"').strip("'")
                        if val:
                            return val
        except Exception:
            pass
    return ""


def _load_seo_cache() -> Dict[str, Any]:
    if SEO_CACHE_FILE.exists():
        try:
            mtime = SEO_CACHE_FILE.stat().st_mtime
            if _SEO_MEM_CACHE["data"] is not None and _SEO_MEM_CACHE["mtime"] == mtime:
                return _SEO_MEM_CACHE["data"]
            with open(SEO_CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                _SEO_MEM_CACHE["mtime"] = mtime
                _SEO_MEM_CACHE["data"] = data
                return data
        except Exception:
            pass
    return {}


def _save_seo_cache(cache: Dict[str, Any]) -> None:
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(SEO_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2, ensure_ascii=False)
        _SEO_MEM_CACHE["mtime"] = SEO_CACHE_FILE.stat().st_mtime
        _SEO_MEM_CACHE["data"] = cache
    except Exception:
        pass


def clean_text_for_seo(text: str) -> str:
    if not text:
        return ""
    no_tags = re.sub(r"<[^>]+>", " ", str(text))
    unescaped = html.unescape(no_tags)
    cleaned = (
        unescaped.replace("\ufffd", "-")
        .replace("\u2013", "-")
        .replace("\u2014", "-")
        .replace("\u2018", "'")
        .replace("\u2019", "'")
        .replace("\u201c", '"')
        .replace("\u201d", '"')
        .replace("Zenlora™", "")
        .replace("Zenlora", "")
    )
    cleaned = re.sub(r"^\d{3,5}[A-Za-z]?\s*[-–:]?\s*", "", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def build_deterministic_seo_title(title: str, category: str = "", price: int = 0) -> str:
    """
    Creates a high-CTR, viral SEO title strictly <= 60 characters.
    Formulas:
    1. 'Buy <Title> Online | Zenlora'
    2. '<Title> (Best Price) | Zenlora'
    3. '<Title> | Zenlora'
    """
    clean_name = clean_text_for_seo(title).rstrip(" &-–|,:/")
    if not clean_name:
        clean_name = "Trending Home Utility Product"

    brand = " | Zenlora"
    max_name_len = 60 - len(brand)

    # If clean_name fits with brand
    if len(clean_name) <= max_name_len:
        # Check if we can prepend 'Buy '
        if len(clean_name) + len(brand) + 4 <= 60:
            return f"Buy {clean_name}{brand}"
        return f"{clean_name}{brand}"

    # If clean_name is slightly long, truncate cleanly at word boundary
    truncated = clean_name[:max_name_len].rsplit(" ", 1)[0].rstrip(" &-–|,:/")
    if truncated:
        candidate = f"{truncated}{brand}"
        if len(candidate) <= 60:
            return candidate

    return clean_name[:60].rstrip(" &-–|,:/")


def build_deterministic_seo_description(
    title: str,
    description: str = "",
    price: int = 299,
    mrp: int = 599,
    category: str = "",
) -> str:
    """
    Creates a high-conversion, viral SEO Meta Description strictly <= 160 characters.
    Includes:
    - Problem solved / aesthetic upgrade
    - Selling Price (Rs. <Price>)
    - Trust trigger: Free Pan-India Delivery & COD
    - High-intent CTA: Shop Online
    """
    clean_name = clean_text_for_seo(title).rstrip(" &-–|,:/")
    raw_desc = clean_text_for_seo(description)

    # Extract first sentence or benefit snippet
    benefit = ""
    if raw_desc and len(raw_desc) > 15:
        first_clause = re.split(r"[.!?\n]", raw_desc)[0].strip()
        if len(first_clause) > 10:
            benefit = first_clause

    sp = int(price or 299)
    if sp <= 0:
        sp = 299

    trust_cta = f"Buy online at Rs.{sp}. Free Pan-India Delivery & COD. Order now!"
    avail_len = 160 - len(trust_cta) - 1

    if benefit and len(benefit) <= avail_len:
        candidate = f"{benefit}. {trust_cta}"
        if len(candidate) <= 160:
            return candidate

    short_name = clean_name[:avail_len].rsplit(" ", 1)[0].rstrip(" &-–|,:/") if len(clean_name) > avail_len else clean_name
    candidate = f"Upgrade your lifestyle with {short_name}. {trust_cta}"
    if len(candidate) <= 160:
        return candidate

    # Fallback safe clamp
    fallback = f"Shop {clean_name} at Rs.{sp} on Zenlora. Premium quality, Free Pan-India Delivery & COD available. Buy now!"
    if len(fallback) <= 160:
        return fallback

    return fallback[:157].rsplit(" ", 1)[0] + "..."


class SEOEngine:
    """
    Gemini AI & Rule-Powered SEO Metadata Generator.
    Guarantees:
    - seo_title: Strictly <= 60 characters
    - seo_description: Strictly <= 160 characters
    """

    @classmethod
    def generate_product_seo(
        cls,
        title: str,
        description: str = "",
        price: int = 299,
        mrp: int = 599,
        category: str = "Home & Kitchen",
        handle: str = "",
        force_refresh: bool = False,
    ) -> Dict[str, Any]:
        cache_key = (handle or title[:40]).strip().lower()
        cache = _load_seo_cache()

        if not force_refresh and cache_key in cache:
            cached_item = cache[cache_key]
            # Ensure strict length adherence on cached values
            if (
                isinstance(cached_item, dict)
                and cached_item.get("seo_title")
                and len(cached_item["seo_title"]) <= 60
                and cached_item.get("seo_description")
                and len(cached_item["seo_description"]) <= 160
            ):
                return cached_item

        api_key = _get_api_key()
        clean_name = clean_text_for_seo(title)

        if api_key:
            import requests

            models = ["gemini-3.5-flash-lite", "gemini-3.8-flash", "gemini-flash-latest"]
            prompt = f"""You are an elite Indian D2C e-commerce SEO copywriter for Zenlora (https://zenlora.in).
Generate a click-magnet, viral Google Search Title Tag and Meta Description for this dropshipping product:

- Product Name: {clean_name}
- Category: {category}
- Selling Price: Rs. {price}
- MRP: Rs. {mrp}
- Description: {description[:300]}

MANDATORY CHARACTER LIMIT CONSTRAINTS (STRICT):
1. "seo_title": MAXIMUM 60 CHARACTERS (including spaces).
   - High-CTR search magnet. Format: [Commercial Hook] [Product Name] | Zenlora
   - Example: Buy Crystal Rose Diamond Table Lamp | Zenlora (49 chars)
   - MUST NEVER EXCEED 60 CHARACTERS.

2. "seo_description": MAXIMUM 160 CHARACTERS (including spaces).
   - High-converting search snippet.
   - Must include: Problem solved / aesthetic upgrade + price point (Rs.{price}) + 'Free Pan-India Delivery & COD' + CTA.
   - Example: Upgrade your room with the 16-color Crystal Rose Lamp. Touch control & rechargeable. Buy now at Rs.399 with Free Pan-India Delivery & COD! (149 chars)
   - MUST NEVER EXCEED 160 CHARACTERS.

3. "keywords": Array of 5 high-intent Indian search keywords for this item.

Return ONLY a valid JSON object with keys: "seo_title", "seo_description", "keywords"."""

            for model in models:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
                payload = {
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"temperature": 0.3, "maxOutputTokens": 450},
                }
                try:
                    res = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=15)
                    if res.status_code == 200:
                        parts = res.json().get("candidates", [{}])[0].get("content", {}).get("parts", [])
                        text = "".join(p.get("text", "") for p in parts).strip()
                        if text.startswith("```"):
                            text = re.sub(r"^```[a-zA-Z]*\n", "", text)
                            text = re.sub(r"\n```$", "", text)
                        parsed = json.loads(text.strip())

                        ai_title = str(parsed.get("seo_title") or "").strip()
                        ai_desc = str(parsed.get("seo_description") or "").strip()
                        keywords = parsed.get("keywords") or []

                        # Enforce strict length clamps if AI slightly overran
                        if len(ai_title) > 60:
                            ai_title = build_deterministic_seo_title(ai_title, category, price)
                        if len(ai_desc) > 160:
                            ai_desc = build_deterministic_seo_description(clean_name, ai_desc, price, mrp, category)

                        if not ai_title:
                            ai_title = build_deterministic_seo_title(clean_name, category, price)
                        if not ai_desc:
                            ai_desc = build_deterministic_seo_description(clean_name, description, price, mrp, category)

                        result = {
                            "seo_title": ai_title[:60],
                            "seo_description": ai_desc[:160],
                            "title_len": len(ai_title[:60]),
                            "desc_len": len(ai_desc[:160]),
                            "keywords": keywords[:5],
                            "ai_powered": True,
                            "ai_model": model,
                            "handle": handle,
                        }
                        cache[cache_key] = result
                        _save_seo_cache(cache)
                        return result
                except Exception:
                    continue

        # Deterministic Instant Fallback (Guarantees <= 60 and <= 160 characters)
        det_title = build_deterministic_seo_title(clean_name, category, price)
        det_desc = build_deterministic_seo_description(clean_name, description, price, mrp, category)
        result = {
            "seo_title": det_title[:60],
            "seo_description": det_desc[:160],
            "title_len": len(det_title[:60]),
            "desc_len": len(det_desc[:160]),
            "keywords": [clean_name[:30], f"{category} online", "best dropshipping product", "zenlora india", "buy online"],
            "ai_powered": False,
            "ai_model": "deterministic-high-ctr-rules",
            "handle": handle,
        }
        cache[cache_key] = result
        _save_seo_cache(cache)
        return result
