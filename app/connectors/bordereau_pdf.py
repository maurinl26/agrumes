"""
Connecteur d'export : bordereau de production PDF.

Workflow opérationnel :
    1. L'utilisateur lance les algorithmes dans Streamlit.
    2. Il valide visuellement le plan choisi (tableaux, viz section, viz 3D).
    3. Une fois satisfait, il déclenche l'export bordereau, qui produit un
       PDF imprimable destiné à accompagner les grumes en scierie.

Le PDF contient :
    - Page 1 : synthèse opérationnelle (KPIs + tableau d'allocations).
    - Une page par grume utilisée : plan de section transversale + plan de
      tronçonnage par rail (avec longueurs et noms des débits).

Pas de dépendance Speckle / spécifique BIM ici : c'est un livrable de
production, pas un échange de modèle.
"""

from __future__ import annotations

import datetime as dt
import math
from collections import defaultdict
from io import BytesIO

import matplotlib
matplotlib.use("Agg")
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

from .. import equarissage
from .. import metrics


# Palette cohérente avec app.py (couleurs par nom de débit)
PALETTE = ["#A8D5BA", "#F2C078", "#F2A07B", "#A1C9F4", "#FFB7B2",
           "#B5A8D9", "#FFD3B6", "#C7CEEA", "#B6E2D3", "#FAB1A0"]


def _color_debit(nom: str):
    base = nom.split("#")[0]
    return PALETTE[sum(ord(c) for c in base) % len(PALETTE)]


# ============================================================
#                Page 1 : synthèse opérationnelle
# ============================================================

