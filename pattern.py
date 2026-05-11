"""
Solveur couplé 1D+2D par sélection de patterns.

Chemin opérationnel disjoint du pipeline « 1D pur puis 2D post-hoc » :
les deux restent disponibles, on compare systématiquement.

Approche :
1. Pré-vérification de faisabilité (longueur totale + sections compatibles).
   Si demande > offre => stop avec message clair.
2. Pour chaque grume, génération d'un catalogue de patterns :
   - Mono-section (une seule section répétée)
   - Bi-section (1 grosse + plusieurs petites)
   - Experts : configurations classiques de scierie (boule, quartanier, plot 2)
3. Filtrage qualité scierie : pas de rail < 4 cm, pas de pattern < 30% utilisation.
4. Modèle CP-SAT global :
   - Variables : choix de pattern par grume, et tronçonnage par rail
   - Contraintes : 1 pattern par grume, longueur respectée, demande couverte exactement
   - Objectif : minimiser la longueur totale de grumes activées
5. Reconstruit un Resultat compatible avec le reste de l'app
   (attache Pattern et rails aux Coupes pour la viz 2D fidèle).
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Optional

import equarissage
from equarissage import Section
from engine import Grume, Debit, Coupe, Allocation, Resultat, KERF


# ============================================================
#                         Données
# ============================================================

@dataclass
class Rail:
    """
    Une bande rectangulaire dans la section transversale d'une grume,
    parcourant toute la longueur. Coordonnées en m, repère centré sur le cœur.
    """
    largeur: float       # m (dimension X dans le disque)
    hauteur: float       # m (dimension Y dans le disque)
    x: float             # m, coin bas-gauche dans le disque
    y: float
    rotation: int = 0    # 0 ou 90 (info, déjà appliquée aux dimensions)

    @property
    def section(self) -> tuple:
        return (self.largeur, self.hauteur)


@dataclass
class Pattern:
    """Schéma d'équarrissage 2D pour une grume spécifique."""
    grume_id: str
    grume_longueur: float
    grume_diametre: float
    rails: list = field(default_factory=list)
    nom: str = ""

    @property
    def surface_utilisee(self) -> float:
        return sum(r.largeur * r.hauteur for r in self.rails)

    @property
    def surface_disque(self) -> float:
        return math.pi * (self.grume_diametre / 2) ** 2

    @property
    def taux_section(self) -> float:
        s = self.surface_disque
        return self.surface_utilisee / s if s > 0 else 0.0

    def signature(self) -> tuple:
        """Pour dédup : tuple trié des rails (à 1 mm près)."""
        return tuple(sorted(
            (round(r.largeur, 3), round(r.hauteur, 3),
             round(r.x, 3), round(r.y, 3))
            for r in self.rails
        ))


# ============================================================
#                      Pré-vérification
# ============================================================

def verifier_faisabilite(grumes: list, debits: list,
                         rendement_max: float = 0.70) -> tuple[bool, str]:
    """
    Vérifie 2 conditions nécessaires avant de lancer le solveur couplé :

    1. **Volume** : volume des débits demandés ≤ volume des grumes × rendement_max.
       Le rendement scierie atteignable plafonne en pratique à ~70 % (geom. + écorce).
    2. **Compatibilité** : chaque débit doit pouvoir tenir dans au moins une grume
       (section inscrite dans le disque ET longueur ≤ longueur grume).

    Retourne (ok, message). Si ok=False, c'est que le problème est strictement
    infaisable même en mode couplé : on stoppe l'utilisateur.
    """
    # 1. Volume
    vol_demande = sum(d.longueur * d.largeur * d.hauteur * d.quantite
                      for d in debits)
    vol_offre = sum(g.longueur * math.pi * (g.diametre / 2) ** 2
                    for g in grumes)
    vol_dispo = vol_offre * rendement_max
    if vol_demande > vol_dispo:
        return False, (
            f"Volume demandé ({vol_demande:.3f} m³) supérieur au "
            f"volume utile estimé des grumes "
            f"({vol_dispo:.3f} m³ = {vol_offre:.3f} × {rendement_max:.0%}). "
            f"Ajoutez des grumes ou réduisez la demande."
        )

    # 2. Compatibilité débit / grume
    incompatibles = []
    for d in debits:
        diag = math.hypot(d.largeur, d.hauteur)
        if not any(diag <= g.diametre and d.longueur <= g.longueur
                   for g in grumes):
            incompatibles.append(d.nom)
    if incompatibles:
        return False, (
            "Débits sans grume compatible (section trop grande ou longueur "
            "supérieure à toutes les grumes) : " + ", ".join(incompatibles)
        )
    return True, "OK"


