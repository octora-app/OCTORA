"""SEO metadata engine (v1.2) — rules + best-practice templates, NOT "AI".

Renders per-upload title / description / tags / caption from per-campaign
templates with variables:
    {keyword}  — extracted from the video filename (or typed)
    {episode}   — trailing number found in the filename, e.g. "tips_014" -> "14"
    {niche}     — the campaign's niche, e.g. "tech"
    {date}      — today's date in IST, e.g. "16 Sep 2026"
    {platform}  — "YouTube Shorts" / "Instagram Reels" / ...
    {filename}  — raw filename without extension

Each platform ships with a proven default template + hard rules
(title length, tag limits, hashtag counts). Campaigns can override every
template; individual scheduled posts can override the rendered result.
"""
import os
import re
from datetime import datetime

from .database import now_ist

# ---------------------------------------------------------------------------
# editable niche keyword / hashtag banks
# ---------------------------------------------------------------------------
NICHE_BANKS = {
    "tech": {
        "keywords": ["tech tips", "gadgets", "smartphone tricks", "AI tools", "coding"],
        "hashtags": ["#tech", "#technology", "#gadgets", "#techtips", "#innovation",
                     "#smartphone", "#ai", "#coding"],
    },
    "fitness": {
        "keywords": ["home workout", "fat loss", "muscle tips", "gym motivation", "diet plan"],
        "hashtags": ["#fitness", "#workout", "#gym", "#health", "#fit", "#training",
                     "#exercise", "#motivation"],
    },
    "cooking": {
        "keywords": ["quick recipes", "5-minute meals", "street food", "baking hacks", "healthy food"],
        "hashtags": ["#cooking", "#food", "#recipes", "#foodie", "#homemade", "#yummy",
                     "#instafood", "#chef"],
    },
    "finance": {
        "keywords": ["money tips", "investing basics", "saving hacks", "stock market", "passive income"],
        "hashtags": ["#finance", "#money", "#investing", "#stocks", "#wealth", "#business",
                     "#entrepreneur", "#financetips"],
    },
    "motivation": {
        "keywords": ["morning motivation", "success mindset", "discipline", "life lessons", "focus"],
        "hashtags": ["#motivation", "#mindset", "#success", "#inspiration", "#goals",
                     "#discipline", "#nevergiveup", "#hustle"],
    },
    "comedy": {
        "keywords": ["funny moments", "relatable comedy", "memes", "pranks", "daily laughs"],
        "hashtags": ["#comedy", "#funny", "#memes", "#humor", "#lol", "#laugh",
                     "#relatable", "#funnymemes"],
    },
    "education": {
        "keywords": ["study hacks", "exam tips", "learn fast", "general knowledge", "english speaking"],
        "hashtags": ["#education", "#study", "#learn", "#knowledge", "#student", "#exam",
                     "#studytips", "#learning"],
    },
    "fashion": {
        "keywords": ["outfit ideas", "style tips", "fashion hacks", "thrift finds", "makeup"],
        "hashtags": ["#fashion", "#style", "#outfit", "#ootd", "#beauty", "#makeup",
                     "#shopping", "#trends"],
    },
    "travel": {
        "keywords": ["hidden places", "travel hacks", "budget travel", "street food tour", "vlogs"],
        "hashtags": ["#travel", "#wanderlust", "#travelgram", "#adventure", "#vacation",
                     "#explore", "#nature", "#trip"],
    },
    "gaming": {
        "keywords": ["gaming highlights", "pro tips", "funny gameplay", "new releases", "mobile gaming"],
        "hashtags": ["#gaming", "#gamer", "#gameplay", "#esports", "#videogames",
                     "#twitch", "#pubg", "#freefire"],
    },
}

