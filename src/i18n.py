"""
Internationalization (i18n) support using gettext.
The software must support English (default) and French.
"""
import gettext
import os
import sys
from pathlib import Path

# Path to locale directory
LOCALE_DIR = Path(__file__).parent.parent / "locale"

# Supported languages
SUPPORTED_LANGUAGES = ["en", "fr"]
DEFAULT_LANGUAGE = "en"


def _normalize_language(raw_language: str | None) -> str:
    """Normalize locale values such as 'fr_FR.UTF-8' to 'fr'."""
    if not raw_language:
        return DEFAULT_LANGUAGE
    normalized = raw_language.split(".")[0].split("@")[0].split("_")[0]
    return normalized or DEFAULT_LANGUAGE


def _detect_environment_language() -> str:
    """Detect language from environment using LC_ALL first, then LANG."""
    return _normalize_language(
        os.environ.get("LC_ALL") or os.environ.get("LANG") or DEFAULT_LANGUAGE
    )


def setup_i18n(language: str | None = None) -> gettext.NullTranslations:
    """
    Setup internationalization for the application.
    
    Args:
        language: Language code ('en' or 'fr'). If None, uses system default.
        
    Returns:
        Translation object for the specified language.
    """
    if language is None:
        language = _detect_environment_language()
    else:
        language = _normalize_language(language)

    if language not in SUPPORTED_LANGUAGES:
        sys.stderr.write(
            "warning: unsupported language "
            f"'{language}', falling back to '{DEFAULT_LANGUAGE}'\n"
        )
        language = DEFAULT_LANGUAGE

    # Setup gettext. fallback=True avoids crashing when translation files are missing.
    translation = gettext.translation(
        "quoridor",
        localedir=str(LOCALE_DIR),
        languages=[language],
        fallback=True,
    )
    translation.install()
    return translation


# Initialize i18n with default language
_ = setup_i18n()
