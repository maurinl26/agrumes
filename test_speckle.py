"""Tests du connecteur Speckle (ne nécessitent pas de serveur)."""

from connectors.speckle_io import (
    is_available, parse_speckle_url, _aggregate,
    DEFAULT_DEBIT_KEYWORDS, DEFAULT_GRUME_KEYWORDS,
)
from engine import Debit


def assert_eq(actual, expected, label):
    status = "✅" if actual == expected else "❌"
    print(f"  {status} {label}")
    if actual != expected:
        print(f"     attendu  : {expected}")
        print(f"     obtenu   : {actual}")


print(f"\n=== specklepy disponible ? {is_available()} ===\n")

print("=== parse_speckle_url ===")

# Format moderne
r = parse_speckle_url("https://app.speckle.systems/projects/abc123/models/def456")
assert_eq(r["host"], "app.speckle.systems", "moderne: host")
assert_eq(r["project_id"], "abc123", "moderne: project_id")
assert_eq(r["model_id"], "def456", "moderne: model_id")
assert_eq(r["version_id"], None, "moderne: pas de version_id")

# Avec version
r = parse_speckle_url("https://app.speckle.systems/projects/abc123/models/def456@xyz789")
assert_eq(r["version_id"], "xyz789", "moderne avec @version")

# Format legacy
r = parse_speckle_url("https://speckle.xyz/streams/abc123/branches/main")
assert_eq(r["host"], "speckle.xyz", "legacy: host")
assert_eq(r["project_id"], "abc123", "legacy: stream->project_id")
assert_eq(r["model_id"], "main", "legacy: branch->model_id")

# Legacy sans branche
r = parse_speckle_url("https://speckle.xyz/streams/abc123")
assert_eq(r["project_id"], "abc123", "legacy nu: project_id")
assert_eq(r["model_id"], None, "legacy nu: pas de model_id")

# Legacy commit
r = parse_speckle_url("https://speckle.xyz/streams/abc123/commits/cmt456")
assert_eq(r["version_id"], "cmt456", "legacy: commit->version_id")

print()
print("=== _aggregate ===")
debits = [
    Debit("Sablière", 5.0, 0.20, 0.20, 1),
    Debit("Sablière", 5.0, 0.20, 0.20, 1),  # doublon
    Debit("Poteau",   3.0, 0.20, 0.20, 1),
    Debit("Sablière", 5.0, 0.20, 0.20, 1),  # encore un
    Debit("Poteau",   3.0, 0.20, 0.20, 1),
]
agg = _aggregate(debits)
agg_par_nom = {d.nom: d.quantite for d in agg}
assert_eq(agg_par_nom.get("Sablière"), 3, "agrégation: 3 sablières")
assert_eq(agg_par_nom.get("Poteau"), 2, "agrégation: 2 poteaux")
assert_eq(len(agg), 2, "agrégation: 2 entrées distinctes")

print()
print("=== keywords par défaut ===")
print(f"  débits : {DEFAULT_DEBIT_KEYWORDS}")
print(f"  grumes : {DEFAULT_GRUME_KEYWORDS}")

print()
print("=== Test simulation traversée Speckle ===")
# Simuler des objets Speckle Base avec les attributs typiques
if is_available():
    from specklepy.objects.base import Base
    from connectors.speckle_io import _traverse, _matches_type, _get_attr

    # Créer un mini-arbre simulé
    class FakeProfile:
        width = 0.20
        depth = 0.22

    root = Base()
    beam1 = Base()
    beam1["speckle_type"] = "Objects.BuiltElements.Beam"
    beam1.name = "Sablière"
    beam1.length = 5.0
    beam1["profile"] = FakeProfile()  # attribut dynamique

    column1 = Base()
    column1["speckle_type"] = "Objects.BuiltElements.Column"
    column1.name = "Poteau"
    column1.length = 3.0
    column1["profile"] = FakeProfile()

    root["@elements"] = [beam1, column1]

    # Traverser
    objs = list(_traverse(root))
    print(f"  Objets traversés : {len(objs)} (root + 2 enfants attendus)")

    # Filtrer
    beams_cols = [o for o in objs if _matches_type(o, ["Beam", "Column"])]
    print(f"  Beam/Column trouvés : {len(beams_cols)}")
    for b in beams_cols:
        nom = _get_attr(b, "name")
        l = _get_attr(b, "length", "baseLine.length")
        w = _get_attr(b, "profile.width")
        h = _get_attr(b, "profile.depth", "profile.height")
        print(f"    - {nom}: L={l}m, section={w}×{h}")
else:
    print("  (skipped, specklepy non installé)")

print("\n✓ Tests terminés.")
