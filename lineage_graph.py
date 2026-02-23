import argparse
from pathlib import Path
import json
import re

import pandas as pd
import networkx as nx
from pyvis.network import Network


# =========================
# AJUSTES
# =========================
FOCUS_SCALE      = 0.81   # reducido 25% respecto al original
FOCUS_ANIM_MS    = 650

X_STEP = 240
Y_GAP  = 190

DIM_NODE_ALPHA_DARK   = 0.13
DIM_NODE_ALPHA_LIGHT  = 0.22
DIM_EDGE_OPACITY_DARK  = 0.22   # dark: aristas dimmeadas más visibles
DIM_EDGE_OPACITY_LIGHT = 0.45   # light: aristas dimmeadas claramente visibles

EDGE_DARK_COLOR   = "#38BDF8"
EDGE_LIGHT_COLOR  = "#334155"
EDGE_BASE_OPACITY_DARK  = 0.50   # aristas en dark theme
EDGE_BASE_OPACITY_LIGHT = 0.75   # aristas en light theme (mas visible)
EDGE_BASE_WIDTH     = 2.4
EDGE_DIM_COLOR      = "#94A3B8"
EDGE_ANCESTOR_WIDTH = 3.6

SELECT_BORDER_COLOR_DARK  = "#60A5FA"
SELECT_BORDER_COLOR_LIGHT = "#2563EB"
SELECT_BORDER_WIDTH = 3

# Nodos — tamaños generosos para que el texto entre
CIRCLE_SIZE        = 52    # radio minimo; la formula lo sube segun el texto
CIRCLE_FONT_SIZE   = 13
TRIANGLE_SIZE      = 90
TRIANGLE_FONT_SIZE = 13

BOX_MIN_W = 150
BOX_MAX_W = 240

CUSTOM_TEXT_COLOR = "#F1F5F9"   # texto claro uniforme en todos los nodos


# =========================
# Normalizaciones
# =========================
def norm(x) -> str:
    return "" if pd.isna(x) else str(x).strip()


def normalize_estado(s: str) -> str:
    s = norm(s).upper()
    for a, b in [("Á","A"),("É","E"),("Í","I"),("Ó","O"),("Ú","U")]:
        s = s.replace(a, b)
    s = s.replace("-"," ").replace("_"," ").strip()
    if s in ("EN PROCESO","ENPROCESO","ENPROCESO"): return "EN_PROCESO"
    if s in ("PRODUCTIVO","TERMINADO"): return "PRODUCTIVO"
    return "PENDIENTE"


def normalize_tipo(s: str) -> str:
    s = norm(s).upper()
    for a, b in [("Á","A"),("É","E"),("Í","I"),("Ó","O"),("Ú","U")]:
        s = s.replace(a, b)
    s = s.replace("-"," ").replace("_"," ").strip()
    if s in ("DATA ENTRY","DATAENTRY","DATA"):           return "DATA_ENTRY"
    if s in ("MODELO COE","MODELOCOE","COE"):            return "MODELO_COE"
    if s in ("MODELO INHOUSE","MODELOINHOUSE","INHOUSE"): return "MODELO_INHOUSE"
    if s in ("MODELO PRICING","MODELOPRICING","PRICING"): return "MODELO_PRICING"
    if s in ("BROAD",):                                   return "BROAD"
    if s in ("PROCESO","PROCESS"):                        return "PROCESO"
    return "PROCESO"


def parse_avance(v) -> float:
    if pd.isna(v): return 0.0
    if isinstance(v, str):
        s = v.strip()
        m = re.match(r"^\s*(\d+(?:\.\d+)?)\s*%\s*$", s)
        if m: return max(0.0, min(100.0, float(m.group(1))))
        try:
            num = float(s)
            return max(0.0, min(100.0, num * 100.0 if 0.0 <= num <= 1.0 else num))
        except Exception: return 0.0
    try:
        num = float(v)
        return max(0.0, min(100.0, num * 100.0 if 0.0 <= num <= 1.0 else num))
    except Exception: return 0.0


# =========================
# Estado → estilo
# =========================
# Color según ESTADO (forma ignorada aquí — la determina el TIPO)
STATE_COLOR = {
    "PENDIENTE":  {"bg": "#64748B", "border": "#475569"},  # gris
    "EN_PROCESO": {"bg": "#D97706", "border": "#B45309"},  # amarillo
    "PRODUCTIVO": {"bg": "#059669", "border": "#047857"},  # verde
}
STATE_COLOR_LIGHT = {
    "PENDIENTE":  {"bg": "#94A3B8", "border": "#64748B"},
    "EN_PROCESO": {"bg": "#F59E0B", "border": "#D97706"},
    "PRODUCTIVO": {"bg": "#10B981", "border": "#059669"},
}
# Forma según TIPO
TIPO_SHAPE = {
    "DATA_ENTRY":     "triangle",  # triángulo
    "MODELO_COE":     "circle",    # círculo
    "MODELO_INHOUSE": "circle",    # círculo
    "MODELO_PRICING": "circle",    # círculo
    "BROAD":          "square",    # cuadrado
    "PROCESO":        "box",       # rectángulo
}


# =========================
# Wrap
# =========================
def wrap_label_lines(s: str, max_chars: int = 14, max_lines: int = 3) -> list:
    s = (s or "").strip()
    if not s: return [""]
    words = s.split()
    lines, line = [], ""
    for w in words:
        candidate = (line + " " + w).strip()
        if len(candidate) <= max_chars:
            line = candidate
        else:
            if line: lines.append(line)
            if len(lines) >= max_lines: break
            line = w[:max_chars]
    if line and len(lines) < max_lines:
        lines.append(line)
    if not lines:
        lines = [s[:max_chars]]
    full = " ".join(lines)
    if len(full) < len(s) and lines:
        lines[-1] = lines[-1].rstrip("…") + "…"
    return lines[:max_lines]


def wrap_label(s: str, width: int = 22, max_lines: int = 3) -> str:
    return "\n".join(wrap_label_lines(s, max_chars=width, max_lines=max_lines))


# =========================
# Lectura Excel
# =========================
def _pick_col(df, candidates):
    cols = {c.strip().lower(): c for c in df.columns}
    for cand in candidates:
        if cand.strip().lower() in cols:
            return cols[cand.strip().lower()]
    return None


def read_excel(excel_path: str):
    xls   = pd.ExcelFile(excel_path)
    nodos = pd.read_excel(xls, "Nodos")
    deps  = pd.read_excel(xls, "Dependencias")
    nodos.columns = [c.strip() for c in nodos.columns]
    deps.columns  = [c.strip() for c in deps.columns]

    col_id         = _pick_col(nodos, ["ID"])
    col_tipo       = _pick_col(nodos, ["Tipo","TipoNodo"])
    col_nombre     = _pick_col(nodos, ["Nombre","NombreNodo"])
    col_estado     = _pick_col(nodos, ["Estado"])
    col_avance     = _pick_col(nodos, ["Avance","Porcentaje","Progreso"])
    col_comentario = _pick_col(nodos, ["Comentario","Comentarios","Comment","Notes","Notas"])
    col_equipo     = _pick_col(nodos, ["Equipo","Team","Area","Área"])
    col_origen     = _pick_col(deps,  ["IDOrigen"])
    col_dest       = _pick_col(deps,  ["IDDestino"])

    missing = [n for n, c in [("ID",col_id),("Tipo",col_tipo),("Nombre",col_nombre),
                                ("Estado",col_estado),("Avance",col_avance)] if c is None]
    if missing: raise ValueError(f"En hoja 'Nodos' faltan columnas: {missing}")
    if col_origen is None or col_dest is None:
        raise ValueError("En hoja 'Dependencias' faltan columnas: IDOrigen, IDDestino")

    return nodos, deps, (col_id, col_tipo, col_nombre, col_estado, col_avance, col_comentario, col_equipo, col_origen, col_dest)


