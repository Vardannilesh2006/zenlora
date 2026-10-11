"""
Data Provenance, Editable User Settings, Festival Calendar, Manual Entries & Audit Log.
Enforces NON-NEGOTIABLE RULE: REAL DATA ONLY.
Every data point carries: source, source_url, fetched_at, method, is_stale, and null_reason.
"""
import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

CURRENT_DIR = Path(__file__).resolve().parent
BASE_DIR = CURRENT_DIR.parent.parent

if os.environ.get("VERCEL"):
    RUNTIME_DATA_DIR = Path("/tmp/data")
    RUNTIME_DATA_DIR.mkdir(parents=True, exist_ok=True)
    REPO_DATA_DIR = BASE_DIR / "data"
else:
    RUNTIME_DATA_DIR = BASE_DIR / "data"
    RUNTIME_DATA_DIR.mkdir(parents=True, exist_ok=True)
    REPO_DATA_DIR = BASE_DIR / "data"
    REPO_DATA_DIR.mkdir(parents=True, exist_ok=True)

SETTINGS_FILE = RUNTIME_DATA_DIR / "user_settings.json"
REPO_SETTINGS_FILE = REPO_DATA_DIR / "user_settings.json"

MANUAL_ENTRIES_FILE = RUNTIME_DATA_DIR / "manual_entries.json"
REPO_MANUAL_ENTRIES_FILE = REPO_DATA_DIR / "manual_entries.json"

AUDIT_LOG_FILE = RUNTIME_DATA_DIR / "audit_log.json"
REPO_AUDIT_LOG_FILE = REPO_DATA_DIR / "audit_log.json"

IST = timezone(timedelta(hours=5, minutes=30))


def now_iso() -> str:
    """Returns current timestamp in ISO-8601 format (IST)."""
    return datetime.now(IST).isoformat(timespec="seconds")


def is_timestamp_stale(fetched_at: Optional[str], stale_days_limit: int = 7) -> bool:
    """Returns True if fetched_at is older than stale_days_limit days."""
    if not fetched_at:
        return False
    try:
        dt = datetime.fromisoformat(fetched_at)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=IST)
        age = datetime.now(IST) - dt
        return age.total_seconds() > (stale_days_limit * 86400)
    except Exception:
        return False


def make_data_point(
    value: Any,
    source: str,
    source_url: str,
    method: str,
    fetched_at: Optional[str] = None,
    null_reason: Optional[str] = None,
    stale_days_limit: int = 7
) -> Dict[str, Any]:
    """
    Standardized provenance wrapper for every single data point in the application.
    Valid methods: 'api', 'scrape', 'manual_entry', 'rule_based', 'user_assumption', 'ai_opinion'
    """
    ts = fetched_at if fetched_at is not None else (now_iso() if value is not None else None)
    stale = is_timestamp_stale(ts, stale_days_limit) if ts else False
    return {
        "value": value,
        "source": source,
        "source_url": source_url,
        "fetched_at": ts,
        "method": method,
        "is_stale": stale,
        "null_reason": null_reason if value is None else None
    }


