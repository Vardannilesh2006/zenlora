"""
Real Demand & Seasonality Checker:
1. Google Trends India (pytrends - geo=IN, 12 months, last-year festival window, peak month, current-to-baseline ratio)
2. Google Autosuggest India (Official Firefox/JSON Suggest endpoint)
3. YouTube Data API v3 (Official API if YOUTUBE_API_KEY is configured, otherwise null with reason)
Zero fake or hardcoded trend scores.
"""
import json
import os
import urllib.parse
from pathlib import Path
from typing import Dict, Any, Optional
import requests

from winning_engine.data_models import (
    now_iso,
    is_timestamp_stale,
    load_settings,
    append_audit_log,
    RUNTIME_DATA_DIR,
    REPO_DATA_DIR,
)

TRENDS_CACHE_FILE = RUNTIME_DATA_DIR / "trends_cache.json"
REPO_TRENDS_CACHE_FILE = REPO_DATA_DIR / "trends_cache.json"


def _get_youtube_api_key() -> str:
    key = os.environ.get("YOUTUBE_API_KEY", "").strip()
    if key:
        return key
    env_file = REPO_DATA_DIR.parent / ".env"
    if env_file.exists():
        try:
            with open(env_file, "r", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("YOUTUBE_API_KEY="):
                        return line.split("=", 1)[1].strip()
        except Exception:
            pass
    return ""


_TRENDS_MEM_CACHE: Dict[str, Any] = {"mtime": 0.0, "data": None}


def _load_trends_cache() -> Dict[str, Any]:
    for target in (TRENDS_CACHE_FILE, REPO_TRENDS_CACHE_FILE):
        if target.exists():
            try:
                mtime = target.stat().st_mtime
                if _TRENDS_MEM_CACHE["data"] is not None and _TRENDS_MEM_CACHE["mtime"] == mtime:
                    return _TRENDS_MEM_CACHE["data"]
                with open(target, "r", encoding="utf-8") as f:
                    data = json.load(f)
                _TRENDS_MEM_CACHE["mtime"] = mtime
                _TRENDS_MEM_CACHE["data"] = data
                return data
            except Exception:
                pass
    return {}


def _save_trends_cache(cache: Dict[str, Any]) -> None:
    for target in (TRENDS_CACHE_FILE, REPO_TRENDS_CACHE_FILE):
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            with open(target, "w", encoding="utf-8") as f:
                json.dump(cache, f, indent=2, ensure_ascii=False)
            _TRENDS_MEM_CACHE["mtime"] = target.stat().st_mtime
            _TRENDS_MEM_CACHE["data"] = cache
        except Exception:
            pass


def normalize_trend_keyword(keyword: str) -> str:
    """Extracts 2-3 core commercial words for Google Trends & Autosuggest."""
    words = [w for w in keyword.strip().split() if len(w) > 2]
    if len(words) > 3:
        return " ".join(words[:3]).lower()
    return " ".join(words).lower() if words else keyword.strip().lower()


def fetch_live_google_autosuggest(keyword: str) -> Dict[str, Any]:
    """Queries Google India Autosuggest JSON API for real autocomplete queries."""
    q = normalize_trend_keyword(keyword)
    encoded = urllib.parse.quote(q)
    url = f"https://suggestqueries.google.com/complete/search?client=firefox&gl=in&q={encoded}"
    ts = now_iso()
    try:
        resp = requests.get(url, timeout=4.0, headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code == 200:
            data = resp.json()
            suggestions = data[1] if isinstance(data, list) and len(data) > 1 else []
            return {
                "value": suggestions[:8],
                "count": len(suggestions),
                "status": "done",
                "source": "Google Autosuggest API (IN)",
                "source_url": url,
                "fetched_at": ts,
                "method": "api",
                "is_stale": False,
                "null_reason": None
            }
        return {
            "value": None,
            "count": None,
            "status": "unavailable",
            "source": "Google Autosuggest API (IN)",
            "source_url": url,
            "fetched_at": None,
            "method": "api",
            "is_stale": False,
            "null_reason": f"HTTP {resp.status_code} from Google Suggest"
        }
    except Exception as e:
        return {
            "value": None,
            "count": None,
            "status": "unavailable",
            "source": "Google Autosuggest API (IN)",
            "source_url": url,
            "fetched_at": None,
            "method": "api",
            "is_stale": False,
            "null_reason": f"Network error: {type(e).__name__}"
        }


def fetch_live_pytrends_india(keyword: str) -> Dict[str, Any]:
    """
    Fetches real 12-month Google Trends India data via trendspy (with pytrends fallback)
    for geo='IN', timeframe='today 12-m'.
    Computes peak month, current value, 12M baseline average, current-to-baseline ratio,
    and last year's Oct-Nov festival window average.
    """
    q = normalize_trend_keyword(keyword)
    encoded = urllib.parse.quote(q)
    trends_url = f"https://trends.google.com/trends/explore?date=today%2012-m&geo=IN&q={encoded}"
    ts = now_iso()

    df = None
    source_used = "Google Trends India (trendspy)"

    # 1. Try modern trendspy library first (much faster and less rate-limited than pytrends)
    try:
        from trendspy import Trends
        tr = Trends()
        df = tr.interest_over_time([q], geo="IN", timeframe="today 12-m")
    except Exception:
        df = None

    # 2. Fallback to pytrends if trendspy was unavailable
    if df is None or getattr(df, "empty", True):
        try:
            from pytrends.request import TrendReq
            pt = TrendReq(hl="en-IN", tz=330, timeout=(4, 8))
            pt.build_payload([q], cat=0, timeframe="today 12-m", geo="IN")
            df = pt.interest_over_time()
            source_used = "Google Trends India (pytrends)"
        except Exception as e:
            return {
                "value": None,
                "current_value": None,
                "baseline_avg": None,
                "current_to_baseline_ratio": None,
                "peak_month": None,
                "peak_value": None,
                "peak_to_baseline_ratio": None,
                "festival_window_oct_nov_avg": None,
                "status": "unavailable",
                "source": source_used,
                "source_url": trends_url,
                "fetched_at": None,
                "method": "api",
                "is_stale": False,
                "null_reason": f"Google Trends API rate-limit ({type(e).__name__})"
            }

    try:
        if df is not None and not df.empty and q in df.columns:
            series = df[q]
            current_val = int(series.iloc[-1])
            baseline_avg = round(float(series.mean()), 2)
            peak_idx = series.idxmax()
            peak_month = peak_idx.strftime("%b %Y")
            peak_val = int(series.max())
            ratio = round(current_val / baseline_avg, 2) if baseline_avg > 0 else 0.0
            peak_ratio = round(peak_val / baseline_avg, 2) if baseline_avg > 0 else 0.0

            fest_rows = series[[idx.month in (10, 11) for idx in series.index]]
            fest_window_avg = round(float(fest_rows.mean()), 1) if not fest_rows.empty else None

            append_audit_log(
                action="google_trends_fetch",
                target=q,
                source=source_used,
                method="api",
                source_url=trends_url,
                details=f"Peak: {peak_month} ({peak_val}), Current: {current_val}, Baseline: {baseline_avg}, Ratio: {ratio}x"
            )
            return {
                "value": current_val,
                "current_value": current_val,
                "baseline_avg": baseline_avg,
                "current_to_baseline_ratio": ratio,
                "peak_month": peak_month,
                "peak_value": peak_val,
                "peak_to_baseline_ratio": peak_ratio,
                "festival_window_oct_nov_avg": fest_window_avg,
                "status": "done",
                "source": source_used,
                "source_url": trends_url,
                "fetched_at": ts,
                "method": "api",
                "is_stale": False,
                "null_reason": None
            }
    except Exception:
        pass

    return {
        "value": None,
        "current_value": None,
        "baseline_avg": None,
        "current_to_baseline_ratio": None,
        "peak_month": None,
        "peak_value": None,
        "peak_to_baseline_ratio": None,
        "festival_window_oct_nov_avg": None,
        "status": "unavailable",
        "source": source_used,
        "source_url": trends_url,
        "fetched_at": ts,
        "method": "api",
        "is_stale": False,
        "null_reason": f"Specific phrase '{q}' not indexed separately in Google Trends 12M chart"
    }


def fetch_youtube_demand(keyword: str) -> Dict[str, Any]:
    """
    Uses official YouTube Data API v3 if YOUTUBE_API_KEY is present in .env,
    or scrapes real public YouTube India search results (real video IDs & view counts).
    """
    import re
    q = normalize_trend_keyword(keyword)
    encoded = urllib.parse.quote(q)
    yt_search_url = f"https://www.youtube.com/results?search_query={encoded}+india"
    api_key = _get_youtube_api_key()
    ts = now_iso()

    if api_key:
        api_url = (
            f"https://www.googleapis.com/youtube/v3/search"
            f"?part=snippet&q={encoded}&type=video&regionCode=IN&maxResults=5&key={api_key}"
        )
        try:
            resp = requests.get(api_url, timeout=5.0)
            if resp.status_code == 200:
                items = resp.json().get("items", [])
                videos = [
                    {
                        "video_id": it.get("id", {}).get("videoId"),
                        "title": it.get("snippet", {}).get("title"),
                        "published_at": it.get("snippet", {}).get("publishedAt")
                    }
                    for it in items
                ]
                return {
                    "value": len(videos),
                    "videos": videos,
                    "top_views": None,
                    "status": "done",
                    "source": "YouTube Data API v3",
                    "source_url": yt_search_url,
                    "fetched_at": ts,
                    "method": "api",
                    "is_stale": False,
                    "null_reason": None
                }
        except Exception:
            pass

    # Public YouTube India Search Scrape (Real video IDs & public view count strings)
    try:
        resp = requests.get(
            yt_search_url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0"},
            timeout=6.0
        )
        if resp.status_code == 200:
            v_ids = list(dict.fromkeys(re.findall(r"watch\?v=([a-zA-Z0-9_-]{11})", resp.text)))
            views = re.findall(r"([\d,\.]+\s*(?:K|M|lakh|crore)?\s*views)", resp.text, re.I)
            clean_views = [v.strip() for v in views if len(v.strip()) <= 22]
            if v_ids:
                top_view_str = clean_views[0] if clean_views else "Active Videos"
                return {
                    "value": len(v_ids),
                    "video_ids": v_ids[:6],
                    "top_views": top_view_str,
                    "view_samples": clean_views[:5],
                    "status": "done",
                    "source": "YouTube India Public Search",
                    "source_url": yt_search_url,
                    "fetched_at": ts,
                    "method": "scrape",
                    "is_stale": False,
                    "null_reason": None
                }
    except Exception as e:
        return {
            "value": None,
            "videos": None,
            "status": "unavailable",
            "source": "YouTube India Public Search",
            "source_url": yt_search_url,
            "fetched_at": None,
            "method": "scrape",
            "is_stale": False,
            "null_reason": f"YouTube search error: {type(e).__name__}"
        }

    return {
        "value": None,
        "videos": None,
        "status": "unavailable",
        "source": "YouTube India Public Search",
        "source_url": yt_search_url,
        "fetched_at": None,
        "method": "scrape",
        "is_stale": False,
        "null_reason": "No YouTube India results found"
    }


def get_google_trends_analysis(keyword: str, niche: str, fetch_live: bool = False) -> Dict[str, Any]:
    """
    Returns real cached or freshly fetched demand & seasonality data for a product keyword.
    Never invents or hardcodes trend numbers.
    """
    settings = load_settings()
    stale_days = int(settings.get("general", {}).get("stale_days_limit", 7))
    q = normalize_trend_keyword(keyword)
    encoded = urllib.parse.quote(q)
    trends_url = f"https://trends.google.com/trends/explore?date=today%2012-m&geo=IN&q={encoded}"

    cache = _load_trends_cache()
    cached_entry = cache.get(q)

    if fetch_live or (cached_entry is None and fetch_live):
        pytrends_data = fetch_live_pytrends_india(q)
        suggest_data = fetch_live_google_autosuggest(q)
        yt_data = fetch_youtube_demand(q)
        cached_entry = {
            "keyword": q,
            "pytrends": pytrends_data,
            "autosuggest": suggest_data,
            "youtube": yt_data,
            "fetched_at": now_iso()
        }
        cache[q] = cached_entry
        _save_trends_cache(cache)

    if cached_entry:
        pt = cached_entry.get("pytrends", {})
        sug = cached_entry.get("autosuggest", {})
        yt = cached_entry.get("youtube", {})
        fetched_at = pt.get("fetched_at") or sug.get("fetched_at") or yt.get("fetched_at")
        stale = is_timestamp_stale(fetched_at, stale_days)

        sug_count = sug.get("count")
        yt_count = yt.get("value")
        yt_top = yt.get("top_views")

        if pt.get("value") is not None:
            label = f"Peak: {pt['peak_month']} ({pt['current_to_baseline_ratio']}x avg)"
            if sug_count:
                label += f" · {sug_count} Google Suggests"
            status_text = (
                f"Real Google Trends (IN): Current={pt['current_value']}, "
                f"12M Avg={pt['baseline_avg']}, Ratio={pt['current_to_baseline_ratio']}x, "
                f"Peak={pt['peak_month']} ({pt['peak_value']})"
            )
            pipe_status = "done"
        elif sug_count is not None and sug_count > 0:
            yt_suffix = f" · {yt_count} YT Videos ({yt_top})" if yt_count and yt_top else ""
            label = f"{sug_count} IN Search Queries{yt_suffix}"
            status_text = f"Google Autosuggest (IN): {sug_count} real buyer queries{yt_suffix}"
            pipe_status = "done"
        elif yt_count:
            label = f"{yt_count} YT India Videos ({yt_top or 'Active'})"
            status_text = f"YouTube India Search: {yt_count} videos found ({yt_top})"
            pipe_status = "done"
        else:
            label = "Data not available"
            status_text = pt.get("null_reason") or "Data not available (Click 'Fetch Live Demand' to query)"
            pipe_status = "unavailable"

        return {
            "keyword": q,
            "trend_score": pt.get("current_value"),  # Real value or None (never hardcoded)
            "current_value": pt.get("current_value"),
            "baseline_avg": pt.get("baseline_avg"),
            "current_to_baseline_ratio": pt.get("current_to_baseline_ratio"),
            "peak_month": pt.get("peak_month"),
            "peak_value": pt.get("peak_value"),
            "festival_window_oct_nov_avg": pt.get("festival_window_oct_nov_avg"),
            "autosuggest": sug,
            "youtube": yt,
            "trend_status": status_text,
            "trend_label": label,
            "trends_url": trends_url,
            "pipeline_status": pipe_status,
            "source": pt.get("source") if pt.get("value") is not None else sug.get("source", "Google Autosuggest API (IN)"),
            "source_url": trends_url if pt.get("value") is not None else sug.get("source_url", trends_url),
            "fetched_at": fetched_at,
            "method": "api",
            "is_stale": stale,
            "null_reason": pt.get("null_reason")
        }

    # Not fetched yet — return honest null state (Rule #3)
    return {
        "keyword": q,
        "trend_score": None,
        "current_value": None,
        "baseline_avg": None,
        "current_to_baseline_ratio": None,
        "peak_month": None,
        "peak_value": None,
        "festival_window_oct_nov_avg": None,
        "autosuggest": {
            "value": None,
            "count": None,
            "status": "unavailable",
            "source": "Google Autosuggest API (IN)",
            "source_url": f"https://suggestqueries.google.com/complete/search?client=firefox&gl=in&q={encoded}",
            "fetched_at": None,
            "method": "api",
            "is_stale": False,
            "null_reason": "Not fetched yet — click 'Fetch Live Demand' to query"
        },
        "youtube": fetch_youtube_demand(q),
        "trend_status": "Data not available (Click 'Fetch Live Demand' on product page to query pytrends & Autosuggest)",
        "trend_label": "Data not available",
        "trends_url": trends_url,
        "pipeline_status": "manual_needed",
        "source": "Google Trends India (pytrends)",
        "source_url": trends_url,
        "fetched_at": None,
        "method": "api",
        "is_stale": False,
        "null_reason": "Not fetched yet — click 'Fetch Live Demand' to query real Google Trends India"
    }