# ============================================================
#                   Génération de patterns
# ============================================================

# Seuils opérationnels (visent un outil scierie réaliste)
MIN_RAIL_DIM = 0.04         # m, pas de rail < 4 cm de côté
MIN_TAUX_PATTERN = 0.30     # rejeter les patterns < 30% de surface utilisée


def _placements_to_rails(placements) -> list:
    """Convertit les PlacementSection (du solveur 2D) en list[Rail]."""
    return [Rail(p.largeur, p.hauteur, p.x, p.y, p.rotation)
            for p in placements]


def _sections_demandees_uniques(debits: list) -> list:
    """Sections distinctes demandées (1 par dim unique). Tri par surface décr."""
    seen = {}
    for d in debits:
        key = (round(d.largeur, 4), round(d.hauteur, 4))
        if key not in seen:
            seen[key] = Section(d.nom, d.largeur, d.hauteur, 99)
    out = list(seen.values())
    out.sort(key=lambda s: -s.largeur * s.hauteur)
    return out


def patterns_mono_section(grume: Grume, sections: list,
                          resolution_mm: int = 20) -> list:
    """Pour chaque section, place le maximum d'instances dans le disque."""
    patterns = []
    for s in sections:
        if math.hypot(s.largeur, s.hauteur) > grume.diametre:
            continue
        sol = equarissage.equarrissage_cpsat(
            diametre=grume.diametre,
            sections=[Section(s.nom, s.largeur, s.hauteur, 99)],
            resolution_mm=resolution_mm,
            time_limit_s=2,
        )
        if sol and sol.placements:
            patterns.append(Pattern(
                grume_id=grume.id,
                grume_longueur=grume.longueur,
                grume_diametre=grume.diametre,
                rails=_placements_to_rails(sol.placements),
                nom=f"mono {s.nom}×{len(sol.placements)}",
            ))
    return patterns


def patterns_bi_section(grume: Grume, sections: list,
                        resolution_mm: int = 20) -> list:
    """1 grosse section + plusieurs petites."""
    patterns = []
    # 3 plus grosses comme « majeures »
    for i, s_main in enumerate(sections[:3]):
        for j, s_fill in enumerate(sections):
            if i == j:
                continue
            for q_fill in (2, 4, 6):
                sol = equarissage.equarrissage_cpsat(
                    diametre=grume.diametre,
                    sections=[
                        Section(s_main.nom, s_main.largeur, s_main.hauteur, 1),
                        Section(s_fill.nom, s_fill.largeur, s_fill.hauteur, q_fill),
                    ],
                    resolution_mm=resolution_mm,
                    time_limit_s=1,
                )
                if sol and len(sol.placements) >= 2:
                    patterns.append(Pattern(
                        grume_id=grume.id,
                        grume_longueur=grume.longueur,
                        grume_diametre=grume.diametre,
                        rails=_placements_to_rails(sol.placements),
                        nom=f"bi {s_main.nom}+{s_fill.nom}×{q_fill}",
                    ))
    return patterns


