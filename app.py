"""
UI Streamlit pour Optim'Charpente.
Lancement : streamlit run app.py

Deux onglets :
- Tronçonnage 1D : affectation grumes -> débits (longueurs)
- Équarrissage 2D : placement de sections rectangulaires dans le disque
"""

import datetime as dt

import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import plotly.graph_objects as go

import engine
import equarissage
import geometry
import pattern
import metrics
from engine import Grume, Debit
from equarissage import Section
from connectors import speckle_io


st.set_page_config(page_title="Optim'Charpente", page_icon="🪵", layout="wide")
st.title("🪵 Optim'Charpente")
st.caption("Tronçonnage 1D + équarrissage 2D pour charpente amateur")


# ========== Sidebar : réglages globaux ==========

with st.sidebar:
    st.header("⚙️ Réglages")

    st.subheader("Tronçonnage 1D")
    kerf_mm = st.number_input(
        "Trait de scie (mm)", min_value=1.0, max_value=20.0,
        value=5.0, step=0.5,
        help="Épaisseur perdue à chaque coupe en longueur."
    )
    engine.KERF = kerf_mm / 1000.0

    cpsat_time_1d = st.slider("Temps max CP-SAT 1D (s)", 1, 120, 10)

    st.subheader("Équarrissage 2D")
    resolution_mm = st.select_slider(
        "Résolution grille (mm)",
        options=[10, 20, 30, 50],
        value=20,
        help="Plus fin = plus précis mais plus lent."
    )
    cpsat_time_2d = st.slider("Temps max CP-SAT 2D (s)", 1, 60, 5)

    st.divider()
    st.markdown(
        "**Lexique**\n\n"
        "- **Grume** : tronc, défini par longueur et diamètre.\n"
        "- **Débit** : pièce à sortir (poutre, poteau, chevron…).\n"
        "- **Tronçonnage** : découpe en longueur.\n"
        "- **Équarrissage** : choix de la section transversale."
    )

    st.divider()
    with st.expander("🔌 Connexion Speckle", expanded=False):
        if not speckle_io.is_available():
            st.warning("`specklepy` non installé.\n\n"
                       "`pip install specklepy`")
        else:
            st.session_state.setdefault("speckle_url", "")
            st.session_state.setdefault("speckle_token", "")
            st.session_state.speckle_url = st.text_input(
                "URL du modèle Speckle",
                value=st.session_state.speckle_url,
                placeholder="https://app.speckle.systems/projects/.../models/...",
                help="URL du modèle (ou stream legacy). Le commit le plus récent sera utilisé.",
            )
            st.session_state.speckle_token = st.text_input(
                "Personal Access Token",
                value=st.session_state.speckle_token,
                type="password",
                help="Créé depuis votre profil Speckle. Ne sera pas stocké.",
            )
            st.session_state.setdefault("speckle_unit_scale", 1.0)
            st.session_state.speckle_unit_scale = st.select_slider(
                "Unités du modèle Speckle",
                options=[0.001, 0.01, 1.0],
                value=st.session_state.speckle_unit_scale,
                format_func=lambda v: {0.001: "millimètres",
                                       0.01: "centimètres",
                                       1.0: "mètres"}[v],
                help="Pour conversion automatique vers mètres."
            )
            if st.button("🔍 Tester la connexion", width='stretch'):
                ok, msg = speckle_io.test_connection(
                    st.session_state.speckle_url,
                    st.session_state.speckle_token,
                )
                (st.success if ok else st.error)(msg)


# ========== Données démo ==========

GRUMES_DEMO = pd.DataFrame([
    {"id": "G1", "longueur (m)": 5.5, "diamètre (m)": 0.45},
    {"id": "G2", "longueur (m)": 4.2, "diamètre (m)": 0.38},
    {"id": "G3", "longueur (m)": 6.0, "diamètre (m)": 0.50},
    {"id": "G4", "longueur (m)": 4.8, "diamètre (m)": 0.42},
    {"id": "G5", "longueur (m)": 5.2, "diamètre (m)": 0.40},
    {"id": "G6", "longueur (m)": 4.5, "diamètre (m)": 0.36},
    {"id": "G7", "longueur (m)": 6.3, "diamètre (m)": 0.48},
    {"id": "G8", "longueur (m)": 5.8, "diamètre (m)": 0.44},
])

DEBITS_DEMO = pd.DataFrame([
    {"nom": "Sablière",    "longueur (m)": 5.0, "largeur (m)": 0.20, "hauteur (m)": 0.20, "quantité": 2},
    {"nom": "Poteau",      "longueur (m)": 3.0, "largeur (m)": 0.20, "hauteur (m)": 0.20, "quantité": 4},
    {"nom": "Entrait",     "longueur (m)": 5.5, "largeur (m)": 0.22, "hauteur (m)": 0.22, "quantité": 1},
    {"nom": "Arbalétrier", "longueur (m)": 4.0, "largeur (m)": 0.18, "hauteur (m)": 0.18, "quantité": 2},
    {"nom": "Poinçon",     "longueur (m)": 1.8, "largeur (m)": 0.18, "hauteur (m)": 0.18, "quantité": 1},
])

