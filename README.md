# 🪵 Optim'Charpente

Outil d'optimisation **grumes → débits** pour un projet de charpente : on entre les troncs disponibles et la liste des pièces à scier, et l'app propose un plan de découpe minimisant les chutes, jusqu'à la sortie d'un **bordereau de production PDF** prêt pour la scierie.

## Workflow opérationnel

```
   Saisie / import           Calcul                  Validation                Sortie
   ─────────────────────────────────────────────────────────────────────────────────
                                                                              ┌─────┐
  ┌─────────┐   ┌──────────┐   ┌──────────────┐    ┌──────────────┐          │ PDF │
  │ Grumes  │──▶│ Pré-check│──▶│ 4 algos en   │───▶│ Tableau KPIs │          │  +  │
  │ Débits  │   │ volumique│   │ parallèle    │    │ + viz section│ ─ ─ ─ ─ ▶│ plan│
  └─────────┘   │ ⛔ stop  │   │ FFD/BFD/CPSAT│    │ + viz 3D     │          │ par │
                │ si demande│   │ + Couplé     │    │ Choix algo   │          │grume│
                │ > offre×0.7│  │              │    │              │          └─────┘
                └──────────┘   └──────────────┘    └──────────────┘             │
                                                          │                     ▼
                                                          │              Imprimer / scier
                                                          ▼
                                                   Speckle (BIM, optionnel)
```

### Étapes détaillées

1. **Saisie** — directement dans Streamlit (data_editor) ou import depuis un projet Speckle 3.x.
2. **Pré-check de faisabilité** — l'app refuse de calculer si :
   - Volume de débits demandé > volume des grumes × 70 % (rendement scierie max réaliste pour le chêne), OU
   - Au moins un débit n'a aucune grume compatible (section trop grande ou plus longue que toutes les grumes).
3. **Calcul parallèle** — 4 algorithmes lancés simultanément, comparés.
4. **Validation visuelle** — tableau de KPIs opérationnels (rendement matière, couverture demande, mobilisation des grumes), section transversale par grume, vue 3D interactive.
5. **Export bordereau** — PDF imprimable destiné à accompagner les grumes en scierie : page 1 synthèse + une page par grume utilisée (section + plan de tronçonnage par rail).
6. **Export Speckle (optionnel)** — push du plan complet (cylindres + boîtes) vers Speckle pour relecture dans Rhino, Revit, Blender.

## Algorithmes

L'app compare en parallèle quatre algorithmes :

### 1D pur (longueur seule)
Chaque grume est traitée comme une bande linéaire ; on aligne les débits bout-à-bout. Suppose **1 seule section par grume**, donc le bois autour est perdu.

- **First-Fit Decreasing** — heuristique rapide
- **Best-Fit Decreasing** — heuristique rapide
- **CP-SAT 1D** — optimum sous limite de temps, OR-Tools

### Couplé 1D+2D (opérationnel)
Pour chaque grume, choix d'un **schéma d'équarrissage** (un *pattern*) parmi un catalogue généré, puis tronçonnage 1D dans chaque rail :

- **Mono-section** : la même section répétée dans le disque
- **Bi-section** : 1 grosse pièce + plusieurs petites
- **Patterns experts** : configurations classiques de scierie
  - **Boule** : pièce maîtresse centrée (carré inscrit max)
  - **Quartanier** : 4 carrés en disposition 2×2
  - **Plot 2** : 2 plateaux jointifs

Puis CP-SAT global décide :
- Quel pattern par grume (ou aucun → grume conservée en stock)
- Combien de chaque débit tronçonner dans chaque rail
- Objectif : minimiser la longueur cumulée des grumes activées (= conserver des grumes pour la prochaine fournée)

Filtres opérationnels appliqués à la génération de patterns : pas de rail < 4 cm, taux d'utilisation 2D ≥ 30 % (pas de schéma absurde).

### Pourquoi le couplé est différent

Cas-test : 6 chevrons 8×8 cm × 2.5 m + 1 sablière 22×22 cm × 5.5 m, dans 3 grumes Ø50 × 6 m.

| KPI | FFD (1D) | Couplé |
|---|---|---|
| Cubage demandé | 0.362 m³ | 0.362 m³ |
| Cubage produit | 0.330 m³ | **0.362 m³** |
| Couverture demande | 91.2 % | **100 %** |
| Grumes mobilisées | 3 sur 3 | **1 sur 3** |
| Cubage en réserve | 0 m³ | **2.356 m³** |
| Rendement matière | 9.3 % | **30.7 %** |
| Setups scierie | 3 | **1** |

