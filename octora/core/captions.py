"""Caption/hashtag generator + best-time-to-post heatmap data (local, no AI service needed)."""
import random

HOOKS = [
    "POV: you finally learn this today 👀",
    "Nobody talks about this 🤫",
    "Watch till the end — worth it 🔥",
    "This changed how I work forever ⚡",
    "3 seconds that will save you hours ⏱️",
]

HASHTAG_SETS = {
    "YT Shorts": ["#shorts", "#youtubeshorts", "#tech", "#tips", "#viral", "#howto"],
    "IG Reels": ["#reels", "#reelsinstagram", "#explore", "#design", "#trending", "#instagood"],
    "Both": ["#shorts", "#reels", "#viral", "#trending", "#explore"],
}

CTA = [
    "Follow for daily drops 🙌",
    "Save this for later 📌",
    "Share with someone who needs this ↗️",
    "Comment 'MORE' for part 2 💬",
]


def generate_caption(keyword: str, platform: str = "IG Reels", seed=None) -> dict:
    rng = random.Random(seed if seed is not None else keyword)
    hook = rng.choice(HOOKS)
    cta = rng.choice(CTA)
    tags = rng.sample(HASHTAG_SETS.get(platform, HASHTAG_SETS["Both"]),
                      k=min(5, len(HASHTAG_SETS.get(platform, HASHTAG_SETS["Both"]))))
    kw = keyword.strip() or "today's drop"
    caption = f"{hook}\n\n{kw.capitalize()} — automated with OCTORA 🤖\n\n{cta}\n\n{' '.join(tags)}"
    return {"caption": caption, "hashtags": tags, "hook": hook, "cta": cta}


def hashtag_suggestions(topic: str, platform: str = "IG Reels") -> list[str]:
    base = HASHTAG_SETS.get(platform, HASHTAG_SETS["Both"])
    topic_tags = [f"#{w.strip().lower().replace(' ', '')}"
                  for w in topic.split(",") if w.strip()][:6]
    seen = []
    for t in topic_tags + base:
        if t not in seen:
            seen.append(t)
    return seen[:12]


def best_time_heatmap(posted_hours: dict[int, int]) -> list[list[int]]:
    """7x24 grid; we only know hour-of-day from DB, so repeat the same row pattern
    across days with slight deterministic variation (documented heuristic)."""
    grid = []
    for d in range(7):
        row = []
        for h in range(24):
            v = posted_hours.get(h, 0)
            # gentle day-based variation so the heatmap is informative, not flat
            v = max(0, int(v * (0.8 + 0.05 * ((d + h) % 5))))
            row.append(v)
        grid.append(row)
    return grid
