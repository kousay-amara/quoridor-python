# Quoridor

Implémentation du jeu de plateau **Quoridor** en Python : interface en ligne de commande (CLI), mode contest (lecture d’une position et sortie d’un coup), et option d’interface graphique.

## Installation

À la racine du projet, dans un environnement virtuel recommandé :

```bash
pip install -e .
```

Pour le développement (tests, couverture, formatage, doc) :

```bash
pip install -e ".[dev]"
```

Pour l’interface graphique (optionnel) :

```bash
pip install -e ".[gui]"
```

## Lancer le jeu

- **Mode interactif (CLI)**  
  ```bash
  quoridor
  ```

- **Mode contest** (lire un fichier de position et afficher un coup sur la sortie standard)  
  ```bash
  quoridor -c chemin/vers/fichier.txt
  ```

- **Version**  
  ```bash
  quoridor -V
  ```

- **Interface graphique (GTK)**  
  Depuis la racine du dépôt :
  ```bash
  python -m quoridor.interfaces.gui
  ```
  Depuis `quoridor/interfaces` :
  ```bash
  python -m gui
  ```

## Tests

```bash
pytest
```

Sans couverture :

```bash
pytest -q -p no:cov -o addopts= tests
```

Tester uniquement le mode contest :

```bash
PYTHONPATH=. pytest -q -p no:cov -o addopts= tests/test_contest.py
```

## Documentation

La documentation API est générée avec Sphinx. Après installation des dépendances de dev :

```bash
pip install -r docs/requirements.txt
cd docs
make html
```

Si le thème RTD manque (`ThemeError: no theme named 'sphinx_rtd_theme'`) :

```bash
pip install sphinx-rtd-theme
```

Ouvrir ensuite : **`docs/_build/html/index.html`** (ou [index.html](docs/_build/html/index.html) en relatif depuis la racine du dépôt).

## Développement

- Tester le mode contest à la main (exemple) :  
  `PYTHONPATH=. python3 -m quoridor.interfaces.cli -c contest_example.txt`  
  (adapter le chemin du module si ton point d’entrée CLI est différent.)
