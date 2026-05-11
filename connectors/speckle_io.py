"""
Connecteur Speckle (specklepy >= 3.x).

Fonctions exportées :
- is_available()           : True si specklepy installé
- parse_speckle_url(url)   : extrait host, project_id, model_id, version_id
- test_connection(url, token) : vérifie credentials
- import_debits(url, token, ...)   : Speckle  -> list[Debit]
- import_grumes(url, token, ...)   : Speckle  -> list[Grume]
- export_plan(resultat, url, token, model_name) : Resultat -> commit URL

Le connecteur est tolérant aux variations de schéma : pour chaque attribut,
on essaie plusieurs chemins (length, baseLine.length, properties.section.width…)
parce que Speckle n'impose pas de structure rigide aux Beam/Column.

specklepy 3.x utilise la terminologie moderne :
    stream  -> project
    branch  -> model
    commit  -> version
"""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable, Optional
from urllib.parse import urlparse

# Import optionnel : l'app marche sans specklepy
try:
    from specklepy.api.client import SpeckleClient
    from specklepy.api.credentials import get_account_from_token
    from specklepy.transports.server import ServerTransport
    from specklepy.api import operations
    from specklepy.objects.base import Base
    from specklepy.core.api.inputs.version_inputs import CreateVersionInput
    from specklepy.core.api.inputs.model_inputs import CreateModelInput
    SPECKLE_AVAILABLE = True
except ImportError:
    SPECKLE_AVAILABLE = False
    Base = None  # type: ignore

# Format pivot
from engine import Grume, Debit, Resultat
# Helpers de génération de meshes (pour export 3D)
import geometry


def _hex_to_argb(hex_str: str, alpha: int = 255) -> int:
    """'#A8D5BA' -> int ARGB."""
    s = hex_str.lstrip("#")
    r = int(s[0:2], 16)
    g = int(s[2:4], 16)
    b = int(s[4:6], 16)
    return (alpha << 24) | (r << 16) | (g << 8) | b


def _color_for_debit(name: str) -> int:
    """Couleur ARGB stable pour un nom de débit."""
    palette = ["#A8D5BA", "#F2C078", "#F2A07B", "#A1C9F4", "#FFB7B2",
               "#B5A8D9", "#FFD3B6", "#C7CEEA", "#B6E2D3", "#FAB1A0"]
    base = name.split("#")[0]
    h = sum(ord(c) for c in base)
    return _hex_to_argb(palette[h % len(palette)])


# ========== Disponibilité ==========

def is_available() -> bool:
    return SPECKLE_AVAILABLE


def _check_available():
    if not SPECKLE_AVAILABLE:
        raise RuntimeError(
            "specklepy n'est pas installé. "
            "Installation : pip install specklepy"
        )


# ========== URL parsing ==========

def parse_speckle_url(url: str) -> dict:
    """
    Parse une URL Speckle, moderne ou legacy.

    Retourne un dict avec : host, project_id, model_id, version_id.

    URLs supportées :
        https://app.speckle.systems/projects/PID/models/MID
        https://app.speckle.systems/projects/PID/models/MID@VID
        https://speckle.xyz/streams/SID/branches/BNAME       (legacy)
        https://speckle.xyz/streams/SID/commits/CID          (legacy)
        https://speckle.xyz/streams/SID                      (legacy)
    """
    parsed = urlparse(url.strip())
    host = parsed.netloc or "app.speckle.systems"
    parts = [p for p in parsed.path.split("/") if p]

    out = {"host": host, "project_id": None,
           "model_id": None, "version_id": None}

    # Format moderne : /projects/{pid}/models/{mid}@{vid}
    if "projects" in parts:
        i = parts.index("projects")
        if i + 1 < len(parts):
            out["project_id"] = parts[i + 1]
        if "models" in parts:
            j = parts.index("models")
            if j + 1 < len(parts):
                model_part = parts[j + 1]
                if "@" in model_part:
                    out["model_id"], out["version_id"] = model_part.split("@", 1)
                else:
                    out["model_id"] = model_part

    # Format legacy : /streams/{sid}/branches/{bname}
    elif "streams" in parts:
        i = parts.index("streams")
        if i + 1 < len(parts):
            out["project_id"] = parts[i + 1]   # stream_id == project_id en v3
        if "branches" in parts:
            j = parts.index("branches")
            if j + 1 < len(parts):
                out["model_id"] = parts[j + 1]
        if "commits" in parts:
            j = parts.index("commits")
            if j + 1 < len(parts):
                out["version_id"] = parts[j + 1]

    return out


