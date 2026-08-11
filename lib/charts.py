"""Constructores de gráficos Plotly con la paleta/tema del tablero."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from lib import constants as C

FONT_FAMILY = "system-ui, -apple-system, 'Segoe UI', sans-serif"


def _base_layout(fig: go.Figure, height: int = 320, show_legend: bool = True) -> go.Figure:
    fig.update_layout(
        height=height,
        margin=dict(l=8, r=8, t=8, b=8),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=FONT_FAMILY, color=C.INK_SECONDARY, size=12),
        showlegend=show_legend,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0,
                    font=dict(color=C.INK_SECONDARY, size=11)),
        hoverlabel=dict(bgcolor=C.SURFACE, bordercolor=C.AXIS, font=dict(color=C.INK_PRIMARY)),
    )
    fig.update_xaxes(gridcolor=C.GRIDLINE, zerolinecolor=C.AXIS, linecolor=C.AXIS,
                      tickfont=dict(color=C.INK_MUTED, size=11))
    fig.update_yaxes(gridcolor=C.GRIDLINE, zerolinecolor=C.AXIS, linecolor=C.AXIS,
                      tickfont=dict(color=C.INK_MUTED, size=11))
    return fig


def empty_state(message: str = "Sin datos para los filtros seleccionados") -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(text=message, showarrow=False, font=dict(color=C.INK_MUTED, size=13))
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return _base_layout(fig, height=220, show_legend=False)


def created_vs_closed(trend_df: pd.DataFrame) -> go.Figure:
    """Barras agrupadas de creados/cerrados por mes + línea de backlog (cola
    de tickets abiertos al cierre de cada mes), si viene esa columna."""
    if trend_df.empty:
        return empty_state()
    fig = go.Figure()
    fig.add_bar(x=trend_df["label"], y=trend_df["creados"], name="Creados",
                marker_color=C.CATEGORICAL[0], marker_line_width=0)
    fig.add_bar(x=trend_df["label"], y=trend_df["cerrados"], name="Cerrados",
                marker_color=C.STATUS["good"], marker_line_width=0)
    if "backlog" in trend_df.columns:
        fig.add_scatter(x=trend_df["label"], y=trend_df["backlog"], name="Backlog (cola)",
                         mode="lines+markers", line=dict(color=C.STATUS["critical"], width=2, dash="dot"),
                         marker=dict(size=6, color=C.STATUS["critical"]),
                         hovertemplate="%{x}<br>Backlog: %{y}<extra></extra>")
    fig.update_layout(barmode="group", bargap=0.25, bargroupgap=0.08)
    return _base_layout(fig, height=300)


def donut_by_category(df: pd.DataFrame, label_col: str, value_col: str,
                       color_map: dict[str, str] | None = None) -> go.Figure:
    if df.empty or value_col not in df.columns or label_col not in df.columns:
        return empty_state()
    df = df[df[value_col] > 0]
    if df.empty:
        return empty_state()
    colors = [color_map.get(v, C.INK_MUTED) for v in df[label_col]] if color_map else C.CATEGORICAL[: len(df)]
    fig = go.Figure(go.Pie(
        labels=df[label_col], values=df[value_col], hole=0.58,
        marker=dict(colors=colors, line=dict(color=C.SURFACE, width=2)),
        textinfo="value", textfont=dict(color=C.INK_PRIMARY, size=12),
        hovertemplate="%{label}: %{value} (%{percent})<extra></extra>",
    ))
    return _base_layout(fig, height=300)


def line_series(df: pd.DataFrame, x_col: str, y_col: str, name: str,
                 color: str = C.CATEGORICAL[6], y_suffix: str = "", y_range: tuple | None = None) -> go.Figure:
    if df.empty:
        return empty_state()
    fig = go.Figure()
    fig.add_scatter(x=df[x_col], y=df[y_col], mode="lines+markers", name=name,
                     line=dict(color=color, width=2), marker=dict(size=6, color=color),
                     fill="tozeroy", fillcolor=color.replace(")", ",0.12)").replace("rgb", "rgba") if color.startswith("rgb") else _hex_to_rgba(color, 0.12),
                     hovertemplate=f"%{{x}}<br>{name}: %{{y:.1f}}{y_suffix}<extra></extra>")
    if y_range:
        fig.update_yaxes(range=list(y_range))
    return _base_layout(fig, height=280, show_legend=False)


def _hex_to_rgba(hex_color: str, alpha: float) -> str:
    hex_color = hex_color.lstrip("#")
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{alpha})"


def horizontal_bar(df: pd.DataFrame, label_col: str, value_col: str, color: str = C.CATEGORICAL[0],
                    top_n: int | None = None, value_suffix: str = "") -> go.Figure:
    if df.empty:
        return empty_state()
    d = df.sort_values(value_col, ascending=True)
    if top_n:
        d = d.tail(top_n)
    fig = go.Figure(go.Bar(
        x=d[value_col], y=d[label_col], orientation="h",
        marker_color=color, marker_line_width=0,
        text=[f"{v:,.1f}{value_suffix}" if isinstance(v, float) else f"{v}{value_suffix}" for v in d[value_col]],
        textposition="outside", textfont=dict(color=C.INK_SECONDARY, size=11),
        hovertemplate="%{y}: %{x}" + value_suffix + "<extra></extra>",
    ))
    height = max(220, 34 * len(d) + 40)
    return _base_layout(fig, height=height, show_legend=False)


def vertical_bar(df: pd.DataFrame, label_col: str, value_col: str, color: str = C.CATEGORICAL[0],
                  color_by: dict[str, str] | None = None) -> go.Figure:
    if df.empty:
        return empty_state()
    colors = [color_by.get(v, color) for v in df[label_col]] if color_by else color
    fig = go.Figure(go.Bar(
        x=df[label_col], y=df[value_col], marker_color=colors, marker_line_width=0,
        hovertemplate="%{x}: %{y}<extra></extra>",
    ))
    return _base_layout(fig, height=300, show_legend=False)


def heatmap(pivot: pd.DataFrame) -> go.Figure:
    """pivot: index=cliente, columnas=mes. Escala clara→oscura (claro = pocos,
    oscuro = muchos) y el número de tickets visible en cada celda."""
    if pivot.empty or pivot.shape[1] == 0:
        return empty_state()
    fig = go.Figure(go.Heatmap(
        z=pivot.values, x=list(pivot.columns), y=list(pivot.index),
        colorscale=[[i / (len(C.SEQUENTIAL_BLUE) - 1), c] for i, c in enumerate(C.SEQUENTIAL_BLUE)],
        showscale=True, xgap=3, ygap=3,
        text=pivot.values, texttemplate="%{text}", textfont=dict(size=10, color=C.INK_PRIMARY),
        colorbar=dict(tickfont=dict(color=C.INK_MUTED, size=10), outlinewidth=0),
        hovertemplate="%{y} · %{x}: %{z}<extra></extra>",
    ))
    height = max(280, 28 * len(pivot.index) + 60)
    fig.update_yaxes(autorange="reversed")
    return _base_layout(fig, height=height, show_legend=False)


def stacked_bar_by_month_group(pivot: pd.DataFrame, colors: dict[str, str] | None = None,
                                value_labels: bool = True) -> go.Figure:
    """pivot: index=mes (label), columnas=grupo (prioridad, técnico...).

    `colors`: {nombre_columna: color}. Si no se da, cicla la paleta categórica
    (para grupos sin un color fijo con significado, ej. técnicos).
    """
    if pivot.empty:
        return empty_state()
    fig = go.Figure()
    for i, col in enumerate(pivot.columns):
        color = colors.get(str(col), C.CATEGORICAL[i % len(C.CATEGORICAL)]) if colors else C.CATEGORICAL[i % len(C.CATEGORICAL)]
        values = pivot[col]
        fig.add_bar(
            x=pivot.index, y=values, name=str(col), marker_color=color, marker_line_width=0,
            text=[f"{v:,.0f}" if v else "" for v in values] if value_labels else None,
            textposition="inside", textfont=dict(size=10, color="#ffffff"),
        )
    fig.update_layout(barmode="stack", bargap=0.25)
    return _base_layout(fig, height=340)


def multi_line_by_group(pivot: pd.DataFrame, colors: dict[str, str] | None = None,
                         value_suffix: str = "", point_labels: bool = True,
                         y_range: tuple | None = None) -> go.Figure:
    """pivot: index=mes (label), columnas=grupo (prioridad...). Una línea por
    columna, con el valor marcado en cada punto para no dejarlo "a ojo"."""
    if pivot.empty:
        return empty_state()
    fig = go.Figure()
    for i, col in enumerate(pivot.columns):
        color = colors.get(str(col), C.CATEGORICAL[i % len(C.CATEGORICAL)]) if colors else C.CATEGORICAL[i % len(C.CATEGORICAL)]
        values = pivot[col]
        fig.add_scatter(
            x=pivot.index, y=values, name=str(col), mode="lines+markers+text" if point_labels else "lines+markers",
            line=dict(color=color, width=2), marker=dict(size=6, color=color),
            text=[f"{v:,.0f}{value_suffix}" if pd.notna(v) else "" for v in values] if point_labels else None,
            textposition="top center", textfont=dict(size=10, color=color),
            hovertemplate=f"%{{x}}<br>{col}: %{{y:.1f}}{value_suffix}<extra></extra>",
        )
    if y_range:
        fig.update_yaxes(range=list(y_range))
    return _base_layout(fig, height=340)
