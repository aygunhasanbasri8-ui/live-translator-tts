# Live Translator

English | [Türkçe](README.tr.md)

A desktop app that listens to the audio playing on your computer (YouTube, Zoom, games...)
and shows it as translated subtitles at the bottom of the screen. Optionally it also dubs
the translation out loud with Edge-TTS. It captures system audio, not the microphone, so it
only works on Windows (WASAPI loopback).

## Features

- Captures system audio through WASAPI loopback and splits speech into sentences at silences.
- Speech to text with Google Web Speech, translation with deep-translator; 19 languages are defined (`LANGUAGES` in `config.py`).
- Shows the translated subtitle in a transparent, click-through strip at the bottom of the screen, above everything else.
- "Streaming mode": the subtitle is updated roughly once a second while speech is still going on.
- Optional dubbing: the translation is spoken with Edge-TTS; capture is briefly muted during dubbing so the app does not listen to its own voice.
- Global hotkeys (`keyboard`, or `pynput` as a fallback).
- Silence threshold, end-of-sentence wait, font size, width and height can be changed while it runs.

## Installation

Python 3.10 or newer is required:

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev,shortcuts]"
```

`pygame` is optional (`.[audio]`); without it, dubbing is played through Windows MCI.
Hotkeys are bound with `keyboard` first and with `pynput` if that cannot be installed.

Recognition and translation use Google's free endpoints, so an internet connection is
required. If requests come too often, Google may temporarily answer "too many requests".

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

## How it works

1. `capture.py` takes system audio via WASAPI loopback and splits speech into sentences at
   silences.
2. `speech.py` turns each chunk into text with Google Web Speech and translates it into the
   target language with deep-translator.
3. `pipeline.py` processes the chunks in parallel but publishes the results in arrival order,
   so subtitles never appear out of order.
4. `overlay.py` shows the subtitle at the bottom of the screen, above everything else. When
   dubbing is on, `tts.py` speaks the translation.

The UI lives in `main_window.py`. Supported languages and voices are in the `LANGUAGES`
table in `config.py`; adding a language takes one line there.

## Project structure

```
live_translator/
├── app.py            entry point (QApplication, logging)
├── capture.py        WASAPI loopback capture, sentence splitting
├── speech.py         Google Web Speech (STT) and deep-translator (translation)
├── pipeline.py       parallel processing, in-order publishing
├── tts.py            dubbing with Edge-TTS
├── audio_player.py   playback through pygame or Windows MCI
├── audio_math.py     downmix to mono, resampling
├── overlay.py        subtitle strip
├── main_window.py    main window
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
python -m pytest
```

To check the real device, STT, translation and TTS chain:

```powershell
python selftest.py
```

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
(folder) and `dist\selftest.exe`.

## Privacy

Captured speech chunks are sent to Google's free speech recognition endpoint to be turned
into text, and the text is sent to Google Translate for translation. When dubbing is on, the
translated text goes through Edge-TTS to Microsoft's online speech service. Keep this in mind
when playing sensitive content.

## License

MIT. See [`LICENSE`](LICENSE).