SECTIONS_2D_DEMO = pd.DataFrame([
    {"nom": "Poutre",  "largeur (m)": 0.22, "hauteur (m)": 0.22, "qmax": 1},
    {"nom": "Madrier", "largeur (m)": 0.20, "hauteur (m)": 0.08, "qmax": 4},
    {"nom": "Chevron", "largeur (m)": 0.08, "hauteur (m)": 0.08, "qmax": 6},
])

for key, default in [
    ("grumes_df", GRUMES_DEMO.copy()),
    ("debits_df", DEBITS_DEMO.copy()),
    ("sections_2d_df", SECTIONS_2D_DEMO.copy()),
    ("diametre_2d", 0.50),
]:
    if key not in st.session_state:
        st.session_state[key] = default


# ========== Onglets ==========

tab_1d, tab_2d = st.tabs(["📏 Tronçonnage 1D", "⭕ Équarrissage 2D"])


# ===================================================================
#                       ONGLET 1D
# ===================================================================

with tab_1d:
    st.markdown(
        "Affecter une liste de **débits en longueur** à une liste de **grumes**, "
        "en minimisant les chutes."
    )

    # --- Helpers Speckle ---
    def _speckle_creds_ok():
        """Retourne (url, token, scale) si les credentials sont saisis, None sinon."""
        if not speckle_io.is_available():
            return None
        url = st.session_state.get("speckle_url", "").strip()
        token = st.session_state.get("speckle_token", "").strip()
        scale = st.session_state.get("speckle_unit_scale", 1.0)
        if not url or not token:
            return None
        return url, token, scale

    st.subheader("1. Grumes disponibles")

    # Bouton import Speckle pour les grumes
    creds = _speckle_creds_ok()
    if creds:
        with st.expander("🔄 Importer les grumes depuis Speckle", expanded=False):
            keywords_grumes = st.text_input(
                "Mots-clés speckle_type (séparés par virgule)",
                value="Log, Grume",
                key="speckle_kw_grumes",
                help="Tout objet dont le speckle_type contient l'un de ces mots est importé.",
            )
            if st.button("⬇️ Importer les grumes", key="btn_import_grumes",
                         width='stretch'):
                url, token, scale = creds
                kws = [k.strip() for k in keywords_grumes.split(",") if k.strip()]
                try:
                    with st.spinner("Import en cours..."):
                        grumes = speckle_io.import_grumes(
                            url, token, type_keywords=kws, unit_scale=scale,
                        )
                    if not grumes:
                        st.warning(f"Aucun objet trouvé avec les mots-clés {kws}.")
                    else:
                        st.session_state.grumes_df = pd.DataFrame([
                            {"id": g.id, "longueur (m)": g.longueur,
                             "diamètre (m)": g.diametre}
                            for g in grumes
                        ])
                        st.success(f"{len(grumes)} grume(s) importée(s).")
                        st.rerun()
                except Exception as e:
                    st.error(f"{type(e).__name__}: {e}")
    col1, col2 = st.columns([4, 1])
    with col1:
        st.session_state.grumes_df = st.data_editor(
            st.session_state.grumes_df,
            num_rows="dynamic", width='stretch', key="ed_grumes",
            column_config={
                "id": st.column_config.TextColumn("ID", required=True),
                "longueur (m)": st.column_config.NumberColumn(min_value=0.1, format="%.2f"),
                "diamètre (m)": st.column_config.NumberColumn(min_value=0.05, format="%.3f"),
            },
        )
    with col2:
        df_g = st.session_state.grumes_df.dropna()
        st.metric("Nombre", len(df_g))
        st.metric("Total (m)",
                  f"{df_g['longueur (m)'].sum():.2f}" if len(df_g) else "0.00")

    st.subheader("2. Débits demandés")

    if creds:
        with st.expander("🔄 Importer les débits depuis Speckle", expanded=False):
            keywords_debits = st.text_input(
                "Mots-clés speckle_type",
                value="Beam, Column, Member",
                key="speckle_kw_debits",
            )
            if st.button("⬇️ Importer les débits", key="btn_import_debits",
                         width='stretch'):
                url, token, scale = creds
                kws = [k.strip() for k in keywords_debits.split(",") if k.strip()]
                try:
                    with st.spinner("Import en cours..."):
                        debits = speckle_io.import_debits(
                            url, token, type_keywords=kws, unit_scale=scale,
                        )
                    if not debits:
                        st.warning(f"Aucun objet trouvé avec les mots-clés {kws}.")
                    else:
                        st.session_state.debits_df = pd.DataFrame([
                            {"nom": d.nom,
                             "longueur (m)": d.longueur,
                             "largeur (m)": d.largeur,
                             "hauteur (m)": d.hauteur,
                             "quantité": d.quantite}
                            for d in debits
                        ])
                        st.success(f"{len(debits)} débit(s) importé(s) "
                                   f"(quantités agrégées).")
                        st.rerun()
                except Exception as e:
                    st.error(f"{type(e).__name__}: {e}")
    col1, col2 = st.columns([4, 1])
    with col1:
        st.session_state.debits_df = st.data_editor(
            st.session_state.debits_df,
            num_rows="dynamic", width='stretch', key="ed_debits",
            column_config={
                "nom": st.column_config.TextColumn("Nom", required=True),
                "longueur (m)": st.column_config.NumberColumn(min_value=0.1, format="%.2f"),
                "largeur (m)": st.column_config.NumberColumn(min_value=0.01, format="%.3f"),
                "hauteur (m)": st.column_config.NumberColumn(min_value=0.01, format="%.3f"),
                "quantité": st.column_config.NumberColumn(min_value=1, step=1, format="%d"),
            },
        )
    with col2:
        df_d = st.session_state.debits_df.dropna()
        nb = int(df_d["quantité"].sum()) if len(df_d) else 0
        demand = (df_d["longueur (m)"] * df_d["quantité"]).sum() if len(df_d) else 0
        st.metric("Pièces", nb)
        st.metric("Demande (m)", f"{demand:.2f}")

    def to_grumes(df):
        return [Grume(str(r["id"]), float(r["longueur (m)"]),
                      float(r["diamètre (m)"]))
                for _, r in df.dropna().iterrows()]

    def to_debits(df):
        return [Debit(str(r["nom"]), float(r["longueur (m)"]),
                      float(r["largeur (m)"]), float(r["hauteur (m)"]),
                      int(r["quantité"]))
                for _, r in df.dropna().iterrows()]

    st.subheader("3. Algorithmes")
    c1, c2, c3, c4 = st.columns(4)
    with c1: use_ffd = st.checkbox("First-Fit Decreasing", value=True)
    with c2: use_bfd = st.checkbox("Best-Fit Decreasing", value=True)
    with c3: use_cpsat = st.checkbox("CP-SAT 1D", value=True)
    with c4: use_couple = st.checkbox(
        "Couplé 1D+2D", value=True,
        help="Solveur opérationnel : choisit un schéma d'équarrissage par "
             "grume (mono, bi-section, et patterns experts boule/quartanier/"
             "plot2), puis tronçonne. Plus lent mais plus efficace quand "
             "plusieurs sections coexistent."
    )

    if use_couple:
        cpsat_time_couple = st.slider(
            "Temps max Couplé (s)", 5, 180, 30, key="time_couple",
            help="Le solveur couplé est plus lent que le 1D pur "
                 "(génération de patterns + CP-SAT global)."
        )

    if st.button("🚀 Lancer les algorithmes", type="primary",
                 width='stretch', key="btn_1d"):
        grumes = to_grumes(st.session_state.grumes_df)
        debits = to_debits(st.session_state.debits_df)
        if not grumes or not debits:
            st.error("Grumes ou débits manquants.")
            st.stop()

        # Pré-check volumique : seulement si le couplé est demandé.
        # Les algos 1D restent tolérants à demande > offre (ils saturent).
        if use_couple:
            ok, msg = pattern.verifier_faisabilite(grumes, debits)
            if not ok:
                st.error(f"⛔ Faisabilité : {msg}")
                st.info("Décochez « Couplé » pour lancer les algos 1D, "
                        "qui acceptent les cas saturés.")
                st.stop()

        resultats = []
        with st.spinner("Calcul..."):
            if use_ffd: resultats.append(engine.first_fit_decreasing(debits, grumes))
            if use_bfd: resultats.append(engine.best_fit_decreasing(debits, grumes))
            if use_cpsat:
                r = engine.cp_sat_optimise(debits, grumes, time_limit_s=cpsat_time_1d)
                if r is None:
                    st.warning("OR-Tools absent : `pip install ortools`")
                else:
                    resultats.append(r)
            if use_couple:
                r = pattern.solveur_couple_cpsat(
                    debits, grumes,
                    time_limit_s=cpsat_time_couple,
                    resolution_mm=resolution_mm,
                )
                if r is None:
                    st.warning("OR-Tools absent : `pip install ortools`")
                else:
                    resultats.append(r)
        if resultats:
            st.session_state.resultats_1d = resultats

    if "resultats_1d" in st.session_state and st.session_state.resultats_1d:
        st.divider()
        st.subheader("4. Résultats — bordereau opérationnel")

        grumes_init = to_grumes(st.session_state.grumes_df)
        debits_init = to_debits(st.session_state.debits_df)
        ms = [metrics.calculer_metriques(r, grumes_init, debits_init)
              for r in st.session_state.resultats_1d]

        # ----- KPI hero du meilleur algo -----
        # Best = couverture demande max, puis rendement matière max
        idx_best = max(
            range(len(ms)),
            key=lambda i: (ms[i].couverture_demande, ms[i].rendement_matiere)
        )
        m_best = ms[idx_best]
        r_best = st.session_state.resultats_1d[idx_best]

        st.markdown(f"**🏆 Meilleur algo** : `{r_best.nom_algo}`")

        k1, k2, k3, k4 = st.columns(4)
        # Pour les deltas, comparer au pire algo (plus parlant pour le scieur)
        idx_worst = min(
            range(len(ms)),
            key=lambda i: (ms[i].couverture_demande, ms[i].rendement_matiere)
        )
        m_worst = ms[idx_worst]
        with k1:
            st.metric(
                "Rendement matière",
                f"{m_best.rendement_matiere*100:.1f}%",
                delta=(f"{(m_best.rendement_matiere - m_worst.rendement_matiere)*100:+.1f} pts"
                       if idx_best != idx_worst else None),
                help="Volume débité / volume des grumes mobilisées. "
                     "Référence scierie chêne : 50–65 %."
            )
        with k2:
            st.metric(
                "Couverture demande",
                f"{m_best.couverture_demande*100:.1f}%",
                delta=(f"{(m_best.couverture_demande - m_worst.couverture_demande)*100:+.1f} pts"
                       if idx_best != idx_worst else None),
                help="Volume débité / volume demandé. 100 % = tout est produit."
            )
        with k3:
            st.metric(
                "Grumes mobilisées",
                f"{m_best.nb_grumes_utilisees} / {m_best.nb_grumes_dispo}",
                delta=(f"{m_best.nb_grumes_utilisees - m_worst.nb_grumes_utilisees:+d}"
                       if idx_best != idx_worst else None),
                delta_color="inverse",
                help="Mobilisées sur disponibles. Moins = plus de réserve "
                     "+ moins de manutention."
            )
        with k4:
            st.metric(
                "Cubage en réserve",
                f"{m_best.cubage_grumes_reservees:.2f} m³",
                help="Volume des grumes laissées au stock pour la prochaine fournée."
            )

        # ----- Bordereau comparatif -----
        with st.expander("📋 Bordereau de production complet", expanded=True):
            rows = metrics.formater_pour_dataframe(
                ms,
                [r.nom_algo for r in st.session_state.resultats_1d],
            )
            df_metrics = pd.DataFrame(rows)
            st.dataframe(df_metrics, width='stretch', hide_index=True)
            st.caption(
                f"💡 **Rendement matière** = cubage produit / cubage des grumes "
                f"mobilisées (référence scierie chêne : 50–65 %). "
                f"**Couverture demande** = cubage produit / cubage demandé "
                f"(100 % = tout est satisfait). "
                f"**Setups** = nombre de schémas d'équarrissage différents "
                f"(= changements de réglage scierie). "
                f"Cubage demande commune : {ms[0].cubage_demande:.3f} m³ — "
                f"stock total disponible : {ms[0].cubage_grumes_dispo:.3f} m³."
            )

        nom_choisi = st.selectbox("Détail :",
                                  [r.nom_algo for r in st.session_state.resultats_1d])
        res = next(r for r in st.session_state.resultats_1d if r.nom_algo == nom_choisi)

        fig, ax = plt.subplots(figsize=(11, max(2.5, len(res.allocations) * 0.7)))
        bases = sorted({c.debit_nom.split("#")[0]
                        for a in res.allocations for c in a.coupes})
        cmap_colors = plt.cm.Set3.colors + plt.cm.Pastel1.colors
        cmap = {b: cmap_colors[i % len(cmap_colors)] for i, b in enumerate(bases)}

        for i, a in enumerate(res.allocations):
            ax.barh(i, a.grume_longueur, color="#f4ecd8",
                    edgecolor="#444", linewidth=0.6)
            x = 0
            for c in a.coupes:
                base = c.debit_nom.split("#")[0]
                ax.barh(i, c.longueur, left=x, color=cmap[base],
                        edgecolor="#222", linewidth=0.6)
                if c.longueur > 0.3:
                    ax.text(x + c.longueur/2, i, c.debit_nom,
                            ha="center", va="center",
                            fontsize=8, fontweight="bold")
                x += c.longueur
                ax.barh(i, engine.KERF, left=x, color="black")
                x += engine.KERF
            if a.chute > 0.05:
                ax.text(x + a.chute/2, i, f"chute {a.chute*100:.0f} cm",
                        ha="center", va="center",
                        fontsize=8, style="italic", color="#555")
        ax.set_yticks(range(len(res.allocations)))
        ax.set_yticklabels([f"{a.grume_id}\nØ {a.grume_diametre*100:.0f} cm"
                           for a in res.allocations])
        ax.set_xlabel("Longueur (m)")
        ax.set_title(f"Plan de coupe — {res.nom_algo}")
        ax.invert_yaxis()
        ax.spines[['top', 'right']].set_visible(False)
        plt.tight_layout()
        st.pyplot(fig)

        # --- Vue 3D du plan de coupe ---
        with st.expander("🧊 Vue 3D du plan de coupe", expanded=True):
            st.plotly_chart(
                figure_3d_plan_de_coupe(res, kerf=engine.KERF),
                width='stretch',
            )

        # --- Section transversale par grume ---
        with st.expander("⭕ Section transversale par grume", expanded=False):
            grumes_avec_coupes = [a for a in res.allocations if a.coupes]
            if not grumes_avec_coupes:
                st.info("Aucune grume utilisée dans cette solution.")
            else:
                grume_choisie = st.selectbox(
                    "Choisir une grume :",
                    [a.grume_id for a in grumes_avec_coupes],
                    key=f"sel_grume_{nom_choisi}",
                )
                a_choisie = next(a for a in grumes_avec_coupes
                                 if a.grume_id == grume_choisie)

                with st.spinner("Calcul du placement 2D…"):
                    out = equarissage_pour_allocation(
                        a_choisie,
                        resolution_mm=resolution_mm,
                        time_limit_s=cpsat_time_2d,
                    )

                if out is None:
                    st.info("Pas de coupes dans cette grume.")
                else:
                    res_2d, sections_uniques = out
                    n_sections = len(sections_uniques)
                    n_placees = len(res_2d.placements) if res_2d else 0

                    cl, cm, cr = st.columns(3)
                    cl.metric("Sections distinctes", n_sections)
                    cm.metric("Sections placées en 2D", f"{n_placees}/{n_sections}")
                    cr.metric("Surface utilisée",
                              f"{res_2d.taux_utilisation*100:.1f}%"
                              if res_2d else "—")

                    if res_2d and res_2d.placements:
                        st.pyplot(figure_section_grume(res_2d))

                    if res_2d and n_placees < n_sections:
                        st.warning(
                            f"⚠️ Le solveur 2D ne fait tenir que {n_placees}"
                            f"/{n_sections} sections distinctes ensemble dans "
                            f"le disque. L'algo 1D place les coupes "
                            f"séquentiellement en longueur ; pour cette grume "
                            f"il faudrait optimiser conjointement le 2D et le 1D."
                        )

                    # Détail des cuts dans cette grume
                    df_cuts = pd.DataFrame([{
                        "Débit": c.debit_nom,
                        "Longueur (m)": round(c.longueur, 3),
                        "Section (cm)": f"{c.section[0]*100:.1f}×{c.section[1]*100:.1f}",
                    } for c in a_choisie.coupes])
                    st.dataframe(df_cuts, hide_index=True, width='stretch')

        rows = [{
            "Grume": a.grume_id, "Débit": c.debit_nom,
            "Longueur (m)": round(c.longueur, 3),
            "Section (cm)": f"{c.section[0]*100:.1f} × {c.section[1]*100:.1f}",
        } for a in res.allocations for c in a.coupes]
        if rows:
            df_bord = pd.DataFrame(rows).sort_values(["Grume", "Débit"])
            with st.expander("📋 Bordereau de coupe (CSV exportable)"):
                st.dataframe(df_bord, width='stretch', hide_index=True)
                st.download_button(
                    "⬇️ Télécharger CSV",
                    df_bord.to_csv(index=False).encode("utf-8"),
                    "bordereau_coupe.csv", "text/csv",
                    width='stretch',
                )
        if res.debits_non_alloues:
            st.warning(f"⚠️ Débits non alloués : {', '.join(res.debits_non_alloues)}")
        else:
            st.success("✅ Tous les débits ont été alloués.")

        # Export Speckle
        if creds:
            with st.expander("📤 Pousser ce plan vers Speckle", expanded=False):
                model_name = st.text_input(
                    "Nom du modèle de destination",
                    value="cut-plan",
                    help="Sera créé s'il n'existe pas dans le projet.",
                )
                msg = st.text_input(
                    "Message du commit (optionnel)",
                    value="",
                )
                with_geom = st.checkbox(
                    "Inclure la géométrie 3D (cylindres + boîtes)",
                    value=True,
                    help="Visible dans le viewer Speckle et récupérable "
                         "comme géométrie réelle dans Rhino via le connecteur.",
                )
                if st.button("📤 Envoyer", key="btn_export_speckle",
                             type="primary", width='stretch'):
                    url, token, _ = creds
                    try:
                        with st.spinner("Push en cours..."):
                            commit_url = speckle_io.export_plan(
                                resultat=res,
                                url=url,
                                token=token,
                                model_name=model_name,
                                message=msg or None,
                                with_geometry=with_geom,
                                kerf=engine.KERF,
                            )
                        st.success(f"Plan envoyé : {commit_url}")
                        st.markdown(f"[Voir sur Speckle ↗]({commit_url})")
                    except Exception as e:
                        st.error(f"{type(e).__name__}: {e}")

        # ============== Export bordereau de production ==============
        st.divider()
        st.subheader("📋 Bordereau de production")
        st.markdown(
            "Une fois satisfait du plan ci-dessus, génère un **PDF imprimable** "
            "qui accompagne les grumes en scierie : page de synthèse "
            "(KPIs + allocations) puis une page par grume utilisée "
            "(section transversale + plan de tronçonnage par rail)."
        )
        from connectors import bordereau_pdf

        cb1, cb2 = st.columns([2, 1])
        with cb1:
            algo_export = st.selectbox(
                "Algo à exporter",
                [r.nom_algo for r in st.session_state.resultats_1d],
                index=idx_best,    # défaut = meilleur algo
                key="algo_export_pdf",
            )
        with cb2:
            project_name = st.text_input(
                "Nom du projet",
                value="Charpente",
                key="project_name_pdf",
            )

        if st.button("📄 Générer le bordereau PDF",
                     type="primary", width='stretch',
                     key="btn_export_pdf"):
            res_to_export = next(
                r for r in st.session_state.resultats_1d
                if r.nom_algo == algo_export
            )
            try:
                with st.spinner("Génération du PDF..."):
                    pdf_bytes = bordereau_pdf.exporter_bordereau_bytes(
                        resultat=res_to_export,
                        grumes_init=grumes_init,
                        debits_init=debits_init,
                        project_name=project_name,
                    )
                st.session_state.pdf_bordereau = pdf_bytes
                st.success(f"Bordereau prêt ({len(pdf_bytes)//1024} Ko).")
            except Exception as e:
                st.error(f"Erreur génération PDF : {type(e).__name__}: {e}")

        if "pdf_bordereau" in st.session_state and st.session_state.pdf_bordereau:
            fname = (f"bordereau_{project_name.replace(' ', '_')}_"
                     f"{dt.datetime.now().strftime('%Y%m%d_%H%M')}.pdf")
            st.download_button(
                "⬇️ Télécharger le bordereau PDF",
                data=st.session_state.pdf_bordereau,
                file_name=fname,
                mime="application/pdf",
                width='stretch',
                key="dl_pdf_bordereau",
            )