def _page_synthese(pdf, metriques, resultat, project_name, date_str):
    fig = plt.figure(figsize=(8.27, 11.69))      # A4 portrait
    fig.suptitle("BORDEREAU DE PRODUCTION", fontsize=20,
                 fontweight="bold", y=0.96)

    # En-tête
    fig.text(0.08, 0.91, f"Projet     : {project_name}", fontsize=11,
             family="monospace")
    fig.text(0.08, 0.89, f"Date       : {date_str}", fontsize=11,
             family="monospace")
    fig.text(0.08, 0.87, f"Algorithme : {resultat.nom_algo}", fontsize=11,
             family="monospace")

    # ----- KPI cartes -----
    kpis = [
        ("Rendement matière",
         f"{metriques.rendement_matiere*100:.1f}%", "#A1C9F4"),
        ("Couverture demande",
         f"{metriques.couverture_demande*100:.1f}%", "#A8D5BA"),
        ("Grumes mobilisées",
         f"{metriques.nb_grumes_utilisees}/{metriques.nb_grumes_dispo}",
         "#F2C078"),
        ("Setups scierie",
         f"{metriques.nb_patterns_distincts}", "#FFB7B2"),
    ]
    for i, (label, value, color) in enumerate(kpis):
        ax = fig.add_axes([0.06 + i * 0.225, 0.74, 0.20, 0.10],
                          frameon=False)
        ax.set_xticks([]); ax.set_yticks([])
        ax.set_xlim(0, 1); ax.set_ylim(0, 1)
        ax.add_patch(mpatches.FancyBboxPatch(
            (0.03, 0.03), 0.94, 0.94, boxstyle="round,pad=0.02",
            facecolor=color, edgecolor="#333", alpha=0.55))
        ax.text(0.5, 0.65, value, ha="center", va="center",
                fontsize=18, fontweight="bold")
        ax.text(0.5, 0.22, label, ha="center", va="center", fontsize=9)

    # ----- Bloc cubage -----
    fig.text(0.08, 0.66, "Cubage", fontsize=14, fontweight="bold")
    cubage_lines = [
        ("Cubage demandé",         metriques.cubage_demande),
        ("Cubage produit",         metriques.cubage_produit),
        ("Cubage grumes mobilisé", metriques.cubage_grumes_utilisees),
        ("Cubage chute",           metriques.cubage_chute),
        ("Cubage en réserve",      metriques.cubage_grumes_reservees),
    ]
    if metriques.cubage_non_alloue > 0:
        cubage_lines.append(
            (f"Cubage non alloué ({metriques.nb_debits_non_alloues} u.)",
             metriques.cubage_non_alloue)
        )
    for i, (label, val) in enumerate(cubage_lines):
        y = 0.63 - i * 0.022
        fig.text(0.10, y, f"{label:<35}", fontsize=10, family="monospace")
        fig.text(0.55, y, f"{val:>8.3f} m³", fontsize=10,
                 family="monospace", fontweight="bold")

    # ----- Tableau allocation -----
    fig.text(0.08, 0.46, "Allocation par grume utilisée",
             fontsize=14, fontweight="bold")
    headers = [("Grume", 0.08), ("Ø × L", 0.20),
               ("Pattern", 0.34), ("Coupes", 0.62), ("Util. 2D", 0.76)]
    for label, x in headers:
        fig.text(x, 0.43, label, fontsize=10, fontweight="bold",
                 family="monospace")
    fig.add_artist(plt.Line2D([0.07, 0.93], [0.42, 0.42],
                              color="#333", linewidth=0.8))

    y = 0.40
    for a in resultat.allocations:
        if not a.coupes:
            continue
        pat = getattr(a, "pattern", None)
        pat_name = pat.nom if pat is not None else "1D pur"
        taux_2d = f"{pat.taux_section*100:.1f}%" if pat is not None else "—"
        fig.text(0.08, y, a.grume_id, fontsize=9, family="monospace")
        fig.text(0.20, y,
                 f"Ø{a.grume_diametre*100:.0f}×{a.grume_longueur:.1f}m",
                 fontsize=9, family="monospace")
        fig.text(0.34, y, pat_name[:34], fontsize=9, family="monospace")
        fig.text(0.62, y, str(len(a.coupes)), fontsize=9, family="monospace")
        fig.text(0.76, y, taux_2d, fontsize=9, family="monospace")
        y -= 0.022

    # Grumes non utilisées (réserve)
    grumes_reservees = [a.grume_id for a in resultat.allocations
                        if not a.coupes]
    if grumes_reservees:
        y -= 0.015
        fig.text(0.08, y,
                 f"Grumes en réserve ({len(grumes_reservees)}) : "
                 + ", ".join(grumes_reservees[:8])
                 + ("..." if len(grumes_reservees) > 8 else ""),
                 fontsize=9, style="italic", color="#666")

    # Footer
    fig.text(0.5, 0.04,
             f"Optim'Charpente — Bordereau généré le {date_str}",
             ha="center", fontsize=8, color="#666", style="italic")

    pdf.savefig(fig)
    plt.close(fig)


# ============================================================
#                  Page n : détail par grume
# ============================================================

def _section_pour_1d_pur(allocation, resolution_mm=20):
    """Reconstruit un plan 2D a posteriori pour une allocation 1D pure
    (chaque section unique → 1 rail). Renvoie list[(rect, n_coupes, label)]."""
    sections_uniques = {}
    for c in allocation.coupes:
        key = (round(c.section[0], 4), round(c.section[1], 4))
        sections_uniques[key] = sections_uniques.get(key, 0) + 1
    sec_list = [equarissage.Section(f"{w*100:.0f}×{h*100:.0f}", w, h, 1)
                for (w, h) in sections_uniques.keys()]
    res = equarissage.equarrissage_cpsat(
        diametre=allocation.grume_diametre,
        sections=sec_list,
        resolution_mm=resolution_mm,
        time_limit_s=2.0,
    )
    rects = []
    if res and res.placements:
        for p in res.placements:
            n = sections_uniques.get(
                (round(p.largeur, 4), round(p.hauteur, 4)), 0
            )
            rects.append((p.x, p.y, p.largeur, p.hauteur, n,
                          f"{p.largeur*100:.0f}×{p.hauteur*100:.0f}"))
    return rects