def patterns_experts(grume: Grume, sections: list) -> list:
    """Configurations classiques de scierie codées en dur."""
    patterns = []
    R = grume.diametre / 2

    # ---- BOULE : 1 grosse pièce centrée (carré inscrit max) ----
    # Le carré inscrit a un côté max D/√2.
    cote_boule = R * math.sqrt(2) * 0.95
    cb = [s for s in sections
          if max(s.largeur, s.hauteur) <= cote_boule
          and abs(s.largeur - s.hauteur) < 0.005]
    if cb:
        s = max(cb, key=lambda s: s.largeur)
        rails = [Rail(s.largeur, s.hauteur,
                      -s.largeur / 2, -s.hauteur / 2, 0)]
        patterns.append(Pattern(
            grume.id, grume.longueur, grume.diametre,
            rails, nom=f"boule {s.nom}",
        ))

    # ---- QUARTANIER : 4 carrés en 2×2 ----
    # Chaque carré a un côté max R/√2 (les 4 coins externes sur le disque).
    cote_q = R / math.sqrt(2) * 0.95
    cq = [s for s in sections
          if s.largeur <= cote_q and s.hauteur <= cote_q
          and abs(s.largeur - s.hauteur) < 0.005]
    if cq:
        s = max(cq, key=lambda s: s.largeur)
        a = s.largeur
        rails = [
            Rail(a, a, 0, 0, 0),       # haut-droite
            Rail(a, a, -a, 0, 0),      # haut-gauche
            Rail(a, a, -a, -a, 0),     # bas-gauche
            Rail(a, a, 0, -a, 0),      # bas-droite
        ]
        patterns.append(Pattern(
            grume.id, grume.longueur, grume.diametre,
            rails, nom=f"quartanier {s.nom}",
        ))

    # ---- PLOT 2 : 2 plateaux jointifs ----
    # Conditions : √((2w)² + h²) ≤ D
    cp2 = []
    for s in sections:
        for w, h in ((s.largeur, s.hauteur), (s.hauteur, s.largeur)):
            if math.hypot(2 * w, h) <= grume.diametre * 0.98:
                cp2.append((s, w, h))
    if cp2:
        s, w, h = max(cp2, key=lambda x: 2 * x[1] * x[2])
        rails = [
            Rail(w, h, -w, -h / 2, 0),
            Rail(w, h, 0, -h / 2, 0),
        ]
        patterns.append(Pattern(
            grume.id, grume.longueur, grume.diametre,
            rails, nom=f"plot2 {s.nom}",
        ))

    return patterns


def _filtrer_qualite(patterns: list) -> list:
    """Élimine les patterns non-opérationnels."""
    out = []
    for p in patterns:
        if not p.rails:
            continue
        if any(min(r.largeur, r.hauteur) < MIN_RAIL_DIM for r in p.rails):
            continue
        if p.taux_section < MIN_TAUX_PATTERN:
            continue
        out.append(p)
    return out


def _dedup(patterns: list) -> list:
    seen, out = set(), []
    for p in patterns:
        sig = p.signature()
        if sig not in seen:
            seen.add(sig)
            out.append(p)
    return out


def generer_patterns_grume(grume: Grume, sections: list,
                           n_max: int = 15,
                           resolution_mm: int = 20) -> list:
    """Orchestre la génération + filtrage. Renvoie au plus n_max patterns,
    triés par taux d'utilisation décroissant."""
    pats = []
    pats += patterns_mono_section(grume, sections, resolution_mm)
    pats += patterns_bi_section(grume, sections, resolution_mm)
    pats += patterns_experts(grume, sections)
    pats = _dedup(pats)
    pats = _filtrer_qualite(pats)
    pats.sort(key=lambda p: -p.taux_section)
    return pats[:n_max]


# ============================================================
#                Solveur couplé CP-SAT
# ============================================================

def _rail_compatible(rail: Rail, debit: Debit) -> bool:
    """Vrai si la section du rail accueille la section du débit (avec ε)."""
    eps = 1e-6
    fits_direct = (debit.largeur <= rail.largeur + eps
                   and debit.hauteur <= rail.hauteur + eps)
    fits_rotated = (debit.hauteur <= rail.largeur + eps
                    and debit.largeur <= rail.hauteur + eps)
    return fits_direct or fits_rotated


