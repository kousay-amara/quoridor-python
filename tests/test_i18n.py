import gettext

from quoridor import i18n


def test_detect_language_prefers_lc_all_over_lang(monkeypatch):
    monkeypatch.setenv("LC_ALL", "fr_FR.UTF-8")
    monkeypatch.setenv("LANG", "en_US.UTF-8")

    lang = i18n._detect_environment_language()

    assert lang == "fr"


def test_detect_language_falls_back_to_lang(monkeypatch):
    monkeypatch.delenv("LC_ALL", raising=False)
    monkeypatch.setenv("LANG", "fr_CA.UTF-8")

    lang = i18n._detect_environment_language()

    assert lang == "fr"


def test_setup_i18n_warns_and_falls_back_for_unsupported_language(capsys):
    translation = i18n.setup_i18n("es_ES.UTF-8")
    captured = capsys.readouterr()

    assert isinstance(translation, gettext.NullTranslations)
    assert "warning: unsupported language 'es'" in captured.err


def test_setup_i18n_accepts_supported_language_without_warning(capsys):
    translation = i18n.setup_i18n("fr_FR.UTF-8")
    captured = capsys.readouterr()

    assert isinstance(translation, gettext.NullTranslations)
    assert captured.err == ""
