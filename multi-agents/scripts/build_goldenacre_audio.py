"""Pre-generate the Insights page's spoken clips so the live app never runs the
TTS model at request time.

Why this exists: Kokoro generation measured at roughly 30 SECONDS per insight,
and it is flat across text length rather than proportional to it, so neither
shortening the copy nor raising the speech rate buys the wait back (see the
benchmark in kokoro_voice.DEFAULT_SPEED's comment). The only fix that actually
removes the wait is not running the model on click. This writes the clips ahead
of time; the app serves them instantly and falls back to live synthesis only for
text it has no clip for.

Clips are named by a hash of the exact speech text (plus voice and speed), so a
clip physically cannot be played against numbers it wasn't generated from. If a
data refresh moves a figure by one decimal place, the hash misses, the app falls
back to live synthesis, and nobody hears a stale number read aloud as fact.

Run this after build_goldenacre_hc.py / build_goldenacre_insights_data.py, i.e.
whenever the underlying data has moved:

    SSLKEYLOGFILE= python multi-agents/scripts/build_goldenacre_audio.py

Then commit whatever lands in assets/audio/.
"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import goldenacre_analytics_engine as engine  # noqa: E402
import kokoro_voice  # noqa: E402


def main():
    kokoro_voice.CLIP_DIR.mkdir(parents=True, exist_ok=True)

    conn = engine.connection()
    try:
        kpis = engine.load_kpis(conn)
        manufacturer_view = engine.load_manufacturer_view(conn)
    finally:
        conn.close()

    cards = engine.build_insight_texts(kpis, manufacturer_view)
    print(f"{len(cards)} insight cards\n")

    expected = set()
    total_bytes = 0
    for key, html in cards:
        speech = kokoro_voice.to_speech(html)
        path = kokoro_voice.clip_path(speech)
        expected.add(path.name)
        if path.exists():
            total_bytes += path.stat().st_size
            print(f"  {key:16} already current -> {path.name}")
            continue
        samples, sample_rate = kokoro_voice.synthesize(speech)
        wav = kokoro_voice.to_wav_bytes(samples, sample_rate)
        path.write_bytes(wav)
        total_bytes += len(wav)
        print(f"  {key:16} generated {len(samples)/sample_rate:5.1f}s -> {path.name} ({len(wav)/1e3:.0f}KB)")

    # Clips for text that no longer exists are dead weight in the repo. They are
    # pure build output and fully regenerable, so removing them is safe - but
    # name each one rather than deleting silently.
    stale = [p for p in kokoro_voice.CLIP_DIR.glob("*.wav") if p.name not in expected]
    for p in stale:
        print(f"  removing stale clip {p.name} ({p.stat().st_size/1e3:.0f}KB)")
        p.unlink()

    print(f"\n{len(expected)} clips, {total_bytes/1e6:.1f}MB total in {kokoro_voice.CLIP_DIR.relative_to(REPO_ROOT)}")
    print("Commit assets/audio/ for the deployed app to serve these instantly.")


if __name__ == "__main__":
    main()