# ---------------------------------------------------------------------------
# platform presets: proven defaults + hard rules
# ---------------------------------------------------------------------------
PLATFORM_PRESETS = {
    "youtube": {
        "label": "YouTube Shorts",
        # keyword front-loaded inside the first 60 chars, <= 100 chars total
        "title_template": "{keyword} 🔥 #{niche} #Shorts",
        "description_template": (
            "{keyword} — full breakdown 👇\n\n"
            "🎯 Topic: {keyword}\n"
            "📅 {date}\n\n"
            "{tags_line}\n\n"
            "#Shorts #YouTubeShorts"
        ),
        "tags_template": "{niche}, {keyword}, shorts, youtube shorts, viral shorts",
        "rules": {
            "title_max": 100,
            "title_min_keyword_pos": 60,   # keyword should appear in first 60 chars
            "desc_max": 5000,
            "tags_max": 15,                # YouTube ignores beyond ~15 useful tags
            "tag_max_len": 30,
        },
        "caption_note": "YouTube uses title + description + tags (no hashtags in caption).",
    },
    "instagram": {
        "label": "Instagram Reels",
        # hook first, hashtags last, 3-8 hashtags is the sweet spot
        "title_template": "{keyword}",
        "description_template": "",
        "tags_template": "",
        "caption_template": (
            "👀 {keyword}\n\n"
            "Save this for later 📌\n"
            "Follow for daily {niche} drops 🙌\n\n"
            "{hashtags}"
        ),
        "rules": {
            "caption_max": 2200,
            "hashtags_min": 3,
            "hashtags_max": 8,
            "hashtags_block": True,  # hashtags grouped at the end, not mid-caption
        },
        "caption_note": "Reels = hook-first caption + 3–8 hashtags at the end.",
    },
    "tiktok": {
        "label": "TikTok",
        "title_template": "{keyword} 🔥",
        "description_template": "",
        "tags_template": "",
        "caption_template": "{keyword} 🔥 {hashtags}",
        "rules": {
            "caption_max": 2200,
            "title_max": 150,
            "hashtags_min": 3,
            "hashtags_max": 6,
            "punchy": True,  # keep titles short and punchy
        },
        "caption_note": "TikTok = punchy short title + 3–6 hashtags.",
    },
    "facebook": {
        "label": "Facebook Reels",
        "title_template": "{keyword}",
        "description_template": "",
        "tags_template": "",
        "caption_template": (
            "{keyword} 👀\n\n"
            "Follow for more {niche} videos 🙌\n\n"
            "{hashtags}"
        ),
        "rules": {
            "caption_max": 2200,
            "hashtags_min": 2,
            "hashtags_max": 5,
        },
        "caption_note": "FB Reels = simple caption + a few hashtags.",
    },
}

LABEL_TO_PRESET = {
    "YT Shorts": "youtube",
    "IG Reels": "instagram",
    "TikTok": "tiktok",
    "FB Reels": "facebook",
}

JUNK_WORDS = {
    "final", "final2", "v1", "v2", "new", "clip", "video", "demo", "export",
    "render", "copy", "edited", "draft", "hd", "4k", "dl", "download",
}

VARIABLES_HELP = ("{keyword} {episode} {niche} {date} {platform} {filename} "
                  "{hashtags} {tags_line}")


# ---------------------------------------------------------------------------
# smart helpers
# ---------------------------------------------------------------------------
def extract_keyword(filename: str) -> str:
    """Turns 'morning-productivity-tips_final2.mp4' -> 'Morning Productivity Tips'."""
    name = re.sub(r"\.[a-zA-Z0-9]+$", "", filename or "")
    name = re.sub(r"(dl_|demo_dl_)\d+", "", name)          # downloader prefixes
    parts = re.split(r"[_\-\.\s]+", name)
    kept = [p for p in parts if p and p.lower() not in JUNK_WORDS and not p.isdigit()]
    if not kept:
        kept = [p for p in parts if p][:3]
    return " ".join(w.capitalize() for w in kept) or "New Drop"


def extract_episode(filename: str) -> str:
    """'tips_014.mp4' -> '14'. '' when no number found."""
    m = re.findall(r"(\d+)", re.sub(r"\.[a-zA-Z0-9]+$", "", filename or ""))
    return str(int(m[-1])) if m else ""


