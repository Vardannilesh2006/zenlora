import math
import re
from config import CATEGORIES, SHIPPING_BUFFER, MIN_MARKUP, TARGET_MARKUP, COMPARE_PRICE_RATIO

class ClassifierAndPricingEngine:
    """Classifies products into Zenlora categories and computes psychological pricing."""

    PSYCHOLOGICAL_POINTS = [199, 249, 299, 339, 349, 369, 379, 399, 429, 449, 479, 499, 549, 599, 699, 799, 899, 999, 1199, 1299, 1499, 1999]

    @classmethod
    def classify(cls, title: str, description: str, tags: list, product_type: str) -> dict:
        if tags is None:
            tag_list = []
        elif isinstance(tags, str):
            tag_list = [tag.strip() for tag in re.split(r"[,|;]+", tags) if tag.strip()]
        else:
            tag_list = [str(tag).strip() for tag in tags if str(tag).strip()]

        combined_text = f"{title} {description} {' '.join(tag_list)} {product_type}".lower()

        scores = {}
        for category, keywords in CATEGORIES.items():
            score = 0
            for kw in keywords:
                # Word boundary search for precision
                pattern = r"\b" + re.escape(kw) + r"\b"
                matches = len(re.findall(pattern, combined_text))
                if matches > 0:
                    score += (matches * 2 if kw in title.lower() else matches)
            scores[category] = score

        # Find category with highest score
        best_category = max(scores, key=scores.get)
        if scores[best_category] > 0:
            assigned_category = best_category
            confidence = "High" if scores[best_category] >= 3 else "Medium"
        else:
            assigned_category = "Trending Problem-Solver Gadget"
            confidence = "Dynamic"

        return {
            "primary_category": assigned_category,
            "confidence": confidence,
            "scores": scores
        }

    @classmethod
    def generate_zenlora_title(cls, deodap_title: str) -> str:
        """Transforms long wholesale titles into clean, high-converting D2C brand titles."""
        clean = deodap_title.strip()
        # Remove common wholesale noise words
        noise_patterns = [
            r"\(pack of \d+\)", r"pack of \d+", r"set of \d+", r"\(set of \d+\)",
            r"wholesale", r"best quality", r"hot sale", r"combo", r"with box",
            r"-\s*multi\s*color", r"\(random color\)", r"mix color", r"colour", r"color",
            r"\[.*?\]", r"\(.*?\)"
        ]
        for p in noise_patterns:
            clean = re.sub(p, "", clean, flags=re.IGNORECASE)

        clean = " ".join(clean.split())
        words = clean.split()
        if len(words) > 8:
            clean = " ".join(words[:8])

        # Title Case
        clean = clean.title()
        return f"Zenlora™ {clean}"

    @classmethod
    def calculate_pricing(cls, wholesale_price: float, seed_key: str = "") -> dict:
        """Calculates realistic D2C psychological selling price, MRP, and gross profit margins."""
        if wholesale_price <= 0:
            wholesale_price = 100.0

        # Estimated bare-minimum breakeven (Wholesale + absorbed shipping)
        landed_cost = wholesale_price + SHIPPING_BUFFER

        if 0 < wholesale_price <= 50.0:
            key = str(seed_key or "zenlora").strip().lower()
            seed = sum((idx + 1) * ord(ch) for idx, ch in enumerate(key)) + int(round(float(wholesale_price)))
            selling_price = 179 + (seed % 7)
        elif 50.0 < wholesale_price <= 100.0:
            # Budget utilities selling at 249-299 with 100-140 profit
            target_raw = wholesale_price + 50.0 + 110.0
            selling_price = 249 if target_raw <= 249 else 299
        else:
            # Target Premium Sweet Spot: Wholesale (100-240) + Shipping (50) + Healthy Net Margin (120-160)
            target_raw = wholesale_price + 50.0 + 135.0
            
            # Snap to psychological points (339, 349, 369, 379, 399, 429, 449, 479, 499)
            sweet_points = [339, 349, 369, 379, 399, 429, 449, 479, 499, 549, 599]
            selling_price = sweet_points[-1]
            for pt in sweet_points:
                if pt >= target_raw:
                    selling_price = pt
                    break
            # Hard bounds: keep worth-it products in the 339-499 sweet spot
            if 100 <= wholesale_price <= 240 and selling_price > 499:
                selling_price = 499

        # Realistic D2C Box MRP: 25% - 35% discount perception (believable, authentic, zero inflated fake markup)
        # e.g. Selling 349 -> MRP 499 (30% OFF), Selling 399 -> MRP 569, Selling 449 -> MRP 649, Selling 499 -> MRP 699
        mrp_targets = {
            179: 249, 184: 249, 199: 299, 239: 349, 249: 349, 299: 449,
            319: 449, 329: 479, 339: 489, 349: 499, 369: 529, 379: 549,
            399: 569, 429: 599, 449: 649, 479: 679, 499: 699, 549: 779,
            599: 849, 699: 999, 799: 1149, 899: 1299, 999: 1399
        }
        if int(selling_price) in mrp_targets:
            mrp = mrp_targets[int(selling_price)]
        else:
            raw_mrp = math.ceil((selling_price * 1.42) / 10.0) * 10 - 1
            mrp = max(raw_mrp, selling_price + 100)

        # Gross Margin (after product cost and shipping buffer)
        gross_profit = round(selling_price - landed_cost, 2)
        profit_margin_pct = round((gross_profit / selling_price) * 100, 1)
        discount_pct = round(((mrp - selling_price) / mrp) * 100)

        return {
            "wholesale_price": round(wholesale_price, 2),
            "selling_price": int(selling_price),
            "mrp": int(mrp),
            "discount_pct": int(discount_pct),
            "shipping_buffer": int(SHIPPING_BUFFER),
            "gross_profit": gross_profit,
            "profit_margin_pct": profit_margin_pct,
            "badge": f"Save {discount_pct}%"
        }

    @classmethod
    def process(cls, extracted_data: dict) -> dict:
        """Full processing pipeline for classification and pricing."""
        classification = cls.classify(
            title=extracted_data.get("title", ""),
            description=extracted_data.get("description", ""),
            tags=extracted_data.get("tags", []),
            product_type=extracted_data.get("product_type", "")
        )

        pricing = cls.calculate_pricing(
            extracted_data.get("wholesale_price", 0.0),
            seed_key=extracted_data.get("handle") or extracted_data.get("sku") or extracted_data.get("title", ""),
        )
        zenlora_title = cls.generate_zenlora_title(extracted_data.get("title", ""))

        return {
            **classification,
            **pricing,
            "zenlora_title": zenlora_title
        }
