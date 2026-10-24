from live_translator.providers import Provider
from live_translator.speech import TranslatorService
from live_translator.translation_cache import LruCache


def test_lru_evicts_least_recently_used_not_oldest():
    cache = LruCache(2)
    cache.put(("a",), "A")
    cache.put(("b",), "B")
    assert cache.get(("a",)) == "A"  # "a" yeniden kullanıldı, sıradaki kurban "b"
    cache.put(("c",), "C")

    assert cache.get(("a",)) == "A"
    assert cache.get(("b",)) is None
    assert cache.get(("c",)) == "C"


def _service(answers):
    calls = []

    def fake(text, source, target):
        calls.append(text)
        return answers.pop(0)

    service = TranslatorService()
    service._providers = (Provider("sahte", fake),)
    return service, calls


def test_empty_translation_is_not_cached():
    service, calls = _service(["", "Merhaba dünya"])

    assert service.translate("Hello world", "en", "tr") == "Hello world"
    assert service.translate("Hello  world ", "en", "tr") == "Merhaba dünya"
    assert service.translate("Hello world", "en", "tr") == "Merhaba dünya"
    assert len(calls) == 2


def test_partials_do_not_push_finals_out():
    service, calls = _service(["Evet"] + ["kısmi"] * 100)
    service.translate("Yes.", "en", "tr", is_final=True)
    for i in range(100):
        service.translate(f"partial {i}", "en", "tr", is_final=False)

    assert service.translate("Yes.", "en", "tr", is_final=True) == "Evet"
    assert calls.count("Yes.") == 1
