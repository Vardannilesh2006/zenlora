"""
Zero-Repeat SmartBiz Export Vault & 4-Key Deduplication Ledger
==============================================================
Guarantees that no product is ever exported twice across unlimited CSV/XLSX downloads,
multiple sessions, or Vercel serverless restarts.

4-Key Product Fingerprint:
1. `sku`        — Normalized DeoDap / Custom SKU
2. `handle`     — Normalized DeoDap URL handle
3. `variant_id` — Stringified Shopify Variant ID
4. `title_fp`   — Normalized core product title fingerprint (catches duplicate DeoDap listings under different SKUs)
"""

import csv
import io
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

CURRENT_DIR = Path(__file__).resolve().parent
ROOT_DIR = CURRENT_DIR.parent.parent
REPO_LEDGER_FILE = ROOT_DIR / "data" / "exported_skus_ledger.json"
TMP_LEDGER_FILE = Path("/tmp/zenlora_exported_skus_ledger.json") if os.name != "nt" else (ROOT_DIR / "data" / "exported_skus_ledger_runtime.json")

_STOP_WORDS = {
    "premium", "quality", "high", "best", "new", "latest", "modern", "stylish",
    "multipurpose", "multi", "purpose", "function", "functional", "portable",
    "durable", "heavy", "duty", "home", "kitchen", "use", "daily", "for", "with",
    "and", "the", "in", "of", "to", "a", "an", "by", "on", "at", "from", "set",
    "pack", "pc", "pcs", "piece", "pieces", "combo", "deodap", "zenlora", "india",
    "original", "authentic", "assorted", "color", "colour", "multicolor", "random",
}


def normalize_sku(sku: Any) -> str:
    if not sku:
        return ""
    return re.sub(r"\s+", "", str(sku).strip().lower())


def normalize_handle(handle: Any) -> str:
    if not handle:
        return ""
    h = str(handle).strip().lower()
    if "/products/" in h:
        h = h.split("/products/")[-1]
    h = h.split("?")[0].split("#")[0].strip("/")
    return h


def normalize_title_fingerprint(title: Any) -> str:
    """
    Produces a canonical title fingerprint so identical products listed under two different DeoDap SKUs
    (e.g. '22461_2in1_cleaning_brush' and '7928_2in1_cleaning_brush') share the same fingerprint.
    """
    if not title:
        return ""
    t = str(title).lower()
    # Strip trailing parenthetical SKU/pack notes
    t = re.sub(r"\([^)]*\)", " ", t)
    t = re.sub(r"\[[^\]]*\]", " ", t)
    # Normalize "2-in-1" / "2 in 1" -> "2in1"
    t = re.sub(r"(\d+)\s*-\s*in\s*-\s*(\d+)", r"\1in\2", t)
    t = re.sub(r"(\d+)\s+in\s+(\d+)", r"\1in\2", t)
    # Remove weight/volume/pack tokens like 100ml, 250g, 1pc, 10pc
    t = re.sub(r"\b\d+\s*(?:pc|pcs|piece|pieces|gm|g|kg|ml|ltr|l|cm|mm|inch|w|led|leds)\b", " ", t)
    # Split into alphanumeric tokens
    tokens = re.findall(r"[a-z0-9]+", t)
    core_tokens = [tok for tok in tokens if tok not in _STOP_WORDS and len(tok) > 1 and not tok.isdigit()]
    if not core_tokens:
        core_tokens = [tok for tok in tokens if len(tok) > 1]
    # Take first 5 distinctive tokens in order
    return "_".join(core_tokens[:5])


def extract_product_fingerprints(product: Dict[str, Any]) -> Dict[str, str]:
    """
    Extracts all 4 deduplication keys from a product dictionary.
    """
    sku = normalize_sku(
        product.get("sku")
        or (product.get("smartbiz_preset") or {}).get("custom_sku")
        or product.get("custom_sku")
    )
    handle = normalize_handle(product.get("handle") or product.get("deodap_url") or product.get("source_url"))
    variant_id = str(product.get("variant_id") or "").strip()
    # Use raw DeoDap title first for stable fingerprinting, fallback to zenlora_title/product_name
    raw_title = product.get("title") or product.get("product_name") or product.get("zenlora_title") or ""
    title_fp = normalize_title_fingerprint(raw_title)

    return {
        "sku": sku,
        "handle": handle,
        "variant_id": variant_id,
        "title_fp": title_fp,
        "title": str(raw_title).strip()[:140],
    }


def _read_json_file(path: Path) -> Dict[str, Any]:
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return {}


