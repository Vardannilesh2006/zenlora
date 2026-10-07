import re
from config import CONTINUITY_PROMPT

class UGCEngine:
    """Generates viral UGC storyboard image prompts and multi-scene video prompts with continuity."""

    @classmethod
    def determine_content_bucket(cls, category: str, title: str, description: str) -> dict:
        text = f"{title} {description}".lower()

        # Check for sales/problem-solver keywords
        pas_keywords = ["clean", "scrub", "spray", "mop", "organizer", "rack", "wire", "dispenser", "peeler", "knife", "fast", "hack"]
        if any(k in text for k in pas_keywords) or "Kitchen" in category:
            return {
                "bucket": "Bucket C: Traffic & Sales Drivers (PAS)",
                "strategy": "Problem-Agitate-Solution with strong CTA. Designed to drive comments and link clicks.",
                "type": "conversion"
            }

        # Check for relatable / social / gifting keywords
        relatable_keywords = ["gift", "couple", "roommate", "partner", "behen", "bhai", "sister", "friend", "messy", "funny"]
        if any(k in text for k in relatable_keywords) or "Grooming" in category or "Festive Gifting" in category:
            return {
                "bucket": "Bucket B: Relatable & Shareable",
                "strategy": "High aesthetic visual paired with relatable emotional or humorous hook for DM shares.",
                "type": "viral_share"
            }

        # Default for aesthetic items (Lamps, decor, vases, aroma)
        return {
            "bucket": "Bucket A: Pure Aesthetics & Saves",
            "strategy": "Aesthetic Japandi / warm cozy vibe focusing on room transformation to maximize saves.",
            "type": "aesthetic"
        }

    @classmethod
    def generate_prompts(cls, product_data: dict, classification_data: dict) -> dict:
        title = product_data.get("title", "")
        clean_title = classification_data.get("zenlora_title", title).replace("Zenlora™", "").strip()
        category = classification_data.get("primary_category", "")
        description = product_data.get("description", "")
        price = classification_data.get("selling_price", 399)

        bucket_info = cls.determine_content_bucket(category, title, description)
        bucket_type = bucket_info["type"]

        # 1. Storyboard Base Image Prompt (Midjourney v6 / Ideogram / DALL-E 3)
        storyboard_prompt = cls._build_storyboard_image_prompt(clean_title, category, bucket_type)

        # 2. Multi-Scene Video Prompts (Kling / Runway Gen-3 / Luma)
        scenes = cls._build_video_scenes(clean_title, category, bucket_type)

        # 3. On-screen Hook & Engagement
        hook_text = cls._build_hook_text(clean_title, category, bucket_type, price)
        caption_data = cls._build_caption_and_cta(clean_title, bucket_type, price)

        return {
            "content_bucket": bucket_info["bucket"],
            "bucket_strategy": bucket_info["strategy"],
            "storyboard_image_prompt": storyboard_prompt,
            "scene_1_video_prompt": scenes["scene_1"],
            "scene_2_video_prompt": scenes["scene_2"],
            "scene_3_video_prompt": scenes["scene_3"],
            "estimated_video_duration": "10-15 seconds (2-3 clips stitched in CapCut @ 0.8x)",
            "on_screen_hook_text": hook_text,
            "audio_recommendation": scenes["audio"],
            "instagram_caption": caption_data["caption"],
            "cta_keyword": caption_data["keyword"],
        }

    @classmethod
    def _build_storyboard_image_prompt(cls, title: str, category: str, bucket_type: str) -> str:
        if bucket_type == "conversion":
            environment = "modern luxury aesthetic Indian modular kitchen with clean quartz countertop, warm under-cabinet ambient lighting, sparkling clean and organized"
        elif "Beauty" in category or "Grooming" in category:
            environment = "spa-like luxury aesthetic bathroom with fluted wood vanity, warm backlit mirror, soft cotton towels, morning golden hour sunlight"
        else:
            environment = "cozy warm Japandi style living room, soft bouclé sofa, warm evening ambient lamp glow, minimalist oak wooden table"

        return (
            f"Commercial aesthetic product photography of {title}, placed in a {environment}. "
            f"Hyper-realistic, soft natural shadows, 8k resolution, cinematic lighting, ultra-clean commercial look, "
            f"shot on 35mm lens, f/1.8 depth of field --ar 9:16 --v 6.0 --style raw"
        )

    @classmethod
    def _build_video_scenes(cls, title: str, category: str, bucket_type: str) -> dict:
        if bucket_type == "conversion":
            # Scene 1: Problem / Before (0-5s)
            scene_1 = (
                f"Close-up macro shot opening on the common clutter or problem area, camera slowly panning in. "
                f"A person's hand reaches in with {title}, placing it neatly into position. "
                f"Soft cinematic focus pull, warm natural lighting."
            )
            # Scene 2: Demonstration (5-10s) with CONTINUITY PROMPT
            scene_2 = (
                f"{CONTINUITY_PROMPT} "
                f"The person demonstrates using {title} effortlessly and smoothly. "
                f"Instant satisfying result is revealed as the area transforms into a neat, modern setup. "
                f"Smooth slow-motion 60fps camera tracking right, crisp product details visible."
            )
            # Scene 3: Satisfying After / Hero Glow (10-15s) with CONTINUITY PROMPT
            scene_3 = (
                f"{CONTINUITY_PROMPT} "
                f"Camera pulls back into a wide cinematic beauty shot showing the complete transformed space. "
                f"Warm golden ambient light glows softly in the background. Ultra-satisfying aesthetic finish."
            )
            audio = "Upbeat Lo-Fi montage beat or trending ASMR clean click audio (Speed 0.8x in CapCut)"

        elif bucket_type == "viral_share":
            # Scene 1: Relatable Hook (0-5s)
            scene_1 = (
                f"Eye-level aesthetic shot in a beautifully lit room. "
                f"Camera slowly pushes in towards {title} arranged in a luxurious gift box / vanity setting. "
                f"Soft dust particles floating in golden hour sunlight, cozy mood."
            )
            # Scene 2: Unboxing / Touch (5-10s) with CONTINUITY PROMPT
            scene_2 = (
                f"{CONTINUITY_PROMPT} "
                f"Hands gently lift {title} up, turning it slightly to reveal the premium textures and finish. "
                f"Smooth handheld camera motion, beautiful bokeh background."
            )
            # Scene 3: Aesthetic Final Frame (10-15s) with CONTINUITY PROMPT
            scene_3 = (
                f"{CONTINUITY_PROMPT} "
                f"Camera glides smoothly to an overhead angle showing {title} completely styled in everyday use. "
                f"Warm evening lighting, cozy ambient aesthetic vibe."
            )
            audio = "Trending acoustic guitar / cozy indie aesthetic audio"

        else:
            # Bucket A: Pure Aesthetics
            scene_1 = (
                f"Cinematic slow push-in shot of a cozy aesthetic space. "
                f"{title} is prominently featured under warm glowing ambient light. "
                f"Minimalist Japandi interior, soft linen textures, evening mood."
            )
            scene_2 = (
                f"{CONTINUITY_PROMPT} "
                f"Gentle slow-motion camera pan from left to right capturing the subtle reflections and warm glow of {title}. "
                f"Ultra-peaceful, dreamy cinematic atmosphere, high dynamic range."
            )
            scene_3 = (
                f"{CONTINUITY_PROMPT} "
                f"Slow zoom out revealing the full cozy corner. Warm lamp light softly fills the frame. "
                f"Hypnotic, loop-friendly final frame."
            )
            audio = "Ambient dreamy synth / Lofi rain sound (Loop seamlessly at 7 seconds)"

        return {
            "scene_1": scene_1,
            "scene_2": scene_2,
            "scene_3": scene_3,
            "audio": audio
        }

    @classmethod
    def _build_hook_text(cls, title: str, category: str, bucket_type: str, price: int) -> str:
        if bucket_type == "conversion":
            hooks = [
                f"The ₹{price} hack you didn't know you needed ✨ (Link in bio)",
                f"Stop doing this mistake in your home! Try this instead 🚫",
                f"The most satisfying home upgrade under ₹{price} 🤍",
                f"How I organized my entire space in 5 minutes 📦"
            ]
        elif bucket_type == "viral_share":
            hooks = [
                f"Send this to someone who needs to gift you this 🎁",
                f"POV: Your space is finally your safe aesthetic space 🌙",
                f"Budget luxury find under ₹{price} that feels like ₹2000 ✨",
                f"Tell me you're obsessed with aesthetic finds without telling me 😭"
            ]
        else:
            hooks = [
                f"Why you should NEVER use the big light at night 🕯️",
                f"The ultimate room aesthetic secret ✨ (Read caption)",
                f"Golden hour in my favorite corner 🌿",
                f"How to make your room feel like a 5-star hotel room 🤎"
            ]
        # Return first hook for default
        return hooks[0]

    @classmethod
    def _build_caption_and_cta(cls, title: str, bucket_type: str, price: int) -> dict:
        keyword = "LINK"
        if "clean" in title.lower() or "spray" in title.lower():
            keyword = "CLEAN"
        elif "light" in title.lower() or "lamp" in title.lower():
            keyword = "GLOW"
        elif "gift" in title.lower():
            keyword = "GIFT"
        else:
            keyword = "ZEN"

        caption = (
            f"Transform your space effortlessly with the {title} ✨\n\n"
            f"✓ Premium aesthetic finish\n"
            f"✓ High utility & everyday convenience\n"
            f"✓ Available for only ₹{price} + FREE Pan-India Shipping!\n\n"
            f"👉 Comment '{keyword}' below and we'll DM you the direct festive discount link instantly!\n"
            f"(Or check link in bio: zenlora.store)"
        )

        return {
            "caption": caption,
            "keyword": keyword
        }
