"""
Internationalization (i18n) support using gettext.
The software must support English (default) and French.
"""
import gettext
import os
from pathlib import Path

# Path to locale directory
LOCALE_DIR = Path(__file__).parent.parent / "locale"

# Supported languages
SUPPORTED_LANGUAGES = ["en", "fr"]
DEFAULT_LANGUAGE = "en"


def setup_i18n(language: str = None) -> gettext.GNUTranslations:
    """
    Setup internationalization for the application.
    
    Args:
        language: Language code ('en' or 'fr'). If None, uses system default.
        
    Returns:
        Translation object for the specified language.
    """
    if language is None:
        # Try to get language from environment
        language = os.environ.get("LANG", DEFAULT_LANGUAGE).split("_")[0]
    
    if language not in SUPPORTED_LANGUAGES:
        language = DEFAULT_LANGUAGE
    
    # Setup gettext
    try:
        translation = gettext.translation(
            "quoridor",
            localedir=str(LOCALE_DIR),
            languages=[language],
            fallback=True
        )
        translation.install()
        return translation
    except FileNotFoundError:
        # If translation files don't exist yet, use null translation
        gettext.install("quoridor")
        return gettext.NullTranslations()


# Initialize i18n with default language
_ = setup_i18n()

