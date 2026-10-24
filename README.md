# Live Translator

English | [Türkçe](README.tr.md)

A desktop app that listens to the audio playing on your computer (YouTube, Zoom, games...)
and shows it as translated subtitles at the bottom of the screen. Optionally it also dubs
the translation out loud with Edge-TTS. It captures system audio, not the microphone, so it
only works on Windows (WASAPI loopback).

## Features

- Captures system audio through WASAPI loopback and splits speech into sentences at silences.
- Speech to text with Google Web Speech or, if installed, local Whisper; 37 languages are defined (`LANGUAGES` in `config.py`).
- Translation tries three services in order (Google, Google web, MyMemory); when one rate-limits, the app backs off and moves to the next.
- Shows the translated subtitle in a transparent, click-through strip at the bottom of the screen, above everything else; color, size, width, height and opacity are adjustable, and on a multi-monitor setup you can pick the screen.
- "Streaming mode": the subtitle is updated roughly once a second while speech is still going on.
- Optional dubbing: the translation is spoken with Edge-TTS; it speeds up when it falls behind and switches to a backup voice if one is broken.
- Tray icon, global hotkeys, and capture that re-attaches itself when the audio output changes.
- Saving the subtitle transcript as SRT or plain text.
- Settings are kept between sessions.

## Installation