# =========================
# Grafo
# =========================
def build_dag(nodos, deps, cols):
    col_id, col_tipo, col_nombre, col_estado, col_avance, col_comentario, col_equipo, col_origen, col_dest = cols
    G = nx.DiGraph()
    for _, r in nodos.iterrows():
        _id = norm(r[col_id])
        if not _id: continue
        comentario = norm(r[col_comentario]) if col_comentario else ""
        equipo     = norm(r[col_equipo])     if col_equipo     else ""
        G.add_node(_id,
                   label=norm(r[col_nombre]),
                   tipo=normalize_tipo(r[col_tipo]),
                   estado=normalize_estado(r[col_estado]),
                   avance=parse_avance(r[col_avance]),
                   comentario=comentario,
                   equipo=equipo)
    for _, r in deps.iterrows():
        src, dst = norm(r[col_origen]), norm(r[col_dest])
        if not src or not dst: continue
        for n in (src, dst):
            if n not in G:
                G.add_node(n, label=n, tipo="PROCESO", estado="PENDIENTE", avance=0.0, comentario="")
        G.add_edge(src, dst)
    if not nx.is_directed_acyclic_graph(G):
        cyc = nx.find_cycle(G, orientation="original")
        raise ValueError(f"❌ Ciclo detectado: {cyc}")
    return G


def topological_levels(G):
    level = {}
    for v in nx.topological_sort(G):
        preds = list(G.predecessors(v))
        level[v] = 0 if not preds else 1 + max(level[p] for p in preds)
    return level


