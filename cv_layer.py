import os
import json
from tempfile import NamedTemporaryFile

import requests
from colorthief import ColorThief
import cv2
import numpy as np
import pandas as pd
from PIL import Image, ImageStat
from dotenv import load_dotenv


_DEEPFACE = None
_DEEPFACE_IMPORT_ATTEMPTED = False
_VISION_CLIENT = None
_VISION_CLIENT_ATTEMPTED = False


def _get_deepface():
    """Load the optional DeepFace stack only when thumbnail analysis needs it."""
    global _DEEPFACE, _DEEPFACE_IMPORT_ATTEMPTED
    if not _DEEPFACE_IMPORT_ATTEMPTED:
        _DEEPFACE_IMPORT_ATTEMPTED = True
        try:
            from deepface import DeepFace
        except Exception:
            _DEEPFACE = None
        else:
            _DEEPFACE = DeepFace
    return _DEEPFACE


def _get_vision_client():
    """Load Gemini vision only when an API key is configured."""
    global _VISION_CLIENT, _VISION_CLIENT_ATTEMPTED
    if not _VISION_CLIENT_ATTEMPTED:
        _VISION_CLIENT_ATTEMPTED = True
        load_dotenv()
        api_key = os.getenv("GEMINI_API_KEY")
        if api_key:
            try:
                from google import genai
            except Exception:
                _VISION_CLIENT = None
            else:
                _VISION_CLIENT = genai.Client(api_key=api_key)
    return _VISION_CLIENT

def download_image(url, filename):
    response = requests.get(url, timeout=15)
    response.raise_for_status()
    with open(filename, 'wb') as file:
        file.write(response.content)

def rgb_to_hex(rgb):
    return '#{:02x}{:02x}{:02x}'.format(rgb[0], rgb[1], rgb[2])


def _color_temperature(rgb):
    red, green, blue = rgb
    if red > blue + 10:
        return "warm"
    if blue > red + 10:
        return "cool"
    return "balanced"


def _thumbnail_metrics(img_path):
    with Image.open(img_path) as image:
        rgb = image.convert("RGB")
        grayscale = rgb.convert("L")
        brightness = ImageStat.Stat(grayscale).mean[0] / 255
        contrast = min(ImageStat.Stat(grayscale).stddev[0] / 127.5, 1.0)
        array = np.asarray(rgb)
    hsv = cv2.cvtColor(array, cv2.COLOR_RGB2HSV)
    saturation = float(hsv[:, :, 1].mean() / 255)
    gray_array = cv2.cvtColor(array, cv2.COLOR_RGB2GRAY)
    edges = cv2.Canny(gray_array, 100, 200)
    edge_density = float(np.count_nonzero(edges) / edges.size)
    _, threshold = cv2.threshold(
        gray_array, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
    )
    joined = cv2.morphologyEx(
        threshold,
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_RECT, (15, 3)),
    )
    height, width = gray_array.shape
    text_like_area = 0
    for contour in cv2.findContours(
        joined, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )[0]:
        _, _, box_width, box_height = cv2.boundingRect(contour)
        if (
            box_width >= width * 0.05
            and box_height <= height * 0.35
            and box_width / max(box_height, 1) >= 1.5
        ):
            text_like_area += box_width * box_height
    clutter = (
        "low" if edge_density < 0.08 else "medium" if edge_density < 0.18 else "high"
    )
    return {
        "brightness": round(brightness, 3),
        "saturation": round(saturation, 3),
        "contrast": round(contrast, 3),
        "edge_density": round(edge_density, 3),
        "text_like_region_density": round(
            min(text_like_area / (width * height), 1.0), 3
        ),
        "visual_clutter": clutter,
    }


def _detect_faces(img_path):
    image = cv2.imread(img_path)
    if image is None:
        return [], None
    grayscale = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    classifier = getattr(cv2, "CascadeClassifier", None)
    data = getattr(cv2, "data", None)
    if classifier is None or data is None:
        return [], grayscale.shape
    cascade = classifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    )
    boxes = cascade.detectMultiScale(grayscale, scaleFactor=1.1, minNeighbors=5)
    return [tuple(int(value) for value in box) for box in boxes], grayscale.shape


