# Quoridor

Implémentation en Python du jeu de plateau **Quoridor**, avec une interface en ligne de commande interactive, un mode « concours » (lecture d'une position et calcul d'un coup), une interface graphique GTK optionnelle et un mode multijoueur en réseau local. Projet universitaire réalisé entre janvier et avril 2026 dans le cadre du cursus informatique de l'**Université de Bordeaux**, par une équipe de 6 étudiants.

## Fonctionnalités

- Moteur de règles complet (déplacements, murs, pathfinding, conditions de victoire), 2 à 4 joueurs
- Interface en ligne de commande interactive (shell avec historique, auto-complétion, aide intégrée)
- Mode « concours » : lecture d'une position depuis un fichier, calcul et affichage d'un coup
- Interface graphique optionnelle (GTK)
- Mode réseau multijoueur : serveur TCP concurrent, découverte automatique des serveurs sur le réseau local (UDP broadcast), système d'invitations/salons de jeu, tableau des scores
- Intelligence artificielle configurable (Minimax, Monte Carlo Tree Search avec sélection assistée par un modèle scikit-learn)
- Mode blitz (chronomètre par joueur)
- Sauvegarde/chargement de parties

## Technologies

- **Langage** : Python ≥ 3.10
- **Dépendances runtime** : `joblib`, `pandas`, `scikit-learn` (IA), `PyGObject` (GUI GTK, optionnelle)
- **Tests** : `pytest`, `pytest-cov`
- **Qualité** : `black`, `flake8`, `mypy`, `pylint`
- **Documentation** : Sphinx (`docs/`)
- **Build** : `setuptools` (`pyproject.toml`)
- **CI** : GitHub Actions (tests automatiques à chaque push, voir `.github/workflows/`)

## Installation

Un environnement virtuel est recommandé.

```bash
python -m venv venv
source venv/bin/activate
pip install -e ".[dev]"
```

Pour l'interface graphique (optionnel, nécessite GTK installé au niveau système) :

```bash
pip install -e ".[gui]"
```

## Lancement

```bash
quoridor                      # mode interactif
quoridor -c chemin/vers/fichier.txt   # mode concours
quoridor -V                   # affiche la version
python -m quoridor.interfaces.gui     # interface graphique GTK
```

## Tests

```bash
pytest
```

Sans mesure de couverture :

```bash
pytest -q -p no:cov -o addopts= tests
```

**Résultat mesuré sur cette version** : 268 tests, 265 passent, couverture de code à **85 %** (seuil minimum de 85 % configuré dans `pyproject.toml`).

### Limites connues

3 tests dans `tests/test_gui.py` échouent actuellement (`test_apply_game_config_updates_runtime_and_restarts`, `test_apply_game_config_accepts_auto_depth_for_minimax`, `test_load_response_branches`) — désynchronisation entre certains tests et le code de la GUI, non corrigée dans cette version. Le cœur du jeu, le mode réseau et le mode CLI ne sont pas affectés.

## Structure du projet

```
quoridor/
├── core/           # modèle du jeu
├── rules/          # règles, pathfinding, conditions de victoire
├── application/    # services applicatifs, moteurs IA (minimax, MCTS), historique, blitz
├── network/        # serveur/client TCP, protocole, découverte LAN
├── interfaces/      # CLI (shell), GUI (GTK)
├── ML/             # génération de données d'entraînement et sélection de features pour l'IA
└── utils/, ui/, i18n.py
tests/              # suite de tests pytest
docs/               # documentation Sphinx
```

## Auteurs

Projet réalisé en équipe, encadré par Emmanuel Fleury (Université de Bordeaux). D'après l'historique Git :

| Contributeur | Rôle |
|---|---|
| **Kousay Amara** | Étudiant — voir « Ce que j'ai réalisé » ci-dessous |
| Guilhem Causse | Étudiant |
| Mohamed Ait Issad | Étudiant |
| Bilal Al Fayoumi | Étudiant |
| Omar Harchi | Étudiant |
| Emmanuel Fleury | Enseignant, encadrant du projet |

*(Les adresses email des contributeurs autres que moi ont été anonymisées lors de la migration de ce dépôt, par respect de leur vie privée.)*

## Ce que j'ai réalisé (Kousay Amara)

Cette section distingue ma contribution individuelle de celle de l'équipe, d'après l'analyse de l'historique Git (`git blame`) :

- **Module réseau (`quoridor/network/`)** : conçu et implémenté la quasi-totalité du serveur TCP concurrent (multi-thread), du protocole texte avec sérialisation JSON de l'état de partie, et de la découverte automatique de serveurs sur le réseau local (UDP broadcast) — `basic_network.py`, `server.py`, `discovery.py`, `client.py`.
- **Interface CLI côté réseau** (`cli_network.py`, en grande partie) : commandes de connexion à un serveur, invitations de partie, liste des joueurs, tableau des scores.
- **Shell interactif** (`cli_shell.py`, en bonne partie) et catalogue de commandes (`command_catalog.py`, en bonne partie) : structure du shell (parsing, aide, historique, auto-complétion).
- **Tests associés** : auteur principal de `tests/test_network.py` et de `tests/test_cli_network_minimal.py`, et contributeur majoritaire de `tests/test_cli.py`.

Le module d'intelligence artificielle par apprentissage (`quoridor/ML/`) a été principalement écrit par mon coéquipier Bilal Al Fayoumi ; j'ai contribué à son intégration dans le moteur MCTS (`quoridor/application/mcts_engine.py`).

## Licence

Ce projet est sous licence [MIT](LICENSE).

## Origine du sujet

Le sujet du projet (`pdp/quoridor-specs.pdf`) a été fourni par l'enseignant encadrant, Emmanuel Fleury, dans le cadre du cursus de l'Université de Bordeaux. Il n'est pas de notre fait et reste la propriété de l'établissement.
