"""Comparaison 1D pur vs solveur couplé 1D+2D."""

from app import engine, pattern


def comparer(nom, grumes, debits):
    print(f"\n{'='*60}")
    print(f"  {nom}")
    print(f"{'='*60}")
    print(f"  Demande : {sum(d.longueur*d.quantite for d in debits):.1f} m")
    print(f"  Offre   : {sum(g.longueur for g in grumes):.1f} m "
          f"({len(grumes)} grumes)")

    print(f"\n  {'Algo':<28} {'Util.':>7} {'Chute':>8} {'Grumes':>7} {'NA':>4} {'ms':>7}")
    print("  " + "-" * 64)

    # 1D
    for nom_algo, algo in engine.ALGOS.items():
        if "CP-SAT" in nom_algo:
            r = algo(debits, grumes, time_limit_s=10)
        else:
            r = algo(debits, grumes)
        if r is None:
            continue
        n_grumes_used = sum(1 for a in r.allocations if a.coupes)
        print(f"  {nom_algo:<28} "
              f"{r.taux_utilisation*100:>6.1f}% "
              f"{r.chute_totale:>7.2f}m "
              f"{n_grumes_used:>7} "
              f"{len(r.debits_non_alloues):>4} "
              f"{r.duree_s*1000:>6.1f}")

    # Couplé
    r = pattern.solveur_couple_cpsat(debits, grumes, time_limit_s=20)
    if r is not None:
        n_used = sum(1 for a in r.allocations if a.coupes)
        print(f"  {r.nom_algo:<28} "
              f"{r.taux_utilisation*100:>6.1f}% "
              f"{r.chute_totale:>7.2f}m "
              f"{n_used:>7} "
              f"{len(r.debits_non_alloues):>4} "
              f"{r.duree_s*1000:>6.1f}")
        # Détail par grume utilisée pour le couplé
        print("\n  Détail couplé :")
        for a in r.allocations:
            if not a.coupes:
                continue
            pat = getattr(a, "pattern", None)
            pat_name = pat.nom if pat else "?"
            sections_uniques = sorted({(c.section[0], c.section[1])
                                        for c in a.coupes})
            print(f"    {a.grume_id} (Ø{a.grume_diametre*100:.0f}, "
                  f"L={a.grume_longueur:.1f}m): pattern « {pat_name} »")
            print(f"       {len(a.coupes)} coupes, "
                  f"{len(sections_uniques)} sections distinctes "
                  f"({len(pat.rails) if pat else '?'} rails)")


# Cas A : où le 1D pur galère parce qu'il n'utilise qu'1 section/grume
comparer(
    "Cas A : chevrons en parallèle (1D ne peut pas)",
    grumes=[engine.Grume(f"G{i}", 6.0, 0.50) for i in range(1, 4)],
    debits=[
        engine.Debit("Sablière",  5.5, 0.22, 0.22, 1),
        engine.Debit("Chevron",   2.5, 0.08, 0.08, 6),  # 6 chevrons, 1 grume Ø50 en tient 4 en parallèle
    ],
)

# Cas B : matière juste, le couplé doit finasser
comparer(
    "Cas B : matière juste, multi-section",
    grumes=[
        engine.Grume("G1", 6.0, 0.50),
        engine.Grume("G2", 5.5, 0.45),
        engine.Grume("G3", 4.5, 0.42),
    ],
    debits=[
        engine.Debit("Sablière",   5.0, 0.22, 0.22, 1),
        engine.Debit("Poteau",     3.0, 0.20, 0.20, 2),
        engine.Debit("Arbalétrier", 4.0, 0.18, 0.18, 1),
        engine.Debit("Chevron",    2.0, 0.08, 0.08, 4),
    ],
)

# Cas C : Demande > offre → infaisable (test du garde-fou)
comparer(
    "Cas C : demande > offre (le couplé doit STOP)",
    grumes=[engine.Grume("G1", 4.0, 0.40)],
    debits=[engine.Debit("Long", 5.0, 0.20, 0.20, 2)],
)