# ========== Connexion ==========

def _connect(host: str, token: str):
    _check_available()
    client = SpeckleClient(host=host)
    account = get_account_from_token(token, host)
    client.authenticate_with_account(account)
    return client


def test_connection(url: str, token: str) -> tuple[bool, str]:
    """Teste les credentials. Retourne (ok, message)."""
    if not SPECKLE_AVAILABLE:
        return False, "specklepy non installé"
    if not token:
        return False, "Token vide"
    try:
        info = parse_speckle_url(url)
        client = _connect(info["host"], token)
        if info["project_id"]:
            project = client.project.get(info["project_id"])
            return True, f"OK : projet « {project.name} » accessible"
        user = client.active_user.get()
        name = getattr(user, "name", "?") if user else "?"
        return True, f"OK : connecté en tant que {name}"
    except Exception as e:
        return False, f"Échec : {type(e).__name__}: {e}"


# ========== Réception de l'objet racine ==========

def _receive_root(url: str, token: str):
    info = parse_speckle_url(url)
    if not info["project_id"]:
        raise ValueError(f"URL invalide : pas de project_id dans « {url} »")

    client = _connect(info["host"], token)

    if info["version_id"]:
        version = client.version.get(info["version_id"], info["project_id"])
        object_id = version.referencedObject
    elif info["model_id"]:
        model = client.model.get_with_versions(
            info["model_id"], info["project_id"], versions_limit=1
        )
        if not model.versions.items:
            raise RuntimeError(
                f"Aucune version sur le modèle « {info['model_id']} »"
            )
        object_id = model.versions.items[0].referencedObject
    else:
        raise ValueError(
            "URL invalide : il faut au moins un model_id "
            "(ou un version_id pour cibler une version précise)"
        )

    transport = ServerTransport(account=client.account,
                                stream_id=info["project_id"])
    return operations.receive(obj_id=object_id, remote_transport=transport)


# ========== Traversée de l'arbre Speckle ==========

def _traverse(obj) -> Iterable:
    """Yield récursivement tous les Base sous-jacents."""
    if not isinstance(obj, Base):
        return
    seen = set()
    stack = [obj]
    while stack:
        cur = stack.pop()
        if id(cur) in seen:
            continue
        seen.add(id(cur))
        yield cur
        for name in cur.get_member_names():
            if name.startswith("_") or name == "totalChildrenCount":
                continue
            try:
                value = getattr(cur, name, None)
            except Exception:
                continue
            if isinstance(value, Base):
                stack.append(value)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, Base):
                        stack.append(item)


def _get_attr(obj, *paths, default=None):
    """Essaie plusieurs chemins en pointé jusqu'à en trouver un défini."""
    for path in paths:
        cur = obj
        ok = True
        for part in path.split("."):
            try:
                cur = getattr(cur, part)
            except (AttributeError, KeyError):
                ok = False
                break
            if cur is None:
                ok = False
                break
        if ok and cur is not None:
            return cur
    return default


def _matches_type(obj, type_keywords) -> bool:
    """speckle_type contient l'un des mots-clés (case-insensitive)."""
    stype = (getattr(obj, "speckle_type", "") or "").lower()
    return any(kw.lower() in stype for kw in type_keywords)


def _length_from_baseline(obj) -> Optional[float]:
    """Calcule la longueur depuis baseLine.start/end si dispo."""
    start = _get_attr(obj, "baseLine.start")
    end = _get_attr(obj, "baseLine.end")
    if start is None or end is None:
        return None
    try:
        return ((end.x - start.x) ** 2
                + (end.y - start.y) ** 2
                + (end.z - start.z) ** 2) ** 0.5
    except AttributeError:
        return None


# ========== Import débits ==========

DEFAULT_DEBIT_KEYWORDS = ["Beam", "Column", "Member", "StructuralFraming"]


