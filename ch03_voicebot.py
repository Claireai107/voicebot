##### 기본 정보 입력 #####
# 책 3.7 ~ 3.10절 구조를 그대로 두고, OpenAI 부분만 Gemini로 교체한 버전입니다.
#
#   STT (음성→텍스트) : Whisper      →  Gemini (오디오를 그대로 입력받음)
#   답변             : GPT          →  Gemini
#   TTS (텍스트→음성) : gTTS         →  gTTS (그대로. 무료라 바꿀 이유가 없습니다)
#
# 실행: streamlit run ch03_voicebot.py
# API 키 발급(무료): https://aistudio.google.com/apikey

import streamlit as st
# audiorecorder 패키지 추가
from audiorecorder import audiorecorder
# Gemini 패키지 추가 (기존 openai 자리)
from google import genai
from google.genai import types
# 파일 삭제를 위한 패키지 추가
import os
# 시간 정보를 위한 패키지 추가
from datetime import datetime
# TTS 패키지 추가
from gtts import gTTS
# 음원 파일을 재생하기 위한 패키지 추가
import base64


# Gemini는 시스템 지시문을 대화 기록과 따로 전달합니다.
# (OpenAI는 messages 리스트 안에 {"role": "system"} 으로 넣었던 부분입니다.)
SYSTEM_PROMPT = "You are a thoughtful assistant. Respond to all input in 25 words and answer in korean"

# 음성을 텍스트로 옮길 때 쓰는 모델. 받아쓰기는 가볍고 빠른 모델로 충분합니다.
#
# 참고: gemini-2.5 계열은 모델 목록에는 보이지만 새로 발급한 키로는 호출되지 않습니다.
#       ("no longer available to new users" 404) 그래서 3.5 이상을 씁니다.
STT_MODEL = "gemini-3.5-flash-lite"


##### 기능 구현 함수 #####
def STT(audio, apikey):
    """녹음된 음성(AudioSegment)을 텍스트로 변환합니다.

    Whisper는 '음성 전용' 모델이라 파일만 넘기면 됐지만,
    Gemini는 범용 모델이라 [오디오 + 무엇을 해달라는 지시] 를 같이 넘깁니다.
    """
    # 파일 저장
    filename = 'input.mp3'
    audio.export(filename, format="mp3")

    # 음원 파일을 바이트로 읽기
    with open(filename, "rb") as audio_file:
        audio_bytes = audio_file.read()

    # 파일 삭제
    os.remove(filename)

    # Gemini에 오디오와 지시문을 함께 전달해 텍스트 얻기
    client = genai.Client(api_key=apikey)
    response = client.models.generate_content(
        model=STT_MODEL,
        contents=[
            types.Part.from_bytes(data=audio_bytes, mime_type="audio/mp3"),
            "이 오디오에 담긴 말을 그대로 받아써 줘. "
            "설명이나 따옴표 없이 말한 내용만 출력해.",
        ],
    )
    return (response.text or "").strip()


def ask_gemini(prompt, model, apikey):
    """대화 기록(prompt)을 Gemini에 전달하고 답변 텍스트를 반환합니다."""
    client = genai.Client(api_key=apikey)

    # 저장해 둔 대화 기록을 Gemini가 받는 형식으로 변환합니다.
    contents = [
        types.Content(role=turn["role"], parts=[types.Part(text=turn["text"])])
        for turn in prompt
    ]

    response = client.models.generate_content(
        model=model,
        contents=contents,
        config=types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT),
    )
    return response.text


def TTS(response):
    """답변 텍스트를 음성 파일로 만들고 자동 재생합니다. (책 그대로)"""
    # gTTS를 활용하여 음성 파일 생성
    filename = "output.mp3"
    tts = gTTS(text=response, lang="ko")
    tts.save(filename)

    # 음원 파일 자동 재생
    # 스트림릿에는 음원을 자동 재생하는 함수가 없으므로 HTML로 직접 구현합니다.
    with open(filename, "rb") as f:
        data = f.read()
        b64 = base64.b64encode(data).decode()
        md = f"""
            <audio autoplay="True">
            <source src="data:audio/mp3;base64,{b64}" type="audio/mp3">
            </audio>
            """
        st.markdown(md, unsafe_allow_html=True)
    # 파일 삭제
    os.remove(filename)