# ===================================================================
#                       ONGLET 2D
# ===================================================================

def figure_section_grume(res):
    """Trace le disque de la grume + les rectangles placés."""
    fig, ax = plt.subplots(figsize=(7, 7))
    R = res.diametre / 2

    cercle = plt.Circle((0, 0), R, facecolor="#f4ecd8",
                        edgecolor="#5a4a2a", linewidth=2, zorder=1)
    ax.add_patch(cercle)
    # Cernes décoratifs
    for r in (R*0.85, R*0.65, R*0.45, R*0.25):
        ax.add_patch(plt.Circle((0, 0), r, fill=False,
                                edgecolor="#c8b88a", linewidth=0.5,
                                linestyle="--", zorder=2))
    # Cœur
    ax.plot(0, 0, marker="+", markersize=14, color="#5a4a2a",
            markeredgewidth=2, zorder=10)

    bases = sorted({p.nom for p in res.placements})
    cmap_colors = plt.cm.Set2.colors + plt.cm.Pastel2.colors
    cmap = {b: cmap_colors[i % len(cmap_colors)] for i, b in enumerate(bases)}

    for p in res.placements:
        rect = mpatches.Rectangle((p.x, p.y), p.largeur, p.hauteur,
                                   facecolor=cmap[p.nom], edgecolor="black",
                                   linewidth=1.0, zorder=5)
        ax.add_patch(rect)
        if min(p.largeur, p.hauteur) > 0.04:
            ax.text(p.x + p.largeur/2, p.y + p.hauteur/2,
                    f"{p.nom}\n{p.largeur*100:.0f}×{p.hauteur*100:.0f}",
                    ha="center", va="center",
                    fontsize=8, fontweight="bold", zorder=6)

    margin = R * 0.15
    ax.set_xlim(-R - margin, R + margin)
    ax.set_ylim(-R - margin, R + margin)
    ax.set_aspect("equal")
    ax.set_xlabel("x (m)")
    ax.set_ylabel("y (m)")
    ax.set_title(f"Section transversale Ø {res.diametre*100:.0f} cm — "
                 f"surface utilisée : {res.taux_utilisation*100:.1f}%")
    ax.grid(True, alpha=0.3)

    if bases:
        handles = [mpatches.Patch(color=cmap[b], label=b) for b in bases]
        ax.legend(handles=handles, loc="upper right",
                  framealpha=0.9, fontsize=9)
    plt.tight_layout()
    return fig