def load_export_ledger() -> Dict[str, Any]:
    """
    Loads and merges the permanent repository ledger (`data/exported_skus_ledger.json`)
    and runtime ledger (`/tmp/zenlora_exported_skus_ledger.json`) so zero history is ever lost.
    """
    repo_data = _read_json_file(REPO_LEDGER_FILE)
    tmp_data = _read_json_file(TMP_LEDGER_FILE)

    entries_by_key: Dict[str, Dict[str, Any]] = {}
    for source_dict in (repo_data, tmp_data):
        for item in source_dict.get("entries", []):
            if not isinstance(item, dict):
                continue
            primary_key = item.get("sku") or item.get("handle") or item.get("title_fp")
            if primary_key:
                entries_by_key[primary_key] = item

    last_page = max(
        int(repo_data.get("last_harvested_deodap_page") or 3),
        int(tmp_data.get("last_harvested_deodap_page") or 3),
    )
    export_batches = max(
        int(repo_data.get("total_export_batches") or 0),
        int(tmp_data.get("total_export_batches") or 0),
    )

    entries_list = list(entries_by_key.values())
    skus: Set[str] = set()
    handles: Set[str] = set()
    variant_ids: Set[str] = set()
    title_fps: Set[str] = set()

    for e in entries_list:
        if e.get("sku"):
            skus.add(normalize_sku(e["sku"]))
        if e.get("handle"):
            handles.add(normalize_handle(e["handle"]))
        if e.get("variant_id"):
            variant_ids.add(str(e["variant_id"]).strip())
        if e.get("title_fp"):
            title_fps.add(e["title_fp"])

    return {
        "updated_at": tmp_data.get("updated_at") or repo_data.get("updated_at") or datetime.now().isoformat(),
        "last_harvested_deodap_page": last_page,
        "total_export_batches": export_batches,
        "total_blocked_products": len(entries_list),
        "entries": entries_list,
        "skus": sorted(skus),
        "handles": sorted(handles),
        "variant_ids": sorted(variant_ids),
        "title_fps": sorted(title_fps),
    }


def save_export_ledger(ledger: Dict[str, Any]) -> None:
    """
    Persists the ledger to both the repo file (when writable) and the runtime `/tmp` file.
    """
    payload = {
        "updated_at": datetime.now().isoformat(),
        "last_harvested_deodap_page": int(ledger.get("last_harvested_deodap_page") or 3),
        "total_export_batches": int(ledger.get("total_export_batches") or 0),
        "total_blocked_products": len(ledger.get("entries", [])),
        "entries": ledger.get("entries", []),
    }
    serialized = json.dumps(payload, indent=2, ensure_ascii=False)
    for target in (REPO_LEDGER_FILE, TMP_LEDGER_FILE):
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(serialized, encoding="utf-8")
        except Exception:
            pass


def build_exclusion_sets(extra_client_keys: Optional[Iterable[str]] = None) -> Tuple[Set[str], Set[str], Set[str], Set[str]]:
    """
    Returns `(skus_set, handles_set, variant_ids_set, title_fps_set)` combining
    the server ledger plus any browser `localStorage` keys passed by the client.
    """
    ledger = load_export_ledger()
    skus = set(ledger.get("skus", []))
    handles = set(ledger.get("handles", []))
    variant_ids = set(ledger.get("variant_ids", []))
    title_fps = set(ledger.get("title_fps", []))

    if extra_client_keys:
        for raw_key in extra_client_keys:
            if not raw_key:
                continue
            k = str(raw_key).strip()
            if not k:
                continue
            skus.add(normalize_sku(k))
            handles.add(normalize_handle(k))
            title_fps.add(k.lower())

    return skus, handles, variant_ids, title_fps


def is_product_already_exported(
    product: Dict[str, Any],
    exclusion_sets: Optional[Tuple[Set[str], Set[str], Set[str], Set[str]]] = None,
) -> bool:
    """
    Returns True if ANY of the product's 4 keys (SKU, Handle, Variant ID, or Core Title Fingerprint)
    matches an already-exported or store-listed product.
    """
    skus, handles, variant_ids, title_fps = exclusion_sets or build_exclusion_sets()
    fp = extract_product_fingerprints(product)

    if fp["sku"] and fp["sku"] in skus:
        return True
    if fp["handle"] and fp["handle"] in handles:
        return True
    if fp["variant_id"] and fp["variant_id"] in variant_ids:
        return True
    if fp["title_fp"] and len(fp["title_fp"]) >= 5 and fp["title_fp"] in title_fps:
        return True
    return False


