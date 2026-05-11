"""
Équarrissage 2D : placer des sections rectangulaires dans le disque
de la section transversale d'une grume.

Problème : étant donné une grume de diamètre D et une liste de sections
(largeur × hauteur, quantité max), trouver le placement qui maximise
la surface utilisée, sans chevauchement, et avec tous les coins de
chaque rectangle dans le disque.

Approche : énumération de candidats sur grille discrète + CP-SAT.
- chaque candidat = (section, orientation, position_grille)
- variable binaire par candidat
- contrainte cell-par-cell : au plus un candidat par cellule
- contrainte par section : quantité max
- objectif : maximiser la surface totale placée

Résolution typique 20 mm. À régler selon la taille des grumes :
- 50 mm : très rapide, suffisant pour grosses sections (poutres)
- 20 mm : bon compromis
- 10 mm : précis, plus lent
"""

from dataclasses import dataclass, field
from typing import Optional
import math
import time


@dataclass
class Section:
    """Une section rectangulaire à placer dans le disque."""
    nom: str
    largeur: float       # m
    hauteur: float       # m
    quantite_max: int = 99


@dataclass
class PlacementSection:
    """Une section effectivement placée."""
    nom: str
    x: float             # m, coin bas-gauche, dans repère centré sur le cœur
    y: float
    largeur: float       # peut différer de la section originale si rotation
    hauteur: float
    rotation: int        # 0 ou 90


@dataclass
class ResultatEquarrissage:
    diametre: float
    placements: list = field(default_factory=list)
    duree_s: float = 0.0
    statut: str = ""

    @property
    def surface_disque(self) -> float:
        return math.pi * (self.diametre / 2) ** 2

    @property
    def surface_utilisee(self) -> float:
        return sum(p.largeur * p.hauteur for p in self.placements)

    @property
    def taux_utilisation(self) -> float:
        if self.surface_disque == 0:
            return 0.0
        return self.surface_utilisee / self.surface_disque


def _coins_dans_cercle(cx: int, cy: int, w: int, h: int,
                       centre_x: int, centre_y: int, r2: int) -> bool:
    """Vrai si les 4 coins du rectangle (en cellules) sont dans le cercle."""
    for ddx, ddy in ((0, 0), (w, 0), (0, h), (w, h)):
        dx = cx + ddx - centre_x
        dy = cy + ddy - centre_y
        if dx * dx + dy * dy > r2:
            return False
    return True


def equarrissage_cpsat(diametre: float, sections: list,
                       resolution_mm: int = 20,
                       time_limit_s: float = 5.0) -> Optional[ResultatEquarrissage]:
    """
    Solveur exact (ou faisable sous limite de temps) pour le placement 2D.

    Args:
        diametre : diamètre de la grume (m)
        sections : liste de Section
        resolution_mm : pas de la grille (mm)
        time_limit_s : temps max accordé

    Returns:
        ResultatEquarrissage, ou None si OR-Tools absent.
    """
    try:
        from ortools.sat.python import cp_model
    except ImportError:
        return None

    t0 = time.time()

    # Conversion en cellules de grille
    D_cells = int(round(diametre * 1000 / resolution_mm))
    R_cells = D_cells / 2
    centre = D_cells / 2  # le centre du disque, en cellules
    r2 = R_cells ** 2

    # On veut des entiers : centre = D_cells // 2 si pair, sinon décalage
    # On utilise des comparaisons en flottants pour la précision
    centre_x = centre
    centre_y = centre

    # Énumération des candidats : (i_section, w, h, rotation, cx, cy)
    candidats = []
    for i_sec, s in enumerate(sections):
        w0 = max(1, int(round(s.largeur * 1000 / resolution_mm)))
        h0 = max(1, int(round(s.hauteur * 1000 / resolution_mm)))
        # 2 orientations si non carré
        orients = [(w0, h0, 0)]
        if w0 != h0:
            orients.append((h0, w0, 90))
        for w, h, rot in orients:
            for cx in range(D_cells - w + 1):
                for cy in range(D_cells - h + 1):
                    # Test : tous les coins dans le disque
                    coins_ok = True
                    for ddx, ddy in ((0, 0), (w, 0), (0, h), (w, h)):
                        dx = cx + ddx - centre_x
                        dy = cy + ddy - centre_y
                        if dx * dx + dy * dy > r2:
                            coins_ok = False
                            break
                    if coins_ok:
                        candidats.append((i_sec, w, h, rot, cx, cy))

    if not candidats:
        return ResultatEquarrissage(
            diametre=diametre, placements=[],
            duree_s=time.time() - t0,
            statut="aucun placement faisable",
        )

    model = cp_model.CpModel()
    var_cands = [model.NewBoolVar(f"c{k}") for k in range(len(candidats))]

    # Contrainte : non-superposition (au plus 1 candidat par cellule)
    occupants = {}  # (cx, cy) -> liste de variables qui occupent cette cellule
    for k, (_, w, h, _, cx, cy) in enumerate(candidats):
        for dx in range(w):
            for dy in range(h):
                occupants.setdefault((cx + dx, cy + dy), []).append(var_cands[k])
    for vars_in_cell in occupants.values():
        if len(vars_in_cell) > 1:
            model.Add(sum(vars_in_cell) <= 1)

    # Contrainte : quantité max par section
    for i_sec, s in enumerate(sections):
        vars_sec = [var_cands[k] for k, c in enumerate(candidats) if c[0] == i_sec]
        if vars_sec:
            model.Add(sum(vars_sec) <= s.quantite_max)

    # Objectif : maximiser la surface (en cellules²)
    model.Maximize(
        sum(c[1] * c[2] * var_cands[k] for k, c in enumerate(candidats))
    )

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(time_limit_s)
    solver.parameters.num_search_workers = 4
    status = solver.Solve(model)

    statut_lbl = {
        cp_model.OPTIMAL: "optimal",
        cp_model.FEASIBLE: "faisable (limite atteinte)",
        cp_model.INFEASIBLE: "infaisable",
        cp_model.UNKNOWN: "inconnu",
    }.get(status, "inconnu")

    placements = []
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        res_m = resolution_mm / 1000.0
        R_m = diametre / 2
        for k, (i_sec, w, h, rot, cx, cy) in enumerate(candidats):
            if solver.Value(var_cands[k]) == 1:
                # Repère centré sur le cœur (le centre du disque est à (R_m, R_m)
                # dans le repère bas-gauche, on translate)
                x_m = cx * res_m - R_m
                y_m = cy * res_m - R_m
                placements.append(PlacementSection(
                    nom=sections[i_sec].nom,
                    x=x_m, y=y_m,
                    largeur=w * res_m,
                    hauteur=h * res_m,
                    rotation=rot,
                ))

    return ResultatEquarrissage(
        diametre=diametre,
        placements=placements,
        duree_s=time.time() - t0,
        statut=statut_lbl,
    )