# ========== Helpers 3D et section par grume (mode 1D) ==========

# Palette stable par nom de débit (ignorant le suffixe #N)
_PALETTE = [
    "#A8D5BA", "#F2C078", "#F2A07B", "#A1C9F4", "#FFB7B2", "#B5A8D9",
    "#FFD3B6", "#C7CEEA", "#B6E2D3", "#FAB1A0", "#A29BFE", "#FAD390",
]


def _color_for(name: str) -> str:
    base = name.split("#")[0]
    h = sum(ord(c) for c in base)
    return _PALETTE[h % len(_PALETTE)]


def equarissage_pour_allocation(allocation, resolution_mm=20, time_limit_s=3.0):
    """
    Pour une allocation issue d'un solveur, retourne un ResultatEquarrissage
    + un dict {section: nb_coupes} pour la viz 2D du disque.

    Si l'allocation porte un Pattern (mode couplé), on utilise directement ses
    rails (placement fidèle, pas de recalcul). Sinon (mode 1D pur), on lance
    le solveur 2D a posteriori sur les sections uniques de l'allocation.
    """
    sections_uniques = {}
    for c in allocation.coupes:
        sec = (round(c.section[0], 4), round(c.section[1], 4))
        sections_uniques[sec] = sections_uniques.get(sec, 0) + 1

    if not sections_uniques:
        return None

    # Mode couplé : on a les rails du pattern, on les convertit en
    # ResultatEquarrissage sans relancer le solveur.
    pat = getattr(allocation, "pattern", None)
    if pat is not None and pat.rails:
        from equarissage import PlacementSection, ResultatEquarrissage
        placements = []
        for r in pat.rails:
            # Compter combien de coupes sont placées sur ce rail
            n_in_rail = sum(1 for c in allocation.coupes
                            if abs(c.section[0] - r.largeur) < 1e-3
                            and abs(c.section[1] - r.hauteur) < 1e-3
                            and c.rail_x is not None
                            and abs(c.rail_x - r.x) < 1e-3
                            and abs(c.rail_y - r.y) < 1e-3)
            label = f"{r.largeur*100:.0f}×{r.hauteur*100:.0f}"
            if n_in_rail:
                label += f" ×{n_in_rail}"
            placements.append(PlacementSection(
                nom=label,
                x=r.x, y=r.y,
                largeur=r.largeur, hauteur=r.hauteur,
                rotation=r.rotation,
            ))
        res = ResultatEquarrissage(
            diametre=allocation.grume_diametre,
            placements=placements,
            duree_s=0.0,
            statut=f"pattern « {pat.nom} »",
        )
        return res, sections_uniques

    # Mode 1D pur : recalcul a posteriori
    sections_list = [
        Section(f"{w*100:.0f}×{h*100:.0f}", w, h, 1)
        for (w, h) in sections_uniques.keys()
    ]
    res = equarissage.equarrissage_cpsat(
        diametre=allocation.grume_diametre,
        sections=sections_list,
        resolution_mm=resolution_mm,
        time_limit_s=time_limit_s,
    )
    return res, sections_uniques