def record_exported_products(
    products: List[Dict[str, Any]],
    source_label: str = "smartbiz_csv_export",
    extra_client_keys: Optional[Iterable[str]] = None,
    last_deodap_page: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Atomically records newly exported products into the permanent ledger so they can never be exported again.
    """
    ledger = load_export_ledger()
    existing_entries = ledger.get("entries", [])
    by_key: Dict[str, Dict[str, Any]] = {}
    for e in existing_entries:
        pk = e.get("sku") or e.get("handle") or e.get("title_fp")
        if pk:
            by_key[pk] = e

    # Also preserve any client-sent keys that weren't in server storage yet (e.g., after serverless cold start)
    if extra_client_keys:
        for ck in extra_client_keys:
            ck_norm = normalize_sku(ck)
            if ck_norm and ck_norm not in by_key:
                by_key[ck_norm] = {
                    "sku": ck_norm,
                    "handle": ck_norm,
                    "variant_id": "",
                    "title_fp": ck_norm,
                    "title": f"Synced from Browser Vault ({ck_norm})",
                    "source": "browser_vault_sync",
                    "exported_at": datetime.now().isoformat(),
                }

    now_str = datetime.now().isoformat()
    newly_added = []
    for prod in products:
        fp = extract_product_fingerprints(prod)
        pk = fp["sku"] or fp["handle"] or fp["title_fp"]
        if not pk:
            continue
        entry = {
            "sku": fp["sku"],
            "handle": fp["handle"],
            "variant_id": fp["variant_id"],
            "title_fp": fp["title_fp"],
            "title": fp["title"],
            "selling_price": prod.get("selling_price"),
            "mrp": prod.get("mrp"),
            "source": source_label,
            "exported_at": now_str,
        }
        by_key[pk] = entry
        newly_added.append(entry)

    ledger["entries"] = list(by_key.values())
    ledger["total_export_batches"] = int(ledger.get("total_export_batches") or 0) + (1 if newly_added else 0)
    if last_deodap_page is not None and last_deodap_page > int(ledger.get("last_harvested_deodap_page") or 3):
        ledger["last_harvested_deodap_page"] = last_deodap_page

    save_export_ledger(ledger)
    return load_export_ledger()


def import_smartbiz_sheet_to_ledger(file_bytes: bytes, filename: str = "upload.xlsx") -> Dict[str, Any]:
    """
    Reads an uploaded SmartBiz `.xlsx` or `.csv` catalog sheet and adds all its rows
    (Custom SKU, Product Name, SKU ID, Variant ID) into the permanent Zero-Repeat Blocklist.
    """
    imported_products: List[Dict[str, Any]] = []
    fname_lower = (filename or "").lower()

    if fname_lower.endswith(".csv"):
        text = file_bytes.decode("utf-8-sig", errors="replace")
        reader = list(csv.reader(io.StringIO(text)))
        for row in reader[1:]:
            if len(row) >= 7:
                sku = str(row[5] or row[0] or "").strip()
                title = str(row[6] or "").strip()
                vid = str(row[1] or "").strip()
                if sku or title:
                    imported_products.append({
                        "sku": sku,
                        "title": title,
                        "variant_id": vid,
                        "handle": normalize_handle(title.replace(" ", "-")),
                    })
    else:
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
        ws = wb["bulk_upload_template"] if "bulk_upload_template" in wb.sheetnames else wb.active
        for r_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            if not row or len(row) < 7:
                continue
            sku = str(row[5] or row[0] or "").strip()
            title = str(row[6] or "").strip()
            vid = str(row[1] or "").strip()
            if sku or title:
                imported_products.append({
                    "sku": sku,
                    "title": title,
                    "variant_id": vid,
                    "handle": normalize_handle(title.replace(" ", "-")),
                })
        wb.close()

    updated = record_exported_products(imported_products, source_label=f"store_sheet_import:{filename}")
    return {
        "imported_count": len(imported_products),
        "total_blocked_products": updated["total_blocked_products"],
        "ledger": updated,
    }


def reset_export_ledger(keep_store_baseline: bool = True) -> Dict[str, Any]:
    """
    Clears exported CSV history while optionally keeping the 39 initial store baseline products locked.
    """
    ledger = load_export_ledger()
    if keep_store_baseline:
        baseline = [
            e for e in ledger.get("entries", [])
            if str(e.get("source", "")).startswith("store_baseline")
        ]
    else:
        baseline = []

    ledger["entries"] = baseline
    ledger["total_export_batches"] = 0
    save_export_ledger(ledger)
    return load_export_ledger()
