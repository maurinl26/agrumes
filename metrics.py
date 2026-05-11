"""
Bordereau de production opérationnel — métriques scierie.

Objectif : donner au scieur les chiffres clés pour décider, et comparer
les algorithmes sur les bons indicateurs (cubage, rendement matière,
mobilisation des grumes, simplicité de production).

Toutes les métriques de cubage sont en m³.
"""

import math
from dataclasses import dataclass


@dataclass
class MetriquesOps:
    """Bordereau de production pour un Resultat donné."""

    # ----- Cubage (m³) -----
    cubage_demande: float            # volume net total des débits demandés
    cubage_produit: float            # volume net effectivement produit
    cubage_grumes_dispo: float       # volume brut de toutes les grumes en stock
    cubage_grumes_utilisees: float   # volume brut des grumes activées
    cubage_grumes_reservees: float   # volume brut des grumes laissées en réserve
    cubage_chute: float              # volume perdu dans les grumes utilisées

    # ----- Rendements (fraction 0..1) -----
    rendement_matiere: float         # cubage_produit / cubage_grumes_utilisees
    couverture_demande: float        # cubage_produit / cubage_demande
    taux_mobilisation: float         # nb_grumes_utilisees / nb_grumes_dispo

    # ----- Production -----
    nb_grumes_utilisees: int
    nb_grumes_dispo: int
    nb_coupes: int                   # = nombre de tronçonnages = temps scierie
    nb_patterns_distincts: int       # nombre de schémas différents (= setups)

    # ----- Manquants -----
    nb_debits_non_alloues: int
    cubage_non_alloue: float         # volume non produit (cumulé)


def _vol_grume(g) -> float:
    return g.longueur * math.pi * (g.diametre / 2) ** 2


def _vol_unite_debit(d) -> float:
    return d.longueur * d.largeur * d.hauteur


def calculer_metriques(resultat, grumes_initiales, debits_demandes) -> MetriquesOps:
    """
    Construit un bordereau à partir d'un Resultat et des entrées originales.
    Compatible 1D pur ET solveur couplé.
    """
    # Cubage
    cubage_demande = sum(_vol_unite_debit(d) * d.quantite
                         for d in debits_demandes)
    cubage_produit = resultat.volume_utilise
    cubage_grumes_dispo = sum(_vol_grume(g) for g in grumes_initiales)
    cubage_grumes_utilisees = resultat.volume_grumes_actives
    cubage_grumes_reservees = cubage_grumes_dispo - cubage_grumes_utilisees
    cubage_chute = max(0.0, cubage_grumes_utilisees - cubage_produit)

    # Rendements
    rendement_matiere = (cubage_produit / cubage_grumes_utilisees
                         if cubage_grumes_utilisees > 0 else 0.0)
    couverture = (cubage_produit / cubage_demande
                  if cubage_demande > 0 else 0.0)
    taux_mobilisation = (resultat.nb_grumes_utilisees / len(grumes_initiales)
                         if grumes_initiales else 0.0)

    # Patterns distincts (mode couplé) ou défaut = nb grumes utilisées
    sigs = set()
    for a in resultat.allocations:
        pat = getattr(a, "pattern", None)
        if pat is not None and a.coupes:
            sigs.add(pat.signature())
    if sigs:
        nb_patterns = len(sigs)
    else:
        # Mode 1D pur : pas de notion de pattern, on prend le nb de
        # grumes utilisées comme proxy (chacune = 1 réglage scierie)
        nb_patterns = resultat.nb_grumes_utilisees

    # Cubage non alloué (1 entrée = 1 unité manquante).
    # expand_debits renomme en "Nom#1", "Nom#2"... pour les quantités > 1,
    # donc on strip le suffixe avant le lookup.
    debits_par_nom = {d.nom: d for d in debits_demandes}
    cubage_na = 0.0
    for nom in resultat.debits_non_alloues:
        nom_base = nom.split("#", 1)[0]
        d = debits_par_nom.get(nom_base)
        if d is not None:
            cubage_na += _vol_unite_debit(d)

    return MetriquesOps(
        cubage_demande=cubage_demande,
        cubage_produit=cubage_produit,
        cubage_grumes_dispo=cubage_grumes_dispo,
        cubage_grumes_utilisees=cubage_grumes_utilisees,
        cubage_grumes_reservees=cubage_grumes_reservees,
        cubage_chute=cubage_chute,
        rendement_matiere=rendement_matiere,
        couverture_demande=couverture,
        taux_mobilisation=taux_mobilisation,
        nb_grumes_utilisees=resultat.nb_grumes_utilisees,
        nb_grumes_dispo=len(grumes_initiales),
        nb_coupes=resultat.nb_coupes,
        nb_patterns_distincts=nb_patterns,
        nb_debits_non_alloues=len(resultat.debits_non_alloues),
        cubage_non_alloue=cubage_na,
    )