def suggest_hashtags(niche: str, platform_id: str = "instagram",
                     keyword: str = "", count: int | None = None) -> list[str]:
    """Hashtag suggestions from the built-in niche bank (+ keyword tag)."""
    bank = NICHE_BANKS.get((niche or "").lower(), NICHE_BANKS["tech"])
    rules = PLATFORM_PRESETS.get(platform_id, PLATFORM_PRESETS["instagram"])["rules"]
    want = count or rules.get("hashtags_max", 8)
    tags: list[str] = []
    if keyword:
        kw_tag = "#" + re.sub(r"\s+", "", keyword.strip().lower())
        if len(kw_tag) > 2:
            tags.append(kw_tag)
    for h in bank["hashtags"]:
        if h not in tags:
            tags.append(h)
        if len(tags) >= want:
            break
    return tags[: max(want, rules.get("hashtags_min", 3))]


def niche_keywords(niche: str) -> list[str]:
    return NICHE_BANKS.get((niche or "").lower(), NICHE_BANKS["tech"])["keywords"]


# ---------------------------------------------------------------------------
# validation (best-practice rules, plain warnings — no hype)
# ---------------------------------------------------------------------------
def validate(platform_id: str, title: str, description: str,
             tags: list[str], caption: str) -> list[str]:
    """Returns human-readable warnings. Empty list = all good."""
    warns: list[str] = []
    rules = PLATFORM_PRESETS.get(platform_id, PLATFORM_PRESETS["youtube"])["rules"]
    if platform_id == "youtube":
        if len(title) > rules["title_max"]:
            warns.append(f"Title is {len(title)} chars — YouTube cuts titles past "
                         f"{rules['title_max']}.")
        elif len(title) > rules["title_min_keyword_pos"]:
            warns.append(f"Title is {len(title)} chars — search results show ~"
                         f"{rules['title_min_keyword_pos']}; keep the keyword front-loaded.")
        if len(tags) > rules["tags_max"]:
            warns.append(f"{len(tags)} tags — YouTube only weighs the first "
                         f"{rules['tags_max']}.")
        for t in tags:
            if len(t) > rules["tag_max_len"]:
                warns.append(f"Tag '{t}' is over {rules['tag_max_len']} chars — likely ignored.")
                break
        if not tags:
            warns.append("No tags — add 5–10 relevant tags for search.")
    else:
        n_tags = len(re.findall(r"#\w+", caption))
        lo, hi = rules.get("hashtags_min", 3), rules.get("hashtags_max", 8)
        if n_tags < lo:
            warns.append(f"Only {n_tags} hashtag(s) — {lo}–{hi} performs best on "
                         f"{PLATFORM_PRESETS[platform_id]['label']}.")
        if n_tags > hi:
            warns.append(f"{n_tags} hashtags — over {hi} looks spammy; trim to the best {hi}.")
        if len(caption) > rules.get("caption_max", 2200):
            warns.append("Caption exceeds the platform limit and will be cut off.")
        if not caption.split("\n")[0].strip():
            warns.append("Caption starts empty — put the hook on line one.")
    return warns


# ---------------------------------------------------------------------------
# rendering
# ---------------------------------------------------------------------------
def _fill(template: str, ctx: dict) -> str:
    out = template or ""
    for k, v in ctx.items():
        out = out.replace("{" + k + "}", str(v))
    # drop any unknown leftover {placeholders} instead of leaking them
    out = re.sub(r"\{[a-z_]+\}", "", out)
    return re.sub(r"[ \t]{2,}", " ", out).strip()


