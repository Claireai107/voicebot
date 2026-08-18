##### 귀쫑긋 — 말하면 알아듣는 고양이 비서 #####
#
# 「진짜 챗GPT API 활용법」 3장(나만의 음성 비서 만들기)을 바탕으로,
# OpenAI 자리를 Gemini로 바꾸고 녹음 방식을 "계속 듣기"로 바꾼 버전입니다.
#
#   STT (음성→텍스트) : Whisper      →  Gemini (오디오를 그대로 입력받음)
#   답변             : GPT          →  Gemini
#   TTS (텍스트→음성) : gTTS         →  gTTS (그대로. 무료라 바꿀 이유가 없습니다)
#   녹음             : 녹음 버튼      →  마이크를 열어둔 채 침묵으로 끊기
#
# 컨셉: 귀를 쫑긋 세우고 늘 듣고 있는 고양이.
#       버튼을 누르는 게 아니라 그냥 말을 걸면 되는 물건이라서,
#       "듣고 있다"는 상태가 화면에 계속 보이는 게 이 앱의 핵심입니다.
#
# 실행: streamlit run ch03_voicebot.py
# API 키 발급(무료): https://aistudio.google.com/apikey

import streamlit as st
# 마이크를 계속 열어두기 위한 패키지 (기존 audiorecorder 자리)
from streamlit_webrtc import webrtc_streamer, WebRtcMode
# 소리 조각을 다루고 침묵을 재기 위한 패키지
from pydub import AudioSegment
# 마이크에서 아직 소리가 안 왔을 때를 구분하기 위한 패키지
import queue
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
# 일시적인 서버 오류를 잠깐 기다렸다 다시 시도하기 위한 패키지
import time


##### 이 프로그램의 이름과 말투 #####
APP_NAME = "귀쫑긋"
APP_TAGLINE = "말하면 알아듣는 고양이 비서"

# Gemini는 시스템 지시문을 대화 기록과 따로 전달합니다.
# (OpenAI는 messages 리스트 안에 {"role": "system"} 으로 넣었던 부분입니다.)
# 컨셉에 맞춰 말투도 여기서 정합니다.
SYSTEM_PROMPT = (
    "너는 '귀쫑긋'이라는 이름의 고양이 비서다. "
    "친근한 반말은 쓰지 말고, 짧고 다정한 존댓말로 답한다. "
    "답변은 한국어로 25단어 안쪽으로 짧게 한다. "
    "가끔 문장 끝에 고양이다운 여운을 살짝 남겨도 좋지만, 과하게 하지 않는다."
)

# 음성을 텍스트로 옮길 때 쓰는 모델. 받아쓰기는 가볍고 빠른 모델로 충분합니다.
#
# 참고: gemini-2.5 계열은 모델 목록에는 보이지만 새로 발급한 키로는 호출되지 않습니다.
#       ("no longer available to new users" 404) 그래서 3.5 이상을 씁니다.
STT_MODEL = "gemini-3.5-flash-lite"

# 사이드바에서 고르는 '머리'(답변 모델)입니다.
# pro 계열은 무료 사용량이 없어 429가 나므로 flash 계열만 넣었습니다.
BRAINS = {
    "똑똑한 머리": "gemini-3.6-flash",
    "보통 머리": "gemini-3.5-flash",
    "가벼운 머리": "gemini-3.5-flash-lite",
}

