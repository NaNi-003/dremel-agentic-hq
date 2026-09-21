import comment_analysis


def test_analyze_comments_returns_separate_sentiment_with_coverage():
    comments = [
        {"text": "Amazing restoration, I love this result!", "like_count": 12},
        {"text": "This is terrible and the result looks broken.", "like_count": 2},
        {"text": "Which tool did you use?", "like_count": 1},
    ]

    result = comment_analysis.analyze_comments(comments)

    assert result["comments_sampled"] == 3
    assert set(result["distribution"]) == {"positive", "neutral", "negative"}
    assert sum(result["distribution"].values()) == 3
    assert -1.0 <= result["sentiment_score"] <= 1.0
    assert result["confidence"] == "low"
    assert "sample" in result["limitations"].lower()


def test_analyze_comments_handles_empty_sample_without_inventing_sentiment():
    result = comment_analysis.analyze_comments([])

    assert result["comments_sampled"] == 0
    assert result["sentiment_score"] is None
    assert result["confidence"] == "unavailable"
