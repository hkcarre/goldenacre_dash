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
import re
import urllib.request
from pathlib import Path

import streamlit as st
from kokoro_onnx import Kokoro

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
    model_path, voices_path = _ensure_model_files()
    return Kokoro(str(model_path), str(voices_path))


@st.cache_data(show_spinner="Generating audio...")
def synthesize(text, voice=DEFAULT_VOICE, speed=1.0, lang=DEFAULT_LANG):
    """Returns (samples: np.ndarray, sample_rate: int). Cached by the exact
    (text, voice, speed, lang) tuple, so re-rendering the same insight on a
    Streamlit rerun never re-runs the model - only a genuinely new/changed
    insight (e.g. after a data refresh) pays the generation cost again."""
    kokoro = _load_kokoro()
    return kokoro.create(text, voice=voice, speed=speed, lang=lang)


def strip_html(html_text):
    """Insight cards are built as HTML (<strong> tags for emphasis) - strip
    tags for natural speech. Currency/percent symbols are left as-is and fed
    to Kokoro's phonemizer as-is - this was verified to run without error and
    produce audio of a sane duration, but nobody has actually listened to
    confirm £/% come out sounding natural; flag it if a generated clip reads
    those oddly."""
    return re.sub(r"<[^>]+>", "", html_text)
