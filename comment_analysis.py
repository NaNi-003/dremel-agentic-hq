from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer


_ANALYZER = SentimentIntensityAnalyzer()


def analyze_comments(comments):
    """Return bounded, separate viewer-sentiment evidence without changing ranking."""
    texts = [
        item.get("text", "").strip()
        for item in comments or []
        if isinstance(item, dict) and isinstance(item.get("text"), str) and item["text"].strip()
    ]
    if not texts:
        return {
            "comments_sampled": 0,
            "distribution": {"positive": 0, "neutral": 0, "negative": 0},
            "shares": {"positive": 0.0, "neutral": 0.0, "negative": 0.0},
            "sentiment_score": None,
            "confidence": "unavailable",
            "limitations": "No usable top-level comment sample was available.",
        }

    scores = [_ANALYZER.polarity_scores(text)["compound"] for text in texts]
    distribution = {
        "positive": sum(score >= 0.05 for score in scores),
        "neutral": sum(-0.05 < score < 0.05 for score in scores),
        "negative": sum(score <= -0.05 for score in scores),
    }
    total = len(scores)
    confidence = "high" if total >= 50 else "medium" if total >= 20 else "low"
    return {
        "comments_sampled": total,
        "distribution": distribution,
        "shares": {
            label: round(count / total, 3) for label, count in distribution.items()
        },
        "sentiment_score": round(sum(scores) / total, 3),
        "confidence": confidence,
        "limitations": (
            "Sentiment reflects a bounded top-level comment sample; sarcasm, spam, "
            "language, moderation, and audience self-selection can bias it."
        ),
    }
