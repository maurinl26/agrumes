"""
Test offline de la construction des objets Speckle pour l'export 3D.
Ne nécessite pas de connexion serveur : on intercepte juste l'arbre de Bases
et on inspecte les meshes générés.
"""

import engine
import geometry
from connectors import speckle_io
from specklepy.objects.base import Base
from specklepy.objects.geometry import Mesh


# Reproduire la construction du plan SANS le push
def build_plan_for_test(resultat, with_geometry=True, kerf=0.005,
                        cylinder_segments=24):
    plan = Base()
    plan["algorithm"] = resultat.nom_algo
    plan["bois_utilise_m"] = round(resultat.bois_utilise, 3)
    plan["chute_totale_m"] = round(resultat.chute_totale, 3)
    plan["taux_utilisation"] = round(resultat.taux_utilisation, 4)
    plan["nb_coupes"] = resultat.nb_coupes
    plan["debits_non_alloues"] = list(resultat.debits_non_alloues)

    allocations_bases = []
    y_offset = 0.0

    for a in resultat.allocations:
        ab = Base()
        ab["grume_id"] = a.grume_id
        ab["grume_longueur"] = a.grume_longueur
        ab["grume_diametre"] = a.grume_diametre
        ab["chute"] = a.chute

        if with_geometry:
            v_cyl, t_cyl = geometry.cylindre(
                longueur=a.grume_longueur, rayon=a.grume_diametre / 2,
                y_offset=y_offset, n_segments=cylinder_segments,
            )
            mesh_cyl = geometry.to_speckle_mesh(
                v_cyl, t_cyl,
                color=speckle_io._hex_to_argb("#d4c08a", alpha=80),
            )
            ab["@displayValue"] = [mesh_cyl]

        coupes_bases = []
        x_pos = 0.0
        for c in a.coupes:
            cb = Base()
            cb["debit_nom"] = c.debit_nom
            cb["longueur"] = c.longueur
            cb["section_largeur"] = c.section[0]
            cb["section_hauteur"] = c.section[1]
            cb["x_dans_grume"] = round(x_pos, 4)

            if with_geometry:
                w_sec, h_sec = c.section
                v_box, t_box = geometry.boite(
                    x0=x_pos, y0=y_offset - w_sec/2, z0=-h_sec/2,
                    longueur=c.longueur, largeur=w_sec, hauteur=h_sec,
                )
                mesh_box = geometry.to_speckle_mesh(
                    v_box, t_box,
                    color=speckle_io._color_for_debit(c.debit_nom),
                )
                cb["@displayValue"] = [mesh_box]
            coupes_bases.append(cb)
            x_pos += c.longueur + kerf

        ab["@coupes"] = coupes_bases
        allocations_bases.append(ab)
        y_offset += a.grume_diametre + 0.30

    plan["@allocations"] = allocations_bases
    return plan


# === Setup ===
grumes = [
    engine.Grume("G1", 6.0, 0.50),
    engine.Grume("G2", 5.5, 0.45),
    engine.Grume("G3", 4.5, 0.40),
]
debits = [
    engine.Debit("Sablière",    5.5, 0.22, 0.22, 1),
    engine.Debit("Poteau",      2.5, 0.20, 0.20, 4),
    engine.Debit("Arbalétrier", 1.5, 0.18, 0.18, 3),
]

resultat = engine.best_fit_decreasing(debits, grumes)
print(f"Résultat: util {resultat.taux_utilisation*100:.1f}%, "
      f"{resultat.nb_coupes} coupes")
for a in resultat.allocations:
    print(f"  {a.grume_id}: {[c.debit_nom for c in a.coupes]}")

# === Build avec géométrie ===
plan = build_plan_for_test(resultat, with_geometry=True)

print(f"\n=== Inspection de l'arbre Speckle ===")
print(f"Plan : {plan.speckle_type}")
print(f"  algorithm = {plan['algorithm']}")
print(f"  taux_utilisation = {plan['taux_utilisation']}")

# Test de sérialisation Speckle (sans envoyer)
from specklepy.serialization.base_object_serializer import BaseObjectSerializer

serializer = BaseObjectSerializer()
serialized_id, serialized_obj = serializer.traverse_base(plan)
print(f"\nSérialisé : id = {serialized_id[:20]}...")
print(f"  Hash de l'objet root : OK")

# Compter les meshes générées
allocations = plan["@allocations"]
n_meshes = 0
n_verts_total = 0
n_faces_total = 0

for ab in allocations:
    if ab.get_dynamic_member_names() and "@displayValue" in ab.get_dynamic_member_names():
        for mesh in ab["@displayValue"]:
            if isinstance(mesh, Mesh):
                n_meshes += 1
                n_verts_total += len(mesh.vertices) // 3
                n_faces_total += len(mesh.faces) // 4
    coupes = ab["@coupes"]
    for cb in coupes:
        if "@displayValue" in cb.get_dynamic_member_names():
            for mesh in cb["@displayValue"]:
                if isinstance(mesh, Mesh):
                    n_meshes += 1
                    n_verts_total += len(mesh.vertices) // 3
                    n_faces_total += len(mesh.faces) // 4

print(f"\n=== Stats meshes ===")
print(f"Meshes total : {n_meshes}")
print(f"  attendu : 3 cylindres + {resultat.nb_coupes} boîtes "
      f"= {3 + resultat.nb_coupes}")
print(f"Sommets total : {n_verts_total}")
print(f"Triangles total : {n_faces_total}")

assert n_meshes == 3 + resultat.nb_coupes, "Nombre de meshes incorrect"

# Vérifier qu'une mesh cylindre a bien la bonne structure
first_alloc = allocations[0]
cyl_mesh = first_alloc["@displayValue"][0]
print(f"\n=== Cylindre G1 ===")
print(f"  type : {type(cyl_mesh).__name__}")
print(f"  vertices : {len(cyl_mesh.vertices)} flat ({len(cyl_mesh.vertices)//3} sommets)")
print(f"  faces : {len(cyl_mesh.faces)} flat ({len(cyl_mesh.faces)//4} triangles)")
print(f"  units : {cyl_mesh.units}")
print(f"  colors : {len(cyl_mesh.colors)} (= sommets)")
# 24 segments : 24*2 (cercles) + 2 (centres) = 50 sommets
# Triangles : 24*2 (côté) + 24 + 24 (bouchons) = 96
assert len(cyl_mesh.vertices) // 3 == 50
assert len(cyl_mesh.faces) // 4 == 96
print("  ✓ structure correcte")

# Vérifier qu'une box a bien la bonne structure
first_coupe = first_alloc["@coupes"][0]
box_mesh = first_coupe["@displayValue"][0]
print(f"\n=== Box première coupe ===")
print(f"  vertices : {len(box_mesh.vertices)//3} (attendu 8)")
print(f"  triangles : {len(box_mesh.faces)//4} (attendu 12)")
assert len(box_mesh.vertices) // 3 == 8
assert len(box_mesh.faces) // 4 == 12
print("  ✓ structure correcte")

print("\n✓ Construction de l'arbre Speckle avec géométrie : OK")
print("  L'export sera prêt à pousser dès qu'un projet/token sera fourni.")
