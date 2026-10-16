"""
Script Director Engine
======================
Generates structured multi-scene video scripts tailored for high-conversion Instagram Reels
and Meesho Creator Club Auto-DM workflows.

Key Principle:
1. Generates ONE continuous narrative voiceover track (never broken across scenes).
2. Sets exact second cutoffs for Scene 1 (Hook), Scene 2 (Demo), Scene 3 (CTA).
3. Defines the exact Auto-DM Trigger Keyword (e.g., 'DIWALI', 'LINK', 'DECOR').
"""
import re
from typing import Dict, Any, List

class ScriptDirector:
    """Generates continuous multi-scene reel scripts with exact time budget and Auto-DM triggers."""

    HOOK_TEMPLATES = [
        # Price Shock (Highest CTR in India)
        {
            "type": "price_shock",
            "hook_format": "Amazon pe yeh same cheez ₹{fake_high_price} ki mil rahi thi, but Meesho pe mujhe mili sirf ₹{price} me! 😱",
            "body_format": "Quality itni solid hai ki aap trust nahi karoge! {features}. Festive season aur daily use ke liye ekdum perfect aesthetic vibe deta hai.",
            "cta_format": "Agar aapko bhi direct link chahiye, toh comment karo '{keyword}', aur Meesho ka official bot direct link aapke DM me bhej dega! ✨"
        },
        # Aesthetic Problem Solver
        {
            "type": "problem_solver",
            "hook_format": "Agar aapke ghar me bhi festive makeover aur safai shuru ho gayi hai, toh Meesho ka yeh product aapko zaroor chahiye!",
            "body_format": "Isko set karna super easy hai. {features}. Pura room instant luxury aur festive ready lagne lagta hai.",
            "cta_format": "Link chahiye toh jaldi comment karo '{keyword}', direct link instant aapke DM me aa jayega!"
        },
        # Under Budget Aesthetic Finds
        {
            "type": "under_budget",
            "hook_format": "Meesho Festive Home Decor Finds under ₹{budget_round} that actually look super expensive! ✨",
            "body_format": "Pehli nazar me koi bol hi nahi sakta ki yeh Meesho ka hai. {features}. Limited stock bacha hai toh miss mat karna.",
            "cta_format": "Comment karo '{keyword}', aur Meesho direct link aur coupon code aapke DM me bhej dega!"
        }
    ]

    @classmethod
    def generate_script(cls, product_title: str, price: int, category: str = "Home Decor", keyword: str = "DIWALI") -> Dict[str, Any]:
        clean_title = re.sub(r"[^a-zA-Z0-9\s]", "", product_title).strip()
        price_val = max(99, int(price))
        fake_high = max(499, price_val * 3 - (price_val % 100) - 1)
        budget_round = (price_val // 100 + 1) * 100

        # Select template
        template = cls.HOOK_TEMPLATES[0] if "decor" in category.lower() or "festive" in category.lower() else cls.HOOK_TEMPLATES[1]

        # Natural feature extraction
        feature_desc = f"Handcrafted premium finish ke sath durable quality hai, jo har kisi ko attract karegi"
        if "light" in clean_title.lower() or "diya" in clean_title.lower():
            feature_desc = "Water sensor technology hai, paani daalte hi automatic glowing warm festive lights jal jaati hain"
        elif "kitchen" in category.lower() or "oil" in clean_title.lower() or "dispenser" in clean_title.lower():
            feature_desc = "Zero mess aur controlled spray system hai, jo cooking ko super convenient bana deta hai"

        hook_text = template["hook_format"].format(fake_high_price=fake_high, price=price_val)
        body_text = template["body_format"].format(features=feature_desc)
        cta_text = template["cta_format"].format(keyword=keyword)

        # ONE continuous master voiceover string (No interruptions!)
        master_voiceover = f"{hook_text} {body_text} {cta_text}".strip()

        # Target scene breakdown
        scenes = [
            {
                "scene_id": 1,
                "name": "Visual Hook",
                "target_duration_s": 3.5,
                "narration": hook_text,
                "visual_prompt": f"Dramatic cinematic macro camera push-in on {clean_title}, warm festive rim lighting, 4K luxury D2C aesthetic, studio backdrop",
                "on_screen_text": f"AMAZON: ₹{fake_high} ❌\nMEESHO: ₹{price_val} ✅"
            },
            {
                "scene_id": 2,
                "name": "Feature Demo & Proof",
                "target_duration_s": 6.5,
                "narration": body_text,
                "visual_prompt": f"Smooth slow-motion demonstration of {clean_title} in modern Indian living space, authentic hands-on product interaction, warm bokeh",
                "on_screen_text": "PREMIUM QUALITY ✨"
            },
            {
                "scene_id": 3,
                "name": "Auto-DM Call To Action",
                "target_duration_s": 4.5,
                "narration": cta_text,
                "visual_prompt": f"Aesthetic table display of {clean_title} with glowing festival backdrop, high-contrast CTA banner overlay",
                "on_screen_text": f"👇 COMMENT '{keyword}' FOR DIRECT LINK 👇"
            }
        ]

        total_words = len(master_voiceover.split())
        est_duration = round(total_words / 2.6, 1)  # ~150 words per minute cadence

        # High-CTR Instagram Caption
        caption = (
            f"Meesho Festive Find Under ₹{price_val}! 😱✨\n\n"
            f"Quality is 10/10 and it looks so premium in real life!\n\n"
            f"💬 Comment '{keyword}' below and I'll send the direct buy link straight to your DMs!\n\n"
            f"Follow @zenlorafinds for daily budget festive & home decor finds ✨\n\n"
            f"#meeshofinds #meeshofestive #diwalidecor #meeshodecor #budgetdecor #homemakeover #reelsindia #trendingreels"
        )

        return {
            "product_title": clean_title,
            "price": price_val,
            "category": category,
            "keyword": keyword,
            "master_voiceover": master_voiceover,
            "estimated_duration_s": est_duration,
            "scenes": scenes,
            "caption": caption,
            "hashtags": ["meeshofinds", "diwalidecor", "meeshocreatorclub", "budgetbuys", "festivemakeover"]
        }