def solveur_couple_cpsat(debits: list, grumes: list,
                         time_limit_s: float = 30.0,
                         resolution_mm: int = 20) -> Optional[Resultat]:
    """
    Solveur couplé. Renvoie un Resultat (ou None si OR-Tools absent).
    En cas de pré-check négatif ou d'infaisabilité du modèle,
    le Resultat porte un nom_algo « INFAISABLE » et un statut explicite.
    """
    try:
        from ortools.sat.python import cp_model
    except ImportError:
        return None

    t0 = time.time()

    # Pré-check
    ok, msg = verifier_faisabilite(grumes, debits)
    if not ok:
        return Resultat(
            nom_algo="Couplé 1D+2D — INFAISABLE",
            allocations=[Allocation(g.id, g.longueur, g.diametre)
                         for g in grumes],
            debits_non_alloues=[d.nom for d in debits],
            duree_s=time.time() - t0,
            statut=msg,
        )

    # Catalogue de patterns
    sections = _sections_demandees_uniques(debits)
    grume_patterns = {}
    for g in grumes:
        grume_patterns[g.id] = generer_patterns_grume(
            g, sections, n_max=15, resolution_mm=resolution_mm,
        )

    # Aucun pattern génériquement → infaisable
    if all(not lst for lst in grume_patterns.values()):
        return Resultat(
            nom_algo="Couplé 1D+2D — INFAISABLE",
            allocations=[Allocation(g.id, g.longueur, g.diametre)
                         for g in grumes],
            debits_non_alloues=[d.nom for d in debits],
            duree_s=time.time() - t0,
            statut="Aucun pattern viable n'a pu être généré.",
        )

    # ===== Modèle CP-SAT =====
    model = cp_model.CpModel()

    # y[g, p] : 1 si pattern p choisi pour grume g
    y = {}
    for g in grumes:
        for p_idx in range(len(grume_patterns[g.id])):
            y[g.id, p_idx] = model.NewBoolVar(f"y_{g.id}_{p_idx}")

    # n[g, p, r, i] : nombre de débits i tirés du rail r du pattern p de la grume g
    n = {}
    for g in grumes:
        for p_idx, pat in enumerate(grume_patterns[g.id]):
            for r_idx, rail in enumerate(pat.rails):
                for i, d in enumerate(debits):
                    if _rail_compatible(rail, d):
                        max_in_rail = int(g.longueur / (d.longueur + KERF))
                        max_qty = min(d.quantite, max_in_rail)
                        if max_qty > 0:
                            n[g.id, p_idx, r_idx, i] = model.NewIntVar(
                                0, max_qty,
                                f"n_{g.id}_{p_idx}_{r_idx}_{i}",
                            )

    # 1. Au plus 1 pattern par grume
    for g in grumes:
        ks = [(g.id, p) for p in range(len(grume_patterns[g.id]))]
        if ks:
            model.Add(sum(y[k] for k in ks) <= 1)

    # 2. Longueur respectée par rail (active si pattern actif), n = 0 sinon
    for g in grumes:
        for p_idx, pat in enumerate(grume_patterns[g.id]):
            yvar = y[g.id, p_idx]
            for r_idx in range(len(pat.rails)):
                terms = [int((debits[i].longueur + KERF) * 1000)
                         * n[g.id, p_idx, r_idx, i]
                         for i in range(len(debits))
                         if (g.id, p_idx, r_idx, i) in n]
                if terms:
                    model.Add(sum(terms) <= int(g.longueur * 1000)
                              ).OnlyEnforceIf(yvar)
                    for i in range(len(debits)):
                        k = (g.id, p_idx, r_idx, i)
                        if k in n:
                            model.Add(n[k] == 0).OnlyEnforceIf(yvar.Not())

    # 3. Couvrir exactement la demande
    for i, d in enumerate(debits):
        terms = [n[k] for k in n if k[3] == i]
        if not terms:
            return Resultat(
                nom_algo="Couplé 1D+2D — INFAISABLE",
                allocations=[Allocation(g.id, g.longueur, g.diametre)
                             for g in grumes],
                debits_non_alloues=[d.nom for d in debits],
                duree_s=time.time() - t0,
                statut=f"Aucun pattern ne peut produire « {d.nom} ».",
            )
        model.Add(sum(terms) == d.quantite)

    # Objectif : minimiser la longueur totale de grumes activées
    # (= maximiser bois disponible non utilisé, conservation des grumes)
    obj_terms = []
    for g in grumes:
        for p_idx in range(len(grume_patterns[g.id])):
            obj_terms.append(int(g.longueur * 1000) * y[g.id, p_idx])
    model.Minimize(sum(obj_terms))

    # ===== Résolution =====
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

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        # CP-SAT n'a pas trouvé de solution : reporter
        return Resultat(
            nom_algo=f"Couplé 1D+2D — {statut_lbl}",
            allocations=[Allocation(g.id, g.longueur, g.diametre)
                         for g in grumes],
            debits_non_alloues=[d.nom for d in debits],
            duree_s=time.time() - t0,
            statut=("Le modèle a été déclaré infaisable malgré le pré-check. "
                    "Probable conflit géométrique/granularité. "
                    "Tentez d'augmenter la résolution 2D ou le temps."
                    if status == cp_model.INFEASIBLE else statut_lbl),
        )

    # ===== Reconstruction =====
    allocations = []
    for g in grumes:
        chosen_idx = None
        for p_idx in range(len(grume_patterns[g.id])):
            if solver.Value(y[g.id, p_idx]) == 1:
                chosen_idx = p_idx
                break

        coupes = []
        chosen_pattern = None
        if chosen_idx is not None:
            chosen_pattern = grume_patterns[g.id][chosen_idx]
            for r_idx, rail in enumerate(chosen_pattern.rails):
                for i, d in enumerate(debits):
                    k = (g.id, chosen_idx, r_idx, i)
                    if k not in n:
                        continue
                    qty = solver.Value(n[k])
                    for _ in range(qty):
                        coupes.append(Coupe(
                            debit_nom=d.nom,
                            longueur=d.longueur,
                            section=(rail.largeur, rail.hauteur),
                            rail_x=rail.x,
                            rail_y=rail.y,
                        ))

        a = Allocation(
            grume_id=g.id,
            grume_longueur=g.longueur,
            grume_diametre=g.diametre,
            coupes=coupes,
        )
        # Attache du Pattern (champ dynamique, lu via getattr ailleurs)
        a.pattern = chosen_pattern
        allocations.append(a)

    return Resultat(
        nom_algo=f"Couplé 1D+2D ({statut_lbl})",
        allocations=allocations,
        debits_non_alloues=[],
        duree_s=time.time() - t0,
        statut=statut_lbl,
    )


