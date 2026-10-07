import os
import requests
import json
from pathlib import Path
from typing import Dict, Any, Optional

def _get_api_key() -> str:
    key = os.environ.get("GEMINI_API_KEY", "")
    if key:
        return key
    # Try reading local .env if available
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

def analyze_with_gemini(product_title: str, niche: str, wholesale_price: float, selling_price: float) -> Dict[str, Any]:
    """
    Uses Gemini API (gemini-flash-lite-latest) to evaluate product viral potential,
    generate a high-converting Hinglish dropshipping hook, and assess customer appeal.
    """
    models = ["gemini-flash-lite-latest", "gemini-flash-latest"]
    
    prompt = f"""You are an elite Indian dropshipping product research director for 'Zenlora' (a premium D2C brand in India).
Analyze this product:
- Product Title: {product_title}
- Niche: {niche}
- Sourcing Cost: Rs. {wholesale_price}
- Selling Retail Price: Rs. {selling_price} (Target Profit: Rs. {selling_price - wholesale_price - 70})

Provide a concise JSON response with:
1. "ai_verdict": 1 sentence why this product sells or if it has high impulse-buy appeal.
2. "viral_hook_hinglish": 1 punchy 3-second hook line for Instagram Reels/Ads in natural Hinglish.
3. "target_audience": Who buys this in India (e.g., 'Modern Homemakers', 'Tier 1/2 Bachelors', 'Gen-Z Aesthetic Room Decorators').
4. "ai_viral_score": Integer between 75 and 98 based on impulse viral purchase desire.

Respond ONLY with valid JSON, no markdown codeblocks."""

    api_key = _get_api_key()
    if not api_key:
        # Fallback if no key configured
        return {
            "ai_verdict": f"High margin problem-solver with strong visual appeal in {niche}.",
            "viral_hook_hinglish": f"Ye {product_title[:25]} dekh kar aapke dost bhi sochenge kahan se liya!",
            "target_audience": "Tier 1 & 2 Aesthetic Shoppers",
            "ai_viral_score": 85 + (hash(product_title) % 10),
            "gemini_powered": False
        }

    for model in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.4,
                "maxOutputTokens": 250
            }
        }
        try:
            res = requests.post(url, json=payload, headers=headers, timeout=6)
            if res.status_code == 200:
                data = res.json()
                text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                # Clean markdown block if model added it
                if text.startswith("```"):
                    text = text.strip("`")
                    if text.startswith("json"):
                        text = text[4:]
                parsed = json.loads(text.strip())
                return {
                    "ai_verdict": parsed.get("ai_verdict", "Strong impulse-buy potential in Indian market."),
                    "viral_hook_hinglish": parsed.get("viral_hook_hinglish", "Ye smart gadget aapke room ko 2 second me luxury look de dega!"),
                    "target_audience": parsed.get("target_audience", "Indian Online Shoppers & Homemakers"),
                    "ai_viral_score": int(parsed.get("ai_viral_score", 88)),
                    "gemini_powered": True
                }
        except Exception:
            continue

    # Deterministic fallback if Gemini network times out
    return {
        "ai_verdict": f"High margin problem-solver with strong visual before/after transformation in {niche}.",
        "viral_hook_hinglish": f"Ye {product_title[:25]} dekh kar aapke dost bhi sochenge kahan se liya!",
        "target_audience": "Tier 1 & 2 Aesthetic Shoppers",
        "ai_viral_score": 85 + (hash(product_title) % 10),
        "gemini_powered": False
    }