def render(platform_id: str, campaign: dict | None, asset_filename: str,
           overrides: dict | None = None) -> dict:
    """Renders the final metadata. overrides may hold title/description/tags/
    caption to replace the rendered value (per-video override from Scheduler)."""
    preset = PLATFORM_PRESETS.get(platform_id, PLATFORM_PRESETS["youtube"])
    campaign = campaign or {}
    keyword = extract_keyword(asset_filename)
    niche = (campaign.get("niche") or "tech").strip() or "tech"
    ctx = {
        "keyword": keyword,
        "episode": extract_episode(asset_filename),
        "niche": niche,
        "date": now_ist().strftime("%d %b %Y"),
        "platform": preset["label"],
        "filename": re.sub(r"\.[a-zA-Z0-9]+$", "", asset_filename or ""),
        "hashtags": " ".join(suggest_hashtags(niche, platform_id, keyword)),
        "tags_line": "",
    }
    title_tpl = campaign.get("title_template") or preset["title_template"]
    desc_tpl = campaign.get("description_template") if campaign.get("description_template") is not None \
        else preset["description_template"]
    tags_tpl = campaign.get("tags_template") if campaign.get("tags_template") is not None \
        else preset["tags_template"]
    cap_tpl = campaign.get("caption_template") or preset.get("caption_template", "")

    tags_raw = _fill(tags_tpl, ctx)
    tags = [t.strip().lstrip("#") for t in re.split(r"[,|\n]", tags_raw) if t.strip()]
    # de-dupe, keep order
    _seen: set = set()
    _uniq = []
    for t in tags:
        if t.lower() not in _seen:
            _seen.add(t.lower())
            _uniq.append(t)
    tags = _uniq
    ctx["tags_line"] = ", ".join("#" + t.replace(" ", "") for t in tags[:10])

    title = _fill(title_tpl, ctx)
    description = _fill(desc_tpl, ctx)
    caption = _fill(cap_tpl, ctx)
    if platform_id == "youtube":
        # YouTube: fold hashtags into the description tail (best practice)
        tail = " ".join(suggest_hashtags(niche, "youtube", keyword, 5))
        if tail and tail not in description:
            description = (description + "\n\n" + tail).strip()

    ov = overrides or {}
    if ov.get("title"):
        title = ov["title"]
    if ov.get("description") is not None and ov.get("description") != "":
        description = ov["description"]
    if ov.get("tags"):
        tags = [t.strip().lstrip("#") for t in re.split(r"[,|\n]", ov["tags"]) if t.strip()]
    if ov.get("caption"):
        caption = ov["caption"]

    if platform_id == "youtube":
        title = title[:100]

    warnings = validate(platform_id, title, description, tags, caption)
    return {"title": title, "description": description, "tags": tags,
            "caption": caption or title, "warnings": warnings,
            "keyword": keyword, "niche": niche}


# ---------------------------------------------------------------------------
# Autopilot metadata modes (v1.4): manual templates vs Gemini auto-generation
# ---------------------------------------------------------------------------
def apply_manual(niche: dict, asset_filename: str, index: int) -> dict:
    """Manual mode: the user sets templates once per niche; every video in
    that niche gets them filled with {niche} {date} {index} {filename}
    (+ {keyword} for convenience). Never raises."""
    try:
        niche = niche or {}
        fname = re.sub(r"\.[a-zA-Z0-9]+$", "", asset_filename or "")
        ctx = {
            "niche": niche.get("name") or "",
            "date": datetime.now().strftime("%Y-%m-%d"),
            "index": index,
            "filename": fname,
            "keyword": extract_keyword(asset_filename),
        }
        title = _fill(niche.get("manual_title") or "{keyword}", ctx)
        description = _fill(niche.get("manual_description") or "", ctx)
        tags_raw = _fill(niche.get("manual_tags") or "", ctx)
        tags = [t.strip().lstrip("#") for t in re.split(r"[,|\n]", tags_raw)
                if t.strip()]
        caption = _fill(niche.get("manual_caption") or "", ctx) or title
        return {"title": title, "description": description, "tags": tags,
                "caption": caption, "warnings": [],
                "keyword": ctx["keyword"], "niche": ctx["niche"]}
    except Exception:  # noqa: BLE001
        return {"title": asset_filename or "clip", "description": "",
                "tags": [], "caption": asset_filename or "clip",
                "warnings": [], "keyword": "", "niche": ""}


def _auto_fallback(asset_filename: str, keyword: str, niche_name: str) -> dict:
    """Keyword/template metadata — used when Gemini is unavailable. Never raises."""
    kws = niche_keywords(niche_name)
    seen: set = set()
    tags: list[str] = []
    for t in list(kws) + suggest_hashtags(niche_name, "instagram", keyword, 8):
        clean = t.strip().lstrip("#")
        if clean and clean.lower() not in seen:
            seen.add(clean.lower())
            tags.append(clean)
    hook = kws[0].title() if kws else niche_name.title()
    title = f"{keyword} | {hook}" if keyword.lower() != hook.lower() else keyword
    description = (f"{keyword}\n\n"
                   f"Niche: {niche_name}\n"
                   f"Topics: {', '.join(kws[:5])}\n\n"
                   f"Follow for daily {niche_name} videos!")
    caption = (f"👀 {keyword}\n\n"
               f"{' '.join(suggest_hashtags(niche_name, 'instagram', keyword, 5))}")
    return {"title": title[:100], "description": description, "tags": tags[:15],
            "caption": caption, "warnings": [], "keyword": keyword,
            "niche": niche_name}


