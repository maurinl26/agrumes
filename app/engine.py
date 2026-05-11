"""
Moteur d'optimisation grumes -> débits pour charpente.

Trois algorithmes sont fournis :
- First-Fit Decreasing (FFD) : heuristique classique, rapide
- Best-Fit Decreasing (BFD) : heuristique souvent meilleure que FFD
- CP-SAT (OR-Tools) : recherche d'optimum (ou solution prouvée bonne) sous limite de temps

Pourquoi pas A* ?
A* est imbattable sur des graphes avec une heuristique admissible serrée.
Ici l'espace d'états (toutes les affectations partielles débits -> grumes) explose
combinatoirement et toute heuristique admissible utile est très lâche.
CP-SAT (programmation par contraintes + LP relaxation + branch & bound interne)
exploite bien mieux la structure du problème.
"""

from dataclasses import dataclass, field
from typing import Optional
import time
import math


# Trait de scie : 5 mm, à ajuster selon la lame utilisée
KERF = 0.005


# ========== Modèle de données ==========

@dataclass
class Debit:
    """Une pièce à débiter dans la charpente."""
    nom: str
    longueur: float    # mètres
    largeur: float     # mètres (section)
    hauteur: float     # mètres (section)
    quantite: int = 1


@dataclass
class Grume:
    """Une grume (tronc) disponible."""
    id: str
    longueur: float
    diametre: float


@dataclass
class Coupe:
    """Une coupe placée dans une grume."""
    debit_nom: str
    longueur: float
    section: tuple    # (largeur, hauteur)
    # Coordonnées (m, repère centré sur le cœur du disque) du rail dans
    # lequel la coupe est tirée. None pour les solveurs 1D purs (rétro-compat).
    rail_x: Optional[float] = None
    rail_y: Optional[float] = None


@dataclass
class Allocation:
    """Le résultat pour une grume : quelles coupes y sont placées."""
    grume_id: str
    grume_longueur: float
    grume_diametre: float
    coupes: list = field(default_factory=list)

    @property
    def longueur_utilisee(self) -> float:
        # 1 trait de scie consommé par coupe (sur-estimation prudente)
        return sum(c.longueur for c in self.coupes) + len(self.coupes) * KERF

    @property
    def chute(self) -> float:
        return max(0.0, self.grume_longueur - self.longueur_utilisee)


@dataclass
class Resultat:
    """Le résultat global d'un algorithme."""
    nom_algo: str
    allocations: list
    debits_non_alloues: list
    duree_s: float
    statut: str = ""

    @property
    def chute_totale(self) -> float:
        return sum(a.chute for a in self.allocations)

    @property
    def bois_utilise(self) -> float:
        return sum(sum(c.longueur for c in a.coupes) for a in self.allocations)

    @property
    def bois_total(self) -> float:
        return sum(a.grume_longueur for a in self.allocations)

    @property
    def taux_utilisation(self) -> float:
        if self.bois_total == 0:
            return 0.0
        return self.bois_utilise / self.bois_total

    @property
    def nb_coupes(self) -> int:
        return sum(len(a.coupes) for a in self.allocations)

    # ----- Métriques volumiques (pertinentes en mode couplé) -----

    @property
    def volume_utilise(self) -> float:
        """Volume de bois effectivement débité (m³)."""
        return sum(c.longueur * c.section[0] * c.section[1]
                   for a in self.allocations for c in a.coupes)

    @property
    def volume_grumes_actives(self) -> float:
        """Volume cylindrique brut des grumes utilisées (m³)."""
        import math
        return sum(a.grume_longueur * math.pi * (a.grume_diametre / 2) ** 2
                   for a in self.allocations if a.coupes)

    @property
    def taux_volumique(self) -> float:
        """Volume débité / volume des grumes utilisées."""
        v = self.volume_grumes_actives
        return self.volume_utilise / v if v > 0 else 0.0

    @property
    def nb_grumes_utilisees(self) -> int:
        return sum(1 for a in self.allocations if a.coupes)


# ========== Helpers ==========

