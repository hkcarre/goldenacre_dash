"""Local, open-source text-to-speech via Kokoro (the kokoro-onnx package) - no
cloud API, no per-request cost, runs entirely in-process on CPU.

Model weights are NOT committed to the repo - at ~92MB (int8-quantized model)
+ 28MB (voices), that would roughly double every clone's size for a binary
asset git handles poorly. Downloaded once into a local cache directory on
first use and reused after that (see _ensure_model_files below).

Deliberately uses the int8-quantized model, not the full fp32 one (325MB) or
fp16 (177MB) - this app is deployed to Streamlit Community Cloud (see
README's "Deploying to Streamlit Community Cloud" section), whose free tier
has tight disk/RAM limits, so the smaller download is a real constraint here,
not just a nice-to-have. espeakng-loader (a kokoro-onnx dependency) ships its
phonemization data as pure Python/data files, so no system package
(apt-get espeak-ng) is needed either - confirmed by a real end-to-end test
(load + synthesize + write a valid WAV) before this was wired into the app,
not assumed from the package description.
"""
import hashlib
import io
import re
import urllib.request
import wave
from pathlib import Path

import numpy as np
import streamlit as st

# kokoro_onnx is imported lazily inside _load_kokoro(), NOT here. A clip that was
# pre-generated and committed can be served with nothing but the standard library,
# so a deploy that only ever plays pre-generated audio does not need the package
# installed at all. Importing at module scope would have made the whole module
# unimportable without it and thrown that away.

# Pre-generated clips, committed to the repo. Named by a hash of the exact speech
# text, so a clip can never be played against numbers it wasn't generated from -
# if the data refresh changes an insight by even one digit, the hash misses and
# the app falls back to live synthesis rather than reading a stale figure aloud.
CLIP_DIR = Path(__file__).resolve().parent / "assets" / "audio"

_MODEL_RELEASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"
_MODEL_FILE = "kokoro-v1.0.int8.onnx"
_VOICES_FILE = "voices-v1.0.bin"
_CACHE_DIR = Path.home() / ".cache" / "kokoro"

# British female - matches Golden Acre/Optia's UK audience. Swap this one
# constant to change voice for every caller; other British options confirmed
# available in this model: bf_alice, bf_isabella, bf_lily (female),
# bm_daniel, bm_fable, bm_george, bm_lewis (male).
DEFAULT_VOICE = "bf_emma"
DEFAULT_LANG = "en-gb"

# Slightly faster than natural - a listening-pace choice only: it reads as more
# confident and less plodding for short analytic statements. Past about 1.25 the
# British voices start clipping consonants.
#
# It does NOT make generation quicker. Measured on this text: 29.9s to produce a
# 16.6s clip, 30.6s for an 18.2s clip, 30.9s at speed 1.1 - i.e. cost is roughly
# FLAT across these lengths, not proportional to duration, so neither shortening
# the text nor raising the speed buys back the wait. Anything that actually fixes
# the latency has to avoid running the model at request time at all.
DEFAULT_SPEED = 1.1

# Dashboard prose is written to be READ, and is full of shorthand that a
# phonemizer voices literally: "MAT" becomes the word "mat", "YA" becomes "ya",
# "£2.52bn" gets spelled out, and a spaced hyphen is read as the word "dash".
# These rewrite the text for the ear only - the on-screen card is untouched.
# Order matters: longest/most specific patterns first, since several of these
# would otherwise partially match each other.
_SPEECH_SUBS = [
    # "3.6% MAT vs. MAT YA" - the whole idiom reads far better as one phrase
    # than as two independent expansions of MAT.
    (r"\bMAT\s+vs\.?\s+MAT\s+YA\b", "moving annual total versus the same period a year ago"),
    (r"\bMAT\s+YA\b", "the same period a year ago"),
    (r"\bMAT\b", "moving annual total"),
    # Currency with a magnitude suffix, before the bare-currency rule below.
    # Case-insensitive suffixes deliberately: the codebase writes both "£15.2M"
    # and "£2.52bn". A lowercase-only rule let the bare-currency rule below fire
    # first and produced "15.2 poundsM".
    (r"£\s*([\d,]+(?:\.\d+)?)\s*[bB][nN]\b", r"\1 billion pounds"),
    (r"£\s*([\d,]+(?:\.\d+)?)\s*[mM]\b", r"\1 million pounds"),
    (r"£\s*([\d,]+(?:\.\d+)?)\s*[kK]\b", r"\1 thousand pounds"),
    (r"£\s*([\d,]+(?:\.\d+)?)", r"\1 pounds"),
    (r"\b([\d.]+)\s*[bB][nN]\b", r"\1 billion"),
    (r"\b([\d.]+)\s*pp\b", r"\1 percentage points"),
    (r"\bYoY\b", "year on year"),
    (r"\bvs\.?(?=\s)", "versus"),
    (r"#(\d+)", r"number \1"),
    # "rose +0.42pp" - the verb already carries direction, so voicing the sign
    # as "plus" is redundant and reads oddly.
    (r"(?<=\s)\+(?=[\d.])", ""),
    (r"(\w)/(\w)", r"\1 \2"),          # "price/mix" - a slash is read aloud otherwise
    (r"\s+-\s+", ", "),                # spaced hyphen: a pause, not the word "dash"
    (r"£", " pounds "),                # any stray symbol the rules above missed
    (r"\s{2,}", " "),
]


