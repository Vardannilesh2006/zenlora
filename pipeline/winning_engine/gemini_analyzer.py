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

def generate_creative_direction(product_title: str, category: str, description: str = "", price: int = 499) -> Dict[str, Any]:
    """
    Uses Gemini API to generate professional D2C creative direction:
    - Storyboard luxury setting & atmosphere
    - Trending video style (ASMR / Speedramp / Transformation)
    - 10-15s conversational Hinglish voiceover script
    - Time-coded Sound Effects (SFX) cues
    - Scene-by-scene camera movements
    - Lighting and color setup
    - Elite dropshipper retention trick
    """
    models = ["gemini-flash-lite-latest", "gemini-3.5-flash-lite", "gemini-3-flash-preview"]
    api_key = _get_api_key()

    prompt = f"""You are the lead creative director for a top 1% Indian D2C dropshipping brand ('Zenlora').
Analyze this product and plan the ultimate high-retention viral video ad for Instagram Reels, TikTok, and Meta Ads.

Product: {product_title}
Category: {category}
Selling Price: Rs. {price}
Context: {description[:300] if description else 'Viral lifestyle home & living product'}

Return a JSON object with EXACTLY these keys:
{{
  "storyboard_setting": "Detailed description of a realistic luxury interior setting where this product looks 10x premium (mention exact materials, surfaces, room vibe)",
  "storyboard_atmosphere": "Lighting details, lens choice, depth of field, atmospheric mood, realistic shadows",
  "video_style": "Trending viral video style (e.g. 'ASMR Luxury Unboxing & Tactile Demo', 'Problem-Agitate-Solve Speedramp', 'Japandi Aesthetic Room Makeover', or 'High-Energy Lifestyle Flex')",
  "voiceover_script": "High-converting 10-15 second punchy conversational Hinglish voiceover script with natural Hindi slang that hooks Indian shoppers in the first 2 seconds and ends with a clear CTA",
  "sound_effects": "Exact SFX cues with second markers [0s], [3s], [6s], [9s] (e.g. [0s] Bass drop & box peel, [3s] Crisp click lock, [7s] Satisfying water glug, [10s] Cash register chime)",
  "camera_movements": "Scene-by-scene camera movements (e.g. Scene 1: Macro 45-degree slow push-in; Scene 2: Continuous orbital tracking with subtle speed ramp; Scene 3: Wide cinematic beauty hero pull-back)",
  "lighting_setup": "Professional studio/ambient lighting setup (e.g. 2700K warm rim light, soft 45-degree key diffuser, subtle atmospheric haze)",
  "creator_secret_tip": "One secret trick used by elite dropshippers to achieve 70%+ 3-second hook retention and massive link clicks for this specific product"
}}

Respond ONLY with valid JSON, without any markdown code blocks or additional text."""

    if api_key:
        for model in models:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
            headers = {"Content-Type": "application/json"}
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": 0.5,
                    "maxOutputTokens": 900
                }
            }
            try:
                res = requests.post(url, json=payload, headers=headers, timeout=10)
                if res.status_code == 200:
                    data = res.json()
                    text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                    if text.startswith("```"):
                        text = text.strip("`")
                        if text.startswith("json"):
                            text = text[4:]
                    parsed = json.loads(text.strip())
                    parsed["ai_generated"] = True
                    parsed["model_used"] = model
                    return parsed
            except Exception:
                continue

    # High-quality fallback if Gemini is offline
    cat_lower = category.lower()
    if "kitchen" in cat_lower:
        setting = "modern luxury aesthetic Indian modular kitchen with clean white quartz countertops, fluted oak cabinets, and warm under-cabinet LED glow"
        atmosphere = "golden ambient morning highlights, soft natural diffusion, shallow f/1.8 depth of field"
        style = "ASMR High-Utility Kitchen Problem-Solver"
        vo = f"Agar aapka counter bhi roz messy ho jata hai, toh ye dekho! Zenlora ka yeh {product_title[:30]} sirf Rs. {price} me aapke daily kitchen tasks ko 10x easy bana dega. Link bio me hai, abhi order karo!"
        sfx = "[0s] Rapid whoosh & counter thud, [3s] Satisfying crisp click / slice, [7s] Clean snap lock, [10s] Soft upbeat riser & chime"
        cams = "Scene 1: Close-up macro push-in on problem; Scene 2: High-speed continuous tracking on effortless action; Scene 3: Glide-back wide hero reveal"
        lighting = "3200K warm under-counter LED strips paired with 5600K soft daylight key diffuser"
        tip = "First 1.5 seconds must show the chaotic before state or instant action without any talking intro to cut bounce rate in half."
    elif "beauty" in cat_lower or "grooming" in cat_lower:
        setting = "spa-like luxury marble bathroom vanity, natural fluted teak accents, warm backlit circular mirror, and plush cotton towels"
        atmosphere = "soft morning golden hour diffusion, tranquil serene spa aesthetic, gentle mist"
        style = "Luxury Self-Care ASMR & Aesthetic Glow Routine"
        vo = f"Stop wasting thousands on expensive salon visits! Yeh {product_title[:30]} ghar baithe wahi luxury glow deta hai wo bhi sirf Rs. {price} me. Comment 'GLOW' for direct discount link!"
        sfx = "[0s] Calming water droplet splash, [3s] Soft soothing glide sound, [7s] Satisfying tactile tap, [10s] Sparkle shimmer audio"
        cams = "Scene 1: Ultra-macro texture focus gliding across surface; Scene 2: Slow-motion 60fps soothing demonstration; Scene 3: Pull back to warm backlit mirror beauty shot"
        lighting = "Warm 3000K circular ring glow behind mirror + soft diffused frontal beauty light"
        tip = "Highlight skin texture or sensory sound in the first 2 seconds; ASMR audio drastically increases video saves and shares on Instagram."
    else:
        setting = "warm cozy Japandi-style living room, textured bouclé furniture, smooth oak wooden coffee table, neutral beige limestone wall"
        atmosphere = "tranquil evening golden hour light, soft linen curtains catching gentle breeze, cozy peaceful atmosphere"
        style = "Japandi Aesthetic Room Transformation & Cozy Flex"
        vo = f"Ye choti si cheez aapke boring room ko instant 5-star hotel jaisa cozy bana degi! Zenlora ka {product_title[:30]} under Rs. {price}. Check the link in bio before it sells out!"
        sfx = "[0s] Soft ambient cinematic whoosh, [3s] Warm switch click or surface tap, [7s] Gentle golden glow hum, [10s] Satisfying lo-fi beat drop"
        cams = "Scene 1: Slow cinematic push-in through warm shadows; Scene 2: Smooth 360-degree orbital sweep capturing textures; Scene 3: Seamless wide pull-back into full cozy room glow"
        lighting = "2700K warm incandescent ambient glow paired with soft golden-hour window fill"
        tip = "Use a dim room that instantly transforms with warm lighting when the product is showcased; transformation hooks yield 4x higher CTR on Meta Ads."

    return {
        "storyboard_setting": setting,
        "storyboard_atmosphere": atmosphere,
        "video_style": style,
        "voiceover_script": vo,
        "sound_effects": sfx,
        "camera_movements": cams,
        "lighting_setup": lighting,
        "creator_secret_tip": tip,
        "ai_generated": False,
        "model_used": "deterministic-d2c-engine"
    }
