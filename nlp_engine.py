import logging
from datetime import datetime, timezone
import pandas as pd
import spacy
import math

logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)

nlp = spacy.load("en_core_web_sm")

DREMEL_VERBS = {
    "carve", "engrave", "cut", "sand", "grind", "polish", "drill", "grout",
    "route", "clean", "build", "upcycle", "restore", "repair",
    "assemble", "paint", "make", "create", "transform", "turn", "share", "show",
    "teach", "use", "find", "do", "make", "replace", "install", "remove"
}

# EXPANDED: We must include specific furniture and hardware for the filter to survive
SURFACE_MATERIALS = {
    "wood", "table", "desk", "chair", "metal", "brass", "hardware", 
    "cabinet", "surface", "veneer", "mdf", "plywood", "board", "frame",
    "floor", "wall", "door", "glass", "tile", "countertop", "resin", 
    "plastic", "dresser", "drawer", "shelf", "bench", "box", "mirror", 
    "stool", "pallet", "log", "timber", "iron", "steel", "copper", 
    "ceramic", "fabric", "canvas", "leather", "wardrobe", "knob", 
    "handle", "hinge", "window", "panel", "base", "leg"
}

def _safe_int(value):
    try:
        return int(value or 0)
    except Exception:
        return 0

def _parse_publish_date(publish_str, video_id):
    try:
        return datetime.strptime(publish_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except Exception as exc:
        logger.warning("Unable to parse publish_date '%s' for video_id=%s: %s", publish_str, video_id, exc)
        return None

def _find_fallback_noun(token):
    for noun_chunk in token.sent.noun_chunks:
        lemma = noun_chunk.root.lemma_.lower()
        if noun_chunk.root.i > token.i and noun_chunk.root.pos_ in ["NOUN", "PROPN"]:
            if lemma in SURFACE_MATERIALS:
                return noun_chunk.root.lemma_.capitalize()
    return None

def _actions_for_token(token):
    if token.pos_ != "VERB" or token.lemma_ not in DREMEL_VERBS:
        return []

    actions = [
        (token.lemma_.capitalize(), child.lemma_.capitalize())
        for child in token.children
        if child.dep_ in ["dobj", "pobj"] and child.pos_ in ["NOUN", "PROPN"] and child.lemma_.lower() in SURFACE_MATERIALS
    ]

    if actions:
        return actions

    fallback_noun = _find_fallback_noun(token)
    if fallback_noun:
        return [(token.lemma_.capitalize(), fallback_noun)]

    return []

def _loose_actions_for_token(token):
    # FIXED: Enforce Dremel Verbs even in the loose metadata parse to prevent junk actions
    if token.pos_ != "VERB" or token.lemma_ not in DREMEL_VERBS:
        return []

    actions = [
        (token.lemma_.capitalize(), child.lemma_.capitalize())
        for child in token.children
        if child.pos_ in ["NOUN", "PROPN"] and child.dep_ in ["dobj", "pobj", "attr"] and child.lemma_.lower() in SURFACE_MATERIALS
    ]

    if actions:
        return actions

    fallback_noun = _find_fallback_noun(token)
    if fallback_noun:
        return [(token.lemma_.capitalize(), fallback_noun)]

    return []

def extract_loose_actions(text):
    if not text: return []
    doc = nlp(text.lower())
    actions = []
    for token in doc:
        actions.extend(_loose_actions_for_token(token))
    return actions

def _build_fallback_corpus(video):
    transcript = (video.get("transcript") or "").strip()
    fallback_corpus = " ".join(
        part.strip() for part in [video.get("title", ""), video.get("description", "")]
        if part and part.strip()
    )
    return transcript, fallback_corpus

def extract_dremel_actions(transcript_text):
    if not transcript_text: return []
    doc = nlp(transcript_text.lower())
    actions = []
    for token in doc:
        actions.extend(_actions_for_token(token))
    return actions

def _build_result_rows(video, actions, velocity):
    return [
        {
            "video_id": video.get("video_id"),
            "video_title": video.get("title"),
            "thumbnail_url": video.get("thumbnail_url"),
            "detected_verb": verb,
            "detected_material": noun,
            "action_pair": f"{verb} {noun}",
            "velocity_score": round(velocity, 2),
        }
        for verb, noun in actions
    ]

def _resolve_actions_for_video(video):
    transcript_text, fallback_corpus = _build_fallback_corpus(video)
    if not transcript_text and not fallback_corpus:
        return []

    if transcript_text:
        actions = extract_dremel_actions(transcript_text)
        if actions or not fallback_corpus:
            return actions
        return extract_loose_actions(fallback_corpus)

    return extract_loose_actions(fallback_corpus)

def process_and_score_data(video_data_list, now=None):
    output_columns = [
        "video_id", "video_title", "thumbnail_url", "detected_verb", 
        "detected_material", "action_pair", "velocity_score"
    ]
    rows = []
    today = now or datetime.now(timezone.utc)

    for video in video_data_list:
        if not isinstance(video, dict): continue
        
        actions = _resolve_actions_for_video(video)
        if not actions: continue

        publish_str = video.get("publish_date")
        if not publish_str: continue

        pub_date = _parse_publish_date(publish_str, video.get("video_id"))
        if pub_date is None: continue

        # 1. Base Variables
        days_live = max((today - pub_date).days, 1)
        views = _safe_int(video.get("views", 0))
        comments = _safe_int(video.get("comments", 0))
        
        # 2. Base Engagement Velocity (V)
        base_velocity = (views + (comments * 5)) / days_live
        
        # 3. EXPONENTIAL TREND DECAY PENALTY (The Upgrade)
        # This penalizes older videos heavily. A video loses 10% of its multiplier weight every 7 days.
        decay_constant = 0.015 
        recency_multiplier = math.exp(-decay_constant * days_live)
        
        # 4. Final Predictive Score
        final_velocity = base_velocity * recency_multiplier

        # Only add to rows if it has a meaningful velocity
        if final_velocity > 0:
            rows.extend(_build_result_rows(video, actions, final_velocity))

    df = pd.DataFrame(rows, columns=output_columns)
    if not df.empty:
        # Rank by the new, time-penalized velocity score
        df = df.sort_values(by="velocity_score", ascending=False)
    return df