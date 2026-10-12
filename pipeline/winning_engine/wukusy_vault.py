import json
from pathlib import Path
from typing import Set, List, Dict, Any, Optional
from datetime import datetime

ROOT_DIR = Path(__file__).resolve().parent.parent
VAULT_FILE = ROOT_DIR / "data" / "wukusy_vault.json"


def load_wukusy_vault() -> Dict[str, Any]:
    """
    Loads active Wukusy wholesaler SKUs from data/wukusy_vault.json.
    """
    if VAULT_FILE.exists():
        try:
            with open(VAULT_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "updated_at": None,
        "total_active_skus": 0,
        "skus": [],
    }


def save_wukusy_vault(vault_data: Dict[str, Any]) -> None:
    """
    Persists Wukusy wholesaler active SKUs to data/wukusy_vault.json.
    """
    VAULT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(VAULT_FILE, "w", encoding="utf-8") as f:
        json.dump(vault_data, f, indent=2, ensure_ascii=False)


def get_wukusy_sku_set() -> Set[str]:
    """
    Returns normalized uppercase/lowercase set of all active Wukusy SKUs.
    """
    vault = load_wukusy_vault()
    skus = vault.get("skus", [])
    result = set()
    for s in skus:
        if s and str(s).strip():
            clean = str(s).strip().lower()
            result.add(clean)
            # Also keep alphanumeric clean variation
            result.add(clean.replace("-", "_"))
            result.add(clean.replace("_", "-"))
    return result


def is_sku_in_wukusy(sku: Optional[str], sku_set: Optional[Set[str]] = None) -> bool:
    """
    Checks whether a DeoDap product SKU is available on Wukusy wholesaler.
    """
    if not sku:
        return False
    if sku_set is None:
        sku_set = get_wukusy_sku_set()
    clean = str(sku).strip().lower()
    return (
        clean in sku_set
        or clean.replace("-", "_") in sku_set
        or clean.replace("_", "-") in sku_set
    )


def sync_wukusy_skus(new_skus: List[str], merge: bool = True) -> Dict[str, Any]:
    """
    Syncs new list of active SKUs from browser bookmarklet or bulk paste.
    """
    vault = load_wukusy_vault()
    existing_skus = set(vault.get("skus", [])) if merge else set()

    added = 0
    for s in new_skus:
        if s and str(s).strip():
            val = str(s).strip()
            if val not in existing_skus:
                existing_skus.add(val)
                added += 1

    sorted_skus = sorted(list(existing_skus))
    updated_vault = {
        "updated_at": datetime.now().isoformat(),
        "total_active_skus": len(sorted_skus),
        "skus": sorted_skus,
    }
    save_wukusy_vault(updated_vault)
    return {
        "success": True,
        "total_active_skus": len(sorted_skus),
        "added_count": added,
        "updated_at": updated_vault["updated_at"],
    }


def reset_wukusy_vault() -> None:
    """
    Clears Wukusy vault.
    """
    save_wukusy_vault({
        "updated_at": datetime.now().isoformat(),
        "total_active_skus": 0,
        "skus": [],
    })