def assign_positions(G, level):
    CENTER = 450
    counters = {}
    pos = {}
    nodes_sorted = sorted(G.nodes(data=True),
        key=lambda item: (level.get(item[0],0), item[1].get("tipo",""), item[1].get("label",item[0])))
    offsets = [0,+1,-1,+2,-2,+3,-3,+4,-4,+5,-5,+6,-6]
    for n, _d in nodes_sorted:
        lvl = level.get(n, 0)
        counters[lvl] = counters.get(lvl, 0) + 1
        idx = counters[lvl] - 1
        step = offsets[idx] if idx < len(offsets) else (idx//2)*(1 if idx%2 else -1)
        pos[n] = (lvl * X_STEP, CENTER + step * Y_GAP)
    return pos


# =========================
# UI + JS — tooltip custom en JS, sin HTML en vis title
# =========================
UI_INJECT = r"""
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=DM+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">

<style>
*, *::before, *::after { box-sizing: border-box; }

:root {
  --panel-bg: rgba(10,15,30,0.84);
  --panel-border: rgba(148,163,184,0.14);
  --panel-shadow: 0 24px 60px rgba(0,0,0,0.55), inset 0 1px 0 rgba(255,255,255,0.04);
  --input-bg: rgba(248,250,252,0.06);
  --input-border: rgba(148,163,184,0.15);
  --text-primary: #F1F5F9;
  --text-secondary: #94A3B8;
  --text-muted: #475569;
  --divider: rgba(148,163,184,0.08);
  --dd-bg: rgba(10,15,30,0.97);
  --item-hover: rgba(99,102,241,0.12);
  --toast-bg: rgba(10,15,30,0.94);
  --pct-badge-bg: rgba(99,102,241,0.14);
  --pct-badge-color: #818CF8;
  --range-track: rgba(148,163,184,0.15);
  --select-opt-bg: #0F172A;
  --select-opt-color: #E2E8F0;
}
body.light-theme {
  --panel-bg: rgba(255,255,255,0.90);
  --panel-border: rgba(30,58,138,0.12);
  --panel-shadow: 0 24px 60px rgba(30,58,138,0.12), inset 0 1px 0 rgba(255,255,255,0.9);
  --input-bg: rgba(241,245,249,0.9);
  --input-border: rgba(30,58,138,0.15);
  --text-primary: #0F172A;
  --text-secondary: #334155;
  --text-muted: #64748B;
  --divider: rgba(15,23,42,0.08);
  --dd-bg: rgba(255,255,255,0.98);
  --item-hover: rgba(37,99,235,0.08);
  --toast-bg: rgba(255,255,255,0.95);
  --pct-badge-bg: rgba(37,99,235,0.10);
  --pct-badge-color: #1D4ED8;
  --range-track: rgba(15,23,42,0.12);
  --select-opt-bg: #F1F5F9;
  --select-opt-color: #0F172A;
}

html, body { height:100%; margin:0; padding:0; overflow:hidden; font-family:'DM Sans',sans-serif; }
body { background:#080D1C; transition:background .4s; }
body.light-theme { background:#EEF2FF; }

#mynetwork { width:100vw!important; height:100vh!important; border:0!important; transition:background .4s; }
.card,.card-body { border:0!important; box-shadow:none!important; padding:0!important; margin:0!important; background:transparent!important; }
.vis-network,.vis-network>div,.vis-network canvas { border:0!important; outline:none!important; }
.vis-navigation { display:none!important; }
/* Suprimir tooltip nativo de vis (lo reemplazamos con el nuestro) */
.vis-tooltip { display:none!important; visibility:hidden!important; opacity:0!important; pointer-events:none!important; }
#mynetwork canvas { cursor:grab!important; }
#mynetwork.grabbing canvas { cursor:grabbing!important; }

/* ── Panel ── */
.ui-panel {
  position:fixed; top:18px; left:18px; z-index:9999;
  width:320px;
  background:var(--panel-bg);
  border:1px solid var(--panel-border);
  border-radius:20px; padding:15px;
  box-shadow:var(--panel-shadow);
  backdrop-filter:blur(20px); -webkit-backdrop-filter:blur(20px);
  transition:background .35s,border-color .35s,box-shadow .35s,
             transform .3s cubic-bezier(.4,0,.2,1),opacity .3s;
}
.ui-panel.collapsed {
  transform: translateX(calc(-100% - 22px));
  opacity: 0;
  pointer-events: none;
}
/* Botón toggle del panel — siempre visible */
.ui-panel-toggle {
  position:fixed; top:18px; left:18px; z-index:10000;
  width:36px; height:36px;
  border-radius:10px;
  border:1px solid var(--panel-border);
  background:var(--panel-bg);
  backdrop-filter:blur(20px); -webkit-backdrop-filter:blur(20px);
  box-shadow:0 4px 14px rgba(0,0,0,0.25);
  cursor:pointer;
  display:none;   /* oculto cuando panel está abierto */
  align-items:center; justify-content:center;
  transition:background .2s, border-color .2s, opacity .3s;
}
.ui-panel-toggle:hover { background:rgba(99,102,241,0.22); border-color:rgba(99,102,241,0.4); }
.ui-panel-toggle svg { width:16px; height:16px; }
.ui-panel-close-btn {
  width:32px; height:32px;
  display:flex; align-items:center; justify-content:center; flex-shrink:0;
  border-radius:9px;
  border:1px solid var(--panel-border);
  background:var(--input-bg);
  cursor:pointer;
  transition:background .2s, border-color .2s, transform .1s;
  box-shadow:0 2px 8px rgba(0,0,0,0.18);
}
.ui-panel-close-btn:hover { background:rgba(99,102,241,0.22); border-color:rgba(99,102,241,0.4); }
.ui-panel-close-btn:active { transform:scale(.91); }
.ui-panel-close-btn svg { width:15px; height:15px; }
.ui-brand { display:flex; align-items:center; gap:9px; margin-bottom:13px; }
.ui-brand-name { font-size:12px; font-weight:700; color:var(--text-primary); letter-spacing:.5px; text-transform:uppercase; transition:color .3s; }
.ui-brand-sub  { font-size:10px; color:var(--text-muted); font-family:'IBM Plex Mono',monospace; transition:color .3s; }

.ui-search-wrap { position:relative; }
.ui-search-icon { position:absolute; left:11px; top:50%; transform:translateY(-50%); color:var(--text-muted); pointer-events:none; transition:color .3s; }
.ui-search { width:100%; padding:9px 11px 9px 34px; border-radius:11px; border:1px solid var(--input-border); font-size:13px; font-family:'DM Sans',sans-serif; outline:none; background:var(--input-bg); color:var(--text-primary); transition:border-color .2s,box-shadow .2s,background .3s,color .3s; }
.ui-search::placeholder { color:var(--text-muted); }
.ui-search:focus { border-color:rgba(99,102,241,0.5); box-shadow:0 0 0 3px rgba(99,102,241,0.14); }

.ui-divider { height:1px; background:var(--divider); margin:11px 0; transition:background .3s; }

.ui-filters { display:grid; grid-template-columns:1fr 1fr; gap:8px; }
.ui-label { font-size:10px; font-weight:600; color:var(--text-muted); text-transform:uppercase; letter-spacing:.6px; margin-bottom:5px; transition:color .3s; }
.ui-select { width:100%; padding:8px 10px; border-radius:10px; border:1px solid var(--input-border); font-size:12px; font-family:'DM Sans',sans-serif; outline:none; background:var(--input-bg); color:var(--text-primary); cursor:pointer; -webkit-appearance:none; appearance:none; transition:border-color .2s,background .3s,color .3s; }
.ui-select:focus { border-color:rgba(99,102,241,0.4); }
.ui-select option { background:var(--select-opt-bg); color:var(--select-opt-color); }

.ui-slider-wrap { margin-top:8px; }
.ui-slider-header { display:flex; justify-content:space-between; align-items:center; margin-bottom:5px; }
.ui-pct-badge { font-size:11px; font-family:'IBM Plex Mono',monospace; color:var(--pct-badge-color); font-weight:600; background:var(--pct-badge-bg); padding:2px 7px; border-radius:6px; transition:background .3s,color .3s; }
.ui-range { width:100%; height:4px; -webkit-appearance:none; appearance:none; background:var(--range-track); border-radius:99px; outline:none; cursor:pointer; transition:background .3s; }
.ui-range::-webkit-slider-thumb { -webkit-appearance:none; width:16px; height:16px; border-radius:50%; background:linear-gradient(135deg,#6366F1,#3B82F6); cursor:pointer; box-shadow:0 2px 8px rgba(99,102,241,0.45); border:2px solid rgba(255,255,255,0.25); }
.ui-range::-moz-range-thumb { width:16px; height:16px; border-radius:50%; background:linear-gradient(135deg,#6366F1,#3B82F6); cursor:pointer; border:2px solid rgba(255,255,255,0.25); }

/* Leyenda */
.ui-legend { display:flex; gap:10px; margin-top:11px; flex-wrap:wrap; }
.ui-leg-item { display:flex; align-items:center; gap:5px; }
.ui-leg-sym { width:10px; height:10px; flex-shrink:0; }
.ui-leg-sym.cir { border-radius:50%; }
.ui-leg-sym.tri { width:0; height:0; border-left:6px solid transparent; border-right:6px solid transparent; border-bottom:10px solid #94A3B8; background:transparent; }
.ui-leg-sym.bx  { border-radius:2px; }
.ui-leg-label { font-size:10px; color:var(--text-muted); transition:color .3s; }

/* ── Controles derecha ── */
.ui-controls {
  position:fixed; top:18px; right:18px; z-index:9999;
  display:flex; flex-direction:column; gap:6px; align-items:center;
}
.ui-btn {
  width:40px; height:40px; display:flex; align-items:center; justify-content:center;
  border-radius:11px; border:1px solid var(--panel-border);
  background:var(--panel-bg); backdrop-filter:blur(20px); -webkit-backdrop-filter:blur(20px);
  cursor:pointer; transition:background .2s,border-color .2s,transform .1s;
  box-shadow:0 4px 14px rgba(0,0,0,0.25);
}
.ui-btn:hover { background:rgba(99,102,241,0.22); border-color:rgba(99,102,241,0.4); }
.ui-btn:active { transform:scale(.91); }
.ui-btn svg { width:17px; height:17px; }

/* Slider de zoom vertical */
.ui-zoom-track {
  width:40px; height:120px;
  background:var(--panel-bg);
  border:1px solid var(--panel-border);
  border-radius:12px;
  backdrop-filter:blur(20px); -webkit-backdrop-filter:blur(20px);
  box-shadow:0 4px 14px rgba(0,0,0,0.25);
  display:flex; align-items:center; justify-content:center;
  padding:10px 0;
}
.ui-zoom-slider {
  -webkit-appearance:none; appearance:none;
  writing-mode:vertical-lr;
  direction:rtl;
  width:4px; height:100%;
  background:var(--range-track);
  border-radius:99px; outline:none; cursor:pointer;
  transition:background .3s;
}
.ui-zoom-slider::-webkit-slider-thumb {
  -webkit-appearance:none;
  width:16px; height:16px; border-radius:50%;
  background:linear-gradient(135deg,#6366F1,#3B82F6);
  cursor:pointer;
  box-shadow:0 2px 8px rgba(99,102,241,0.45);
  border:2px solid rgba(255,255,255,0.25);
}
.ui-zoom-slider::-moz-range-thumb {
  width:16px; height:16px; border-radius:50%;
  background:linear-gradient(135deg,#6366F1,#3B82F6);
  cursor:pointer; border:2px solid rgba(255,255,255,0.25);
}

.ui-sep { height:1px; background:var(--panel-border); width:28px; margin:1px 6px; transition:background .3s; }

/* ── Tooltip custom ── */
.ui-tooltip {
  position:fixed; z-index:99999; pointer-events:none;
  background:#0F172A;
  border:1px solid rgba(148,163,184,0.18);
  border-radius:14px;
  padding:13px 15px;
  min-width:210px; max-width:300px;
  box-shadow:0 20px 50px rgba(0,0,0,0.55);
  font-family:'DM Sans','Segoe UI',sans-serif;
  display:none;
  transition:background .35s, border-color .35s;
}
body.light-theme .ui-tooltip {
  background:#FFFFFF;
  border:1px solid rgba(30,58,138,0.15);
  box-shadow:0 16px 40px rgba(30,58,138,0.18);
}
body.light-theme .ui-tooltip-name { color:#0F172A; }
body.light-theme .ui-tooltip-avance-label { color:#475569; }
body.light-theme .ui-tooltip-avance-label span { color:#0F172A; }
body.light-theme .ui-tooltip-comment { border-top-color:rgba(15,23,42,0.10); }
body.light-theme .ui-tooltip-comment-label { color:#64748B; }
body.light-theme .ui-tooltip-comment-text { color:#334155; }
body.light-theme .ui-tooltip-tag.tipo  { background:rgba(99,102,241,0.12); color:#4338CA; }
body.light-theme .ui-tooltip-tag.estado{ background:rgba(15,23,42,0.07);   color:#475569; }
body.light-theme .ui-tooltip-tag.equipo{ background:rgba(5,150,105,0.12);   color:#065F46; }
.ui-tooltip-name { font-size:13px; font-weight:700; color:#F1F5F9; margin-bottom:8px; line-height:1.3; }
.ui-tooltip-tags { display:flex; gap:6px; flex-wrap:wrap; margin-bottom:9px; }
.ui-tooltip-tag { font-size:10px; padding:2px 8px; border-radius:6px; }
.ui-tooltip-tag.tipo  { background:rgba(99,102,241,0.20); color:#A5B4FC; }
.ui-tooltip-tag.estado{ background:rgba(148,163,184,0.12); color:#94A3B8; }
.ui-tooltip-tag.equipo{ background:rgba(16,185,129,0.18);  color:#6EE7B7; }
.ui-tooltip-avance-label { font-size:10px; color:#64748B; margin-bottom:4px; }
.ui-tooltip-avance-label span { color:#E2E8F0; font-weight:600; }
.ui-tooltip-bar-track { background:rgba(148,163,184,0.12); border-radius:99px; height:6px; overflow:hidden; }
.ui-tooltip-bar-fill  { height:100%; border-radius:99px; }
.ui-tooltip-comment { margin-top:9px; padding-top:9px; border-top:1px solid rgba(148,163,184,0.15); }
.ui-tooltip-comment-label { font-size:10px; color:#64748B; text-transform:uppercase; letter-spacing:.5px; margin-bottom:3px; }
.ui-tooltip-comment-text  { font-size:12px; color:#CBD5E1; line-height:1.45; }

/* ── Dropdown ── */
.ui-dd { position:fixed; top:80px; left:18px; width:320px; max-height:270px; overflow:auto; background:var(--dd-bg); border:1px solid var(--panel-border); border-radius:15px; box-shadow:0 24px 60px rgba(0,0,0,0.45); display:none; z-index:10000; transition:background .3s; }
.ui-item { padding:9px 13px; font-size:13px; cursor:pointer; color:var(--text-primary); border-bottom:1px solid var(--divider); transition:background .15s,color .3s; }
.ui-item:last-child { border-bottom:0; }
.ui-item:hover { background:var(--item-hover); }
.ui-item small { color:var(--text-muted); display:block; margin-top:2px; font-family:'IBM Plex Mono',monospace; font-size:10px; }

/* ── Toast ── */
.ui-toast { position:fixed; bottom:22px; left:50%; transform:translateX(-50%); z-index:9999; background:var(--toast-bg); border:1px solid var(--panel-border); border-radius:13px; padding:9px 17px; font-size:12px; color:var(--text-secondary); font-family:'IBM Plex Mono',monospace; box-shadow:0 8px 32px rgba(0,0,0,0.35); backdrop-filter:blur(16px); -webkit-backdrop-filter:blur(16px); display:none; white-space:nowrap; max-width:90vw; text-overflow:ellipsis; overflow:hidden; transition:background .3s; }
.ui-toast.visible { display:block; }
.ui-toast strong { color:var(--text-primary); }

/* Scrollbar */
.ui-dd::-webkit-scrollbar { width:4px; }
.ui-dd::-webkit-scrollbar-track { background:transparent; }
.ui-dd::-webkit-scrollbar-thumb { background:rgba(148,163,184,0.2); border-radius:4px; }
</style>

<!-- Botón toggle flotante (se muestra cuando panel está oculto) -->
<button id="btnShowPanel" class="ui-panel-toggle" title="Mostrar panel">
  <svg viewBox="0 0 24 24" fill="none" stroke="var(--text-primary)" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
    <line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="18" x2="21" y2="18"/>
  </svg>
</button>

<!-- Panel principal -->
<div class="ui-panel" id="uiPanel">
  <div class="ui-brand" style="justify-content:space-between;">
    <div>
      <div class="ui-brand-name">Mapeo Dependencias</div>
      <div class="ui-brand-sub">grafo de dependencias</div>
    </div>
    <button id="btnCollapsePanel" class="ui-panel-close-btn" title="Ocultar panel">
      <svg viewBox="0 0 24 24" fill="none" stroke="#94A3B8" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M15 18l-6-6 6-6"/>
      </svg>
    </button>
  </div>

  <div class="ui-search-wrap">
    <span class="ui-search-icon">
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round">
        <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
      </svg>
    </span>
    <input id="uiSearch" class="ui-search" placeholder="Buscar nodo..." autocomplete="off"/>
  </div>

  <div class="ui-divider"></div>

  <div class="ui-filters">
    <div>
      <div class="ui-label">Estado</div>
      <select id="uiEstado" class="ui-select">
        <option value="ALL">Todos</option>
        <option value="PENDIENTE">Pendiente</option>
        <option value="EN_PROCESO">En proceso</option>
        <option value="PRODUCTIVO">Productivo</option>
      </select>
    </div>
    <div>
      <div class="ui-label">Tipo</div>
      <select id="uiTipo" class="ui-select">
        <option value="ALL">Todos</option>
        <option value="DATA_ENTRY">Data Entry</option>
        <option value="MODELO_COE">Modelo CoE</option>
        <option value="MODELO_INHOUSE">Modelo Inhouse</option>
        <option value="MODELO_PRICING">Modelo Pricing</option>
        <option value="BROAD">Broad</option>
        <option value="PROCESO">Proceso</option>
      </select>
    </div>
  </div>

  <div class="ui-slider-wrap">
    <div class="ui-slider-header">
      <div class="ui-label">Avance mínimo</div>
      <div class="ui-pct-badge" id="uiPct">0%</div>
    </div>
    <input id="uiRange" class="ui-range" type="range" min="0" max="100" step="1" value="0"/>
  </div>

  <div class="ui-divider"></div>

  <div class="ui-label" style="margin-top:2px;">Estado</div>
  <div class="ui-legend">
    <div class="ui-leg-item">
      <div class="ui-leg-sym bx" style="background:#64748B;"></div>
      <span class="ui-leg-label">Pendiente</span>
    </div>
    <div class="ui-leg-item">
      <div class="ui-leg-sym bx" style="background:#D97706;"></div>
      <span class="ui-leg-label">En proceso</span>
    </div>
    <div class="ui-leg-item">
      <div class="ui-leg-sym bx" style="background:#059669;"></div>
      <span class="ui-leg-label">Productivo</span>
    </div>
  </div>
  <div class="ui-label" style="margin-top:8px;">Tipo</div>
  <div class="ui-legend">
    <div class="ui-leg-item">
      <div class="ui-leg-sym cir" style="background:#64748B;"></div>
      <span class="ui-leg-label">Modelo</span>
    </div>
    <div class="ui-leg-item">
      <div class="ui-leg-sym tri"></div>
      <span class="ui-leg-label">Data Entry</span>
    </div>
    <div class="ui-leg-item">
      <div class="ui-leg-sym bx" style="background:#64748B;width:14px;height:10px;"></div>
      <span class="ui-leg-label">Proceso</span>
    </div>
    <div class="ui-leg-item">
      <div class="ui-leg-sym bx" style="background:#64748B;width:10px;height:10px;"></div>
      <span class="ui-leg-label">Broad</span>
    </div>
  </div>
</div>

<!-- Controles derecha -->
<div class="ui-controls">
  <button id="uiZoomIn" class="ui-btn" title="Acercar">
    <svg viewBox="0 0 24 24" fill="none" stroke="#94A3B8" stroke-width="2.2" stroke-linecap="round">
      <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
      <line x1="11" y1="8" x2="11" y2="14"/><line x1="8" y1="11" x2="14" y2="11"/>
    </svg>
  </button>

  <!-- Slider zoom vertical -->
  <div class="ui-zoom-track">
    <input id="uiZoomSlider" class="ui-zoom-slider" type="range" min="25" max="250" step="5" value="100" title="Zoom"/>
  </div>

  <button id="uiZoomOut" class="ui-btn" title="Alejar">
    <svg viewBox="0 0 24 24" fill="none" stroke="#94A3B8" stroke-width="2.2" stroke-linecap="round">
      <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
      <line x1="8" y1="11" x2="14" y2="11"/>
    </svg>
  </button>

  <button id="uiFit" class="ui-btn" title="Ajustar pantalla">
    <svg viewBox="0 0 24 24" fill="none" stroke="#94A3B8" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
      <path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"/>
    </svg>
  </button>

  <div class="ui-sep"></div>

  <button id="uiReset" class="ui-btn" title="Restablecer">
    <svg viewBox="0 0 24 24" fill="none" stroke="#94A3B8" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
      <path d="M21 12a9 9 0 1 1-3.2-6.9"/><path d="M21 4v6h-6"/>
    </svg>
  </button>

  <button id="uiTheme" class="ui-btn" title="Cambiar tema">
    <svg id="iconSun" viewBox="0 0 24 24" fill="none" stroke="#94A3B8" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
      <circle cx="12" cy="12" r="5"/>
      <line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/>
      <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/>
      <line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/>
      <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>
    </svg>
    <svg id="iconMoon" viewBox="0 0 24 24" fill="none" stroke="#94A3B8" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" style="display:none;">
      <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>
    </svg>
  </button>
</div>

<!-- Tooltip custom (reemplaza al de vis) -->
<div id="uiTooltip" class="ui-tooltip">
  <div id="ttName"   class="ui-tooltip-name"></div>
  <div id="ttTags"   class="ui-tooltip-tags"></div>
  <div id="ttEquipo" style="display:none;margin-bottom:6px;">
    <span id="ttEquipoTag" class="ui-tooltip-tag equipo"></span>
  </div>
  <div id="ttAvLbl"  class="ui-tooltip-avance-label">Avance: <span id="ttAvNum"></span></div>
  <div class="ui-tooltip-bar-track">
    <div id="ttBar"  class="ui-tooltip-bar-fill"></div>
  </div>
  <div id="ttComment" class="ui-tooltip-comment" style="display:none;">
    <div class="ui-tooltip-comment-label">Comentario</div>
    <div id="ttCommentText" class="ui-tooltip-comment-text"></div>
  </div>
</div>

<div id="uiDD" class="ui-dd"></div>
<div id="uiToast" class="ui-toast"></div>

<script>
(function(){
  if (typeof network === 'undefined' || typeof nodes === 'undefined' || typeof edges === 'undefined') return;

  // ── Constantes ────────────────────────────────────
  var FOCUS_SCALE         = __FOCUS_SCALE__;
  var FOCUS_ANIM_MS       = __FOCUS_ANIM_MS__;
  var DIM_NODE_ALPHA_DARK    = __DIM_NODE_ALPHA_DARK__;
  var DIM_NODE_ALPHA_LIGHT   = __DIM_NODE_ALPHA_LIGHT__;
  var DIM_EDGE_OPACITY_DARK  = __DIM_EDGE_OPACITY_DARK__;
  var DIM_EDGE_OPACITY_LIGHT = __DIM_EDGE_OPACITY_LIGHT__;
  function dimNodeAlpha(){ return isDark ? DIM_NODE_ALPHA_DARK : DIM_NODE_ALPHA_LIGHT; }
  function dimEdgeOpacity(){ return isDark ? DIM_EDGE_OPACITY_DARK : DIM_EDGE_OPACITY_LIGHT; }
  var EDGE_DARK_COLOR     = "__EDGE_DARK_COLOR__";
  var EDGE_LIGHT_COLOR    = "__EDGE_LIGHT_COLOR__";
  var EDGE_BASE_OPACITY_DARK  = __EDGE_BASE_OPACITY_DARK__;
  var EDGE_BASE_OPACITY_LIGHT = __EDGE_BASE_OPACITY_LIGHT__;
  function edgeOpacity(){ return isDark ? EDGE_BASE_OPACITY_DARK : EDGE_BASE_OPACITY_LIGHT; }
  var EDGE_BASE_WIDTH     = __EDGE_BASE_WIDTH__;
  var EDGE_DIM_COLOR      = "__EDGE_DIM_COLOR__";
  var EDGE_ANCESTOR_WIDTH = __EDGE_ANCESTOR_WIDTH__;
  var SEL_BORDER_DARK     = "__SELECT_BORDER_COLOR_DARK__";
  var SEL_BORDER_LIGHT    = "__SELECT_BORDER_COLOR_LIGHT__";
  var SEL_BORDER_WIDTH    = __SELECT_BORDER_WIDTH__;
  var CUSTOM_TEXT_COLOR   = "__CUSTOM_TEXT_COLOR__";

  var isDark = true;
  function edgeColor(){ return isDark ? EDGE_DARK_COLOR : EDGE_LIGHT_COLOR; }
  function selBorder(){ return isDark ? SEL_BORDER_DARK : SEL_BORDER_LIGHT; }

  // ── DOM ───────────────────────────────────────────
  var container   = document.getElementById("mynetwork");
  var input       = document.getElementById("uiSearch");
  var dd          = document.getElementById("uiDD");
  var btnReset    = document.getElementById("uiReset");
  var btnFit      = document.getElementById("uiFit");
  var btnZoomIn   = document.getElementById("uiZoomIn");
  var btnZoomOut  = document.getElementById("uiZoomOut");
  var zoomSlider  = document.getElementById("uiZoomSlider");
  var btnTheme    = document.getElementById("uiTheme");
  var iconSun     = document.getElementById("iconSun");
  var iconMoon    = document.getElementById("iconMoon");
  var range       = document.getElementById("uiRange");
  var pct         = document.getElementById("uiPct");
  var selEstado   = document.getElementById("uiEstado");
  var selTipo     = document.getElementById("uiTipo");
  var toast       = document.getElementById("uiToast");
  var tooltip     = document.getElementById("uiTooltip");
  var ttName      = document.getElementById("ttName");
  var ttTags      = document.getElementById("ttTags");
  var ttAvNum     = document.getElementById("ttAvNum");
  var ttBar       = document.getElementById("ttBar");
  var ttEquipo    = document.getElementById("ttEquipo");
  var ttEquipoTag = document.getElementById("ttEquipoTag");
  var ttComment   = document.getElementById("ttComment");
  var ttCommentText = document.getElementById("ttCommentText");
  var toastTimer  = null;
  var tooltipTimer = null;

  // ── Color utils ───────────────────────────────────
  function hexToRgb(hex){
    var h=(hex||"").trim();
    if(h.length!==7||h[0]!=="#") return null;
    return {r:parseInt(h.slice(1,3),16),g:parseInt(h.slice(3,5),16),b:parseInt(h.slice(5,7),16)};
  }
  function rgba(hex,a){
    var c=hexToRgb(hex); if(!c) return hex;
    return "rgba("+c.r+","+c.g+","+c.b+","+a+")";
  }
  function alphaFromRgba(s){
    var m=String(s||"").match(/rgba\([^,]+,[^,]+,[^,]+,\s*([0-9.]+)\s*\)/i);
    return m?Math.max(0,Math.min(1,parseFloat(m[1]))):1.0;
  }

  // ── Snapshot ──────────────────────────────────────
  var nodeIds=nodes.getIds(), edgeIds=edges.getIds();
  var initialPos={};
  nodes.get().forEach(function(n){ initialPos[n.id]={x:n.x,y:n.y}; });

  var baseNode={};
  nodes.get().forEach(function(n){
    baseNode[n.id]={
      bg:       (n.color&&n.color.background)?n.color.background:"#475569",
      border:   (n.color&&n.color.border)?n.color.border:"#334155",
      bg_l:     n.bg_light   || ((n.color&&n.color.background)?n.color.background:"#64748B"),
      border_l: n.border_light|| ((n.color&&n.color.border)?n.color.border:"#475569"),
      fontColor:    CUSTOM_TEXT_COLOR,
      borderWidth:  n.borderWidth||2,
      shape:        (n.shape||"").toLowerCase(),
      customText:   !!n.customText,
      customFontSize: Number(n.customFontSize||10)
    };
  });

  // nodeData: todos los metadatos por id (para tooltip)
  var nodeData={};
  nodes.get().forEach(function(n){
    nodeData[n.id]={
      nombre:    (n.nombre||n.label||n.id||"").replace(/\n/g," ").trim(),
      tipo:      (n.tipo||"").toUpperCase(),
      estado:    (n.estado||"").toUpperCase(),
      avance:    isFinite(Number(n.avance))?Number(n.avance):0,
      comentario:(n.comentario||""),
      equipo:    (n.equipo||"")
    };
  });

  var incoming={};
  edges.get().forEach(function(e){ if(!incoming[e.to])incoming[e.to]=[]; incoming[e.to].push(e.id); });

  var meta={};
  nodes.get().forEach(function(n){
    meta[n.id]={tipo:(n.tipo||"").toUpperCase(),estado:(n.estado||"").toUpperCase(),avance:isFinite(Number(n.avance))?Number(n.avance):0};
  });

  // ── Tooltip custom ────────────────────────────────
  function barColor(av){
    if(av>=80) return "#10B981";
    if(av>=40) return "#F59E0B";
    return "#EF4444";
  }

  function showTooltip(nodeId, mouseX, mouseY){
    var d=nodeData[nodeId]; if(!d) return;
    var av=Math.round(d.avance);
    var estadoDisp=(d.estado||"").replace("_"," ");
    // Capitalizar primera letra de cada palabra
    estadoDisp=estadoDisp.replace(/\w\S*/g,function(t){ return t.charAt(0).toUpperCase()+t.substr(1).toLowerCase(); });

    ttName.textContent = d.nombre;
    ttTags.innerHTML =
      '<span class="ui-tooltip-tag tipo">'+d.tipo+'</span>'+
      '<span class="ui-tooltip-tag estado">'+estadoDisp+'</span>';
    ttAvNum.textContent = av+"%";
    ttBar.style.width   = av+"%";
    ttBar.style.background = barColor(av);

    if(d.equipo && d.equipo.trim()){
      ttEquipoTag.textContent = d.equipo;
      ttEquipo.style.display = "block";
    } else {
      ttEquipo.style.display = "none";
    }
    if(d.comentario && d.comentario.trim()){
      ttCommentText.textContent = d.comentario;
      ttComment.style.display = "block";
    } else {
      ttComment.style.display = "none";
    }

    // El posicionamiento lo hace positionTooltip() separadamente
    tooltip.style.display = "block";
  }

  function hideTooltip(){
    tooltip.style.display="none";
  }

  // Rastrear posicion real del mouse en todo momento
  var lastMouseX = 0, lastMouseY = 0;
  document.addEventListener("mousemove", function(e){
    lastMouseX = e.clientX;
    lastMouseY = e.clientY;
    // Si el tooltip ya esta visible, lo mueve con el mouse
    if(tooltip.style.display === "block"){
      positionTooltip(e.clientX, e.clientY);
    }
  });

  function positionTooltip(mx, my){
    tooltip.style.display = "block";
    var tw = tooltip.offsetWidth  || 260;
    var th = tooltip.offsetHeight || 180;
    var vw = window.innerWidth, vh = window.innerHeight;
    var tx = mx + 20, ty = my - 10;
    if(tx + tw > vw - 12) tx = mx - tw - 12;
    if(ty + th > vh - 12) ty = vh - th - 12;
    if(ty < 12) ty = 12;
    tooltip.style.left = tx + "px";
    tooltip.style.top  = ty + "px";
  }

  // hoverNode: mostrar tooltip en la posicion actual del mouse (ya rastreada)
  var hoveredNode = null;
  network.on("hoverNode", function(params){
    if(tooltipTimer) clearTimeout(tooltipTimer);
    hoveredNode = params.node;
    // Pequeno delay para que el DOM del tooltip este listo antes de posicionar
    tooltipTimer = setTimeout(function(){
      showTooltip(hoveredNode, lastMouseX, lastMouseY);
      positionTooltip(lastMouseX, lastMouseY);
    }, 60);
  });
  network.on("blurNode", function(){
    if(tooltipTimer) clearTimeout(tooltipTimer);
    hoveredNode = null;
    hideTooltip();
  });

  // ── Búsqueda ──────────────────────────────────────
  function cleanLabel(s){ return (s||"").replace(/\n/g," ").trim(); }
  var items=nodes.get().map(function(n){
    return {id:n.id,name:cleanLabel(n.label||""),tipo:(meta[n.id]?meta[n.id].tipo:"")};
  }).sort(function(a,b){ return a.name.localeCompare(b.name); });

  function esc(s){
    return (s||"").replace(/[&<>"']/g,function(m){
      return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[m];
    });
  }
  function showDD(list){
    if(!list.length){dd.style.display="none";dd.innerHTML="";return;}
    dd.style.display="block";
    dd.innerHTML=list.map(function(x){
      return '<div class="ui-item" data-id="'+esc(x.id)+'">'+esc(x.name)+'<small>'+esc(x.tipo)+'</small></div>';
    }).join("");
  }
  function updateSugg(){
    var q=(input.value||"").toLowerCase().trim();
    if(!q){dd.style.display="none";dd.innerHTML="";return;}
    var f=[];
    for(var i=0;i<items.length;i++){
      if(items[i].name.toLowerCase().indexOf(q)!==-1){f.push(items[i]);if(f.length>=10)break;}
    }
    showDD(f);
  }

  // ── Toast ─────────────────────────────────────────
  function showToast(id){
    if(!id){toast.classList.remove("visible");return;}
    var m=meta[id]||{};
    var n=nodes.get(id);
    var name=n?cleanLabel(n.label||""):id;
    toast.innerHTML="<strong>"+esc(name)+"</strong>  ·  "+esc(m.tipo||"")+"  ·  "+esc((m.estado||"").replace("_"," "))+"  ·  "+Math.round(m.avance||0)+"%";
    toast.classList.add("visible");
    if(toastTimer)clearTimeout(toastTimer);
    toastTimer=setTimeout(function(){toast.classList.remove("visible");},5000);
  }

  // ── Filtros / dim ─────────────────────────────────
  var selectedId=null;

  function ancestors(startId){
    var an={},ae={};
    an[startId]=true;
    var stack=[startId],vis={};
    vis[startId]=true;
    while(stack.length){
      var cur=stack.pop();
      var inl=incoming[cur]||[];
      for(var i=0;i<inl.length;i++){
        var eid=inl[i];ae[eid]=true;
        var e=edges.get(eid);
        if(e&&!vis[e.from]){vis[e.from]=true;an[e.from]=true;stack.push(e.from);}
      }
    }
    return {an:an,ae:ae};
  }

  function matchFilters(id){
    var m=meta[id]||{avance:0,estado:"",tipo:""};
    if(m.avance<Number(range.value||0))return false;
    var fE=selEstado.value||"ALL",fT=selTipo.value||"ALL";
    if(fE!=="ALL"&&m.estado!==fE)return false;
    if(fT!=="ALL"&&m.tipo!==fT)return false;
    return true;
  }

  function applyView(){
    var keep={};
    for(var i=0;i<nodeIds.length;i++){ if(matchFilters(nodeIds[i]))keep[nodeIds[i]]=true; }
    var an=null,ae=null;
    if(selectedId){var r=ancestors(selectedId);an=r.an;ae=r.ae;}

    var eBase=edgeColor(), sb=selBorder();
    var nUp=[];
    for(var i=0;i<nodeIds.length;i++){
      var id=nodeIds[i],b=baseNode[id];
      var dim=!(keep[id]&&(selectedId?!!an[id]:true));
      var curBg=isDark?b.bg:b.bg_l;
      var curBo=isDark?b.border:b.border_l;
      // Texto siempre claro — los nodos tienen fondos saturados en ambos temas
      var dimTextAlpha = isDark ? 0.25 : 0.55;  // light: texto dimmeado mucho más visible
      var fc=b.customText?"rgba(0,0,0,0)":(dim?rgba(CUSTOM_TEXT_COLOR,dimTextAlpha):CUSTOM_TEXT_COLOR);
      nUp.push({id:id,
        color:dim?{background:rgba(curBg,dimNodeAlpha()),border:rgba(curBo,dimNodeAlpha())}:{background:curBg,border:curBo},
        borderWidth:dim?1:b.borderWidth,
        font:{color:fc}
      });
    }
    if(selectedId){
      var b2=baseNode[selectedId];
      var cb=isDark?b2.bg:b2.bg_l;
      nUp.push({id:selectedId,color:{background:cb,border:sb},borderWidth:SEL_BORDER_WIDTH,
        font:{color:b2.customText?"rgba(0,0,0,0)":CUSTOM_TEXT_COLOR}});
    }
    nodes.update(nUp);

    var eUp=[];
    for(var j=0;j<edgeIds.length;j++){
      var eid=edgeIds[j],e=edges.get(eid); if(!e)continue;
      var pass=(!!keep[e.from]&&!!keep[e.to]);
      var rel=selectedId?!!(ae&&ae[eid]):true;
      if(pass&&rel){
        eUp.push({id:eid,color:{color:eBase,opacity:edgeOpacity()},width:selectedId?EDGE_ANCESTOR_WIDTH:EDGE_BASE_WIDTH,dashes:false});
      } else {
        eUp.push({id:eid,color:{color:EDGE_DIM_COLOR,opacity:dimEdgeOpacity()},width:1.0,dashes:[8,6]});
      }
    }
    edges.update(eUp);
  }

  function focusNode(id){
    selectedId=id||null; applyView();
    if(!selectedId)return;
    showToast(selectedId);
    network.selectNodes([selectedId]);
    network.focus(selectedId,{scale:FOCUS_SCALE,animation:{duration:FOCUS_ANIM_MS,easingFunction:"easeInOutQuad"}});
  }

  function resetAll(){
    selectedId=null;
    input.value="";dd.style.display="none";dd.innerHTML="";
    range.value="0";pct.textContent="0%";
    selEstado.value="ALL";selTipo.value="ALL";
    toast.classList.remove("visible");
    hideTooltip();
    for(var id in initialPos){
      var p=initialPos[id];
      if(p&&typeof p.x==="number")network.moveNode(id,p.x,p.y);
    }
    network.unselectAll();applyView();
    network.fit({animation:{duration:350,easingFunction:"easeInOutQuad"}});
    setTimeout(syncSlider, 400);
  }

  // ── Theme ─────────────────────────────────────────
  function applyTheme(){
    if(isDark){
      document.body.classList.remove("light-theme");
      iconSun.style.display=""; iconMoon.style.display="none";
      container.style.background="radial-gradient(ellipse at 30% 20%, #0F1D3A 0%, #080D1C 60%, #020408 100%)";
    } else {
      document.body.classList.add("light-theme");
      iconSun.style.display="none"; iconMoon.style.display="";
      container.style.background="radial-gradient(ellipse at 30% 20%, #C7D7FF 0%, #E8EEFF 55%, #F5F7FF 100%)";
    }
    applyView();
  }
  btnTheme.addEventListener("click",function(){ isDark=!isDark; applyTheme(); });

  // ── Zoom slider — sincronizado en todas direcciones ─────────────────────────
  // El slider va de 10 a 300 (= 0.10x a 3.00x escala)
  // Fuentes de zoom: scroll/pinch en canvas, botones +/-, slider, fit, reset
  // Estrategia: un solo flag "sliderLock" evita loops de retroalimentacion.

  var sliderLock = false;

  // Actualiza el slider desde la escala actual del network (sin disparar moveTo)
  function syncSlider(){
    if(sliderLock) return;
    var s = network.getScale();
    var val = Math.min(250, Math.max(25, Math.round(s * 100)));
    zoomSlider.value = val;
  }

  var ZOOM_MIN = 0.25, ZOOM_MAX = 2.50;

  // Helper: hace zoom animado y sincroniza slider al terminar
  function zoomTo(scale, dur){
    dur = dur || 220;
    scale = Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, scale));
    network.moveTo({scale: scale, animation:{duration: dur, easingFunction:"easeInOutQuad"}});
    // Sync despues de que termina la animacion
    setTimeout(syncSlider, dur + 30);
  }

  // Slider → network
  zoomSlider.addEventListener("input", function(){
    sliderLock = true;
    var scale = Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, Number(zoomSlider.value) / 100));
    network.moveTo({scale: scale});   // sin animacion para que siga el arrastre del slider
    setTimeout(function(){ sliderLock = false; }, 80);
  });

  // Scroll/pinch en canvas → slider + clamp si excede limites
  network.on("zoom", function(){
    var s = network.getScale();
    if(s < ZOOM_MIN){ network.moveTo({scale: ZOOM_MIN}); }
    else if(s > ZOOM_MAX){ network.moveTo({scale: ZOOM_MAX}); }
    syncSlider();
  });

  // Botones +/-
  btnZoomIn.addEventListener("click", function(){
    zoomTo(network.getScale() * 1.25);
  });
  btnZoomOut.addEventListener("click", function(){
    zoomTo(network.getScale() * 0.80);
  });
  btnFit.addEventListener("click", function(){
    network.fit({animation:{duration:350, easingFunction:"easeInOutQuad"}});
    setTimeout(syncSlider, 400);
  });
  btnReset.addEventListener("click",resetAll);

  // ── Eventos UI ────────────────────────────────────
  input.addEventListener("input",updateSugg);
  input.addEventListener("keydown",function(e){
    if(e.key==="Enter"){
      var q=(input.value||"").toLowerCase().trim();
      for(var i=0;i<items.length;i++){
        if(items[i].name.toLowerCase().indexOf(q)!==-1){
          focusNode(items[i].id);dd.style.display="none";return;
        }
      }
    }
    if(e.key==="Escape")dd.style.display="none";
  });
  dd.addEventListener("click",function(e){
    var el=e.target.closest(".ui-item");if(!el)return;
    focusNode(el.getAttribute("data-id"));dd.style.display="none";input.value="";
  });
  document.addEventListener("click",function(e){
    if(!dd.contains(e.target)&&e.target!==input)dd.style.display="none";
  });
  range.addEventListener("input",function(){ pct.textContent=Number(range.value||0)+"%"; applyView(); });
  selEstado.addEventListener("change",applyView);
  selTipo.addEventListener("change",applyView);

  network.on("dragStart",function(){ container.classList.add("grabbing"); hideTooltip(); });
  network.on("dragEnd",  function(){ container.classList.remove("grabbing"); });
  network.on("click",function(p){
    hideTooltip();
    if(p.nodes&&p.nodes.length){ focusNode(p.nodes[0]); }
    else { selectedId=null;network.unselectAll();applyView();toast.classList.remove("visible"); }
  });

  // ── afterDrawing: texto en círculo y triángulo ────
  //
  // TRIÁNGULO: vértice arriba, base abajo.
  // nodeObj.y = centro del bounding box.
  // centroide geométrico ≈ nodeObj.y + size * 0.289
  // Usamos yOffset = size * 0.26 para posicionar el bloque de texto
  // en la parte ancha inferior del triángulo, visualmente centrado.
  //
  // CÍRCULO: centrado en (nodeObj.x, nodeObj.y) exacto.

  var customIds=nodes.get().filter(function(n){ return !!n.customText; }).map(function(n){ return n.id; });

  network.on("afterDrawing",function(ctx){
    ctx.save();
    ctx.textAlign="center";
    ctx.textBaseline="middle";

    for(var i=0;i<customIds.length;i++){
      var id=customIds[i];
      var nodeObj=network.body.nodes[id]; if(!nodeObj)continue;
      var nd=nodes.get(id); if(!nd)continue;
      var b=baseNode[id];
      var raw=String(nd.label||"").trim(); if(!raw)continue;
      var lines=raw.split("\n").slice(0,3);

      var curBg=(nd.color&&nd.color.background)?nd.color.background:b.bg;
      var alpha=alphaFromRgba(curBg);
      var textAlpha=alpha<0.4?Math.max(0,alpha*2.8):1.0;

      var cx=nodeObj.x, cy=nodeObj.y;
      var shape=(b.shape||"circle");
      var nodeSize=nodeObj.options?(nodeObj.options.size||90):90;

      var yOffset=0;
      if(shape==="triangle"){
        yOffset = nodeSize * 0.26;
      }

      var fontSize=Number(b.customFontSize||10);
      ctx.font="600 "+fontSize+"px 'DM Sans','Segoe UI',Arial,sans-serif";

      // En light theme usamos texto oscuro dentro de los nodos custom (mejor legibilidad)
      // afterDrawing: texto siempre claro en ambos temas (fondos saturados)
      var drawColor = CUSTOM_TEXT_COLOR;
      var rgb=hexToRgb(drawColor);
      if(rgb){
        ctx.fillStyle="rgba("+rgb.r+","+rgb.g+","+rgb.b+","+textAlpha+")";
      } else {
        ctx.fillStyle=drawColor;
      }

      var lh=Math.round(fontSize*1.22);
      var totalH=lh*lines.length;
      var y=(cy+yOffset)-totalH/2+lh/2;

      for(var j=0;j<lines.length;j++){
        ctx.fillText(lines[j],cx,y);
        y+=lh;
      }
    }
    ctx.restore();
  });

  // ── Panel toggle ──────────────────────────────────
  var uiPanel      = document.getElementById("uiPanel");
  var btnCollapse  = document.getElementById("btnCollapsePanel");
  var btnShow      = document.getElementById("btnShowPanel");

  function collapsePanel(){
    uiPanel.classList.add("collapsed");
    btnShow.style.display = "flex";
  }
  function expandPanel(){
    uiPanel.classList.remove("collapsed");
    btnShow.style.display = "none";
  }
  btnCollapse.addEventListener("click", collapsePanel);
  btnShow.addEventListener("click",    expandPanel);

  // ── Init ──────────────────────────────────────────
  setTimeout(function(){
    applyTheme();
    network.fit({animation:{duration:400,easingFunction:"easeInOutQuad"}});
    setTimeout(syncSlider, 450);
  },250);

})();
</script>
"""


FAVICON_SVG = (
    '<link rel="icon" type="image/svg+xml" href="data:image/svg+xml,'
    '%3Csvg xmlns=\'http://www.w3.org/2000/svg\' viewBox=\'0 0 32 32\'%3E'
    '%3Crect width=\'32\' height=\'32\' rx=\'8\' fill=\'%23080D1C\'/%3E'
    '%3Ccircle cx=\'6\' cy=\'16\' r=\'4\' fill=\'%23475569\'/%3E'
    '%3Ccircle cx=\'16\' cy=\'7\' r=\'4\' fill=\'%23F59E0B\'/%3E'
    '%3Ccircle cx=\'16\' cy=\'25\' r=\'4\' fill=\'%23475569\'/%3E'
    '%3Ccircle cx=\'27\' cy=\'16\' r=\'4\' fill=\'%2310B981\'/%3E'
    '%3Cline x1=\'10\' y1=\'14\' x2=\'12.5\' y2=\'9\' stroke=\'%237DD3FC\' stroke-width=\'1.5\'/%3E'
    '%3Cline x1=\'10\' y1=\'18\' x2=\'12.5\' y2=\'23\' stroke=\'%237DD3FC\' stroke-width=\'1.5\'/%3E'
    '%3Cline x1=\'20\' y1=\'9\' x2=\'23.5\' y2=\'14\' stroke=\'%237DD3FC\' stroke-width=\'1.5\'/%3E'
    '%3Cline x1=\'20\' y1=\'23\' x2=\'23.5\' y2=\'18\' stroke=\'%237DD3FC\' stroke-width=\'1.5\'/%3E'
    '%3C/svg%3E"/>\
<title>Mapeo Dependencias</title>\
'
)

def inject_ui(html_path: Path):
    html = html_path.read_text(encoding="utf-8")
    inject = UI_INJECT
    replace_map = {
        "__FOCUS_SCALE__":            str(FOCUS_SCALE),
        "__FOCUS_ANIM_MS__":          str(FOCUS_ANIM_MS),
        "__DIM_NODE_ALPHA_DARK__":    str(DIM_NODE_ALPHA_DARK),
        "__DIM_NODE_ALPHA_LIGHT__":   str(DIM_NODE_ALPHA_LIGHT),
        "__DIM_EDGE_OPACITY_DARK__":  str(DIM_EDGE_OPACITY_DARK),
        "__DIM_EDGE_OPACITY_LIGHT__": str(DIM_EDGE_OPACITY_LIGHT),
        "__EDGE_DARK_COLOR__":        EDGE_DARK_COLOR,
        "__EDGE_LIGHT_COLOR__":       EDGE_LIGHT_COLOR,
        "__EDGE_BASE_OPACITY_DARK__":  str(EDGE_BASE_OPACITY_DARK),
        "__EDGE_BASE_OPACITY_LIGHT__": str(EDGE_BASE_OPACITY_LIGHT),
        "__EDGE_BASE_WIDTH__":        str(EDGE_BASE_WIDTH),
        "__EDGE_DIM_COLOR__":         EDGE_DIM_COLOR,
        "__EDGE_ANCESTOR_WIDTH__":    str(EDGE_ANCESTOR_WIDTH),
        "__SELECT_BORDER_COLOR_DARK__":  SELECT_BORDER_COLOR_DARK,
        "__SELECT_BORDER_COLOR_LIGHT__": SELECT_BORDER_COLOR_LIGHT,
        "__SELECT_BORDER_WIDTH__":    str(SELECT_BORDER_WIDTH),
        "__CUSTOM_TEXT_COLOR__":      CUSTOM_TEXT_COLOR,
    }
    for k, v in replace_map.items():
        inject = inject.replace(k, v)
    html = html.replace("</head>", FAVICON_SVG + "\n</head>", 1)
    html = html.replace("</body>", inject + "\n</body>")
    html_path.write_text(html, encoding="utf-8")


# =========================
# Render
# =========================
def render(excel_path: str, out_html: str):
    nodos_df, deps_df, cols = read_excel(excel_path)
    G     = build_dag(nodos_df, deps_df, cols)
    level = topological_levels(G)
    pos   = assign_positions(G, level)

    # IMPORTANTE: deshabilitar tooltip nativo de vis pasando title vacío
    net = Network(height="100vh", width="100%", directed=True, bgcolor="#080D1C")
    net.set_options(json.dumps({
        "interaction": {
            "hover": True,
            "dragNodes": True, "dragView": True,
            "zoomView": True, "navigationButtons": False,
            "keyboard": True,
            "tooltipDelay": 99999   # delay enorme → nuestro tooltip JS aparece antes
        },
        "physics": {"enabled": False},
        "edges": {
            "chosen": False,
            "arrows": {"to": {"enabled": True, "scaleFactor": 1.1}},
            "smooth": False,
            "color": {"color": EDGE_DARK_COLOR, "opacity": EDGE_BASE_OPACITY_DARK},
            "width": EDGE_BASE_WIDTH
        },
        "nodes": {
            "chosen": {"node": False, "label": False},
            "shadow": {"enabled": False},
            "borderWidth": 2,
            "font": {"face": "DM Sans,Segoe UI,Arial,sans-serif"}
        }
    }))

    for node_id, d in G.nodes(data=True):
        estado     = (d.get("estado") or "PENDIENTE").upper()
        tipo       = (d.get("tipo")   or "PROCESO").upper()
        avance     = float(d.get("avance") or 0.0)
        comentario = d.get("comentario", "") or ""
        equipo     = d.get("equipo", "")     or ""
        nombre     = d.get("label", node_id)

        st_d  = STATE_COLOR.get(estado, STATE_COLOR["PENDIENTE"])
        st_l  = STATE_COLOR_LIGHT.get(estado, STATE_COLOR_LIGHT["PENDIENTE"])
        shape = TIPO_SHAPE.get(tipo, "box")

        label_show = "{} ({}%)".format(nombre, int(round(avance)))
        x, y  = pos[node_id]

        # title = "" → evita que vis muestre tooltip HTML crudo
        # Los datos para nuestro tooltip JS van en atributos del nodo
        title_str = ""   # sin tooltip nativo

        if shape == "circle":
            mc = 13
            wl = wrap_label_lines(label_show, max_chars=mc, max_lines=3)
            wrapped = "\n".join(wl)
            # vis.js shape="circle" ignora el param size (lo calcula desde el label).
            # shape="dot" SI respeta size y dibuja un circulo de radio fijo.
            # Usamos dot + label invisible + texto pintado via afterDrawing.
            max_line_len = max(len(l) for l in wl)
            n_lines = len(wl)
            # size = radio del dot. El texto debe caber dentro de un circulo de ese radio.
            # Para que el texto quepa: radio >= sqrt((w/2)^2 + (h/2)^2)
            # Aproximacion simple: radio >= max(w, h) / 1.8
            char_w = CIRCLE_FONT_SIZE * 0.62   # ancho aprox por caracter
            line_h = CIRCLE_FONT_SIZE * 1.3     # alto por linea
            text_w = max_line_len * char_w
            text_h = n_lines * line_h
            # radio minimo para contener el texto con padding
            size_needed = int(max(text_w, text_h) / 1.55) + 14
            size = max(CIRCLE_SIZE, size_needed)
            net.add_node(
                node_id, label=wrapped, title=title_str,
                shape="dot",
                color={"background": st_d["bg"], "border": st_d["border"]},
                font={"color":"rgba(0,0,0,0)","size":1,"face":"DM Sans"},
                x=x, y=y, size=size,
                tipo=tipo, estado=estado, avance=avance,
                comentario=comentario, equipo=equipo, nombre=nombre,
                customText=True, realFontColor=CUSTOM_TEXT_COLOR,
                customFontSize=CIRCLE_FONT_SIZE, borderWidth=2,
                bg_light=st_l["bg"], border_light=st_l["border"]
            )
        elif shape == "triangle":
            mc = 12
            wl = wrap_label_lines(label_show, max_chars=mc, max_lines=3)
            wrapped = "\n".join(wl)
            size = max(TRIANGLE_SIZE, int(max(len(l) for l in wl) * 7.5))
            net.add_node(
                node_id, label=wrapped, title=title_str,
                shape="triangle",
                color={"background": st_d["bg"], "border": st_d["border"]},
                font={"color":"rgba(0,0,0,0)","size":1,"face":"DM Sans"},
                x=x, y=y, size=size,
                tipo=tipo, estado=estado, avance=avance,
                comentario=comentario, equipo=equipo, nombre=nombre,
                customText=True, realFontColor=CUSTOM_TEXT_COLOR,
                customFontSize=TRIANGLE_FONT_SIZE, borderWidth=2,
                bg_light=st_l["bg"], border_light=st_l["border"]
            )
        elif shape == "square":  # Broad — cuadrado
            wrapped = wrap_label(label_show, width=14, max_lines=3)
            net.add_node(
                node_id, label=wrapped, title=title_str,
                shape="box",
                color={"background": st_d["bg"], "border": st_d["border"]},
                font={"color": CUSTOM_TEXT_COLOR, "size":13, "face":"DM Sans"},
                x=x, y=y,
                margin=18,
                widthConstraint={"minimum": 110, "maximum": 110},
                tipo=tipo, estado=estado, avance=avance,
                comentario=comentario, equipo=equipo, nombre=nombre,
                borderWidth=2,
                bg_light=st_l["bg"], border_light=st_l["border"]
            )
        else:  # Proceso — rectángulo
            wrapped = wrap_label(label_show, width=22, max_lines=3)
            net.add_node(
                node_id, label=wrapped, title=title_str,
                shape="box",
                color={"background": st_d["bg"], "border": st_d["border"]},
                font={"color": CUSTOM_TEXT_COLOR, "size":13, "face":"DM Sans"},
                x=x, y=y,
                margin=18,
                widthConstraint={"minimum": BOX_MIN_W, "maximum": BOX_MAX_W},
                tipo=tipo, estado=estado, avance=avance,
                comentario=comentario, equipo=equipo, nombre=nombre,
                borderWidth=2,
                bg_light=st_l["bg"], border_light=st_l["border"]
            )

    for i, (u, v) in enumerate(G.edges()):
        net.add_edge(u, v, id="e{}".format(i))

    net.write_html(out_html)
    inject_ui(Path(out_html))
    print("✅ HTML generado: {}".format(out_html))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--excel", default="datos.xlsx")
    ap.add_argument("--out",   default="lineage.html")
    args = ap.parse_args()
    render(args.excel, args.out)