DEFAULT_SETTINGS: Dict[str, Any] = {
    "cost_assumptions": {
        "_label": "My Assumptions (User-configurable inputs, not external facts)",
        "shipping_cost": 65.0,
        "cod_fee": 20.0,
        "packaging_cost": 10.0,
        "expected_rto_loss": 25.0,
        "min_net_profit": 150.0,
        "min_markup_multiple": 2.5,
        "target_markup_multiple": 3.0,
        "ideal_price_min": 199,
        "ideal_price_max": 799
    },
    "general": {
        "stale_days_limit": 7,
        "delivery_buffer_days": 3,
        "supplier_policy_delivery_min_days": 4,
        "supplier_policy_delivery_max_days": 8,
        "supplier_policy_source_url": "https://deodap.in/policies/shipping-policy"
    },
    "scoring_weights": {
        "c1_pain_or_wow": 12,
        "c2_demo_3_sec": 12,
        "c3_price_band": 10,
        "c4_margin": 15,
        "c5_size_weight_fragility": 10,
        "c6_returns_risk": 10,
        "c7_local_availability": 10,
        "c8_brand_trademark_risk": 7,
        "c9_supplier_reliability": 7,
        "c10_bundle_potential": 7
    },
    "festivals": [
        {
            "id": "navratri",
            "name": "Navratri",
            "date": "2026-10-11",
            "confirmed_by_user": False,
            "verify_note": "Verify date with calendar (User seed date)",
            "regional_note": "Pan-India (Peak in Gujarat, Maharashtra, North India)"
        },
        {
            "id": "dussehra",
            "name": "Dussehra",
            "date": "2026-10-20",
            "confirmed_by_user": False,
            "verify_note": "Verify date with calendar (User seed date)",
            "regional_note": "Pan-India"
        },
        {
            "id": "dhanteras",
            "name": "Dhanteras",
            "date": "2026-11-06",
            "confirmed_by_user": False,
            "verify_note": "Verify date with calendar (User seed date)",
            "regional_note": "Pan-India auspicious buying peak"
        },
        {
            "id": "diwali",
            "name": "Diwali",
            "date": "2026-11-08",
            "confirmed_by_user": False,
            "verify_note": "Verify date with calendar (User seed date)",
            "regional_note": "Pan-India largest festive peak"
        },
        {
            "id": "bhai_dooj",
            "name": "Bhai Dooj",
            "date": "2026-11-11",
            "confirmed_by_user": False,
            "verify_note": "Verify date with calendar (User seed date)",
            "regional_note": "Pan-India sibling gifting"
        },
        {
            "id": "chhath",
            "name": "Chhath Puja",
            "date": "2026-11-15",
            "confirmed_by_user": False,
            "verify_note": "Verify date with calendar (User seed date)",
            "regional_note": "High demand in Bihar, UP, Jharkhand — verify supplier stock before listing"
        }
    ],
    "festival_keyword_seeds": {
        "_label": "Starting Keyword Seeds (User ideas for catalog filtering, not demand data)",
        "Diwali Cleaning": [
            "corner brush", "spin mop", "microfiber", "scrub brush", "drain tool",
            "fan duster", "wiper", "cleaning brush", "lint roller"
        ],
        "Diwali Decor": [
            "led string light", "led diya", "water sensor", "rangoli stencil",
            "toran", "tealight holder", "kapoor dani", "camphor diffuser", "shubh labh", "acrylic lamp"
        ],
        "Diwali Gifting": [
            "scented candle", "aroma diffuser", "gift combo", "dry fruit box", "gift set"
        ],
        "Dhanteras": [
            "pooja thali", "steel utensil", "brass", "kalash", "copper bottle", "chowki"
        ],
        "Bhai Dooj": [
            "grooming kit", "gift box", "manicure set", "wallet combo"
        ],
        "Chhath": [
            "soop", "daura", "pooja", "kalash", "diya"
        ]
    },
    "restricted_rules": {
        "firecrackers_patakhe": [
            "firecracker", "patakha", "patakhe", "cracker", "sparkler", "anar", "chakri"
        ],
        "food_items_fssai": [
            "edible", "chocolate", "sweet", "namkeen", "masala", "spices", "tea leaves", "food item"
        ],
        "health_claims": [
            "cure", "diabetes", "blood pressure", "weight loss pill", " slimming oil", "medical claim"
        ],
        "gold_silver_hallmark": [
            "pure gold", "pure silver", "999 silver", "24k gold", "hallmark", "1 gram gold", "gold forming"
        ],
        "fragile_idols_glass": [
            "crystal ball", "glass jar", "glass cup", "ceramic", "terracotta", "clay", "porcelain", "fragile idol"
        ]
    },
    "returns_risk_rules": {
        "clothing_shoes_sizing": [
            "shirt", "t-shirt", "kurti", "saree", "lehenga", "dress", "jeans", "trouser",
            "shoe", "sneaker", "slipper", "sandal", "heels", "bangle", "ring", "anklet",
            "necklace", "earring", "jhumka", "choker", "mangalsutra", "bracelet"
        ],
        "unsafe_electronics": [
            "220v uncertified", "high voltage heater", "immersion rod"
        ]
    },
    "brand_trademark_list": [
        "nike", "adidas", "puma", "apple", "iphone", "airpods", "samsung", "gucci",
        "rolex", "louis vuitton", "disney", "marvel", "avengers", "sony", "dyson", "boat", "jbl", "zara"
    ]
}