def expand_debits(debits: list) -> list:
    """Développe les quantités > 1 en débits unitaires."""
    out = []
    for d in debits:
        if d.quantite <= 0:
            continue
        if d.quantite == 1:
            out.append(Debit(d.nom, d.longueur, d.largeur, d.hauteur, 1))
        else:
            for i in range(d.quantite):
                out.append(Debit(f"{d.nom}#{i+1}", d.longueur,
                                 d.largeur, d.hauteur, 1))
    return out


def section_compatible(d: Debit, diametre: float) -> bool:
    """
    Le rectangle (largeur x hauteur) doit s'inscrire dans le disque
    de la grume. Sa diagonale doit être <= diamètre.
    """
    diag = math.hypot(d.largeur, d.hauteur)
    return diag <= diametre


def reste_grume(a: Allocation) -> float:
    return a.grume_longueur - a.longueur_utilisee


def peut_placer(d: Debit, a: Allocation) -> bool:
    if not section_compatible(d, a.grume_diametre):
        return False
    # Une coupe en plus consomme un trait de scie
    return d.longueur + KERF <= reste_grume(a) + (KERF if not a.coupes else 0)
    # NB : la première coupe peut "remplacer" un kerf déjà compté


# ========== Algorithmes ==========

def first_fit_decreasing(debits: list, grumes: list) -> Resultat:
    """Trie les débits par longueur décroissante, place chacun
    dans la première grume compatible."""
    t0 = time.time()
    debits_unit = sorted(expand_debits(debits), key=lambda d: -d.longueur)
    allocations = [Allocation(g.id, g.longueur, g.diametre) for g in grumes]
    non_alloues = []

    for d in debits_unit:
        place = False
        for a in allocations:
            if peut_placer(d, a):
                a.coupes.append(Coupe(d.nom, d.longueur, (d.largeur, d.hauteur)))
                place = True
                break
        if not place:
            non_alloues.append(d.nom)

    return Resultat("First-Fit Decreasing", allocations, non_alloues,
                    time.time() - t0)


def best_fit_decreasing(debits: list, grumes: list) -> Resultat:
    """Trie par longueur décroissante, place chacun dans la grume
    compatible qui laissera le moins de chute (meilleur ajustement)."""
    t0 = time.time()
    debits_unit = sorted(expand_debits(debits), key=lambda d: -d.longueur)
    allocations = [Allocation(g.id, g.longueur, g.diametre) for g in grumes]
    non_alloues = []

    for d in debits_unit:
        meilleure = None
        meilleur_reste = float('inf')
        for a in allocations:
            if peut_placer(d, a):
                reste_apres = reste_grume(a) - d.longueur - KERF
                if reste_apres < meilleur_reste:
                    meilleur_reste = reste_apres
                    meilleure = a
        if meilleure is not None:
            meilleure.coupes.append(Coupe(d.nom, d.longueur,
                                          (d.largeur, d.hauteur)))
        else:
            non_alloues.append(d.nom)

    return Resultat("Best-Fit Decreasing", allocations, non_alloues,
                    time.time() - t0)