def import_debits(url: str, token: str,
                  type_keywords: Optional[list] = None,
                  unit_scale: float = 1.0) -> list:
    """
    Importe les débits d'un modèle Speckle.

    Args:
        url : URL Speckle (moderne ou legacy)
        token : Personal Access Token
        type_keywords : mots-clés à matcher dans speckle_type
            (défaut : Beam, Column, Member, StructuralFraming)
        unit_scale : multiplicateur (1.0 si modèle en m, 0.001 si en mm)

    Returns:
        list[Debit] avec quantités agrégées par signature (nom + dimensions).
    """
    _check_available()
    if type_keywords is None:
        type_keywords = DEFAULT_DEBIT_KEYWORDS

    root = _receive_root(url, token)
    debits = []

    for obj in _traverse(root):
        if not _matches_type(obj, type_keywords):
            continue

        length = _get_attr(obj, "length", "baseLine.length",
                           "parameters.length")
        if length is None:
            length = _length_from_baseline(obj)
        if length is None or length <= 0:
            continue

        width = _get_attr(obj, "profile.width", "properties.section.width",
                          "section.width", "width")
        height = _get_attr(obj, "profile.depth", "profile.height",
                           "properties.section.depth",
                           "properties.section.height",
                           "section.depth", "section.height",
                           "depth", "height")
        if width is None or height is None:
            continue

        nom = (getattr(obj, "name", None)
               or getattr(obj, "type", None)
               or obj.speckle_type.split(".")[-1])

        debits.append(Debit(
            nom=str(nom),
            longueur=float(length) * unit_scale,
            largeur=float(width) * unit_scale,
            hauteur=float(height) * unit_scale,
            quantite=1,
        ))

    return _aggregate(debits)


def _aggregate(debits: list) -> list:
    """Regroupe les débits identiques (à 1 mm près)."""
    groups = defaultdict(int)
    sample = {}
    for d in debits:
        key = (d.nom, round(d.longueur, 3),
               round(d.largeur, 3), round(d.hauteur, 3))
        groups[key] += d.quantite
        sample[key] = d
    return [Debit(d.nom, d.longueur, d.largeur, d.hauteur, groups[k])
            for k, d in sample.items()]


# ========== Import grumes ==========

DEFAULT_GRUME_KEYWORDS = ["Log", "Grume", "Trunk", "RoundWood"]


def import_grumes(url: str, token: str,
                  type_keywords: Optional[list] = None,
                  unit_scale: float = 1.0) -> list:
    """
    Importe les grumes d'un modèle Speckle.

    Convention attendue : speckle_type contient « Log » ou « Grume ».
    Attributs requis :
        - length (ou baseLine de longueur calculable)
        - diameter (ou radius)

    Returns:
        list[Grume]
    """
    _check_available()
    if type_keywords is None:
        type_keywords = DEFAULT_GRUME_KEYWORDS

    root = _receive_root(url, token)
    grumes = []
    counter = 1

    for obj in _traverse(root):
        if not _matches_type(obj, type_keywords):
            continue

        length = _get_attr(obj, "length", "baseLine.length")
        if length is None:
            length = _length_from_baseline(obj)

        diameter = _get_attr(obj, "diameter", "diam", "d")
        if diameter is None:
            radius = _get_attr(obj, "radius", "r")
            if radius is not None:
                diameter = 2 * radius

        if length is None or diameter is None:
            continue

        gid = getattr(obj, "name", None) or f"G{counter}"
        counter += 1
        grumes.append(Grume(
            id=str(gid),
            longueur=float(length) * unit_scale,
            diametre=float(diameter) * unit_scale,
        ))

    return grumes


# ========== Export plan de coupe ==========

