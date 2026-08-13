# 예제 3.1 TTS 실습 (책 3.4절 / 67쪽)
# 텍스트를 음성 파일로 변환하는 gTTS 사용법

from gtts import gTTS

# gTTS 메서드의 text에는 음성으로 변경할 텍스트를, lang에는 변환할 언어를 입력합니다.
tts = gTTS(text="안녕하세요 음성비서 프로그램 실습 중입니다.", lang="ko")

# 음성 파일 형태로 저장합니다.
tts.save("output.mp3")

print("output.mp3 저장 완료")
