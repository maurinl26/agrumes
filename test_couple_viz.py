"""Validation visuelle de la viz couplée."""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import plotly.graph_objects as go
from collections import defaultdict

import engine, equarissage, geometry, pattern


# Réplique des fonctions de viz d'app.py
PALETTE = ["#A8D5BA", "#F2C078", "#F2A07B", "#A1C9F4", "#FFB7B2",
           "#B5A8D9", "#FFD3B6", "#C7CEEA", "#B6E2D3", "#FAB1A0"]


def color_for(name):
    base = name.split("#")[0]
    return PALETTE[sum(ord(c) for c in base) % len(PALETTE)]


def figure_3d(resultat, kerf=0.005):
    fig = go.Figure()
    y_offset = 0.0
    for a in resultat.allocations:
        if not a.coupes:  # skip grumes vides
            continue
        # Cylindre
        v, t = geometry.cylindre(a.grume_longueur, a.grume_diametre/2,
                                  y_offset=y_offset, n_segments=24)
        fig.add_trace(go.Mesh3d(**geometry.to_plotly_mesh3d(
            v, t, color="#d4c08a", opacity=0.20, name=a.grume_id,
            hovertext=f"{a.grume_id}<br>L={a.grume_longueur:.2f}m<br>"
                      f"Ø={a.grume_diametre*100:.0f}cm"
        )))
        # Coupes regroupées par rail
        coupes_par_rail = defaultdict(list)
        for c in a.coupes:
            rk = (c.rail_x, c.rail_y, c.section[0], c.section[1])
            coupes_par_rail[rk].append(c)
        for rk, coupes_rail in coupes_par_rail.items():
            rail_x, rail_y, w_sec, h_sec = rk
            if rail_x is None:
                rail_x = -w_sec/2
                rail_y = -h_sec/2
            x_in = 0.0
            for c in coupes_rail:
                v_box, t_box = geometry.boite(
                    x0=x_in, y0=y_offset+rail_x, z0=rail_y,
                    longueur=c.longueur, largeur=w_sec, hauteur=h_sec,
                )
                fig.add_trace(go.Mesh3d(**geometry.to_plotly_mesh3d(
                    v_box, t_box, color=color_for(c.debit_nom),
                    opacity=0.95, name=c.debit_nom,
                    hovertext=f"{c.debit_nom}<br>L={c.longueur:.2f}m"
                )))
                x_in += c.longueur + kerf
        y_offset += a.grume_diametre + 0.30
    fig.update_layout(
        scene=dict(aspectmode="data",
                   camera=dict(eye=dict(x=1.5, y=-2, z=1)),
                   xaxis_title="L (m)", yaxis_title="y", zaxis_title="z"),
        margin=dict(l=0, r=0, t=10, b=0), height=600,
    )
    return fig


def figure_section_grume(diametre, rails_avec_coupes, titre):
    """rails_avec_coupes : list of (Rail, n_coupes)"""
    import math
    fig, ax = plt.subplots(figsize=(7, 7))
    R = diametre / 2
    ax.add_patch(plt.Circle((0,0), R, facecolor="#f4ecd8",
                            edgecolor="#5a4a2a", linewidth=2))
    for r in (R*0.85, R*0.65, R*0.45, R*0.25):
        ax.add_patch(plt.Circle((0,0), r, fill=False, edgecolor="#c8b88a",
                                linewidth=0.5, linestyle="--"))
    ax.plot(0, 0, marker="+", markersize=14, color="#5a4a2a", markeredgewidth=2)
    n_rails = len(rails_avec_coupes)
    cmap = plt.cm.Set2.colors
    for i, (rail, n_coupes) in enumerate(rails_avec_coupes):
        ax.add_patch(mpatches.Rectangle(
            (rail.x, rail.y), rail.largeur, rail.hauteur,
            facecolor=cmap[i % len(cmap)], edgecolor="black"))
        if min(rail.largeur, rail.hauteur) > 0.04:
            ax.text(rail.x + rail.largeur/2, rail.y + rail.hauteur/2,
                    f"{rail.largeur*100:.0f}×{rail.hauteur*100:.0f}\n×{n_coupes}",
                    ha="center", va="center", fontsize=9, fontweight="bold")
    margin = R * 0.15
    ax.set_xlim(-R-margin, R+margin); ax.set_ylim(-R-margin, R+margin)
    ax.set_aspect("equal")
    ax.set_title(titre)
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    return fig


# === Setup : cas où le couplé brille ===
grumes = [engine.Grume(f"G{i}", 6.0, 0.50) for i in range(1, 4)]
debits = [
    engine.Debit("Sablière", 5.5, 0.22, 0.22, 1),
    engine.Debit("Chevron",  2.5, 0.08, 0.08, 6),
]

print("=== Lancement du couplé ===")
r = pattern.solveur_couple_cpsat(debits, grumes, time_limit_s=20)
print(f"  {r.nom_algo}, durée {r.duree_s:.1f}s, util volumique "
      f"{r.taux_volumique*100:.1f}%")
print(f"  {r.nb_grumes_utilisees} grume(s) sur {len(grumes)} utilisée(s)")

for a in r.allocations:
    if not a.coupes:
        continue
    pat = getattr(a, "pattern", None)
    print(f"  {a.grume_id}: {len(a.coupes)} coupes, "
          f"pattern={pat.nom if pat else '?'}, {len(pat.rails) if pat else '?'} rails")

# Génération viz
fig3d = figure_3d(r)
fig3d.write_html("/tmp/test_couple_3d.html")
print(f"\n✓ 3D HTML : /tmp/test_couple_3d.html")

# Pour chaque grume utilisée, dessiner sa section
for a in r.allocations:
    if not a.coupes:
        continue
    pat = getattr(a, "pattern", None)
    if pat is None:
        continue
    # rail -> nb coupes dans ce rail
    rails_count = []
    for r_obj in pat.rails:
        n = sum(1 for c in a.coupes
                if c.rail_x is not None
                and abs(c.rail_x - r_obj.x) < 1e-3
                and abs(c.rail_y - r_obj.y) < 1e-3)
        rails_count.append((r_obj, n))
    fig = figure_section_grume(
        a.grume_diametre, rails_count,
        f"{a.grume_id} — {pat.nom} — taux 2D: {pat.taux_section*100:.1f}%",
    )
    fig.savefig(f"/tmp/test_couple_section_{a.grume_id}.png",
                dpi=100, bbox_inches="tight")
    print(f"✓ Section {a.grume_id} : /tmp/test_couple_section_{a.grume_id}.png")
