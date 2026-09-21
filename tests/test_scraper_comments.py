import scraper


class _Response:
    def execute(self):
        return {
            "items": [
                {
                    "snippet": {
                        "topLevelComment": {
                            "snippet": {
                                "textDisplay": "Great restoration!",
                                "likeCount": 7,
                                "publishedAt": "2026-09-20T00:00:00Z",
                                "authorDisplayName": "Private User",
                            }
                        }
                    }
                }
            ]
        }


class _CommentThreads:
    def list(self, **kwargs):
        assert kwargs["videoId"] == "video-1"
        assert kwargs["textFormat"] == "plainText"
        return _Response()


class _Youtube:
    def commentThreads(self):
        return _CommentThreads()


def test_get_video_comments_collects_bounded_top_level_text_without_usernames():
    comments = scraper.get_video_comments("video-1", max_results=25, youtube_client=_Youtube())

    assert comments == [
        {
            "text": "Great restoration!",
            "like_count": 7,
            "published_at": "2026-09-20T00:00:00Z",
        }
    ]