def _gemini_text(key: str, prompt: str, timeout: int = 30) -> str:
    """Call Gemini 2.0 Flash, return the raw text of the first candidate."""
    import json as _json
    import urllib.request as _req
    import urllib.error as _err
    url = ("https://generativelanguage.googleapis.com/v1beta/models/"
           f"gemini-2.0-flash:generateContent?key={key}")
    body = _json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json",
                             "maxOutputTokens": 512},
    }).encode("utf-8")
    req = _req.Request(url, data=body,
                       headers={"Content-Type": "application/json"}, method="POST")
    try:
        with _req.urlopen(req, timeout=timeout) as resp:
            payload = _json.loads(resp.read().decode("utf-8", "replace"))
    except _err.HTTPError as e:
        raise RuntimeError(f"gemini HTTP {e.code}") from e
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(f"gemini network: {e}") from e
    try:
        return payload["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError) as e:
        raise RuntimeError("gemini: unexpected response shape") from e


def _parse_gemini_json(text: str) -> dict | None:
    """Defensively extract {title, description, tags[], caption} from model text."""
    import json as _json
    t = (text or "").strip()
    # strip markdown code fences if the model added them
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", t, re.S)
    if m:
        t = m.group(1)
    else:
        # fall back to the first {...} block
        s, e = t.find("{"), t.rfind("}")
        if 0 <= s < e:
            t = t[s:e + 1]
    try:
        d = _json.loads(t)
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(d, dict) or not str(d.get("title", "")).strip():
        return None
    tags = d.get("tags") or []
    if isinstance(tags, str):
        tags = [x.strip() for x in re.split(r"[,|\n]", tags) if x.strip()]
    tags = [str(x).strip().lstrip("#") for x in tags if str(x).strip()][:15]
    return {
        "title": str(d.get("title", "")).strip()[:100],
        "description": str(d.get("description", "")).strip(),
        "tags": tags,
        "caption": str(d.get("caption", "")).strip() or str(d.get("title", "")).strip(),
    }


def generate_auto(asset_path: str, niche: dict) -> dict:
    """Auto mode: Gemini 2.0 Flash writes title/description/tags/caption from
    the filename + niche keywords (+ file size as a duration hint — no heavy
    deps). On ANY failure (no key, network, bad JSON…) falls back to the
    keyword/template renderer. Never raises — the pipeline must not break."""
    niche = niche or {}
    filename = os.path.basename(asset_path or "") or "clip.mp4"
    niche_name = (niche.get("name") or "general").strip() or "general"
    keyword = extract_keyword(filename)
    fallback = _auto_fallback(filename, keyword, niche_name)
    try:
        from .config import Config
        key = (Config().get("gemini_api_key") or "").strip()
        if not key:
            return fallback
        try:
            size_mb = os.path.getsize(asset_path) / 1e6 \
                if asset_path and os.path.exists(asset_path) else 0.0
        except OSError:
            size_mb = 0.0
        kws = niche_keywords(niche_name)
        prompt = (
            "You are a short-form video SEO assistant. Write upload metadata "
            "for a vertical short video.\n"
            f"Filename: {filename}\n"
            f"Niche: {niche_name} (keywords: {', '.join(kws[:8])})\n"
            f"Approx file size: {size_mb:.1f} MB\n\n"
            "Return ONLY valid JSON with these keys:\n"
            '{"title": "<=80 chars, hook first, no clickbait lies>", '
            '"description": "<2-3 informative lines>", '
            '"tags": ["<up to 8 plain tags, no #>"], '
            '"caption": "<short hook caption ending with 3-5 hashtags>"}'
        )
        parsed = _parse_gemini_json(_gemini_text(key, prompt))
        if not parsed:
            return fallback
        parsed.update({"warnings": [], "keyword": keyword, "niche": niche_name})
        return parsed
    except Exception:  # noqa: BLE001
        return fallback