def _page_grume(pdf, allocation, kerf=0.005):
    if not allocation.coupes:
        return

    pat = getattr(allocation, "pattern", None)
    fig = plt.figure(figsize=(8.27, 11.69))
    title = (f"{allocation.grume_id} — "
             f"Ø{allocation.grume_diametre*100:.0f} cm × "
             f"{allocation.grume_longueur:.2f} m")
    if pat is not None:
        title += f"   |   Pattern : « {pat.nom} »"
    fig.suptitle(title, fontsize=13, fontweight="bold", y=0.96)

    # --- Section transversale (haut) ---
    ax = fig.add_axes([0.18, 0.50, 0.64, 0.40])
    R = allocation.grume_diametre / 2
    ax.add_patch(plt.Circle((0, 0), R, facecolor="#f4ecd8",
                             edgecolor="#5a4a2a", linewidth=2))
    for r in (R*0.85, R*0.65, R*0.45, R*0.25):
        ax.add_patch(plt.Circle((0, 0), r, fill=False,
                                 edgecolor="#c8b88a",
                                 linewidth=0.5, linestyle="--"))
    ax.plot(0, 0, marker="+", markersize=14, color="#5a4a2a",
            markeredgewidth=2)

    # Rails fidèles si pattern présent, sinon reconstitution 2D
    cmap = plt.cm.Set2.colors
    if pat is not None:
        rails_count = defaultdict(int)
        for c in allocation.coupes:
            if c.rail_x is not None:
                rk = (c.rail_x, c.rail_y, c.section[0], c.section[1])
                rails_count[rk] += 1
        for i, r in enumerate(pat.rails):
            rk = (r.x, r.y, r.largeur, r.hauteur)
            n = rails_count.get(rk, 0)
            ax.add_patch(mpatches.Rectangle(
                (r.x, r.y), r.largeur, r.hauteur,
                facecolor=cmap[i % len(cmap)],
                edgecolor="black", linewidth=1))
            if min(r.largeur, r.hauteur) > 0.04:
                ax.text(r.x + r.largeur/2, r.y + r.hauteur/2,
                        f"{r.largeur*100:.0f}×{r.hauteur*100:.0f}\n×{n}",
                        ha="center", va="center", fontsize=9,
                        fontweight="bold")
    else:
        rects = _section_pour_1d_pur(allocation)
        for i, (x, y, w, h, n, lbl) in enumerate(rects):
            ax.add_patch(mpatches.Rectangle(
                (x, y), w, h, facecolor=cmap[i % len(cmap)],
                edgecolor="black", linewidth=1))
            if min(w, h) > 0.04:
                ax.text(x + w/2, y + h/2, f"{lbl}\n×{n}",
                        ha="center", va="center", fontsize=9,
                        fontweight="bold")

    margin = R * 0.15
    ax.set_xlim(-R-margin, R+margin)
    ax.set_ylim(-R-margin, R+margin)
    ax.set_aspect("equal")
    ax.set_title("Section transversale", fontsize=11)
    ax.grid(True, alpha=0.3)
    ax.set_xlabel("x (m)"); ax.set_ylabel("y (m)")

    # --- Plan de tronçonnage par rail (bas) ---
    ax2 = fig.add_axes([0.10, 0.10, 0.85, 0.30])
    coupes_par_rail = defaultdict(list)
    for c in allocation.coupes:
        rk = (c.rail_x, c.rail_y, c.section[0], c.section[1])
        coupes_par_rail[rk].append(c)
    rails_keys = list(coupes_par_rail.keys())

    for i, rk in enumerate(rails_keys):
        rx, ry, w, h = rk
        # bande grume
        ax2.barh(i, allocation.grume_longueur, color="#f4ecd8",
                 edgecolor="#444", linewidth=0.6)
        x_pos = 0.0
        for c in coupes_par_rail[rk]:
            ax2.barh(i, c.longueur, left=x_pos,
                     color=_color_debit(c.debit_nom),
                     edgecolor="#222", linewidth=0.6)
            if c.longueur > allocation.grume_longueur * 0.06:
                ax2.text(x_pos + c.longueur/2, i,
                         f"{c.debit_nom.split('#')[0]}\n{c.longueur:.2f}m",
                         ha="center", va="center", fontsize=7)
            x_pos += c.longueur + kerf

    yticklabels = []
    for k in rails_keys:
        rx, ry, w, h = k
        if rx is not None:
            yticklabels.append(
                f"{w*100:.0f}×{h*100:.0f}\n@({rx*100:+.0f},{ry*100:+.0f})"
            )
        else:
            yticklabels.append(f"{w*100:.0f}×{h*100:.0f}")
    ax2.set_yticks(range(len(rails_keys)))
    ax2.set_yticklabels(yticklabels, fontsize=8)
    ax2.set_xlabel("Longueur (m)")
    ax2.set_xlim(0, allocation.grume_longueur * 1.02)
    ax2.set_title("Plan de tronçonnage par rail (échelle longueur)",
                  fontsize=11)
    ax2.grid(True, alpha=0.3, axis="x")
    ax2.invert_yaxis()

    # Total
    bois_util = sum(c.longueur for c in allocation.coupes)
    fig.text(0.10, 0.06,
             f"Total : {len(allocation.coupes)} coupes — "
             f"longueur cumulée des débits = {bois_util:.2f} m "
             f"(la grume fait {allocation.grume_longueur:.2f} m)",
             fontsize=9, fontweight="bold")

    pdf.savefig(fig)
    plt.close(fig)