def formater_pour_dataframe(metriques_par_algo: list, noms_algos: list) -> list:
    """
    Formate une liste de (MetriquesOps, nom_algo) en lignes de dict
    prêtes à être passées à pd.DataFrame.
    """
    rows = []
    for m, nom in zip(metriques_par_algo, noms_algos):
        rows.append({
            "Algorithme": nom,
            "Cubage demande (m³)": round(m.cubage_demande, 3),
            "Cubage produit (m³)": round(m.cubage_produit, 3),
            "Cubage grumes mobilisé (m³)": round(m.cubage_grumes_utilisees, 3),
            "Cubage chute (m³)": round(m.cubage_chute, 3),
            "Rendement matière": f"{m.rendement_matiere*100:.1f}%",
            "Couverture demande": f"{m.couverture_demande*100:.1f}%",
            "Grumes mobilisées": f"{m.nb_grumes_utilisees}/{m.nb_grumes_dispo}",
            "Coupes": m.nb_coupes,
            "Setups (patterns)": m.nb_patterns_distincts,
            "Débits manquants": m.nb_debits_non_alloues,
        })
    return rows


# ----- Auto-test -----
if __name__ == "__main__":
    import engine
    import pattern

    grumes = [engine.Grume(f"G{i}", 6.0, 0.50) for i in range(1, 4)]
    debits = [
        engine.Debit("Sablière", 5.5, 0.22, 0.22, 1),
        engine.Debit("Chevron",  2.5, 0.08, 0.08, 6),
    ]

    print("=== Métriques 1D pur (FFD) ===")
    r1 = engine.first_fit_decreasing(debits, grumes)
    m1 = calculer_metriques(r1, grumes, debits)
    print(f"  Cubage demande      : {m1.cubage_demande:.3f} m³")
    print(f"  Cubage produit      : {m1.cubage_produit:.3f} m³")
    print(f"  Cubage grumes mobi. : {m1.cubage_grumes_utilisees:.3f} m³ "
          f"({m1.nb_grumes_utilisees}/{m1.nb_grumes_dispo})")
    print(f"  Cubage chute        : {m1.cubage_chute:.3f} m³")
    print(f"  Cubage manquant     : {m1.cubage_non_alloue:.3f} m³ "
          f"({m1.nb_debits_non_alloues} unités)")
    print(f"  Rendement matière   : {m1.rendement_matiere*100:.1f}%")
    print(f"  Couverture demande  : {m1.couverture_demande*100:.1f}%")
    print(f"  Taux mobilisation   : {m1.taux_mobilisation*100:.1f}%")
    print(f"  Setups scierie      : {m1.nb_patterns_distincts}")

    print("\n=== Métriques Couplé 1D+2D ===")
    r2 = pattern.solveur_couple_cpsat(debits, grumes, time_limit_s=15)
    m2 = calculer_metriques(r2, grumes, debits)
    print(f"  Cubage demande      : {m2.cubage_demande:.3f} m³")
    print(f"  Cubage produit      : {m2.cubage_produit:.3f} m³")
    print(f"  Cubage grumes mobi. : {m2.cubage_grumes_utilisees:.3f} m³ "
          f"({m2.nb_grumes_utilisees}/{m2.nb_grumes_dispo})")
    print(f"  Cubage chute        : {m2.cubage_chute:.3f} m³")
    print(f"  Cubage réservé      : {m2.cubage_grumes_reservees:.3f} m³ "
          f"(grumes non utilisées disponibles pour la prochaine fournée)")
    print(f"  Rendement matière   : {m2.rendement_matiere*100:.1f}%")
    print(f"  Couverture demande  : {m2.couverture_demande*100:.1f}%")
    print(f"  Taux mobilisation   : {m2.taux_mobilisation*100:.1f}%")
    print(f"  Setups scierie      : {m2.nb_patterns_distincts}")

    print("\n=== Comparaison ===")
    delta_grumes = m1.nb_grumes_utilisees - m2.nb_grumes_utilisees
    delta_cubage = m1.cubage_grumes_utilisees - m2.cubage_grumes_utilisees
    print(f"  Économie grumes : {delta_grumes} grumes "
          f"({delta_cubage:.3f} m³ de bois conservé)")
    print(f"  Δ rendement     : "
          f"{(m2.rendement_matiere - m1.rendement_matiere)*100:+.1f} pts")
    print(f"  Δ couverture    : "
          f"{(m2.couverture_demande - m1.couverture_demande)*100:+.1f} pts")
