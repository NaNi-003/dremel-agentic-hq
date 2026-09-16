import requests
from pathlib import Path
from deepface import DeepFace

url = 'https://i.ytimg.com/vi/1eCelg322FM/hqdefault.jpg'
image_path = Path('tmp_test.jpg')
image_path.write_bytes(requests.get(url, timeout=15).content)
result = DeepFace.analyze(str(image_path), actions=['emotion'], enforce_detection=False)
print(type(result))
if isinstance(result, list):
    print(result[0]['dominant_emotion'])
else:
    print(result['dominant_emotion'])
