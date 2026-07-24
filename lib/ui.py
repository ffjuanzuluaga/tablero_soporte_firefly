"""Componentes de interfaz: CSS del tablero y tarjetas KPI."""

from __future__ import annotations

import html

import streamlit as st

from lib import constants as C

CSS = f"""
<style>
.block-container {{ padding-top: 1.6rem; padding-bottom: 2rem; max-width: 1400px; }}

.kpi-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
  gap: 14px;
  margin-bottom: 6px;
}}
.kpi-card {{
  background: {C.SURFACE};
  border: 1px solid {C.AXIS};
  border-radius: 12px;
  padding: 16px 18px;
  position: relative;
  overflow: hidden;
}}
.kpi-card::before {{
  content: '';
  position: absolute; top: 0; left: 0; right: 0; height: 3px;
}}
.kpi-label {{
  font-size: 11px; font-weight: 600; color: {C.INK_MUTED};
  text-transform: uppercase; letter-spacing: .05em; margin-bottom: 6px;
}}
.kpi-value {{ font-size: 26px; font-weight: 700; color: {C.INK_PRIMARY}; line-height: 1.1; }}
.kpi-sub {{ font-size: 12px; color: {C.INK_MUTED}; margin-top: 5px; }}

.section-title {{
  font-size: 15px; font-weight: 700; color: {C.INK_PRIMARY};
  display: flex; align-items: center; gap: 8px; margin: 4px 0 10px 0;
}}
.section-title::before {{
  content: ''; width: 3px; height: 15px; background: {C.CATEGORICAL[0]}; border-radius: 2px;
}}
.chart-title {{ font-size: 13px; font-weight: 600; color: {C.INK_PRIMARY}; margin-bottom: 2px; }}
.chart-sub {{ font-size: 11px; color: {C.INK_MUTED}; margin-bottom: 6px; }}

.badge {{
  display: inline-block; padding: 3px 10px; border-radius: 20px;
  font-size: 11px; font-weight: 600; margin-right: 6px;
}}
</style>
"""


def inject_css() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def kpi_row(items: list[dict]) -> None:
    """items: [{label, value, sub, color}]

    Cada tarjeta se arma en una sola línea, sin indentación ni saltos de
    línea internos: st.markdown pasa el contenido por un parser de Markdown
    antes de permitir el HTML crudo, y una línea en blanco seguida de texto
    indentado 4+ espacios se interpreta como un bloque de código literal en
    vez de HTML — cortando el render a partir de la segunda tarjeta.
    """
    cards = []
    for it in items:
        color = it.get("color", C.CATEGORICAL[0])
        label = html.escape(str(it["label"]))
        value = html.escape(str(it["value"]))
        sub = html.escape(str(it.get("sub", "")))
        cards.append(
            f'<div class="kpi-card" style="--accent:{color}">'
            f'<div style="position:absolute;top:0;left:0;right:0;height:3px;background:{color}"></div>'
            f'<div class="kpi-label">{label}</div>'
            f'<div class="kpi-value">{value}</div>'
            f'<div class="kpi-sub">{sub}</div>'
            f'</div>'
        )
    st.markdown(f'<div class="kpi-grid">{"".join(cards)}</div>', unsafe_allow_html=True)


def section_title(text: str) -> None:
    st.markdown(f'<div class="section-title">{html.escape(text)}</div>', unsafe_allow_html=True)


def chart_header(title: str, subtitle: str = "") -> None:
    st.markdown(f'<div class="chart-title">{html.escape(title)}</div>', unsafe_allow_html=True)
    if subtitle:
        st.markdown(f'<div class="chart-sub">{html.escape(subtitle)}</div>', unsafe_allow_html=True)


def fmt_hours(value) -> str:
    if value is None:
        return "—"
    try:
        if value != value:  # NaN
            return "—"
    except TypeError:
        return "—"
    return f"{value:,.1f} h"


def fmt_pct(value) -> str:
    if value is None:
        return "—"
    try:
        if value != value:
            return "—"
    except TypeError:
        return "—"
    return f"{value:,.1f}%"
