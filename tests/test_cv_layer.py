import cv_layer
import pandas as pd
from PIL import Image, ImageDraw


def test_thumbnail_analysis_keeps_color_tone_separate_from_facial_expression(monkeypatch):
    monkeypatch.setattr(cv_layer, "_get_deepface", lambda: None)

    evidence = cv_layer._analyze_thumbnail(
        "unused-fixture.jpg",
        (120, 80, 40),
        face_count=0,
        image_metrics={"brightness": 0.31, "saturation": 0.5, "contrast": 0.4, "edge_density": 0.2},
        palette=[(120, 80, 40), (30, 40, 50)],
    )

    assert evidence["dominant_color"] == "#785028"
    assert evidence["facial_expression"] is None
    assert evidence["face_count"] == 0
    assert evidence["color_temperature"] == "warm"
    assert evidence["method"] == "thumbnail_features_no_face"


def test_thumbnail_metrics_report_bounded_text_and_clutter_proxies(tmp_path):
    image_path = tmp_path / "thumbnail.png"
    image = Image.new("RGB", (200, 100), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((10, 10, 190, 35), fill="black")
    draw.rectangle((20, 60, 80, 90), fill="red")
    image.save(image_path)

    metrics = cv_layer._thumbnail_metrics(str(image_path))

    assert 0 <= metrics["text_like_region_density"] <= 1
    assert metrics["visual_clutter"] in {"low", "medium", "high"}


def test_face_composition_reports_prominence_and_centrality():
    evidence = cv_layer._face_composition((100, 200), [(75, 20, 50, 60)])

    assert evidence == {
        "face_count": 1,
        "face_area_share": 0.15,
        "central_face": True,
    }


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

        def get_palette(self, color_count, quality):
            return [(120, 80, 40), (30, 40, 50), (220, 210, 190)]

    monkeypatch.setattr(cv_layer, "download_image", download)
    monkeypatch.setattr(cv_layer, "ColorThief", FakeColorThief)
    monkeypatch.setattr(cv_layer, "_get_deepface", lambda: None)
    monkeypatch.setattr(
        cv_layer,
        "_thumbnail_metrics",
        lambda path: {
            "brightness": 0.5,
            "saturation": 0.4,
            "contrast": 0.3,
            "edge_density": 0.2,
            "text_like_region_density": 0.1,
            "visual_clutter": "high",
        },
    )
    monkeypatch.setattr(cv_layer, "_detect_faces", lambda path: ([], (100, 200)))
    monkeypatch.setattr(
        cv_layer,
        "_analyze_objects_with_gemini",
        lambda path: {
            "objects": ["chair"],
            "tools": ["rotary tool"],
            "face_count": 0,
            "facial_expressions": [],
            "method": "fixture_semantic_vision",
        },
    )
    frame = pd.DataFrame(
        [
            {"video_id": "same-id", "thumbnail_url": "https://example.test/1"},
            {"video_id": "same-id", "thumbnail_url": "https://example.test/2"},
        ]
    )

    result = cv_layer.run_visual_analysis(frame, top_n=2)

    assert len(set(downloaded_paths)) == 2
    assert all(not cv_layer.os.path.exists(path) for path in downloaded_paths)
    assert result.iloc[0]["cv_color_temperature"] == "warm"
    assert result.iloc[0]["cv_face_count"] == 0
    assert result.iloc[0]["cv_brightness"] == 0.5
    assert result.iloc[0]["cv_palette"] == ["#785028", "#1e2832", "#dcd2be"]
    assert result.iloc[0]["cv_objects"] == ["chair"]
    assert result.iloc[0]["cv_tools"] == ["rotary tool"]
    assert result.iloc[0]["cv_semantic_method"] == "fixture_semantic_vision"


def test_missing_opencv_face_classifier_does_not_discard_color_analysis(monkeypatch, tmp_path):
    image_path = tmp_path / "thumbnail.png"
    Image.new("RGB", (100, 80), "blue").save(image_path)
    monkeypatch.setattr(cv_layer.cv2, "CascadeClassifier", None)

    boxes, shape = cv_layer._detect_faces(str(image_path))

    assert boxes == []
    assert shape == (80, 100)


def test_semantic_vision_returns_bounded_objects_and_tools(monkeypatch, tmp_path):
    image_path = tmp_path / "thumbnail.png"
    Image.new("RGB", (100, 80), "white").save(image_path)

    class FakeModels:
        def generate_content(self, **kwargs):
            return type(
                "Response",
                (),
                    {"text": '{"objects":["chair","table"],"tools":["drill"],"face_count":1,"facial_expressions":["happy"]}'},
            )()

    fake_client = type("Client", (), {"models": FakeModels()})()
    monkeypatch.setattr(cv_layer, "_get_vision_client", lambda: fake_client)

    result = cv_layer._analyze_objects_with_gemini(str(image_path))

    assert result == {
        "objects": ["chair", "table"],
        "tools": ["drill"],
        "face_count": 1,
        "facial_expressions": ["happy"],
        "method": "gemini_structured_vision",
    }
