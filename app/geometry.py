"""
Génération de meshes 3D génériques (cylindres, boîtes).

Le format pivot est :
    vertices : list[(x, y, z)]              # liste de tuples
    triangles : list[(i, j, k)]             # liste d'indices triangulaires

Deux adaptateurs :
- to_plotly_mesh3d(vertices, triangles)  -> dict pour go.Mesh3d(**dict)
- to_speckle_mesh(vertices, triangles)   -> Mesh Speckle (si specklepy dispo)

Les meshes générés sont volontairement simples : assez fins pour être lisibles
en Streamlit, pas trop pour rester légers à l'export.
"""

from __future__ import annotations
import math


# ========== Génération de meshes ==========

def cylindre(longueur: float, rayon: float,
             x_offset: float = 0.0, y_offset: float = 0.0,
             n_segments: int = 24) -> tuple:
    """
    Cylindre orienté selon l'axe X (longueur le long de X), centré en y/z.

    Returns:
        (vertices, triangles) où vertices = [(x,y,z), ...] et
        triangles = [(i,j,k), ...]
    """
    vertices = []
    triangles = []

    # Cercles aux deux bouts (N points chacun)
    for end_idx in (0, 1):
        x = x_offset + end_idx * longueur
        for n in range(n_segments):
            theta = 2 * math.pi * n / n_segments
            vertices.append((x, y_offset + rayon * math.cos(theta),
                             rayon * math.sin(theta)))

    # Surface latérale : 2 triangles par segment
    for n in range(n_segments):
        n_next = (n + 1) % n_segments
        a = n
        b = n_next
        c = n + n_segments
        d = n_next + n_segments
        triangles.append((a, b, c))   # a-b-c
        triangles.append((b, d, c))   # b-d-c

    # Centres des deux disques (pour les bouchons)
    c_start = len(vertices)
    vertices.append((x_offset, y_offset, 0.0))
    c_end = len(vertices)
    vertices.append((x_offset + longueur, y_offset, 0.0))

    # Bouchon début (normale vers -x : ordre inverse)
    for n in range(n_segments):
        n_next = (n + 1) % n_segments
        triangles.append((c_start, n_next, n))
    # Bouchon fin (normale vers +x)
    for n in range(n_segments):
        n_next = (n + 1) % n_segments
        triangles.append((c_end, n + n_segments, n_next + n_segments))

    return vertices, triangles


def boite(x0: float, y0: float, z0: float,
          longueur: float, largeur: float, hauteur: float) -> tuple:
    """
    Boîte axis-aligned, coin bas-gauche-arrière en (x0, y0, z0).

    Convention : longueur le long de X, largeur Y, hauteur Z.
    """
    L, W, H = longueur, largeur, hauteur
    # 8 sommets
    vertices = [
        (x0,     y0,     z0),       # 0
        (x0+L,   y0,     z0),       # 1
        (x0+L,   y0+W,   z0),       # 2
        (x0,     y0+W,   z0),       # 3
        (x0,     y0,     z0+H),     # 4
        (x0+L,   y0,     z0+H),     # 5
        (x0+L,   y0+W,   z0+H),     # 6
        (x0,     y0+W,   z0+H),     # 7
    ]
    # 12 triangles (2 par face), normales sortantes
    triangles = [
        (0, 3, 2), (0, 2, 1),       # bottom (z=z0)
        (4, 5, 6), (4, 6, 7),       # top (z=z0+H)
        (0, 1, 5), (0, 5, 4),       # front (y=y0)
        (2, 3, 7), (2, 7, 6),       # back (y=y0+W)
        (0, 4, 7), (0, 7, 3),       # left (x=x0)
        (1, 2, 6), (1, 6, 5),       # right (x=x0+L)
    ]
    return vertices, triangles


# ========== Adaptateur Plotly ==========

def to_plotly_mesh3d(vertices, triangles, color="#888", opacity=1.0,
                     name="", showlegend=False, hovertext=None):
    """Retourne un dict de paramètres pour go.Mesh3d(**dict)."""
    x = [v[0] for v in vertices]
    y = [v[1] for v in vertices]
    z = [v[2] for v in vertices]
    i = [t[0] for t in triangles]
    j = [t[1] for t in triangles]
    k = [t[2] for t in triangles]
    out = dict(
        x=x, y=y, z=z, i=i, j=j, k=k,
        color=color, opacity=opacity,
        name=name, showlegend=showlegend,
        flatshading=True,
    )
    if hovertext:
        out["hovertext"] = hovertext
        out["hoverinfo"] = "text"
    return out


# ========== Adaptateur Speckle ==========

def to_speckle_mesh(vertices, triangles, color: int = 0xFFCCCCCC):
    """
    Convertit en Mesh Speckle (specklepy doit être installé).

    color : int ARGB (par défaut beige clair)
    """
    try:
        from specklepy.objects.geometry import Mesh
    except ImportError:
        raise RuntimeError("specklepy non installé : impossible de produire "
                           "un Mesh Speckle.")

    # Format Speckle : vertices à plat [x1,y1,z1,x2,...]
    flat_vertices = []
    for v in vertices:
        flat_vertices.extend([float(v[0]), float(v[1]), float(v[2])])

    # Format Speckle : faces préfixées par leur taille [3,a,b,c, 3,d,e,f, ...]
    flat_faces = []
    for t in triangles:
        flat_faces.extend([3, int(t[0]), int(t[1]), int(t[2])])

    # Couleur uniforme par sommet
    n_verts = len(vertices)
    colors = [int(color)] * n_verts

    return Mesh(
        vertices=flat_vertices,
        faces=flat_faces,
        colors=colors,
        units="m",
    )


# ========== Auto-test ==========

if __name__ == "__main__":
    # Test cylindre
    v, t = cylindre(longueur=2.0, rayon=0.3, n_segments=8)
    print(f"Cylindre N=8 : {len(v)} sommets, {len(t)} triangles")
    # Pour N=8 segments : 16 (cercles) + 2 (centres) = 18 sommets
    # Triangles : 8*2 (côté) + 8 + 8 (bouchons) = 32 triangles
    assert len(v) == 18, f"sommets attendus 18, eu {len(v)}"
    assert len(t) == 32, f"triangles attendus 32, eu {len(t)}"

    # Test boîte
    v, t = boite(0, 0, 0, 1.0, 0.2, 0.2)
    print(f"Boîte : {len(v)} sommets, {len(t)} triangles")
    assert len(v) == 8 and len(t) == 12

    # Test bornes
    xs = [vv[0] for vv in v]
    ys = [vv[1] for vv in v]
    zs = [vv[2] for vv in v]
    assert min(xs) == 0 and max(xs) == 1.0
    assert min(ys) == 0 and max(ys) == 0.2
    assert min(zs) == 0 and max(zs) == 0.2

    # Test adaptateur Plotly
    d = to_plotly_mesh3d(v, t, color="red", name="test")
    assert "x" in d and "i" in d
    assert len(d["x"]) == 8 and len(d["i"]) == 12
    print("Adaptateur Plotly OK")

    # Test Speckle si dispo
    try:
        m = to_speckle_mesh(v, t)
        assert len(m.vertices) == 24  # 8 * 3
        assert len(m.faces) == 48     # 12 * 4 (3 + 3 indices)
        print("Adaptateur Speckle OK")
    except RuntimeError as e:
        print(f"Speckle skipped: {e}")

    print("✓ Tous les tests passent.")