# 브라우저와 서버가 서로를 찾기 위한 공개 STUN 서버입니다.
# 이게 없으면 배포본에서 마이크가 연결되지 않습니다.
RTC_CONFIG = {"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]}

# 침묵 판정 기준 ─ 교실 소음에 맞춰 조정하는 값들입니다.
SILENCE_DBFS = -38.0     # 이보다 조용한 조각은 '침묵'으로 봅니다
SILENCE_HOLD_MS = 1200   # 1.2초 조용하면 말이 끝난 것으로 봅니다
MIN_SPEECH_MS = 400      # 이보다 짧으면 기침·잡음으로 보고 버립니다
MAX_UTTER_MS = 15000     # 계속 말해도 15초에서 한 번 끊습니다 (안전장치)


##### 고양이 그림 #####
# 밈 이미지를 가져다 쓰면 저작권 문제가 생기고 공개 배포에는 더 곤란하므로,
# 상태마다 표정이 바뀌는 고양이를 SVG로 직접 그렸습니다. 외부 파일이 없어서
# 배포할 때 따로 올릴 것도 없습니다.
CAT_FACES = {
    # (귀 각도, 눈, 입, 한마디)
    "sleep": ("-18", "closed", "smile", "쿨…쿨…"),
    "ready": ("0", "wide", "smile", "쫑긋!"),
    "listen": ("0", "wide", "open", "듣는 중"),
    "think": ("6", "up", "flat", "골똘"),
    "talk": ("0", "happy", "open", "냐앙"),
}


def cat_svg(state):
    """상태에 맞는 고양이 얼굴 SVG를 문자열로 만들어 돌려줍니다."""
    ear, eye, mouth, _ = CAT_FACES.get(state, CAT_FACES["ready"])

    if eye == "closed":
        eyes = ('<path d="M40 60 q8 7 16 0" stroke="#5B4636" stroke-width="3" fill="none" stroke-linecap="round"/>'
                '<path d="M74 60 q8 7 16 0" stroke="#5B4636" stroke-width="3" fill="none" stroke-linecap="round"/>')
    elif eye == "up":
        eyes = ('<circle cx="48" cy="60" r="7" fill="#5B4636"/><circle cx="82" cy="60" r="7" fill="#5B4636"/>'
                '<circle cx="50" cy="56" r="2.5" fill="#fff"/><circle cx="84" cy="56" r="2.5" fill="#fff"/>')
    elif eye == "happy":
        eyes = ('<path d="M40 63 q8 -9 16 0" stroke="#5B4636" stroke-width="3" fill="none" stroke-linecap="round"/>'
                '<path d="M74 63 q8 -9 16 0" stroke="#5B4636" stroke-width="3" fill="none" stroke-linecap="round"/>')
    else:  # wide
        eyes = ('<circle cx="48" cy="62" r="9" fill="#5B4636"/><circle cx="82" cy="62" r="9" fill="#5B4636"/>'
                '<circle cx="51" cy="58" r="3" fill="#fff"/><circle cx="85" cy="58" r="3" fill="#fff"/>')

    if mouth == "open":
        lips = '<ellipse cx="65" cy="82" rx="7" ry="9" fill="#E8746F"/>'
    elif mouth == "flat":
        lips = '<path d="M57 82 h16" stroke="#5B4636" stroke-width="3" stroke-linecap="round"/>'
    else:  # smile
        lips = ('<path d="M57 79 q8 8 16 0" stroke="#5B4636" stroke-width="3" fill="none" stroke-linecap="round"/>')

    return f"""
    <svg viewBox="0 0 130 120" width="100%" style="max-width:150px;display:block;margin:0 auto;">
      <g transform="rotate({ear} 40 34)">
        <path d="M28 46 L34 16 L58 34 Z" fill="#F7C873" stroke="#5B4636" stroke-width="3" stroke-linejoin="round"/>
        <path d="M34 41 L37 25 L50 34 Z" fill="#F2A0A0"/>
      </g>
      <g transform="rotate({-int(ear)} 90 34)">
        <path d="M102 46 L96 16 L72 34 Z" fill="#F7C873" stroke="#5B4636" stroke-width="3" stroke-linejoin="round"/>
        <path d="M96 41 L93 25 L80 34 Z" fill="#F2A0A0"/>
      </g>
      <ellipse cx="65" cy="66" rx="42" ry="36" fill="#F7C873" stroke="#5B4636" stroke-width="3"/>
      {eyes}
      <path d="M61 73 h8 l-4 5 Z" fill="#E8746F"/>
      {lips}
      <g stroke="#5B4636" stroke-width="2" stroke-linecap="round">
        <path d="M20 68 h16"/><path d="M20 76 h15"/>
        <path d="M110 68 h-16"/><path d="M110 76 h-15"/>
      </g>
    </svg>
    """


def show_cat(slot, state, line=None):
    """고양이 얼굴과 한마디를 화면의 한 자리에 그려 넣습니다."""
    caption = line or CAT_FACES.get(state, CAT_FACES["ready"])[3]
    slot.markdown(
        f'<div class="cat-box">{cat_svg(state)}'
        f'<div class="cat-line">{caption}</div></div>',
        unsafe_allow_html=True)


##### 기능 구현 함수 #####
def call_gemini(fn, tries=3, wait=2):
    """Gemini 호출을 감싸서, 일시적인 오류면 잠깐 기다렸다 다시 시도합니다.

    Gemini는 몰릴 때 503(UNAVAILABLE, "일시적입니다")을 돌려줍니다.
    실제로 12번 호출에 1번 꼴로 나왔고, 그대로 두면 화면에 파이썬 오류가
    그대로 떠서 수업 중에 당황하기 쉽습니다. 잠깐 기다렸다 다시 부르면
    대부분 그냥 성공합니다.

    키가 틀렸거나 모델 이름이 잘못된 경우처럼 다시 시도해도 소용없는
    오류는 그대로 올려보냅니다. 숨기면 원인을 못 찾습니다.
    """
    for attempt in range(tries):
        try:
            return fn()
        except Exception as e:
            transient = ("503" in str(e)) or ("UNAVAILABLE" in str(e))
            if attempt == tries - 1 or not transient:
                raise
            time.sleep(wait)


def check_apikey(apikey):
    """열쇠(API 키)가 진짜 쓸 수 있는 것인지 실제로 한 번 불러서 확인합니다.

    형식만 보고 넘어가면 "키를 넣었는데 녹음하니까 터진다"가 됩니다.
    가장 싼 모델로 한 마디만 시켜보는 게 확실합니다.

    돌려주는 값: (되는지 여부, 사람에게 보여줄 문구)
    """
    if not apikey:
        return False, "열쇠를 먼저 입력해 주세요."

    try:
        client = genai.Client(api_key=apikey)
        call_gemini(lambda: client.models.generate_content(
            model=STT_MODEL, contents=["ping"]))
        return True, "쓸 수 있는 열쇠입니다. 이제 말을 걸어보세요."
    except Exception as e:
        msg = str(e)
        if "API_KEY_INVALID" in msg or "API key not valid" in msg:
            return False, "맞지 않는 열쇠입니다. 앞뒤 공백이 섞이지 않았는지 확인해 주세요."
        if "PERMISSION_DENIED" in msg or "403" in msg:
            return False, "이 열쇠에는 권한이 없습니다. aistudio에서 새로 발급해 보세요."
        if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
            return False, "열쇠는 맞지만 오늘 사용량을 다 썼습니다."
        return False, f"확인하지 못했습니다 ({type(e).__name__}). 잠시 후 다시 눌러 주세요."


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
    response = call_gemini(lambda: client.models.generate_content(
        model=STT_MODEL,
        contents=[
            types.Part.from_bytes(data=audio_bytes, mime_type="audio/mp3"),
            "이 오디오에 담긴 말을 그대로 받아써 줘. "
            "설명이나 따옴표 없이 말한 내용만 출력해.",
        ],
    ))
    return (response.text or "").strip()


def ask_gemini(prompt, model, apikey):
    """대화 기록(prompt)을 Gemini에 전달하고 답변 텍스트를 반환합니다."""
    client = genai.Client(api_key=apikey)

    # 저장해 둔 대화 기록을 Gemini가 받는 형식으로 변환합니다.
    contents = [
        types.Content(role=turn["role"], parts=[types.Part(text=turn["text"])])
        for turn in prompt
    ]

    response = call_gemini(lambda: client.models.generate_content(
        model=model,
        contents=contents,
        config=types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT),
    ))
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

    # 답변 음성이 몇 초짜리인지 재둡니다. 파일을 지우기 전에 재야 합니다.
    # 이 길이만큼 마이크 입력을 버려야 스피커 소리를 자기가 되받는 걸 막을 수 있습니다.
    spoken_ms = len(AudioSegment.from_mp3(filename))

    # 파일 삭제
    os.remove(filename)
    return spoken_ms