def figure_3d_plan_de_coupe(resultat, kerf=0.005):
    """
    Vue 3D Plotly : pour chaque grume, un cylindre semi-transparent et
    les coupes sous forme de boîtes colorées sur l'axe.
    Les grumes sont décalées en y pour la lisibilité.
    """
    fig = go.Figure()
    y_offset = 0.0

    for a in resultat.allocations:
        # --- Cylindre de la grume (semi-transparent) ---
        v, t = geometry.cylindre(
            longueur=a.grume_longueur,
            rayon=a.grume_diametre / 2,
            x_offset=0.0,
            y_offset=y_offset,
            n_segments=24,
        )
        params = geometry.to_plotly_mesh3d(
            v, t,
            color="#d4c08a", opacity=0.25,
            name=a.grume_id,
            showlegend=False,
            hovertext=(f"{a.grume_id}<br>"
                       f"L = {a.grume_longueur:.2f} m<br>"
                       f"Ø = {a.grume_diametre*100:.0f} cm"),
        )
        fig.add_trace(go.Mesh3d(**params))

        # --- Coupes (boîtes opaques colorées) ---
        # En mode 1D pur, les coupes n'ont pas de rail_x/y → centrées.
        # En mode couplé, on utilise les rails du pattern (placement fidèle).
        # Le tronçonnage en longueur est séquentiel par RAIL (pas global) :
        # on regroupe les coupes par rail puis on cumule x_pos par rail.
        from collections import defaultdict
        coupes_par_rail = defaultdict(list)
        for c in a.coupes:
            rk = (c.rail_x if c.rail_x is not None else None,
                  c.rail_y if c.rail_y is not None else None,
                  c.section[0], c.section[1])
            coupes_par_rail[rk].append(c)

        for rk, coupes_rail in coupes_par_rail.items():
            rail_x, rail_y, w_sec, h_sec = rk
            # Si pas de rail défini (1D pur) : centrer dans le disque
            if rail_x is None or rail_y is None:
                rail_x = -w_sec / 2
                rail_y = -h_sec / 2
            x_in_rail = 0.0
            for c in coupes_rail:
                v_box, t_box = geometry.boite(
                    x0=x_in_rail,
                    y0=y_offset + rail_x,
                    z0=rail_y,
                    longueur=c.longueur,
                    largeur=w_sec,
                    hauteur=h_sec,
                )
                params = geometry.to_plotly_mesh3d(
                    v_box, t_box,
                    color=_color_for(c.debit_nom),
                    opacity=0.95,
                    name=c.debit_nom,
                    showlegend=False,
                    hovertext=(f"{c.debit_nom}<br>"
                               f"L = {c.longueur:.2f} m<br>"
                               f"{w_sec*100:.0f}×{h_sec*100:.0f} cm"),
                )
                fig.add_trace(go.Mesh3d(**params))
                x_in_rail += c.longueur + kerf

        # Décaler la prochaine grume
        y_offset += a.grume_diametre + 0.30

    fig.update_layout(
        scene=dict(
            xaxis_title="Longueur (m)",
            yaxis_title="y (m)",
            zaxis_title="z (m)",
            aspectmode="data",
            camera=dict(eye=dict(x=1.5, y=-2.0, z=1.0)),
        ),
        margin=dict(l=0, r=0, t=10, b=0),
        height=550,
    )
    return fig


