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
