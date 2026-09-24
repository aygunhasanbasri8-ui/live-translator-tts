# -*- coding: utf-8 -*-
"""
Donmuş (.exe) ortamda tüm yığını sınayan konsol testi.
Sadece geliştirme amaçlıdır; dağıtılan uygulamanın parçası değildir.

Derlemek için:  .venv\\Scripts\\python.exe -m PyInstaller --noconfirm selftest.spec
"""
import os
import sys
import time
import queue
import asyncio
import threading

import live_translator as LT

OK, FAIL = "  [OK]  ", "  [HATA]"
results = []


def check(name, fn):
    try:
        detail = fn()
        print(f"{OK} {name}: {detail}")
        results.append(True)
    except Exception as exc:
        print(f"{FAIL} {name}: {type(exc).__name__}: {exc}")
        results.append(False)


print(f"donmuş mu: {getattr(sys, 'frozen', False)}  |  kök: {getattr(sys, '_MEIPASS', '-')}")
print("=" * 64)

# 1) PortAudio + WASAPI loopback cihazı
state = {}


def t_device():
    import pyaudiowpatch as pyaudio
    pa = pyaudio.PyAudio()
    cap = LT.LoopbackAudioCapturer(LT.AppConfig(), queue.Queue(), threading.Event())
    dev = cap._resolve_loopback_device(pa)
    stream, fmt, rate, ch = cap._open_stream(pa, dev)
    stream.stop_stream(); stream.close(); pa.terminate()
    state["rate"] = rate
    return f"{dev['name']} @ {rate} Hz / {ch} kanal"


check("PortAudio + loopback cihazı", t_device)

# 2) Edge-TTS sentezi
mp3 = os.path.join(os.environ.get("TEMP", "."), "selftest_tts.mp3")


def t_edge():
    loop = asyncio.new_event_loop(); asyncio.set_event_loop(loop)
    loop.run_until_complete(
        LT.edge_tts.Communicate("hello everyone", "en-US-AriaNeural").save(mp3))
    loop.close()
    return f"{os.path.getsize(mp3)} bayt üretildi"


check("Edge-TTS sentezi", t_edge)

# 3) Çeviri
check("deep-translator", lambda: repr(LT.TranslatorService().translate("good morning", "en", "tr")))

# 4) UÇTAN UCA: çal -> loopback yakala -> STT (flac) -> çeviri
def t_pipeline():
    cfg = LT.AppConfig()
    q: "queue.Queue[LT.AudioSegment]" = queue.Queue(maxsize=16)
    cap = LT.LoopbackAudioCapturer(cfg, q, threading.Event())
    cap.start()
    time.sleep(1.2)
    player = LT.create_audio_player()
    threading.Thread(target=player.play_blocking, args=(mp3,), daemon=True).start()

    seg = None
    deadline = time.time() + 15
    while time.time() < deadline:
        try:
            seg = q.get(timeout=0.5)
            if seg.is_final:
                break
        except queue.Empty:
            pass
    cap.stop(); cap.wait(5000)
    if seg is None:
        raise RuntimeError("loopback'ten hiç ses segmenti yakalanamadı")

    text = LT.SpeechToTextService().transcribe(seg, "en-US")   # flac-win32.exe burada gerekli
    if not text:
        raise RuntimeError("STT ses yakaladı ama metin döndürmedi")
    tr = LT.TranslatorService().translate(text, "en", "tr")
    return f"{seg.duration:.1f} sn ses -> {text!r} -> {tr!r}"


check("UÇTAN UCA (yakala+STT+çeviri)", t_pipeline)

try:
    os.remove(mp3)
except OSError:
    pass

print("=" * 64)
print(f"SONUÇ: {sum(results)}/{len(results)} geçti")
print("Kapatmak için Enter'a basın...")
try:
    input()
except EOFError:
    pass
sys.exit(0 if all(results) else 1)