def cp_sat_optimise(debits: list, grumes: list,
                    time_limit_s: float = 10.0) -> Optional[Resultat]:
    """
    Programmation par contraintes (OR-Tools CP-SAT).
    Maximise la longueur de bois utilisé sous contraintes
    de capacité de chaque grume et de compatibilité de section.

    Retourne None si OR-Tools n'est pas installé.
    """
    try:
        from ortools.sat.python import cp_model
    except ImportError:
        return None

    t0 = time.time()
    debits_unit = expand_debits(debits)

    model = cp_model.CpModel()

    # Variables : x[i,j] = 1 si débit i est affecté à grume j
    x = {}
    for i, d in enumerate(debits_unit):
        for j, g in enumerate(grumes):
            if section_compatible(d, g.diametre):
                # Vérifier qu'au moins la longueur peut tenir seule
                if d.longueur + KERF <= g.longueur:
                    x[i, j] = model.NewBoolVar(f"x_{i}_{j}")

    if not x:
        return Resultat("CP-SAT", [Allocation(g.id, g.longueur, g.diametre)
                                   for g in grumes],
                        [d.nom for d in debits_unit], time.time() - t0,
                        statut="aucune affectation possible")

    # Contrainte 1 : chaque débit affecté à au plus une grume
    for i in range(len(debits_unit)):
        keys = [(i, j) for j in range(len(grumes)) if (i, j) in x]
        if keys:
            model.Add(sum(x[k] for k in keys) <= 1)

    # Contrainte 2 : capacité de chaque grume (en mm pour rester en entiers)
    # Chaque coupe consomme (longueur + KERF) -- sur-estimation prudente
    for j, g in enumerate(grumes):
        keys = [(i, j) for i in range(len(debits_unit)) if (i, j) in x]
        if keys:
            model.Add(
                sum(int(round((debits_unit[i].longueur + KERF) * 1000))
                    * x[i, j] for (i, j) in keys)
                <= int(round(g.longueur * 1000))
            )

    # Objectif : maximiser le bois utilisé
    model.Maximize(
        sum(int(round(debits_unit[i].longueur * 1000)) * x[i, j]
            for (i, j) in x)
    )

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(time_limit_s)
    solver.parameters.num_search_workers = 4
    status = solver.Solve(model)

    statut_lbl = {
        cp_model.OPTIMAL: "optimal",
        cp_model.FEASIBLE: "faisable (limite de temps)",
        cp_model.INFEASIBLE: "infaisable",
        cp_model.UNKNOWN: "inconnu",
    }.get(status, "inconnu")

    allocations = [Allocation(g.id, g.longueur, g.diametre) for g in grumes]
    alloues = set()

    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        for (i, j), v in x.items():
            if solver.Value(v) == 1:
                d = debits_unit[i]
                allocations[j].coupes.append(
                    Coupe(d.nom, d.longueur, (d.largeur, d.hauteur))
                )
                alloues.add(i)

    non_alloues = [debits_unit[i].nom for i in range(len(debits_unit))
                   if i not in alloues]

    nom = f"CP-SAT ({statut_lbl})"
    return Resultat(nom, allocations, non_alloues, time.time() - t0,
                    statut=statut_lbl)


# Registre des algorithmes disponibles, exposé à l'UI
ALGOS = {
    "First-Fit Decreasing": first_fit_decreasing,
    "Best-Fit Decreasing": best_fit_decreasing,
    "CP-SAT (optimal)": cp_sat_optimise,
}


# ========== Auto-test ==========

if __name__ == "__main__":
    grumes_demo = [
        Grume("G1", 5.5, 0.45),
        Grume("G2", 4.2, 0.38),
        Grume("G3", 6.0, 0.50),
        Grume("G4", 4.8, 0.42),
        Grume("G5", 5.2, 0.40),
        Grume("G6", 4.5, 0.36),
        Grume("G7", 6.3, 0.48),
        Grume("G8", 3.8, 0.35),
        Grume("G9", 5.8, 0.44),
    ]
    debits_demo = [
        Debit("Sablière",    5.0, 0.20, 0.20, 2),
        Debit("Poteau",      3.0, 0.20, 0.20, 4),
        Debit("Entrait",     5.5, 0.22, 0.22, 1),
        Debit("Arbalétrier", 4.0, 0.18, 0.18, 2),
        Debit("Poinçon",     1.8, 0.18, 0.18, 1),
    ]

    print(f"Grumes : {sum(g.longueur for g in grumes_demo):.1f} m total")
    print(f"Débits : {sum(d.longueur*d.quantite for d in debits_demo):.1f} m total\n")

    for nom, algo in ALGOS.items():
        if "CP-SAT" in nom:
            r = algo(debits_demo, grumes_demo, time_limit_s=5)
        else:
            r = algo(debits_demo, grumes_demo)
        if r is None:
            print(f"{nom} : OR-Tools non installé")
            continue
        print(f"{nom}")
        print(f"  bois utilisé : {r.bois_utilise:.2f} m / {r.bois_total:.2f} m"
              f"  ({r.taux_utilisation*100:.1f}%)")
        print(f"  chute        : {r.chute_totale:.2f} m")
        print(f"  non alloués  : {len(r.debits_non_alloues)} {r.debits_non_alloues}")
        print(f"  durée        : {r.duree_s*1000:.1f} ms\n")