##### 마이크에서 한 문장씩 끊어 듣기 #####
def listen_once(ctx, cat_slot):
    """말이 시작되고 끝날 때까지 기다렸다가, 그 구간만 잘라서 돌려줍니다.

    책의 "녹음 버튼을 눌렀다 다시 누른다"를 대신하는 부분입니다.
    소리 크기(dBFS)가 SILENCE_DBFS 를 넘으면 말이 시작된 것으로 보고 모으기
    시작하고, 다시 SILENCE_HOLD_MS 만큼 조용해지면 한 문장이 끝났다고 봅니다.

    돌려주는 값: 말이 담긴 AudioSegment. 마이크가 끊기면 None.
    """
    said = None      # 말이 시작된 뒤 모아온 소리
    quiet_ms = 0     # 말이 시작된 뒤 이어진 침묵의 길이

    while True:
        if not ctx.state.playing or ctx.audio_receiver is None:
            return None

        try:
            frames = ctx.audio_receiver.get_frames(timeout=1)
        except queue.Empty:
            # 아직 소리가 안 들어왔을 뿐입니다. 계속 기다립니다.
            continue

        for frame in frames:
            chunk = AudioSegment(
                data=frame.to_ndarray().tobytes(),
                sample_width=frame.format.bytes,
                frame_rate=frame.sample_rate,
                channels=len(frame.layout.channels),
            )
            loud = chunk.dBFS > SILENCE_DBFS

            if said is None:
                # 아직 말이 시작되지 않았습니다. 조용한 부분은 버립니다.
                if loud:
                    said = chunk
                    quiet_ms = 0
                    show_cat(cat_slot, "listen")
                continue

            said += chunk
            quiet_ms = 0 if loud else quiet_ms + len(chunk)

            if quiet_ms >= SILENCE_HOLD_MS:
                # 뒤에 붙은 침묵을 뺀 실제 말 길이로 판단합니다.
                if len(said) - quiet_ms >= MIN_SPEECH_MS:
                    return said
                # 너무 짧으면 기침이나 잡음으로 보고 버린 뒤 다시 기다립니다.
                said = None
                quiet_ms = 0
                show_cat(cat_slot, "ready")
            elif len(said) >= MAX_UTTER_MS:
                return said


