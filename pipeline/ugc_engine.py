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
    def _build_scene_environment(cls, title: str, category: str, bucket_type: str) -> dict:
        """
        Builds a unified visual environment DNA shared between the Storyboard Image
        and all 3 consecutive video generation scenes.
        """
        title_lower = title.lower()

        if "kitchen" in category.lower() or any(w in title_lower for w in ["peeler", "knife", "chopper", "dispenser", "sponge", "sink", "drain", "cleaner", "mop", "wiper", "dish"]):
            setting = "modern luxury aesthetic Indian modular kitchen with clean white quartz countertops, sleek fluted wooden cabinetry, subtle warm under-cabinet LED strip glow"
            atmosphere = "sparkling clean, organized luxury interior, cinematic golden ambient highlights, realistic soft shadows"
            interaction_problem = "a cluttered or messy countertop needing smart organization"
            interaction_action = f"using {title} smoothly in real-time, instantly slicing, peeling, or organizing with effortless ease"
            interaction_hero = f"{title} resting elegantly on the clean polished quartz countertop beside fresh culinary accents"
        elif "beauty" in category.lower() or "grooming" in category.lower() or any(w in title_lower for w in ["roller", "gua sha", "ice", "facial", "massager", "skin", "hair", "brush"]):
            setting = "spa-like luxury aesthetic bathroom with natural fluted oak vanity, warm backlit circular mirror, folded plush cotton waffle towels"
            atmosphere = "soft morning golden hour diffusion, gentle water mist, tranquil serene spa aesthetic"
            interaction_problem = "a tired morning skincare routine needing instant refresh"
            interaction_action = f"gliding {title} gently across skin with soothing, satisfying natural skincare motion"
            interaction_hero = f"{title} placed on the warm oak vanity next to delicate dried eucalyptus and glowing ambient candle"
        elif "festive" in category.lower() or "diwali" in category.lower() or any(w in title_lower for w in ["diya", "fairy", "curtain light", "puja", "festive", "brass"]):
            setting = "festive modern Indian living room during Diwali twilight, warm terracotta and brass accents, soft marigold floral decor"
            atmosphere = "magical warm bokeh, flickering soft diya glow, warm 2700K golden festive light"
            interaction_problem = "a dim living space awaiting festive warmth and celebration"
            interaction_action = f"switching on or setting up {title}, casting instant breathtaking golden glow across the entire room"
            interaction_hero = f"{title} glowing brightly as the centerpiece of festive home celebration, creating pure warm festive magic"
        elif "gadget" in category.lower() or any(w in title_lower for w in ["usb", "rechargeable", "led", "sensor", "digital", "automatic", "smart"]):
            setting = "minimalist Japandi smart home setup, matte walnut desk, sleek architectural textures, warm diffuse lighting"
            atmosphere = "modern minimalist aesthetic, tactile premium materials, soft warm-white indirect backlight"
            interaction_problem = "a dull, manual routine needing a seamless smart upgrade"
            interaction_action = f"one-touch activating {title}, showing its crisp responsive mechanism and high-tech utility in action"
            interaction_hero = f"{title} functioning seamlessly as a modern lifestyle essential on the minimalist walnut surface"
        else:
            # Home Decor & Aesthetic Living default
            setting = "warm cozy Japandi-style living room, textured bouclé furniture, smooth oak wooden coffee table, neutral beige limestone wall"
            atmosphere = "tranquil evening golden hour light, soft linen curtains catching gentle breeze, cozy peaceful atmosphere"
            interaction_problem = "a plain empty corner in need of warm aesthetic character"
            interaction_action = f"hands gently placing and styling {title} into place, instantly elevating the room's entire visual warmth"
            interaction_hero = f"{title} sitting serenely as the aesthetic hero piece, warm ambient light washing softly across its texture"

        return {
            "setting": setting,
            "atmosphere": atmosphere,
            "interaction_problem": interaction_problem,
            "interaction_action": interaction_action,
            "interaction_hero": interaction_hero,
        }

    @classmethod
    def _build_storyboard_image_prompt(cls, title: str, category: str, bucket_type: str) -> str:
        env = cls._build_scene_environment(title, category, bucket_type)
        return (
            f"Commercial aesthetic product photography of {title}, placed in a {env['setting']}. "
            f"{env['atmosphere']}. "
            f"Hyper-realistic, soft natural shadows, 8k resolution, cinematic lighting, ultra-clean commercial look, "
            f"shot on 35mm lens, f/1.8 depth of field --ar 9:16 --v 6.0 --style raw"
        )

    @classmethod
    def _build_video_scenes(cls, title: str, category: str, bucket_type: str) -> dict:
        env = cls._build_scene_environment(title, category, bucket_type)
        exact_continuity = CONTINUITY_PROMPT.strip()

        # Scene 1: Starting directly from the Storyboard Reference Image (Image-to-Video 0-5s)
        scene_1 = (
            f"Starting directly from the reference image: smooth cinematic camera push-in on {title} placed in the {env['setting']}. "
            f"{env['atmosphere']}. Subtle organic camera movement as hands enter the frame addressing {env['interaction_problem']}. "
            f"4K, 60fps, photographic depth of field, exact color palette and lighting matching the reference image."
        )

        # Scene 2: Continuous Demonstration (5-10s) with EXACT verbatim continuity prefix
        scene_2 = (
            f"{exact_continuity} "
            f"Camera holds steady close-up tracking as hands demonstrate {env['interaction_action']}. "
            f"The environment remains the identical {env['setting']} with matching lighting. "
            f"Smooth 60fps slow-motion capture, crisp tactile sound cues, completely seamless natural flow without any jump cut."
        )

        # Scene 3: Satisfying Hero Aftermath (10-15s) with EXACT verbatim continuity prefix
        scene_3 = (
            f"{exact_continuity} "
            f"Camera glides smoothly back into a wide cinematic beauty hero reveal: {env['interaction_hero']}. "
            f"The same {env['setting']} is now completely transformed, warm ambient lighting softly glowing. "
            f"Ultra-satisfying aesthetic finish, gentle hypnotic loop back to opening frame."
        )

        if bucket_type == "conversion":
            audio = "Upbeat Lo-Fi montage beat or trending ASMR clean click audio (Speed 0.8x in CapCut)"
        elif bucket_type == "viral_share":
            audio = "Trending acoustic guitar / cozy indie aesthetic audio"
        else:
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
