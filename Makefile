# Tâches courantes pour Optim'Charpente.
# Utilise uv (https://docs.astral.sh/uv/) pour gérer l'environnement.
#
#   make install     installe les dépendances (avec connecteur Speckle)
#   make run         lance l'app Streamlit
#   make test        exécute la batterie de tests
#   make bordereau   génère un bordereau PDF de démo (sans Streamlit)
#   make clean       supprime l'environnement virtuel et les caches

.PHONY: install install-base run test bordereau speckle-test viz-test clean

# --- Installation ---------------------------------------------------------

install:        ## Installe + connecteur Speckle (recommandé)
	uv sync --extra speckle --extra dev

install-base:   ## Installe sans Speckle (plus léger)
	uv sync --extra dev

# --- Lancement ------------------------------------------------------------

run:            ## Lance l'app Streamlit
	uv run streamlit run app.py

# --- Tests ----------------------------------------------------------------

test:           ## Exécute tous les scripts de test
	@echo "▶ Test 1D (FFD/BFD/CP-SAT)"
	uv run python test_algos.py
	@echo "\n▶ Test couplé 1D+2D"
	uv run python test_couple.py
	@echo "\n▶ Test métriques opérationnelles"
	uv run python metrics.py

viz-test:       ## Génère les viz dans /tmp pour validation manuelle
	uv run python test_viz.py
	uv run python test_couple_viz.py

speckle-test:   ## Tests Speckle (sans serveur)
	uv run python test_speckle.py
	uv run python test_speckle_export.py

# --- Sorties --------------------------------------------------------------

bordereau:      ## Génère un bordereau PDF de démo dans /tmp
	uv run python connectors/bordereau_pdf.py

# --- Vérification du déploiement uvx --------------------------------------

uvx-test:       ## Simule un déploiement uvx --from . (avant push GitHub)
	@echo "▶ Lancement de l'app via uvx (Ctrl-C pour arrêter)"
	uvx --refresh --from . optim-charpente

# --- Maintenance ----------------------------------------------------------

clean:          ## Supprime venv, lock et caches
	rm -rf .venv uv.lock
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true

help:           ## Affiche cette aide
	@grep -E '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) | \
		awk -F':.*## ' '{printf "  %-15s %s\n", $$1, $$2}'

.DEFAULT_GOAL := help
