"""Test des visualisations : 3D Plotly + section transversale 1D."""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import plotly.graph_objects as go

from app import engine, equarissage, geometry
from app.equarissage import Section


def figure_3d_plan_de_coupe(resultat, kerf=0.005):
    fig = go.Figure()
    palette = [
        "#A8D5BA", "#F2C078", "#F2A07B", "#A1C9F4", "#FFB7B2",
        "#B5A8D9", "#FFD3B6", "#C7CEEA", "#B6E2D3", "#FAB1A0",
    ]
    def color_for(n):
        base = n.split("#")[0]
        h = sum(ord(c) for c in base)
        return palette[h % len(palette)]

    y_offset = 0.0
    for a in resultat.allocations:
        v, t = geometry.cylindre(a.grume_longueur, a.grume_diametre/2,
                                  y_offset=y_offset, n_segments=24)
        fig.add_trace(go.Mesh3d(**geometry.to_plotly_mesh3d(
            v, t, color="#d4c08a", opacity=0.25, name=a.grume_id,
            hovertext=f"{a.grume_id}<br>L={a.grume_longueur:.2f}m"
        )))
        x_pos = 0.0
        for c in a.coupes:
            w_sec, h_sec = c.section
            v_box, t_box = geometry.boite(
                x0=x_pos, y0=y_offset - w_sec/2, z0=-h_sec/2,
                longueur=c.longueur, largeur=w_sec, hauteur=h_sec,
            )
            fig.add_trace(go.Mesh3d(**geometry.to_plotly_mesh3d(
                v_box, t_box, color=color_for(c.debit_nom), opacity=0.95,
                name=c.debit_nom,
                hovertext=f"{c.debit_nom}<br>L={c.longueur:.2f}m"
            )))
            x_pos += c.longueur + kerf
        y_offset += a.grume_diametre + 0.30

    fig.update_layout(
        scene=dict(aspectmode="data",
                   camera=dict(eye=dict(x=1.5, y=-2.0, z=1.0))),
        margin=dict(l=0, r=0, t=10, b=0), height=550,
    )
    return fig


def figure_section_grume(res):
    fig, ax = plt.subplots(figsize=(7, 7))
    R = res.diametre / 2
    ax.add_patch(plt.Circle((0,0), R, facecolor="#f4ecd8",
                            edgecolor="#5a4a2a", linewidth=2))
    for r in (R*0.85, R*0.65, R*0.45, R*0.25):
        ax.add_patch(plt.Circle((0,0), r, fill=False,
                                edgecolor="#c8b88a", linewidth=0.5,
                                linestyle="--"))
    ax.plot(0, 0, marker="+", markersize=14, color="#5a4a2a", markeredgewidth=2)
    bases = sorted({p.nom for p in res.placements})
    cmap = {b: plt.cm.Set2.colors[i % 8] for i, b in enumerate(bases)}
    for p in res.placements:
        ax.add_patch(mpatches.Rectangle((p.x, p.y), p.largeur, p.hauteur,
                                        facecolor=cmap[p.nom], edgecolor="black"))
        if min(p.largeur, p.hauteur) > 0.04:
            ax.text(p.x + p.largeur/2, p.y + p.hauteur/2,
                    f"{p.nom}\n{p.largeur*100:.0f}×{p.hauteur*100:.0f}",
                    ha="center", va="center", fontsize=8, fontweight="bold")
    margin = R * 0.15
    ax.set_xlim(-R-margin, R+margin); ax.set_ylim(-R-margin, R+margin)
    ax.set_aspect("equal")
    ax.set_title(f"Section transversale Ø {res.diametre*100:.0f} cm")
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    return fig


def equarissage_pour_allocation(allocation, resolution_mm=20, time_limit_s=3):
    sections_uniques = {}
    for c in allocation.coupes:
        sec = (round(c.section[0], 4), round(c.section[1], 4))
        sections_uniques[sec] = sections_uniques.get(sec, 0) + 1
    if not sections_uniques:
        return None
    sl = [Section(f"{w*100:.0f}×{h*100:.0f}", w, h, 1)
          for (w, h) in sections_uniques.keys()]
    return equarissage.equarrissage_cpsat(
        diametre=allocation.grume_diametre, sections=sl,
        resolution_mm=resolution_mm, time_limit_s=time_limit_s,
    ), sections_uniques


# === Test ===
grumes = [
    engine.Grume("G1", 6.0, 0.50),    # grosse pour viser le multi-coupes
    engine.Grume("G2", 5.5, 0.45),
    engine.Grume("G3", 4.5, 0.40),
]
debits = [
    engine.Debit("Sablière",    5.5, 0.22, 0.22, 1),
    engine.Debit("Poteau",      2.5, 0.20, 0.20, 4),
    engine.Debit("Arbalétrier", 1.5, 0.18, 0.18, 3),
    engine.Debit("Poinçon",     1.0, 0.15, 0.15, 2),
]

resultat = engine.best_fit_decreasing(debits, grumes)
print(f"Algo: {resultat.nom_algo}")
print(f"Utilisation: {resultat.taux_utilisation*100:.1f}%")
for a in resultat.allocations:
    cpz = [c.debit_nom for c in a.coupes]
    print(f"  {a.grume_id} (Ø {a.grume_diametre*100:.0f}cm): {cpz}, "
          f"chute {a.chute*100:.0f}cm")

# Sauve la figure 3D en HTML (Kaleido demande Chrome pour PNG)
fig3d = figure_3d_plan_de_coupe(resultat)
fig3d.write_html("/tmp/test_3d.html")
print("\n✓ Figure 3D sauvegardée : /tmp/test_3d.html")

# Sauve une section par grume (la première qui a des coupes)
for a in resultat.allocations:
    if a.coupes:
        out = equarissage_pour_allocation(a)
        if out:
            res_2d, secs = out
            print(f"\n  Grume {a.grume_id} : {len(secs)} section(s) unique(s) "
                  f"-> {len(res_2d.placements)} placée(s)")
            if res_2d.placements:
                fig = figure_section_grume(res_2d)
                fig.savefig(f"/tmp/test_section_{a.grume_id}.png",
                            dpi=100, bbox_inches="tight")
                print(f"  Section sauvegardée : /tmp/test_section_{a.grume_id}.png")
        break