def _analyze_objects_with_gemini(img_path):
    """Return bounded semantic object/tool labels for a public thumbnail."""
    client = _get_vision_client()
    if client is None:
        return {
            "objects": [],
            "tools": [],
            "face_count": 0,
            "facial_expressions": [],
            "method": "unavailable_not_configured",
        }
    schema = {
        "type": "object",
        "properties": {
            "objects": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": 8,
                "description": "Prominent visible physical objects only.",
            },
            "tools": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": 5,
                "description": "Clearly visible hand or power tools only.",
            },
            "face_count": {
                "type": "integer",
                "minimum": 0,
                "description": "Number of clearly visible human faces.",
            },
            "facial_expressions": {
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": [
                        "happy", "surprised", "neutral", "sad", "angry",
                        "fearful", "disgusted", "unclear"
                    ],
                },
                "maxItems": 5,
                "description": "One visible expression label per face, or unclear.",
            },
        },
        "required": ["objects", "tools", "face_count", "facial_expressions"],
        "additionalProperties": False,
    }
    prompt = (
        "Inspect this YouTube thumbnail. List only prominent physical objects that "
        "are visibly present. Separately list tools only when clearly visible. Do not "
        "infer hidden items, brands, actions, audience emotions, or marketing "
        "performance. Count clearly visible human faces and describe only their "
        "visible expression using the allowed labels. Use short generic object "
        "labels and return empty lists when uncertain."
    )
    try:
        with Image.open(img_path) as image:
            response = client.models.generate_content(
                model=os.getenv("GEMINI_VISION_MODEL", "gemini-2.5-flash"),
                contents=[image.copy(), prompt],
                config={
                    "response_mime_type": "application/json",
                    "response_schema": schema,
                    "temperature": 0,
                },
            )
        payload = json.loads(response.text or "{}")
        objects = payload.get("objects", [])
        tools = payload.get("tools", [])
        expressions = payload.get("facial_expressions", [])
        face_count = payload.get("face_count", 0)
        if (
            not isinstance(objects, list)
            or not isinstance(tools, list)
            or not isinstance(expressions, list)
            or not isinstance(face_count, int)
        ):
            raise ValueError("Vision response did not contain object lists")
        clean = lambda values, limit: [
            value.strip()[:60]
            for value in values[:limit]
            if isinstance(value, str) and value.strip()
        ]
        return {
            "objects": clean(objects, 8),
            "tools": clean(tools, 5),
            "face_count": max(face_count, 0),
            "facial_expressions": clean(expressions, 5),
            "method": "gemini_structured_vision",
        }
    except Exception:
        return {
            "objects": [],
            "tools": [],
            "face_count": 0,
            "facial_expressions": [],
            "method": "unavailable_analysis_failed",
        }


def _face_composition(image_shape, boxes):
    if not image_shape or not boxes:
        return {"face_count": 0, "face_area_share": 0.0, "central_face": False}
    height, width = image_shape
    total_area = max(height * width, 1)
    area_share = min(
        sum(box_width * box_height for _, _, box_width, box_height in boxes)
        / total_area,
        1.0,
    )
    center_x, center_y = width / 2, height / 2
    central = any(
        x <= center_x <= x + box_width and y <= center_y <= y + box_height
        for x, y, box_width, box_height in boxes
    )
    return {
        "face_count": len(boxes),
        "face_area_share": round(area_share, 3),
        "central_face": central,
    }