def export_plan(resultat: Resultat, url: str, token: str,
                model_name: str = "cut-plan",
                message: Optional[str] = None,
                with_geometry: bool = True,
                kerf: float = 0.005,
                cylinder_segments: int = 24) -> str:
    """
    Pousse un plan de coupe vers Speckle.

    Args:
        resultat : Resultat issu du moteur 1D
        url : URL Speckle (projet)
        token : Personal Access Token
        model_name : nom du modèle de destination (créé si absent)
        message : message du commit (optionnel)
        with_geometry : si True, attache des meshes 3D (cylindres pour les
            grumes, boîtes pour les coupes) en displayValue. Visibles
            ensuite dans le viewer Speckle et dans Rhino via le connecteur.
        kerf : trait de scie (m), pour décaler les coupes
        cylinder_segments : finesse de tessellation des cylindres

    Returns:
        URL du commit créé.
    """
    _check_available()
    info = parse_speckle_url(url)
    if not info["project_id"]:
        raise ValueError(f"URL invalide : pas de project_id dans « {url} »")

    client = _connect(info["host"], token)

    # ----- Construire l'arbre de Bases -----
    plan = Base()
    plan["algorithm"] = resultat.nom_algo
    plan["bois_utilise_m"] = round(resultat.bois_utilise, 3)
    plan["chute_totale_m"] = round(resultat.chute_totale, 3)
    plan["taux_utilisation"] = round(resultat.taux_utilisation, 4)
    plan["nb_coupes"] = resultat.nb_coupes
    plan["debits_non_alloues"] = list(resultat.debits_non_alloues)

    allocations_bases = []
    y_offset = 0.0  # décalage en y pour séparer les grumes en 3D

    for a in resultat.allocations:
        ab = Base()
        ab["grume_id"] = a.grume_id
        ab["grume_longueur"] = a.grume_longueur
        ab["grume_diametre"] = a.grume_diametre
        ab["chute"] = a.chute

        # Mesh du cylindre représentant la grume (semi-transparent côté viewer)
        if with_geometry:
            v_cyl, t_cyl = geometry.cylindre(
                longueur=a.grume_longueur,
                rayon=a.grume_diametre / 2,
                x_offset=0.0,
                y_offset=y_offset,
                n_segments=cylinder_segments,
            )
            mesh_cyl = geometry.to_speckle_mesh(
                v_cyl, t_cyl, color=_hex_to_argb("#d4c08a", alpha=80),
            )
            # @displayValue : convention Speckle pour la géométrie affichable
            ab["@displayValue"] = [mesh_cyl]

        # Coupes
        # Regroupement par rail (mode couplé) ou tout sur un même axe (mode 1D pur)
        from collections import defaultdict
        coupes_par_rail = defaultdict(list)
        for c in a.coupes:
            rk = (c.rail_x, c.rail_y, c.section[0], c.section[1])
            coupes_par_rail[rk].append(c)

        coupes_bases = []
        for rk, coupes_rail in coupes_par_rail.items():
            rail_x, rail_y, w_sec, h_sec = rk
            if rail_x is None or rail_y is None:
                rail_x = -w_sec / 2
                rail_y = -h_sec / 2

            x_in_rail = 0.0
            for c in coupes_rail:
                cb = Base()
                cb["debit_nom"] = c.debit_nom
                cb["longueur"] = c.longueur
                cb["section_largeur"] = c.section[0]
                cb["section_hauteur"] = c.section[1]
                cb["x_dans_grume"] = round(x_in_rail, 4)
                cb["rail_x"] = round(rail_x, 4)
                cb["rail_y"] = round(rail_y, 4)

                if with_geometry:
                    v_box, t_box = geometry.boite(
                        x0=x_in_rail,
                        y0=y_offset + rail_x,
                        z0=rail_y,
                        longueur=c.longueur,
                        largeur=w_sec,
                        hauteur=h_sec,
                    )
                    mesh_box = geometry.to_speckle_mesh(
                        v_box, t_box,
                        color=_color_for_debit(c.debit_nom),
                    )
                    cb["@displayValue"] = [mesh_box]
                coupes_bases.append(cb)
                x_in_rail += c.longueur + kerf

        ab["@coupes"] = coupes_bases   # @ = stocké en objet détaché côté Speckle
        allocations_bases.append(ab)
        y_offset += a.grume_diametre + 0.30  # idem viz Streamlit

    plan["@allocations"] = allocations_bases

    # ----- Trouver ou créer le modèle cible -----
    project = client.project.get_with_models(info["project_id"])
    model_id = None
    for m in project.models.items:
        if m.name == model_name:
            model_id = m.id
            break
    if model_id is None:
        new_model = client.model.create(CreateModelInput(
            name=model_name,
            description="Plans de coupe générés par Optim'Charpente",
            project_id=info["project_id"],
        ))
        model_id = new_model.id

    # ----- Send + créer une version -----
    transport = ServerTransport(account=client.account,
                                stream_id=info["project_id"])
    object_id = operations.send(base=plan, transports=[transport])

    msg = message or (f"Plan de coupe ({resultat.nom_algo}, "
                      f"util. {resultat.taux_utilisation*100:.1f}%)")
    version = client.version.create(CreateVersionInput(
        object_id=object_id,
        model_id=model_id,
        project_id=info["project_id"],
        message=msg,
        source_application="Optim'Charpente",
    ))

    return f"https://{info['host']}/projects/{info['project_id']}/models/{model_id}@{version.id}"
