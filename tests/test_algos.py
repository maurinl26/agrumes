"""Tests des trois algorithmes sur plusieurs instances."""

from app import engine
from app.engine import Grume, Debit


def stress_test(nom, grumes, debits, time_limit=5):
    print(f"\n{'='*60}")
    print(f"  {nom}")
    print(f"{'='*60}")
    print(f"  Grumes : {len(grumes)} pièces, "
          f"{sum(g.longueur for g in grumes):.2f} m total")
    nb_pieces = sum(d.quantite for d in debits)
    long_demande = sum(d.longueur * d.quantite for d in debits)
    print(f"  Débits : {nb_pieces} pièces, {long_demande:.2f} m demandés")

    print(f"\n  {'Algorithme':<28} {'Util.':>8} {'Chute':>8} {'NA':>4} {'ms':>7}")
    print("  " + "-" * 60)

    for nom_algo, algo in engine.ALGOS.items():
        if "CP-SAT" in nom_algo:
            r = algo(debits, grumes, time_limit_s=time_limit)
        else:
            r = algo(debits, grumes)
        if r is None:
            print(f"  {nom_algo:<28} -- OR-Tools absent --")
            continue
        print(f"  {r.nom_algo:<28} "
              f"{r.taux_utilisation*100:>7.1f}% "
              f"{r.chute_totale:>7.2f}m "
              f"{len(r.debits_non_alloues):>4} "
              f"{r.duree_s*1000:>6.1f}")


# Instance 1 : matière abondante, devrait tout placer
stress_test(
    "Cas 1 : matière abondante",
    grumes=[Grume(f"G{i}", 5.0 + (i % 4) * 0.5, 0.40 + (i % 3) * 0.04)
            for i in range(12)],
    debits=[
        Debit("Sablière",    5.0, 0.20, 0.20, 2),
        Debit("Poteau",      3.0, 0.20, 0.20, 4),
        Debit("Entrait",     5.0, 0.22, 0.22, 1),
        Debit("Arbalétrier", 4.0, 0.18, 0.18, 2),
    ],
)

# Instance 2 : matière juste, où l'optimum compte vraiment
stress_test(
    "Cas 2 : matière juste (l'optimum compte)",
    grumes=[
        Grume("G1", 5.5, 0.45),
        Grume("G2", 5.5, 0.45),
        Grume("G3", 5.5, 0.42),
        Grume("G4", 4.0, 0.40),
        Grume("G5", 4.0, 0.38),
    ],
    debits=[
        Debit("Long-A", 4.0, 0.18, 0.18, 1),
        Debit("Long-B", 3.5, 0.18, 0.18, 1),
        Debit("Mid",    2.5, 0.18, 0.18, 3),
        Debit("Court",  1.5, 0.15, 0.15, 4),
        Debit("Mini",   1.0, 0.12, 0.12, 3),
    ],
)

# Instance 3 : cas piège classique pour les heuristiques gloutonnes
# 5 grumes de 6m, débits qui se complètent par paires (5+1, 4+2, 3+3...)
stress_test(
    "Cas 3 : appariements optimaux (piège pour FFD/BFD)",
    grumes=[Grume(f"G{i}", 6.0, 0.45) for i in range(1, 6)],
    debits=[
        Debit("A", 5.0, 0.20, 0.20, 1),
        Debit("B", 4.0, 0.20, 0.20, 1),
        Debit("C", 3.0, 0.20, 0.20, 2),
        Debit("D", 2.0, 0.20, 0.20, 1),
        Debit("E", 1.0, 0.20, 0.20, 1),
    ],
    time_limit=5,
)

# Instance 4 : taille moyenne, vérifier que CP-SAT scale
stress_test(
    "Cas 4 : taille moyenne (50 débits, 20 grumes)",
    grumes=[Grume(f"G{i}", 5.0 + (i*0.137) % 2.0, 0.38 + (i*0.07) % 0.12)
            for i in range(20)],
    debits=[
        Debit("Type-A", 4.5, 0.20, 0.20, 8),
        Debit("Type-B", 3.0, 0.18, 0.18, 12),
        Debit("Type-C", 2.0, 0.15, 0.15, 15),
        Debit("Type-D", 5.0, 0.22, 0.22, 5),
        Debit("Type-E", 1.5, 0.12, 0.12, 10),
    ],
    time_limit=10,
)