with tab_2d:
    st.markdown(
        "Pour une grume circulaire et une liste de **sections rectangulaires** "
        "à inscrire dans le disque, calcule le placement qui maximise la "
        "surface utilisée.\n\n"
        "Utile pour décider, avant tronçonnage, quelles sections sortir d'une "
        "grume donnée (1 grosse poutre, ou 2 madriers + chevrons, etc.)."
    )

    col1, col2 = st.columns([1, 3])
    with col1:
        st.session_state.diametre_2d = st.number_input(
            "Diamètre grume (m)",
            min_value=0.10, max_value=2.00,
            value=float(st.session_state.diametre_2d),
            step=0.01, format="%.3f",
        )
    with col2:
        surface = 3.14159 * (st.session_state.diametre_2d/2)**2
        st.metric("Surface du disque", f"{surface*10000:.0f} cm²")

    st.subheader("Sections demandées")
    st.session_state.sections_2d_df = st.data_editor(
        st.session_state.sections_2d_df,
        num_rows="dynamic", width='stretch', key="ed_sections_2d",
        column_config={
            "nom": st.column_config.TextColumn("Nom", required=True),
            "largeur (m)": st.column_config.NumberColumn(min_value=0.01, format="%.3f"),
            "hauteur (m)": st.column_config.NumberColumn(min_value=0.01, format="%.3f"),
            "qmax": st.column_config.NumberColumn(
                "Quantité max", min_value=0, step=1, format="%d",
                help="Nombre maximum de cette section dans la grume.",
            ),
        },
    )

    if st.button("🚀 Calculer le plan d'équarrissage", type="primary",
                 width='stretch', key="btn_2d"):
        sections = []
        for _, r in st.session_state.sections_2d_df.dropna().iterrows():
            if int(r["qmax"]) <= 0:
                continue
            sections.append(Section(
                nom=str(r["nom"]),
                largeur=float(r["largeur (m)"]),
                hauteur=float(r["hauteur (m)"]),
                quantite_max=int(r["qmax"]),
            ))
        if not sections:
            st.error("Aucune section saisie.")
            st.stop()

        with st.spinner(f"Recherche du placement optimal "
                        f"(résolution {resolution_mm} mm)..."):
            res_2d = equarissage.equarrissage_cpsat(
                diametre=st.session_state.diametre_2d,
                sections=sections,
                resolution_mm=resolution_mm,
                time_limit_s=cpsat_time_2d,
            )
            if res_2d is None:
                st.warning("OR-Tools indisponible, fallback heuristique.")
                res_2d = equarissage.equarrissage_glouton(
                    st.session_state.diametre_2d, sections
                )
        st.session_state.resultat_2d = res_2d

    if "resultat_2d" in st.session_state:
        res_2d = st.session_state.resultat_2d
        st.divider()
        st.subheader("Plan d'équarrissage")

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Statut", res_2d.statut)
        c2.metric("Pièces placées", len(res_2d.placements))
        c3.metric("Surface utile", f"{res_2d.surface_utilisee*10000:.0f} cm²")
        c4.metric("Taux", f"{res_2d.taux_utilisation*100:.1f}%")

        if res_2d.placements:
            col_fig, col_table = st.columns([2, 1])
            with col_fig:
                st.pyplot(figure_section_grume(res_2d))
            with col_table:
                st.markdown("**Détail des placements**")
                df_placements = pd.DataFrame([{
                    "Section": p.nom,
                    "Position (cm)": f"({p.x*100:+.0f}, {p.y*100:+.0f})",
                    "Taille (cm)": f"{p.largeur*100:.0f}×{p.hauteur*100:.0f}",
                    "Rotation": f"{p.rotation}°",
                } for p in res_2d.placements])
                st.dataframe(df_placements, hide_index=True,
                             width='stretch')
                st.caption(f"Calcul en {res_2d.duree_s*1000:.0f} ms")
        else:
            st.warning("Aucune section ne tient dans le disque "
                       "(trop grandes par rapport au diamètre).")