##### 메인 함수 #####
def main():
    # 기본 설정
    st.set_page_config(
        page_title="음성 비서 프로그램",
        layout="wide")

    # 제목
    st.header("음성 비서 프로그램")

    # 구분선
    st.markdown("---")

    # 기본 설명
    with st.expander("음성비서 프로그램에 관하여", expanded=True):
        st.write(
            """
            - 음성비서 프로그램의 UI는 스트림릿을 활용하여 만들었습니다.
            - STT(Speech-To-Text)는 구글의 Gemini를 활용하였습니다.
            - 답변은 구글의 Gemini를 활용하였습니다.
            - TTS(Text-To-Speech)는 구글의 Google Translate TTS를 활용하였습니다.
            """
        )
        st.markdown("")

    # session state 초기화
    if "chat" not in st.session_state:
        st.session_state["chat"] = []

    if "GEMINI_API" not in st.session_state:
        st.session_state["GEMINI_API"] = ""

    # Gemini의 대화 기록 형식입니다.
    # 역할 이름이 OpenAI와 다릅니다: "assistant"가 아니라 "model" 을 씁니다.
    # 시스템 지시문은 여기 넣지 않고 SYSTEM_PROMPT 로 따로 전달하므로 빈 리스트로 시작합니다.
    if "messages" not in st.session_state:
        st.session_state["messages"] = []

    if "check_reset" not in st.session_state:
        st.session_state["check_reset"] = False

    # 사이드바 생성
    with st.sidebar:
        # Gemini API 키 입력받기
        st.session_state["GEMINI_API"] = st.text_input(
            label="Gemini API 키",
            placeholder="Enter Your API Key",
            value="",
            type="password")
        st.caption("무료 발급: aistudio.google.com/apikey")

        st.markdown("---")

        # Gemini 모델을 선택하기 위한 라디오 버튼 생성
        # pro 계열은 무료 사용량이 없어 429가 나므로 flash 계열만 넣었습니다.
        model = st.radio(
            label="Gemini 모델",
            options=["gemini-3.6-flash", "gemini-3.5-flash", "gemini-3.5-flash-lite"])

        st.markdown("---")

        # 리셋 버튼 생성
        if st.button(label="초기화"):
            # 리셋 코드
            st.session_state["chat"] = []
            st.session_state["messages"] = []
            st.session_state["check_reset"] = True

    # 기능 구현 공간
    col1, col2 = st.columns(2)
    with col1:
        # 왼쪽 영역 작성
        st.subheader("질문하기")
        # 음성 녹음 아이콘 추가
        audio = audiorecorder("클릭하여 녹음하기", "녹음 중...")
        if (audio.duration_seconds > 0) and (st.session_state["check_reset"] == False):
            # 음성 재생
            st.audio(audio.export().read())
            # 음원 파일에서 텍스트 추출
            question = STT(audio, st.session_state["GEMINI_API"])

            # 채팅을 시각화하기 위해 질문 내용 저장
            now = datetime.now().strftime("%H:%M")
            st.session_state["chat"] = st.session_state["chat"] + [("user", now, question)]
            # Gemini에 넣을 대화 기록을 위해 질문 내용 저장
            st.session_state["messages"] = st.session_state["messages"] + [{"role": "user", "text": question}]

    with col2:
        # 오른쪽 영역 작성
        st.subheader("질문/답변")
        if (audio.duration_seconds > 0) and (st.session_state["check_reset"] == False):
            # Gemini에게 답변 얻기
            response = ask_gemini(st.session_state["messages"], model, st.session_state["GEMINI_API"])

            # 다음 질문에 대비해 답변 내용 저장 (Gemini에서 답변의 역할 이름은 "model" 입니다)
            st.session_state["messages"] = st.session_state["messages"] + [{"role": "model", "text": response}]

            # 채팅 시각화를 위한 답변 내용 저장
            now = datetime.now().strftime("%H:%M")
            st.session_state["chat"] = st.session_state["chat"] + [("bot", now, response)]

            # 채팅 형식으로 시각화하기
            for sender, time, message in st.session_state["chat"]:
                if sender == "user":
                    st.write(
                        f'<div style="display:flex;align-items:center;">'
                        f'<div style="background-color:#007AFF;color:white;border-radius:12px;padding:8px 12px;margin-right:8px;">{message}</div>'
                        f'<div style="font-size:0.8rem;color:gray;">{time}</div></div>',
                        unsafe_allow_html=True)
                    st.write("")
                else:
                    st.write(
                        f'<div style="display:flex;align-items:center;justify-content:flex-end;">'
                        f'<div style="background-color:lightgray;border-radius:12px;padding:8px 12px;margin-left:8px;">{message}</div>'
                        f'<div style="font-size:0.8rem;color:gray;">{time}</div></div>',
                        unsafe_allow_html=True)
                    st.write("")

            # gTTS를 활용하여 음성 파일 생성 및 재생
            TTS(response)
        else:
            st.session_state["check_reset"] = False


if __name__ == "__main__":
    main()
