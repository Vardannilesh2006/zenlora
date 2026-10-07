import math
import re
from config import CATEGORIES, SHIPPING_BUFFER, MIN_MARKUP, TARGET_MARKUP, COMPARE_PRICE_RATIO

class ClassifierAndPricingEngine:
    """Classifies products into Zenlora categories and computes psychological pricing."""

    PSYCHOLOGICAL_POINTS = [199, 249, 299, 349, 399, 449, 499, 549, 599, 699, 799, 899, 999, 1199, 1299, 1499, 1999]

    @classmethod
    def classify(cls, title: str, description: str, tags: list, product_type: str) -> dict:
        combined_text = f"{title} {description} {' '.join(tags)} {product_type}".lower()

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
    def calculate_pricing(cls, wholesale_price: float) -> dict:
        """Calculates realistic D2C psychological selling price, MRP, and gross profit margins."""
        if wholesale_price <= 0:
            wholesale_price = 100.0

        # Estimated bare-minimum breakeven (Wholesale + absorbed shipping)
        landed_cost = wholesale_price + SHIPPING_BUFFER

        # Target raw retail price
        raw_target = (wholesale_price * TARGET_MARKUP) + SHIPPING_BUFFER

        # Snap to closest upper psychological price point
        selling_price = cls.PSYCHOLOGICAL_POINTS[-1]
        for pt in cls.PSYCHOLOGICAL_POINTS:
            if pt >= raw_target:
                selling_price = pt
                break

        # Ensure selling price is never below (wholesale * 2.2 + shipping)
        min_allowed = math.ceil(wholesale_price * MIN_MARKUP + SHIPPING_BUFFER)
        if selling_price < min_allowed:
            for pt in cls.PSYCHOLOGICAL_POINTS:
                if pt >= min_allowed:
                    selling_price = pt
                    break

        # Calculate MRP (Compare-at price) for a visible 50% - 65% discount
        raw_mrp = selling_price * COMPARE_PRICE_RATIO
        mrp = math.ceil(raw_mrp / 100.0) * 100 - 1  # e.g., 899, 999, 1299
        if mrp <= selling_price:
            mrp = selling_price + 300

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

        pricing = cls.calculate_pricing(extracted_data.get("wholesale_price", 0.0))
        zenlora_title = cls.generate_zenlora_title(extracted_data.get("title", ""))

        return {
            **classification,
            **pricing,
            "zenlora_title": zenlora_title
        }
