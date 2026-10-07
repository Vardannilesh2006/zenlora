import os
import shutil
from pathlib import Path

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent
PIPELINE_DIR = BASE_DIR / "pipeline"

if os.environ.get("VERCEL"):
    EXPORTS_DIR = Path("/tmp/exports")
    DATA_DIR = Path("/tmp/data")
    DATABASE_FILE = DATA_DIR / "products_db.json"
    WINNING_DB_FILE = DATA_DIR / "winning_products.json"
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    # Seed /tmp database from bundled repo data if not present or needs refresh
    seed_file = BASE_DIR / "data" / "products_db.json"
    if seed_file.exists():
        if not DATABASE_FILE.exists() or (DATABASE_FILE.stat().st_size < seed_file.stat().st_size):
            try:
                shutil.copy(seed_file, DATABASE_FILE)
            except Exception:
                pass

    seed_winning = BASE_DIR / "data" / "winning_products.json"
    if seed_winning.exists():
        if not WINNING_DB_FILE.exists() or (WINNING_DB_FILE.stat().st_size < seed_winning.stat().st_size):
            try:
                shutil.copy(seed_winning, WINNING_DB_FILE)
            except Exception:
                pass
else:
    EXPORTS_DIR = BASE_DIR / "exports"
    DATA_DIR = BASE_DIR / "data"
    DATABASE_FILE = DATA_DIR / "products_db.json"
    WINNING_DB_FILE = DATA_DIR / "winning_products.json"
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

# Continuity Prompt for AI Video Generation (Kling / Runway / Luma)
CONTINUITY_PROMPT = (
    "Continue the video seamlessly from the last scene of the previous clip. "
    "Keep the same characters, appearance, clothing, environment, camera style, lighting, "
    "and overall visual consistency. The new scene must naturally begin exactly where the previous scene ended."
)

# Core Niche Categories with keywords
CATEGORIES = {
    "Home Decor & Aesthetic Living": [
        "decor", "vase", "cushion", "curtain", "lamp", "statue", "candle", "aroma", "diffuser",
        "rug", "carpet", "wall", "painting", "clock", "frame", "planter", "pot", "flower",
        "ambient", "lighting", "table", "holder", "sculpture", "aesthetic", "bedsheet"
    ],
    "Kitchen & Home Improvement Hacks": [
        "kitchen", "cookware", "chopper", "dispenser", "cleaner", "scrub", "wiper", "mop",
        "organizer", "rack", "tray", "bottle", "container", "box", "peeler", "knife",
        "sink", "drain", "hanger", "storage", "foldable", "silicone", "mat", "sponge",
        "cloth", "rag", "spray", "clean", "bathroom", "shower", "hook"
    ],
    "Smart Lifestyle & Home Gadgets": [
        "led", "smart", "usb", "rechargeable", "motion", "sensor", "digital", "gadget",
        "portable", "electric", "charger", "wireless", "clock", "mini", "fan", "light",
        "strip", "automatic", "tool", "alarm", "stand", "holder"
    ],
    "Beauty, Grooming & Self-Care": [
        "roller", "gua sha", "ice", "facial", "face", "massager", "razor", "derma",
        "skin", "skincare", "beauty", "hair", "scalp", "makeup", "brush", "cosmetic",
        "trimmer", "grooming", "pouch", "serum", "cleaner", "care"
    ],
    "Diwali & Festive Gifting Specials": [
        "diwali", "festive", "diya", "lights", "gift", "hamper", "fairy", "star",
        "curtain light", "decoration", "puja", "festive gift", "brass"
    ]
}

# Pricing Strategy
SHIPPING_BUFFER = 60.0  # In INR: Absorbed shipping cost for free delivery perception
MIN_MARKUP = 2.6        # Minimum multiplier on wholesale cost
TARGET_MARKUP = 3.2     # Target multiplier on wholesale cost
COMPARE_PRICE_RATIO = 2.2 # MRP multiplier relative to selling price for 50-60% OFF perception
