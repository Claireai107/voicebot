# Gemini 키가 실제로 동작하는지, 어떤 모델을 쓸 수 있는지 확인하는 스크립트입니다.
# key.txt 에 API 키만 한 줄 적어두고 실행하세요. (key.txt는 .gitignore에 있어 커밋되지 않습니다)
#
# 실행: ch03_env\Scripts\python.exe 모델확인.py

from google import genai
from google.genai import types

with open("key.txt", encoding="utf-8") as f:
    APIKEY = f.read().strip()

client = genai.Client(api_key=APIKEY)

# 1) 이 키로 쓸 수 있는 모델 목록
print("=== 사용 가능한 모델 (generateContent 지원) ===")
usable = []
for m in client.models.list():
    actions = getattr(m, "supported_actions", None) or []
    if "generateContent" in actions:
        name = m.name.replace("models/", "")
        usable.append(name)
        print(" ", name)

print()
print("=== 코드에서 쓰려는 모델이 목록에 있는지 ===")
for want in ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-3.5-flash", "gemini-3.6-flash"]:
    print(f"  {want}: {'있음' if want in usable else '없음'}")

# 2) 실제 음성 받아쓰기 테스트 (output.mp3 사용)
print()
print("=== STT 실제 호출 테스트 ===")
with open("output.mp3", "rb") as f:
    audio_bytes = f.read()

r = client.models.generate_content(
    model="gemini-2.5-flash",
    contents=[
        types.Part.from_bytes(data=audio_bytes, mime_type="audio/mp3"),
        "이 오디오에 담긴 말을 그대로 받아써 줘. 설명이나 따옴표 없이 말한 내용만 출력해.",
    ],
)
print("  받아쓴 결과:", repr(r.text.strip()))

# 3) 대화 테스트
print()
print("=== 답변 생성 테스트 ===")
r2 = client.models.generate_content(
    model="gemini-2.5-flash",
    contents=[types.Content(role="user", parts=[types.Part(text="부자가 되는 법을 알려줘")])],
    config=types.GenerateContentConfig(
        system_instruction="You are a thoughtful assistant. Respond to all input in 25 words and answer in korean"
    ),
)
print("  답변:", r2.text.strip())
print()
print("모두 통과했습니다.")