def equarrissage_glouton(diametre: float, sections: list) -> ResultatEquarrissage:
    """
    Heuristique gloutonne, fallback si OR-Tools absent.
    Trie les sections par surface décroissante, place chacune dans la
    première position de grille où ça rentre (sans chevauchement, dans le disque).
    Sous-optimal mais sans dépendance externe.
    """
    t0 = time.time()
    resolution_mm = 20
    res_m = resolution_mm / 1000.0
    D_cells = int(round(diametre * 1000 / resolution_mm))
    centre = D_cells / 2
    r2 = (D_cells / 2) ** 2

    # Trier sections par surface décroissante en gardant les quantités
    sections_etendues = []
    for s in sections:
        for _ in range(s.quantite_max):
            sections_etendues.append(s)
    sections_etendues.sort(key=lambda s: -s.largeur * s.hauteur)

    occupied = set()  # cellules occupées
    placements = []

    for s in sections_etendues:
        w0 = max(1, int(round(s.largeur * 1000 / resolution_mm)))
        h0 = max(1, int(round(s.hauteur * 1000 / resolution_mm)))
        place = False
        for w, h, rot in [(w0, h0, 0)] + ([(h0, w0, 90)] if w0 != h0 else []):
            if place:
                break
            for cx in range(D_cells - w + 1):
                for cy in range(D_cells - h + 1):
                    if not _coins_dans_cercle(cx, cy, w, h, centre, centre, r2):
                        continue
                    # Vérifier non-superposition
                    cells = {(cx + dx, cy + dy) for dx in range(w) for dy in range(h)}
                    if cells & occupied:
                        continue
                    occupied |= cells
                    R_m = diametre / 2
                    placements.append(PlacementSection(
                        nom=s.nom,
                        x=cx * res_m - R_m,
                        y=cy * res_m - R_m,
                        largeur=w * res_m,
                        hauteur=h * res_m,
                        rotation=rot,
                    ))
                    place = True
                    break
                if place:
                    break

    return ResultatEquarrissage(
        diametre=diametre,
        placements=placements,
        duree_s=time.time() - t0,
        statut="glouton",
    )


# ========== Auto-test ==========

if __name__ == "__main__":
    cas = [
        ("Ø 35cm + 1 poutre 22×22",
         0.35, [Section("Poutre", 0.22, 0.22, 1)]),
        ("Ø 30cm + 1 poutre 22×22 (devrait échouer)",
         0.30, [Section("Poutre", 0.22, 0.22, 1)]),
        ("Ø 45cm + 1 poutre + 4 chevrons",
         0.45, [Section("Poutre", 0.22, 0.22, 1),
                Section("Chevron", 0.08, 0.08, 4)]),
        ("Ø 50cm + 4 madriers 22×8",
         0.50, [Section("Madrier", 0.22, 0.08, 4)]),
        ("Ø 60cm mix complet",
         0.60, [Section("Poutre", 0.25, 0.25, 1),
                Section("Madrier", 0.20, 0.08, 4),
                Section("Chevron", 0.08, 0.08, 4)]),
    ]

    for nom, D, secs in cas:
        print(f"\n{nom}")
        r = equarrissage_cpsat(D, secs, resolution_mm=20, time_limit_s=5)
        if r is None:
            print("  OR-Tools absent")
            continue
        print(f"  statut : {r.statut}, durée {r.duree_s*1000:.0f} ms")
        print(f"  surface : {r.surface_utilisee*10000:.0f} cm² / "
              f"{r.surface_disque*10000:.0f} cm² ({r.taux_utilisation*100:.1f}%)")
        for p in r.placements:
            print(f"  - {p.nom}: ({p.x*100:+.0f}, {p.y*100:+.0f}) cm, "
                  f"{p.largeur*100:.0f}×{p.hauteur*100:.0f} rot {p.rotation}°")
