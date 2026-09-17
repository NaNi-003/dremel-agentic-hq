import cv_layer
import pandas as pd


def test_thumbnail_analysis_labels_color_heuristic_provenance(monkeypatch):
    monkeypatch.setattr(cv_layer, "_get_deepface", lambda: None)

    color, emotion, method = cv_layer._analyze_thumbnail(
        "unused-fixture.jpg",
        (120, 80, 40),
    )

    assert color == "#785028"
    assert emotion == "Energetic"
    assert method == "color_heuristic"


def test_visual_analysis_uses_unique_temporary_files_and_cleans_them(monkeypatch):
    downloaded_paths = []

    def download(url, filename):
        downloaded_paths.append(filename)
        with open(filename, "wb") as image:
            image.write(b"fixture")

    class FakeColorThief:
        def __init__(self, filename):
            self.filename = filename

        def get_color(self, quality):
            return (120, 80, 40)

    monkeypatch.setattr(cv_layer, "download_image", download)
    monkeypatch.setattr(cv_layer, "ColorThief", FakeColorThief)
    monkeypatch.setattr(cv_layer, "_get_deepface", lambda: None)
    frame = pd.DataFrame(
        [
            {"video_id": "same-id", "thumbnail_url": "https://example.test/1"},
            {"video_id": "same-id", "thumbnail_url": "https://example.test/2"},
        ]
    )

    cv_layer.run_visual_analysis(frame, top_n=2)

    assert len(set(downloaded_paths)) == 2
    assert all(not cv_layer.os.path.exists(path) for path in downloaded_paths)
