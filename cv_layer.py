import os
import requests
from colorthief import ColorThief
import pandas as pd


_DEEPFACE = None
_DEEPFACE_IMPORT_ATTEMPTED = False


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

def download_image(url, filename):
    response = requests.get(url, timeout=15)
    response.raise_for_status()
    with open(filename, 'wb') as file:
        file.write(response.content)

def rgb_to_hex(rgb):
    return '#{:02x}{:02x}{:02x}'.format(rgb[0], rgb[1], rgb[2])


def _heuristic_emotion_from_color(rgb):
    red, green, blue = rgb
    brightness = (red + green + blue) / 3

    if brightness < 70:
        return "Moody"
    if red >= green and red >= blue:
        return "Energetic"
    if blue >= red and blue >= green:
        return "Calm"
    if green >= red and green >= blue:
        return "Balanced"
    return "Neutral"


def _analyze_thumbnail(img_path, dominant_rgb):
    dom_color = rgb_to_hex(dominant_rgb)
    deepface = _get_deepface()

    if deepface is not None:
        face_analysis = deepface.analyze(img_path, actions=['emotion'], enforce_detection=False)
        if isinstance(face_analysis, list):
            emotion = face_analysis[0].get('dominant_emotion', 'No Face Detected').capitalize()
        else:
            emotion = face_analysis.get('dominant_emotion', 'No Face Detected').capitalize()
    else:
        emotion = _heuristic_emotion_from_color(dominant_rgb)

    return dom_color, emotion


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
    
    for index, row in top_trends.iterrows():
        img_path = f"temp_{row['video_id']}.jpg"
        # If no thumbnail URL, skip download and use defaults
        if not row.get('thumbnail_url'):
            dominant_colors.append('#Unknown')
            dominant_emotions.append('No Thumbnail')
            continue

        try:
            download_image(row['thumbnail_url'], img_path)
        except Exception:
            dominant_colors.append('#Unknown')
            dominant_emotions.append('Download Failed')
            continue
        
        try:
            color_thief = ColorThief(img_path)
            dominant_rgb = color_thief.get_color(quality=1)
            dom_color, emotion = _analyze_thumbnail(img_path, dominant_rgb)
        except Exception:
            dom_color = "#Unknown"
            emotion = "Neutral"
            
        dominant_colors.append(dom_color)
        dominant_emotions.append(emotion)
        
        # Cleanup temp image
        _cleanup_temp_image(img_path)
            
    top_trends['cv_color_hex'] = dominant_colors
    top_trends['cv_emotion'] = dominant_emotions
    
    return top_trends