_SETTINGS_CACHE: Dict[str, Any] = {"mtime": 0.0, "data": None}
_MANUAL_CACHE: Dict[str, Any] = {"mtime": 0.0, "data": None}


def load_settings() -> Dict[str, Any]:
    """Loads user settings from disk (with fast mtime cache), initializing defaults if needed."""
    for target in (SETTINGS_FILE, REPO_SETTINGS_FILE):
        if target.exists():
            try:
                mtime = target.stat().st_mtime
                if _SETTINGS_CACHE["data"] is not None and _SETTINGS_CACHE["mtime"] == mtime:
                    return _SETTINGS_CACHE["data"]
                with open(target, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                merged = json.loads(json.dumps(DEFAULT_SETTINGS))
                for k, v in saved.items():
                    if isinstance(v, dict) and isinstance(merged.get(k), dict):
                        merged[k].update(v)
                    else:
                        merged[k] = v
                _SETTINGS_CACHE["mtime"] = mtime
                _SETTINGS_CACHE["data"] = merged
                return merged
            except Exception:
                pass
    save_settings(DEFAULT_SETTINGS, log_change=False)
    return json.loads(json.dumps(DEFAULT_SETTINGS))


def save_settings(new_settings: Dict[str, Any], log_change: bool = True) -> Dict[str, Any]:
    """Saves updated user settings to disk and records an audit entry."""
    for target in (SETTINGS_FILE, REPO_SETTINGS_FILE):
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            with open(target, "w", encoding="utf-8") as f:
                json.dump(new_settings, f, indent=2, ensure_ascii=False)
            _SETTINGS_CACHE["mtime"] = target.stat().st_mtime
            _SETTINGS_CACHE["data"] = new_settings
        except Exception:
            pass
    if log_change:
        append_audit_log(
            action="settings_updated",
            target="user_settings.json",
            source="User Settings UI/API",
            method="manual_entry",
            details="Updated cost assumptions, weights, festival dates, or keyword rules."
        )
    return new_settings


def calculate_festival_cutoffs(
    supplier_max_days: Optional[int],
    settings: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """
    Delivery cutoff calculator:
    festival_date - supplier_max_delivery_days - user_buffer_days = last_order_date.
    Shows 'too_late' if today is past last_order_date.
    Uses real supplier delivery range (or explicitly labelled store shipping policy if product page doesn't show it).
    """
    if settings is None:
        settings = load_settings()

    buffer_days = int(settings.get("general", {}).get("delivery_buffer_days", 3))
    today_date = datetime.now(IST).date()

    results = []
    for fest in settings.get("festivals", []):
        fest_date_str = fest.get("date", "")
        try:
            f_date = datetime.strptime(fest_date_str, "%Y-%m-%d").date()
        except Exception:
            continue

        days_until_festival = (f_date - today_date).days

        if supplier_max_days is None:
            results.append({
                **fest,
                "festival_date": fest_date_str,
                "days_until_festival": days_until_festival,
                "supplier_max_days_used": None,
                "buffer_days": buffer_days,
                "last_order_date": None,
                "days_until_cutoff": None,
                "can_deliver_in_time": False,
                "status": "unknown_delivery_time",
                "status_label": "Delivery cutoff unknown (Supplier max delivery days not set)"
            })
        else:
            total_lead_days = int(supplier_max_days) + buffer_days
            cutoff_date = f_date - timedelta(days=total_lead_days)
            days_left_to_order = (cutoff_date - today_date).days
            is_too_late = today_date > cutoff_date

            if days_until_festival < 0:
                status = "festival_passed"
                status_label = "Festival Passed"
            elif is_too_late:
                status = "too_late"
                status_label = f"⚠️ TOO LATE for {fest['name']} (Cutoff was {cutoff_date.strftime('%d %b')})"
            elif days_left_to_order <= 5:
                status = "urgent"
                status_label = f"⏳ URGENT: {days_left_to_order}d left (Last order: {cutoff_date.strftime('%d %b')})"
            else:
                status = "on_time"
                status_label = f"✅ Open until {cutoff_date.strftime('%d %b')} ({days_left_to_order}d left)"

            results.append({
                **fest,
                "festival_date": fest_date_str,
                "days_until_festival": days_until_festival,
                "supplier_max_days_used": int(supplier_max_days),
                "buffer_days": buffer_days,
                "last_order_date": cutoff_date.isoformat(),
                "days_left_to_order": days_left_to_order,
                "days_until_cutoff": days_left_to_order,
                "can_deliver_in_time": status in ("on_time", "urgent"),
                "status": status,
                "status_label": status_label
            })
    return results


def load_manual_entries() -> Dict[str, Dict[str, Any]]:
    """Loads all user manual entries (with fast mtime cache)."""
    for target in (MANUAL_ENTRIES_FILE, REPO_MANUAL_ENTRIES_FILE):
        if target.exists():
            try:
                mtime = target.stat().st_mtime
                if _MANUAL_CACHE["data"] is not None and _MANUAL_CACHE["mtime"] == mtime:
                    return _MANUAL_CACHE["data"]
                with open(target, "r", encoding="utf-8") as f:
                    data = json.load(f)
                _MANUAL_CACHE["mtime"] = mtime
                _MANUAL_CACHE["data"] = data
                return data
            except Exception:
                pass
    return {}


def get_product_manual_entry(handle: str) -> Dict[str, Any]:
    """Returns manual entry dictionary for a single product handle."""
    entries = load_manual_entries()
    return entries.get(handle, {})


def save_product_manual_entry(handle: str, section: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Saves a manual entry section for a product handle and records an audit log entry.
    """
    entries = dict(load_manual_entries())
    if handle not in entries:
        entries[handle] = {}

    ts = now_iso()
    payload_with_meta = {
        **payload,
        "fetched_at": ts,
        "method": "manual_entry",
        "source": "Manual User Entry"
    }
    entries[handle][section] = payload_with_meta

    for target in (MANUAL_ENTRIES_FILE, REPO_MANUAL_ENTRIES_FILE):
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            with open(target, "w", encoding="utf-8") as f:
                json.dump(entries, f, indent=2, ensure_ascii=False)
            _MANUAL_CACHE["mtime"] = target.stat().st_mtime
            _MANUAL_CACHE["data"] = entries
        except Exception:
            pass

    append_audit_log(
        action=f"manual_entry_{section}",
        target=handle,
        source="Manual User Entry",
        method="manual_entry",
        details=json.dumps(payload, ensure_ascii=False)[:300]
    )
    return entries[handle]


def append_audit_log(
    action: str,
    target: str,
    source: str,
    method: str,
    details: str = "",
    source_url: str = ""
) -> None:
    """Appends an immutable entry to the audit log."""
    logs = get_audit_logs(limit=500)
    entry = {
        "timestamp": now_iso(),
        "action": action,
        "target": target,
        "source": source,
        "source_url": source_url,
        "method": method,
        "details": details
    }
    logs.insert(0, entry)
    logs = logs[:500]
    for path in (AUDIT_LOG_FILE, REPO_AUDIT_LOG_FILE):
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(logs, f, indent=2, ensure_ascii=False)
        except Exception:
            pass


def get_audit_logs(limit: int = 100) -> List[Dict[str, Any]]:
    """Returns recent audit log entries."""
    for path in (AUDIT_LOG_FILE, REPO_AUDIT_LOG_FILE):
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    return data[:limit]
            except Exception:
                pass
    return []