# ============================================================
#                       Auto-test
# ============================================================

if __name__ == "__main__":
    print("=== Cas 1 : demande modeste ===")
    grumes = [
        Grume("G1", 6.0, 0.50),
        Grume("G2", 5.5, 0.45),
        Grume("G3", 4.5, 0.40),
        Grume("G4", 5.0, 0.42),
    ]
    debits = [
        Debit("Sablière", 5.0, 0.22, 0.22, 1),
        Debit("Poteau",   3.0, 0.20, 0.20, 2),
        Debit("Chevron",  2.0, 0.08, 0.08, 4),
    ]
    print(f"  Demande : {sum(d.longueur*d.quantite for d in debits):.1f} m, "
          f"Offre : {sum(g.longueur for g in grumes):.1f} m")
    r = solveur_couple_cpsat(debits, grumes, time_limit_s=15)
    print(f"  {r.nom_algo}, durée {r.duree_s:.2f}s")
    print(f"  bois utilisé : {r.bois_utilise:.2f}/{r.bois_total:.2f} m")
    for a in r.allocations:
        if a.coupes:
            cp = [f"{c.debit_nom}({c.section[0]*100:.0f}×{c.section[1]*100:.0f})"
                  for c in a.coupes]
            print(f"    {a.grume_id}: {len(a.coupes)} coupes — {cp}")

    print("\n=== Cas 2 : demande dépasse l'offre ===")
    petites_grumes = [Grume("G1", 3.0, 0.40)]
    grosse_demande = [Debit("Long", 5.0, 0.20, 0.20, 1)]
    r = solveur_couple_cpsat(grosse_demande, petites_grumes)
    print(f"  {r.nom_algo}")
    print(f"  statut : {r.statut}")