Le 1D pur ne sait pas placer la sablière **et** 4 chevrons en parallèle dans le même disque ; le couplé y arrive grâce au pattern « bi Sablière + Chevron×4 ».

## Métriques opérationnelles

Le bordereau (Streamlit + PDF) affiche les KPIs scierie classiques :

- **Rendement matière** = volume débité / volume des grumes mobilisées (référence chêne : 50–65 %)
- **Couverture demande** = volume débité / volume demandé (100 % = tout est satisfait)
- **Cubage en réserve** = volume des grumes laissées au stock pour la prochaine fournée
- **Setups scierie** = nombre de schémas d'équarrissage différents (= temps de réglage)
- **Cubage chute** = matière perdue dans les grumes utilisées

## Architecture

### Modules

```
optim_charpente/
├── engine.py              Cœur 1D
│                          - Dataclasses Grume, Debit, Coupe, Allocation, Resultat
│                          - Solveurs : FFD, BFD, CP-SAT
│                          - Constantes : KERF (5 mm)
│
├── equarissage.py         Cœur 2D
│                          - Section, PlacementSection, ResultatEquarrissage
│                          - equarrissage_cpsat (énumération sur grille + CP-SAT)
│                          - equarrissage_glouton (fallback sans OR-Tools)
│
├── geometry.py            Meshes pivots
│                          - cylindre(L, r) → (sommets, triangles)
│                          - boite(x, y, z, L, w, h) → (sommets, triangles)
│                          - to_plotly_mesh3d(...) / to_speckle_mesh(...)
│                          - GARANTIT que viz Streamlit = export Speckle = même géométrie
│
├── pattern.py             Solveur couplé 1D+2D
│                          - Dataclasses Rail, Pattern
│                          - verifier_faisabilite(grumes, debits) → pré-check volumique
│                          - patterns_mono / bi / experts → catalogue
│                          - solveur_couple_cpsat(...) → Resultat enrichi avec rails
│
├── metrics.py             Bordereau opérationnel
│                          - MetriquesOps : KPIs scierie
│                          - calculer_metriques(resultat, grumes, debits)
│                          - formater_pour_dataframe(...) pour Streamlit
│
├── app.py                 Streamlit (UI)
│                          - Onglet Tronçonnage 1D : saisie, lancer algos,
│                            comparaison, viz, export bordereau, export Speckle
│                          - Onglet Équarrissage 2D : exploration interactive
│                            du solveur 2D
│
├── launcher.py            Point d'entrée CLI (`optim-charpente`)
│                          - Utilisé par uvx et par les installs pip/uv
│                          - Lance `streamlit run app.py` avec les bons défauts
│
├── connectors/            I/O avec systèmes externes
│   ├── __init__.py
│   ├── speckle_io.py      Import/export BIM Speckle 3.x
│   │                      - parse_speckle_url, test_connection
│   │                      - import_debits, import_grumes, export_plan
│   └── bordereau_pdf.py   Export PDF de production
│                          - exporter_bordereau(resultat, ...) → fichier PDF
│                          - exporter_bordereau_bytes(...) → bytes (Streamlit)
│                          - Page 1 : synthèse + KPIs + allocation
│                          - Pages 2..N : section transversale + tronçonnage par rail
│
├── tests/
│   ├── test_algos.py            Comparaison FFD/BFD/CP-SAT 1D
│   ├── test_couple.py           Comparaison 1D vs couplé
│   ├── test_couple_viz.py       Validation visuelle viz couplé
│   ├── test_speckle.py          Parsing URLs + agrégation (sans serveur)
│   ├── test_speckle_export.py   Construction Bases Speckle (sans push)
│   └── test_viz.py              Génération HTML 3D + PNG section
│
├── pyproject.toml         Dépendances : streamlit, pandas, matplotlib, plotly,
│                          ortools ; extras : [speckle] = specklepy>=3.0
├── Makefile               Tâches via uv : install / run / test / bordereau / clean
└── README.md
```

### Graphe de dépendances

