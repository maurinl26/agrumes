"""
Point d'entrée CLI pour Optim'Charpente.

Utilisable via :

    uvx --from . optim-charpente
    uvx --from git+https://github.com/USER/REPO optim-charpente
    pip install . && optim-charpente

Tous les flags additionnels sont transmis à Streamlit, par exemple :

    optim-charpente --server.port 8502
"""

import os
import sys
from pathlib import Path


def main() -> None:
    """Lance l'app Streamlit avec des défauts adaptés à un usage CLI."""
    from streamlit.web import cli as stcli

    # En mode installé (flat py-modules), launcher.py et app.py sont
    # tous deux dans site-packages. En dev (uv sync), ils sont à la
    # racine du repo. Dans les deux cas, ils sont voisins.
    here = Path(__file__).resolve().parent
    app_path = here / "app.py"

    if not app_path.exists():
        sys.stderr.write(
            f"❌ app.py introuvable à {app_path}\n"
            "Vérifiez que le package est correctement installé.\n"
        )
        sys.exit(1)

    # Désactive la collecte de stats Streamlit (pas de prompt email
    # au premier lancement, plus poli pour un déploiement uvx).
    os.environ.setdefault("STREAMLIT_BROWSER_GATHER_USAGE_STATS", "false")

    # Construit la commande Streamlit en conservant les flags fournis.
    extra_args = sys.argv[1:]
    sys.argv = ["streamlit", "run", str(app_path)] + extra_args
    sys.exit(stcli.main())


if __name__ == "__main__":
    main()
