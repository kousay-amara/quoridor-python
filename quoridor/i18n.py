"""Internationalization (i18n) support."""

from __future__ import annotations

import gettext
import os
import sys

# Supported languages
SUPPORTED_LANGUAGES = ["en", "fr"]
DEFAULT_LANGUAGE = "en"


class DictTranslations(gettext.NullTranslations):
    """Minimal dictionary-backed gettext translation object."""

    def __init__(self, messages: dict[str, str] | None = None) -> None:
        super().__init__()
        self._messages = messages or {}

    def gettext(self, message: str) -> str:  # noqa: D401 - gettext signature
        return self._messages.get(message, message)

    def ngettext(self, msgid1: str, msgid2: str, n: int) -> str:
        source = msgid1 if n == 1 else msgid2
        return self._messages.get(source, source)


FR_MESSAGES: dict[str, str] = {
    # Common parser/runtime messages
    "error": "erreur",
    "Invalid command.": "Commande invalide.",
    "Bye.": "Au revoir.",
    # Interactive shell startup
    "Loading game from {path}": "Chargement de la partie depuis {path}",
    "Game loaded with blitz timer state.": (
        "Partie chargee avec l'etat du chrono blitz."
    ),
    "New game started (blitz: {minutes} min/player).": (
        "Nouvelle partie demarree (blitz : {minutes} min/joueur)."
    ),
    "New game started with default options.": (
        "Nouvelle partie demarree avec les options par defaut."
    ),
    "warning: 3-player mode can be unbalanced.": (
        "warning: le mode 3 joueurs peut etre desequilibre."
    ),
    "Type 'help' for available commands.": (
        "Tapez 'help' pour afficher les commandes disponibles."
    ),
    "Game loaded from {path}": "Partie chargee depuis {path}",
    "Game saved to {path}": "Partie sauvegardee vers {path}",
    # CLI help strings (optional but useful)
    "Quoridor game command-line interface.": (
        "Interface en ligne de commande de Quoridor."
    ),
    "path to a saved game file": "chemin vers un fichier de sauvegarde",
    "show program version and exit": ("afficher la version du programme puis quitter"),
    "increase program verbosity": "augmenter la verbosite du programme",
    "show debug messages": "afficher les messages de debug",
    "run in headless mode (requires --server)": (
        "lancer en mode sans interface (necessite --server)"
    ),
    "launch the GTK GUI": "lancer l'interface graphique GTK",
    "enable blitz mode": "activer le mode blitz",
    "enable contest mode (read position file and output a move)": (
        "activer le mode concours (lit une position et affiche un coup)"
    ),
    "time limit in minutes for blitz mode": (
        "limite de temps en minutes pour le mode blitz"
    ),
    "number of players ({values})": "nombre de joueurs ({values})",
    "walls per player (negative means unlimited)": (
        "murs par joueur (negatif = illimite)"
    ),
    "board size (odd number between {min} and {max})": (
        "taille du plateau (impaire entre {min} et {max})"
    ),
    "start local server immediately (optional port)": (
        "demarrer un serveur local immediatement (port optionnel)"
    ),
    "Replace a player by an AI (Color, ID or 'A' for all)": (
        "Remplacer un joueur par une IA (couleur, ID ou 'A' pour tous)"
    ),
    "AI mode": "mode IA",
    "AI thinking time in seconds (iterative, mcts)": (
        "temps de reflexion IA en secondes (iterative, mcts)"
    ),
    "minimax depth (fixed for minimax, max for iterative)": (
        "profondeur minimax (fixe pour minimax, max pour iterative)"
    ),
    "AI scoring type (1: Default, 2: Material, 3: Hybrid)": (
        "type de score IA (1: Defaut, 2: Materiel, 3: Hybride)"
    ),
    "MCTS selection policy (UCT or ML)": ("politique de selection MCTS (UCT ou ML)"),
}


def _messages_for_language(language: str) -> dict[str, str]:
    if language == "fr":
        return FR_MESSAGES
    return {}


def runtime_gettext(message: str) -> str:
    """Translate a runtime message from current env without side effects."""
    language = _detect_environment_language()
    if language not in SUPPORTED_LANGUAGES:
        language = DEFAULT_LANGUAGE
    return _messages_for_language(language).get(message, message)


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
        language: Language code (currently 'en'). If None, uses system default.

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

    messages = _messages_for_language(language)
    translation = DictTranslations(messages)
    translation.install()
    return translation


# Note: call setup_i18n() explicitly from application entry points.