def _analyze_thumbnail(
    img_path,
    dominant_rgb,
    *,
    face_count,
    image_metrics,
    palette,
    face_composition=None,
):
    expression = None
    expression_confidence = None
    deepface = _get_deepface()
    method = "thumbnail_features_no_face"
    if face_count and deepface is not None:
        face_analysis = deepface.analyze(img_path, actions=['emotion'], enforce_detection=False)
        if isinstance(face_analysis, list):
            face_analysis = face_analysis[0]
        expression = face_analysis.get('dominant_emotion')
        if isinstance(expression, str):
            expression = expression.capitalize()
            expression_confidence = face_analysis.get("emotion", {}).get(
                expression.lower()
            )
            if isinstance(expression_confidence, (int, float)):
                expression_confidence = round(float(expression_confidence) / 100, 3)
            else:
                expression_confidence = None
            method = "thumbnail_features_with_expression"
        else:
            expression = None
    elif face_count:
        method = "thumbnail_features_face_detected"

    temperature = _color_temperature(dominant_rgb)
    cues = [f"{temperature} color direction"]
    if image_metrics["contrast"] >= 0.55:
        cues.append("high visual contrast")
    if image_metrics["saturation"] >= 0.55:
        cues.append("vivid color treatment")
    if image_metrics["edge_density"] >= 0.2:
        cues.append("visually dense composition")
    if face_count:
        cues.append("face-led creative")
    return {
        "dominant_color": rgb_to_hex(dominant_rgb),
        "palette": [rgb_to_hex(color) for color in palette],
        "color_temperature": temperature,
        "facial_expression": expression,
        "expression_confidence": expression_confidence,
        "face_count": face_count,
        "marketing_cues": cues,
        "method": method,
        **image_metrics,
        **(face_composition or {}),
    }


def _cleanup_temp_image(img_path):
    if os.path.exists(img_path):
        os.remove(img_path)