def drain(ctx, ms):
    """답변이 스피커로 나가는 동안 들어온 마이크 소리를 버립니다.

    마이크가 계속 열려 있으므로, 이걸 안 하면 비서가 자기 답변을 다시 듣고
    거기에 또 답하는 무한 루프에 빠집니다.
    """
    end = time.time() + ms / 1000
    while time.time() < end:
        if not ctx.state.playing or ctx.audio_receiver is None:
            return
        try:
            ctx.audio_receiver.get_frames(timeout=0.5)
        except queue.Empty:
            pass


##### 대화 보여주기 #####
def show_turn(sender, stamp, message):
    """말풍선 하나를 그립니다. 이 앱에서 가장 크게 보여야 할 부분입니다."""
    side = "me" if sender == "user" else "cat"
    who = "나" if sender == "user" else APP_NAME
    st.markdown(
        f'<div class="turn {side}">'
        f'<div class="who">{who} · {stamp}</div>'
        f'<div class="bubble">{message}</div>'
        f'</div>',
        unsafe_allow_html=True)


STYLE = """
<style>
.block-container { padding-top: 2rem; }

/* 고양이 */
.cat-box { text-align:center; padding:6px 0 2px; }
.cat-line {
  margin-top:6px; font-size:1.05rem; font-weight:700; color:#8A6234;
  letter-spacing:.02em;
}

/* 대화 — 이 앱의 주인공이라 크고 넉넉하게 */
.turn { margin: 14px 0; display:flex; flex-direction:column; }
.turn.me  { align-items:flex-end; }
.turn.cat { align-items:flex-start; }
.turn .who { font-size:.78rem; color:#9A9A9A; margin:0 6px 4px; }
.turn .bubble {
  max-width: 82%;
  font-size: 1.25rem;
  line-height: 1.65;
  padding: 14px 18px;
  border-radius: 18px;
  word-break: keep-all;
}
.turn.me .bubble {
  background:#2F7DF6; color:#fff; border-bottom-right-radius:6px;
}
.turn.cat .bubble {
  background:#FFF1D6; color:#3D2E1E; border:1px solid #F0DCB4;
  border-bottom-left-radius:6px;
}

/* 좁은 화면에서는 말풍선이 화면을 더 쓰게 합니다 */
@media (max-width: 640px) {
  .turn .bubble { max-width: 95%; font-size: 1.15rem; }
}
</style>
"""