```
                                ┌─────────────┐
                                │   app.py    │
                                │ (Streamlit) │
                                └──────┬──────┘
                                       │
            ┌──────────────────────────┼─────────────┬───────────────┐
            ▼                          ▼             ▼               ▼
      ┌──────────┐               ┌──────────┐  ┌──────────┐    ┌──────────────┐
      │ engine.py│               │pattern.py│  │metrics.py│    │ connectors/  │
      │  (1D)    │◀──────────────│ (couplé) │  │  (KPIs)  │    │              │
      └──────────┘               └──────┬───┘  └──────────┘    │ ┌──────────┐ │
            ▲                           │                       │ │speckle_io│ │
            │                           │                       │ └──────────┘ │
            │                    ┌──────▼──────┐                │ ┌──────────┐ │
            └────────────────────│equarissage  │                │ │bordereau │ │
                                 │     (2D)    │                │ │   _pdf   │ │
                                 └──────┬──────┘                │ └──────────┘ │
                                        │                       └──────────────┘
                                        ▼
                                  ┌──────────┐
                                  │geometry  │
                                  │ (meshes) │
                                  └──────────┘
```

- `engine.py` est autonome (cœur 1D, sans dépendance interne)
- `pattern.py` couple 1D + 2D, importe `engine` et `equarissage`
- `metrics.py` calcule les KPIs à partir d'un `Resultat` + listes initiales
- Le module `connectors/` est le seul à parler aux systèmes externes (Speckle, PDF). Il importe `geometry`, `metrics`, `equarissage` selon les besoins.

### Principes de conception

- **Modules cœur séparés des I/O** : `engine`, `equarissage`, `pattern`, `metrics` n'ont aucune dépendance Streamlit ni Speckle, on peut les utiliser depuis un script ou un notebook.
- **Pattern attaché aux allocations** : en mode couplé, chaque allocation porte son `Pattern` ; les viz et les exports utilisent les rails fidèles sans recalcul.
- **`Coupe` rétro-compatible** : les champs `rail_x` / `rail_y` sont optionnels (None pour 1D pur), donc le 1D existant continue de marcher inchangé.
- **Géométrie unique** : `geometry.py` produit des meshes (sommets + triangles) qui sont ensuite adaptés à Plotly *ou* Speckle. Garantie que ce qu'on voit dans Streamlit est ce qui partira sur Speckle.

## Installation et lancement

### Lancement rapide via `uvx` (zéro install permanente)

Si tu veux juste **essayer l'app sans rien installer durablement** :

```bash
# Depuis GitHub
uvx --from git+https://github.com/maurinl26/agrumes optim-charpente

# Depuis un clone local
uvx --from . optim-charpente

# Avec connecteur Speckle activé
uvx --from "git+https://github.com/maurinl26/agrumes[speckle]" optim-charpente

# En passant des flags à Streamlit
uvx --from git+https://github.com/maurinl26/agrumes optim-charpente --server.port 8502
```

`uvx` télécharge le code, crée un environnement isolé jetable, installe les dépendances, et lance l'app. À l'arrêt, plus rien ne reste sur ta machine.

Pour une version pinnée (tag git) :

```bash
uvx --from git+https://github.com/maurinl26/agrumes@v0.1.0 optim-charpente
```

### Installation locale (développement) avec [uv](https://docs.astral.sh/uv/)

Si tu prévois de modifier le code ou de lancer l'app souvent :

```bash
# Une fois (si uv pas installé)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Dans le projet
make install     # Python + dépendances + connecteur Speckle
make run         # lance l'app Streamlit
make test        # exécute la batterie de tests
make bordereau   # génère un bordereau PDF de démo
make help        # liste toutes les commandes
```

### Avec pip (alternative)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[speckle]"
streamlit run app.py
# OU
optim-charpente
```

Dépendances clés : Python ≥ 3.10, OR-Tools (CP-SAT), Streamlit, Plotly, matplotlib. specklepy ≥ 3.0 en option.

## Limites connues

- Pas d'optimisation cœur centré vs hors-cœur (stabilité au séchage du chêne)
- Pas de surcote séchage automatique (à appliquer manuellement aux dimensions saisies)
- Pas de gestion de défauts ponctuels (nœuds, pourriture, cernes décentrés)
- Le solveur couplé peut laisser un rail vide si le catalogue de patterns n'a pas la combinaison parfaite (chute marginale en volume)
- En cas de demande dépassant le rendement 70 % des grumes : l'app refuse de calculer
- Pas de prise en compte de la **direction des fibres** : pour les pièces structurelles tordues ou avec fil oblique, l'orientation reste à arbitrer manuellement

## Évolutions possibles

- Génération de colonnes (Gilmore-Gomory) si le catalogue de patterns devient un goulot
- Zone d'exclusion du cœur (~5 cm centraux) pour les pièces critiques
- Pareto chute / nombre de coupes / nombre de setups
- Préférences qualitatives par débit (hors-cœur, sans aubier, hors-fente)
- Connecteur IFC pour Revit / ArchiCAD
- Export bordereau directement vers une imprimante (CUPS) ou un email