def run_visual_analysis(df, top_n=3):
    """Runs CV on the top N trending videos to save GPU memory."""
    print(f"Running Computer Vision on Top {top_n} Trends...")
    
    if df.empty:
        return df.assign(cv_color_hex=pd.Series(dtype="object"), cv_emotion=pd.Series(dtype="object"))

    top_trends = df.head(top_n).copy()
    dominant_colors = []
    dominant_emotions = []
    cv_methods = []
    evidence_rows = []
    
    for index, row in top_trends.iterrows():
        with NamedTemporaryFile(suffix=".jpg", delete=False) as temporary_image:
            img_path = temporary_image.name
        try:
            if not row.get('thumbnail_url'):
                dom_color = '#Unknown'
                emotion = 'No Thumbnail'
                method = 'unavailable_no_thumbnail'
            else:
                try:
                    download_image(row['thumbnail_url'], img_path)
                except Exception:
                    dom_color = '#Unknown'
                    emotion = 'Download Failed'
                    method = 'unavailable_download_failed'
                else:
                    try:
                        color_thief = ColorThief(img_path)
                        dominant_rgb = color_thief.get_color(quality=1)
                        palette = color_thief.get_palette(color_count=3, quality=1)
                        image_metrics = _thumbnail_metrics(img_path)
                    except Exception:
                        dom_color = "#Unknown"
                        emotion = "Unavailable"
                        method = "unavailable_analysis_failed"
                        evidence = {
                            "dominant_color": dom_color,
                            "palette": [],
                            "color_temperature": "unavailable",
                            "facial_expression": None,
                            "expression_confidence": None,
                            "face_count": 0,
                            "marketing_cues": [],
                            "brightness": None,
                            "saturation": None,
                            "contrast": None,
                            "edge_density": None,
                            "text_like_region_density": None,
                            "visual_clutter": "unavailable",
                            "face_area_share": 0.0,
                            "central_face": False,
                            "method": method,
                            "objects": [],
                            "tools": [],
                            "semantic_method": "unavailable_analysis_failed",
                        }
                    else:
                        try:
                            face_boxes, image_shape = _detect_faces(img_path)
                        except Exception:
                            face_boxes, image_shape = [], None
                        face_composition = _face_composition(image_shape, face_boxes)
                        try:
                            evidence = _analyze_thumbnail(
                                img_path,
                                dominant_rgb,
                                face_count=face_composition["face_count"],
                                image_metrics=image_metrics,
                                palette=palette,
                                face_composition=face_composition,
                            )
                        except Exception:
                            evidence = {
                                "dominant_color": rgb_to_hex(dominant_rgb),
                                "palette": [rgb_to_hex(color) for color in palette],
                                "color_temperature": _color_temperature(dominant_rgb),
                                "facial_expression": None,
                                "expression_confidence": None,
                                "face_count": face_composition["face_count"],
                                "marketing_cues": [],
                                **image_metrics,
                                **face_composition,
                                "method": "thumbnail_features_expression_failed",
                            }
                        semantic = _analyze_objects_with_gemini(img_path)
                        evidence["objects"] = semantic["objects"]
                        evidence["tools"] = semantic["tools"]
                        evidence["semantic_method"] = semantic["method"]
                        semantic_expressions = semantic.get("facial_expressions", [])
                        if not evidence["facial_expression"] and semantic_expressions:
                            evidence["facial_expression"] = semantic_expressions[0].capitalize()
                            evidence["method"] += "+gemini_expression"
                        if not evidence["face_count"] and semantic.get("face_count"):
                            evidence["face_count"] = semantic["face_count"]
                        dom_color = evidence["dominant_color"]
                        emotion = evidence["facial_expression"] or (
                            "Face detected; expression unavailable"
                            if evidence["face_count"]
                            else "No face detected"
                        )
                        method = evidence["method"]
        finally:
            _cleanup_temp_image(img_path)

        dominant_colors.append(dom_color)
        dominant_emotions.append(emotion)
        cv_methods.append(method)
        if 'evidence' not in locals():
            evidence = {
                "dominant_color": dom_color,
                "palette": [],
                "color_temperature": "unavailable",
                "facial_expression": None,
                "expression_confidence": None,
                "face_count": 0,
                "marketing_cues": [],
                "brightness": None,
                "saturation": None,
                "contrast": None,
                "edge_density": None,
                "text_like_region_density": None,
                "visual_clutter": "unavailable",
                "face_area_share": 0.0,
                "central_face": False,
                "method": method,
                "objects": [],
                "tools": [],
                "semantic_method": "unavailable",
            }
        evidence_rows.append(evidence)
        del evidence
            
    top_trends['cv_color_hex'] = dominant_colors
    top_trends['cv_emotion'] = dominant_emotions
    top_trends['cv_method'] = cv_methods
    top_trends['cv_palette'] = [item["palette"] for item in evidence_rows]
    top_trends['cv_color_temperature'] = [item["color_temperature"] for item in evidence_rows]
    top_trends['cv_face_count'] = [item["face_count"] for item in evidence_rows]
    top_trends['cv_expression_confidence'] = [item["expression_confidence"] for item in evidence_rows]
    top_trends['cv_brightness'] = [item["brightness"] for item in evidence_rows]
    top_trends['cv_saturation'] = [item["saturation"] for item in evidence_rows]
    top_trends['cv_contrast'] = [item["contrast"] for item in evidence_rows]
    top_trends['cv_edge_density'] = [item["edge_density"] for item in evidence_rows]
    top_trends['cv_text_like_region_density'] = [item["text_like_region_density"] for item in evidence_rows]
    top_trends['cv_visual_clutter'] = [item["visual_clutter"] for item in evidence_rows]
    top_trends['cv_face_area_share'] = [item["face_area_share"] for item in evidence_rows]
    top_trends['cv_central_face'] = [item["central_face"] for item in evidence_rows]
    top_trends['cv_marketing_cues'] = [item["marketing_cues"] for item in evidence_rows]
    top_trends['cv_objects'] = [item.get("objects", []) for item in evidence_rows]
    top_trends['cv_tools'] = [item.get("tools", []) for item in evidence_rows]
    top_trends['cv_semantic_method'] = [item.get("semantic_method", "unavailable") for item in evidence_rows]
    
    return top_trends
