import os
from dotenv import load_dotenv
load_dotenv()
from google import genai
from PIL import Image

def test():
    client = genai.Client()
    schema = {
        "type": "object",
        "properties": {
            "objects": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": 10,
                "description": "Prominent physical items.",
            },
            "tools": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": 5,
                "description": "Tools or equipment explicitly visible.",
            },
            "face_count": {
                "type": "integer",
                "description": "Number of clearly visible human faces.",
            },
            "facial_expressions": {
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": [
                        "angry",
                        "disgust",
                        "fear",
                        "happy",
                        "sad",
                        "surprise",
                        "neutral",
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
    img = Image.new('RGB', (100, 100), color = 'red')
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[img, prompt],
            config={
                "response_mime_type": "application/json",
                "response_schema": schema,
                "temperature": 0,
            }
        )
        print("Success:", response.text)
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    test()