Python 3.10 or newer is required:

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev,shortcuts]"
```

`pygame` is optional (`.[audio]`); without it, dubbing is played through Windows MCI.
Hotkeys are bound with `keyboard` first and with `pynput` if that cannot be installed.

Recognition and translation use Google's free endpoints by default, so an internet
connection is required. If requests come too often, Google may temporarily answer "too
many requests"; in that case the app stops going to that service for a while (starting at
2 seconds and at most 1 minute) and switches to a backup:

- Translation comes first from the endpoint the Google Translate web page uses, and if that
  rate-limits, from the mobile page that deep-translator uses; the two are rate-limited
  separately. When both are limited, the backup is MyMemory. Its keyless daily quota is
  narrow, so it is only used for finalized sentences, not for partial results.
- For recognition the backup is local Whisper, if installed:

  ```powershell
  python -m pip install -e ".[whisper]"
  ```

  Whisper can also be selected directly in the UI; it then works without internet. When it
  is installed, "Auto-detect" also appears at the top of the source language list: Whisper
  finds the language for every sentence, so there is no need to change the source language
  for mixed-language content. The model (tiny/base/small) is downloaded once on first use
  and runs on CPU with int8. It is not bundled in the exe, it is only available when
  running from source. When installed, the Silero VAD that ships with it is used too: chunks
  that contain no speech (music, noise) are never sent to recognition, which reduces the
  requests going to Google and the chance of being rate-limited.

While running, the service in use and the ones on hold are shown on the right of the status
bar (e.g. `Çeviri: Google web (Google 16 sn ara)`; the label text is in Turkish).

## Usage

```powershell
python -m live_translator
```

| Hotkey       |                        |
|--------------|------------------------|
| Ctrl+Shift+R | Start                  |
| Ctrl+Shift+S | Stop                   |
| Ctrl+Shift+H | Hide/show the subtitle |

In the window you pick the source/target language, the mode (subtitles only, or subtitles
plus dubbing), the voice and the speech rate. With "Streaming mode" on, the subtitle is
updated about once a second while speech continues; with it off, the subtitle only appears
when the sentence ends, which sends fewer requests.

In dubbing, the translation often takes longer to speak than the original. While sentences
wait in the queue, the speech rate goes up 10% per waiting sentence (at most +50%); even so,
a sentence that falls more than 12 seconds behind is skipped without being read, since its
subtitle has already been seen. If the selected voice produces no audio on the Edge side,
the app switches to another voice of the same language.

On a multi-monitor setup, the screen the subtitle appears on is chosen in the "Altyazı
görünümü" (subtitle appearance) tab; if that screen is unplugged, it falls back to the
primary screen. If "Önceki cümleyi de göster" (show the previous sentence) is turned on in
the same tab, the translation of the previous sentence stays on top in a faded color, which
makes it easier to keep up with fast speech.

When the window is minimized it goes to the tray; start/stop, hiding the subtitle and quit
are available from the tray menu. When the audio output changes (plugging in headphones,
changing the default device) or the device is removed, listening switches to the new
device by itself within a few seconds.

Finalized sentences accumulate in a transcript; with "Altyazıları kaydet..." (save
subtitles) the translation, the original or a bilingual version can be saved as SRT or
plain text. Times are relative to the first sentence, so they line up roughly when you
watch the video from the start.

Settings (languages, mode, voice, sensitivity, subtitle size/color/position/opacity,
window position) are saved on exit and on every Start and come back as they were on the
next launch. On Windows they live in the registry under `HKCU\Software\LiveTranslator`;
if deleted, the defaults return.

The log is also written to `%LOCALAPPDATA%\LiveTranslator\live_translator.log` (the
windowed exe has no console, so this is where to look when troubleshooting). An unexpected
error does not close the app, it lands in this file.

## How it works

1. `capture.py` takes system audio via WASAPI loopback and splits speech into sentences at
   silences. Speech that runs past 6 seconds without a pause is split not mid-word but at
   the quietest moment of the last 1.5 seconds.
2. `speech.py` turns each chunk into text with Google Web Speech (or `whisper_stt.py`) and
   translates it into the target language with Google/MyMemory. When each provider is
   skipped is decided in `providers.py`.
3. `pipeline.py` processes the chunks in parallel but publishes the results in arrival
   order, so subtitles never appear out of order. Partial results that have been overtaken
   by a newer one are skipped, and one worker is always reserved for finalized sentences;
   even when the network is slow, the end-of-sentence subtitle does not wait.
4. `overlay.py` shows the subtitle at the bottom of the screen, above everything else. When
   dubbing is on, `tts.py` speaks the translation.

The UI lives in `main_window.py`. Supported languages and voices are in the `LANGUAGES`
table in `config.py`; adding a language takes one line there.

## Project structure

```
live_translator/
├── app.py            entry point (QApplication, logging)
├── capture.py        WASAPI loopback capture, sentence splitting, device changes
├── speech.py         Google Web Speech (STT) and the translation services
├── whisper_stt.py    optional local recognition (faster-whisper, Silero VAD)
├── providers.py      provider order and back-off (cooldown)
├── pipeline.py       parallel processing, in-order publishing
├── tts.py            dubbing with Edge-TTS
├── audio_player.py   playback through pygame or Windows MCI
├── audio_math.py     downmix to mono, resampling
├── overlay.py        subtitle strip
├── main_window.py    main window
├── tray.py           tray icon
├── settings.py       persistent settings
├── transcript.py     subtitle transcript, SRT/text export
├── hotkeys.py        global hotkeys
├── config.py         AppConfig and the LANGUAGES table
└── queues.py         queue helpers
tests/                tests that need no hardware or network
selftest.py           end-to-end check with the real device and services
pyinstaller_ortak.py  shared settings of the PyInstaller specs
```

## Testing

Tests that need no hardware or network:

```powershell
pip install -e ".[dev]"
python -m pytest
ruff check .
```

The tests also run outside Windows: PyAudioWPatch only ships Windows wheels, so
`tests/conftest.py` puts a small stand-in module in its place when it is missing, and tests
marked `windows_audio` are skipped there. Importing the package no longer exits when a
dependency is missing; the check runs when the app starts.

To check the real device, STT, translation and TTS chain:

```powershell
python selftest.py            # --no-wait: do not wait for Enter at the end
```

`python -m live_translator --smoke` (or `CanliCevirmen.exe --smoke`) builds the main window,
closes it after a second and exits with 0; it is a quick check that a build really starts.

There is currently no CI workflow in the repo.

## Building an exe

```powershell
python -m PyInstaller --noconfirm live_translator.spec          # single file
python -m PyInstaller --noconfirm live_translator_klasor.spec   # as a folder, starts faster
python -m PyInstaller --noconfirm selftest.spec                 # console self-test
```

The three specs share their settings in `pyinstaller_ortak.py`. `selftest` is not part of
the distributed app; inside the exe it checks the audio capture, TTS and translation chain
and prints the result to the console.

Outputs: `dist\CanliCevirmen.exe` (single file), `dist\CanliCevirmen_klasor\CanliCevirmen.exe`
(folder) and `dist\selftest.exe`. Local Whisper is not included in the exe because of its size.
The version lives in `live_translator/_version.py` and is shown in the window title.

## Privacy

With the default settings, captured speech chunks are sent to Google's free speech
recognition endpoint to be turned into text, and the text is sent to Google's translation
endpoints (or to MyMemory when Google rate-limits). When dubbing is on, the translated text
goes through Edge-TTS to Microsoft's online speech service. If local Whisper is selected,
the audio does not leave the machine; only text goes to the translation services. Keep this
in mind when playing sensitive content.

## License

MIT. See [`LICENSE`](LICENSE).