##### 메인 함수 #####
def main():
    # 기본 설정
    st.set_page_config(
        page_title=f"{APP_NAME} — {APP_TAGLINE}",
        page_icon="🐱",
        layout="wide")

    st.markdown(STYLE, unsafe_allow_html=True)

    # session state 초기화
    if "chat" not in st.session_state:
        st.session_state["chat"] = []

    if "GEMINI_API" not in st.session_state:
        st.session_state["GEMINI_API"] = ""

    # 열쇠 확인 결과를 기억해 둡니다. (되는지, 보여줄 문구)
    if "key_checked" not in st.session_state:
        st.session_state["key_checked"] = None

    # Gemini의 대화 기록 형식입니다.
    # 역할 이름이 OpenAI와 다릅니다: "assistant"가 아니라 "model" 을 씁니다.
    # 시스템 지시문은 여기 넣지 않고 SYSTEM_PROMPT 로 따로 전달하므로 빈 리스트로 시작합니다.
    if "messages" not in st.session_state:
        st.session_state["messages"] = []

    # 책에 있던 check_reset 은 없앴습니다. 녹음 버튼이 있던 시절, 초기화를 눌러도
    # 화면에 남아 있던 녹음이 다시 처리되는 걸 막는 장치였는데, 이제 마이크에서
    # 그때그때 흘러오는 소리를 쓰므로 되돌아올 녹음 자체가 없습니다.

    ##### 사이드바 — 열쇠와 머리 #####
    with st.sidebar:
        st.subheader("🔑 열쇠")
        key_in = st.text_input(
            label="Gemini API 키",
            placeholder="열쇠를 붙여넣으세요",
            type="password",
            label_visibility="collapsed")

        # 키가 바뀌면 이전 확인 결과는 무효입니다.
        if key_in != st.session_state["GEMINI_API"]:
            st.session_state["GEMINI_API"] = key_in
            st.session_state["key_checked"] = None

        if st.button("열쇠 확인", use_container_width=True):
            with st.spinner("열쇠를 돌려보는 중..."):
                st.session_state["key_checked"] = check_apikey(key_in)

        checked = st.session_state["key_checked"]
        if checked is None:
            st.caption("무료 발급: aistudio.google.com/apikey")
        elif checked[0]:
            st.success(checked[1])
        else:
            st.error(checked[1])

        st.markdown("---")

        st.subheader("🧠 머리 고르기")
        brain_label = st.radio(
            label="답변에 쓸 모델",
            options=list(BRAINS.keys()),
            label_visibility="collapsed")
        model = BRAINS[brain_label]

        st.markdown("---")

        if st.button("🧹 싹 잊기", use_container_width=True):
            st.session_state["chat"] = []
            st.session_state["messages"] = []

    ##### 본문 #####
    st.markdown(
        f"<h1 style='margin-bottom:0'>🐱 {APP_NAME}</h1>"
        f"<p style='color:#8A8A8A;margin-top:4px'>{APP_TAGLINE}</p>",
        unsafe_allow_html=True)

    left, right = st.columns([1, 2.4], gap="large")

    with left:
        cat_slot = st.empty()
        show_cat(cat_slot, "sleep")
        # 녹음 버튼 대신 마이크를 열어둡니다.
        # SENDONLY = 브라우저가 서버로 소리를 보내기만 하고 받지는 않습니다.
        ctx = webrtc_streamer(
            key="listen",
            mode=WebRtcMode.SENDONLY,
            audio_receiver_size=1024,
            rtc_configuration=RTC_CONFIG,
            media_stream_constraints={"audio": True, "video": False},
        )
        st.caption("START 를 누르면 귀를 세웁니다. 그 뒤로는 그냥 말하면 됩니다.")

    with right:
        # 지금까지 오간 대화를 먼저 그려둡니다.
        if st.session_state["chat"]:
            for sender, stamp, message in st.session_state["chat"]:
                show_turn(sender, stamp, message)
        else:
            st.markdown(
                "<div style='text-align:center;color:#B0A99A;padding:40px 0;font-size:1.05rem'>"
                "아직 나눈 이야기가 없습니다.<br>왼쪽에서 <b>START</b> 를 누르고 말을 걸어보세요."
                "</div>", unsafe_allow_html=True)

    ##### 맨 아래 설명 #####
    def footer():
        st.markdown("---")
        with st.expander(f"{APP_NAME}에 대하여"):
            st.write(
                f"""
                - **{APP_NAME}** 는 「진짜 챗GPT API 활용법」 3장의 음성 비서를 바탕으로 만들었습니다.
                - UI 는 스트림릿(Streamlit)으로 만들었습니다.
                - 녹음 버튼이 없습니다. 마이크를 열어둔 채 **말이 끝나는 지점을 침묵으로 판단**합니다.
                - STT(Speech-To-Text)는 구글의 **Gemini** 를 활용하였습니다.
                - 답변은 구글의 **Gemini** 를 활용하였습니다.
                - TTS(Text-To-Speech)는 구글의 **Google Translate TTS** 를 활용하였습니다.
                - 고양이 그림은 저작권 문제가 없도록 SVG로 직접 그렸습니다.
                """
            )

    # 마이크가 아직 안 열렸으면 여기서 멈춥니다.
    if not ctx.state.playing:
        show_cat(cat_slot, "sleep", "START 를 눌러 주세요")
        footer()
        return

    # 키가 없거나 확인에 실패했으면 붙잡습니다.
    if not st.session_state["GEMINI_API"]:
        show_cat(cat_slot, "sleep", "열쇠가 필요해요")
        footer()
        return

    show_cat(cat_slot, "ready")
    footer()

    # 마이크가 열려 있는 동안 계속 듣고 답합니다.
    # 이 반복문 안에 머무르는 동안이 곧 "듣고 있는 상태"입니다.
    while True:
        audio = listen_once(ctx, cat_slot)
        if audio is None:
            # STOP 을 눌렀거나 연결이 끊겼습니다.
            show_cat(cat_slot, "sleep", "귀를 접었어요")
            break

        # 음원에서 텍스트 추출
        show_cat(cat_slot, "think", "받아적는 중")
        question = STT(audio, st.session_state["GEMINI_API"])
        if not question:
            # 받아쓸 말이 없었습니다. 잡음이었던 것으로 보고 넘어갑니다.
            show_cat(cat_slot, "ready")
            continue

        # 채팅을 시각화하기 위해 질문 내용 저장
        now = datetime.now().strftime("%H:%M")
        st.session_state["chat"].append(("user", now, question))
        # Gemini에 넣을 대화 기록을 위해 질문 내용 저장
        st.session_state["messages"].append({"role": "user", "text": question})
        with right:
            show_turn("user", now, question)

        # Gemini에게 답변 얻기
        show_cat(cat_slot, "think", "골똘히 생각 중")
        response = ask_gemini(st.session_state["messages"], model, st.session_state["GEMINI_API"])

        # 다음 질문에 대비해 답변 내용 저장 (Gemini에서 답변의 역할 이름은 "model" 입니다)
        st.session_state["messages"].append({"role": "model", "text": response})

        # 채팅 시각화를 위한 답변 내용 저장
        now = datetime.now().strftime("%H:%M")
        st.session_state["chat"].append(("bot", now, response))

        show_cat(cat_slot, "talk", "대답하는 중")
        with right:
            show_turn("bot", now, response)
            # gTTS를 활용하여 음성 파일 생성 및 재생
            spoken_ms = TTS(response)

        # 스피커로 나가는 답변을 마이크가 도로 주워듣지 않도록 그동안은 버립니다.
        drain(ctx, spoken_ms + 500)
        show_cat(cat_slot, "ready")


if __name__ == "__main__":
    main()