def _ensure_model_files():
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    for fname in (_MODEL_FILE, _VOICES_FILE):
        path = _CACHE_DIR / fname
        if not path.exists():
            tmp = path.with_suffix(path.suffix + ".part")
            urllib.request.urlretrieve(f"{_MODEL_RELEASE}/{fname}", tmp)
            tmp.rename(path)  # atomic-ish: never leave a half-downloaded file at the real path
    return _CACHE_DIR / _MODEL_FILE, _CACHE_DIR / _VOICES_FILE


@st.cache_resource(show_spinner="Loading voice model (first run only, ~120MB download)...")
def _load_kokoro():
    from kokoro_onnx import Kokoro  # lazy - see the note at the top of this file
    model_path, voices_path = _ensure_model_files()
    return Kokoro(str(model_path), str(voices_path))


@st.cache_data(show_spinner="Generating audio...")
def synthesize(text, voice=DEFAULT_VOICE, speed=DEFAULT_SPEED, lang=DEFAULT_LANG):
    """Returns (samples: np.ndarray, sample_rate: int). Cached by the exact
    (text, voice, speed, lang) tuple, so re-rendering the same insight on a
    Streamlit rerun never re-runs the model - only a genuinely new/changed
    insight (e.g. after a data refresh) pays the generation cost again."""
    kokoro = _load_kokoro()
    return kokoro.create(text, voice=voice, speed=speed, lang=lang)


def strip_html(html_text):
    """Insight cards are built as HTML (<strong> tags for emphasis) - strip
    tags. Does NOT make the text speakable on its own; use to_speech()."""
    return re.sub(r"<[^>]+>", "", html_text)


def to_speech(html_text):
    """HTML insight card -> text meant for the ear rather than the eye.

    Strips tags, then expands the dashboard shorthand in _SPEECH_SUBS. Without
    this the voice says "mat versus mat ya" and spells out "bn", which is what
    the first deployed version actually did. The visible card is never changed
    by this - only what gets fed to the model."""
    text = strip_html(html_text)
    for pattern, replacement in _SPEECH_SUBS:
        text = re.sub(pattern, replacement, text)
    return text.strip()


# --------------------------------------------------------------------------
# Pre-generated clips
# --------------------------------------------------------------------------
def speech_key(speech_text, voice=DEFAULT_VOICE, speed=DEFAULT_SPEED):
    """Filename key for a clip. Covers voice and speed as well as the text, so
    changing the voice doesn't silently keep serving clips in the old one."""
    payload = f"{voice}|{speed}|{speech_text}".encode("utf-8")
    return hashlib.sha1(payload).hexdigest()[:16]


def clip_path(speech_text, voice=DEFAULT_VOICE, speed=DEFAULT_SPEED):
    return CLIP_DIR / f"{speech_key(speech_text, voice, speed)}.wav"


def to_wav_bytes(samples, sample_rate):
    """float32 samples in [-1, 1] -> 16-bit mono PCM WAV. Standard library only:
    soundfile would drag in a libsndfile system dependency for this alone."""
    pcm = np.clip(np.asarray(samples, dtype=np.float32), -1.0, 1.0)
    pcm = (pcm * 32767.0).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(int(sample_rate))
        w.writeframes(pcm.tobytes())
    return buf.getvalue()


def has_clip(speech_text, voice=DEFAULT_VOICE, speed=DEFAULT_SPEED):
    return clip_path(speech_text, voice, speed).exists()


def can_speak(speech_text):
    """True if this text can be voiced at all - either a committed clip exists,
    or the model is installed and can generate one live."""
    if has_clip(speech_text):
        return True
    try:
        import kokoro_onnx  # noqa: F401
        return True
    except ImportError:
        return False


@st.cache_data(show_spinner="Generating audio (first time only)...")
def audio_wav(speech_text, voice=DEFAULT_VOICE, speed=DEFAULT_SPEED, lang=DEFAULT_LANG):
    """WAV bytes for already-speech-ready text. The one entry point the app uses.

    Serves a committed clip instantly when the text matches one; otherwise runs
    the model, which costs roughly 30s per insight on a free-tier vCPU. That gap
    is the entire reason pre-generated clips exist - see
    multi-agents/scripts/build_goldenacre_audio.py, which writes them."""
    path = clip_path(speech_text, voice, speed)
    if path.exists():
        return path.read_bytes()
    samples, sample_rate = synthesize(speech_text, voice=voice, speed=speed, lang=lang)
    return to_wav_bytes(samples, sample_rate)