# ============================================================
#                       Orchestrateur
# ============================================================

def exporter_bordereau(resultat, grumes_init: list, debits_init: list,
                       output, project_name: str = "Sans titre") -> str:
    """
    Génère un bordereau de production PDF.

    resultat : Resultat à exporter (issu d'un solveur, validé par l'utilisateur).
    grumes_init : grumes en stock au départ (référence pour le cubage).
    debits_init : débits demandés au départ (référence pour le cubage).
    output : chemin (str/Path) ou objet file-like ouvert en binaire (BytesIO).
    project_name : nom du projet, apparaît en en-tête.

    Retourne le chemin (str) si écrit sur disque, sinon "<buffer>".
    """
    metriques = metrics.calculer_metriques(resultat, grumes_init, debits_init)
    date_str = dt.datetime.now().strftime("%d/%m/%Y %H:%M")

    with PdfPages(output) as pdf:
        _page_synthese(pdf, metriques, resultat, project_name, date_str)
        for a in resultat.allocations:
            if a.coupes:
                _page_grume(pdf, a)

    if isinstance(output, (str, Path)):
        return str(output)
    return "<buffer>"


def exporter_bordereau_bytes(resultat, grumes_init, debits_init,
                              project_name="Sans titre") -> bytes:
    """Variante : retourne directement le PDF sous forme de bytes
    (pratique pour st.download_button)."""
    buf = BytesIO()
    exporter_bordereau(resultat, grumes_init, debits_init,
                       output=buf, project_name=project_name)
    buf.seek(0)
    return buf.read()


# ============================================================
#                       Auto-test
# ============================================================

if __name__ == "__main__":
    import engine
    import pattern

    grumes = [engine.Grume(f"G{i}", 6.0, 0.50) for i in range(1, 4)]
    debits = [
        engine.Debit("Sablière", 5.5, 0.22, 0.22, 1),
        engine.Debit("Chevron",  2.5, 0.08, 0.08, 6),
    ]

    print("Lancement du solveur couplé...")
    r = pattern.solveur_couple_cpsat(debits, grumes, time_limit_s=15)
    print(f"  {r.nom_algo}, {r.nb_grumes_utilisees} grume(s) utilisée(s), "
          f"{r.nb_coupes} coupes")

    print("\nGénération du bordereau PDF...")
    path = exporter_bordereau(
        r, grumes, debits,
        output="/tmp/bordereau_production.pdf",
        project_name="Charpente Atelier — démo",
    )
    print(f"✓ {path}")

    # Test variante bytes
    data = exporter_bordereau_bytes(r, grumes, debits, "Démo")
    print(f"✓ variante bytes : {len(data)} octets")
