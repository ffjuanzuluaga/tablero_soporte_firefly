"""Tablero ejecutivo de soporte — Odoo `helpdesk.ticket` (+ registro de horas).

Se conecta en vivo a una instancia de Odoo 19 vía XML-RPC. Todo se analiza
por criticidad (prioridad) y con comparativo histórico mensual (6 meses por
defecto), siguiendo los lineamientos gerenciales del tablero.
"""

from __future__ import annotations

import datetime as dt
import re

import pandas as pd
import streamlit as st

from lib import charts, constants as C, metrics, ui
from lib.demo_data import build_demo_dataframe
from lib.odoo_client import (
    OdooClient,
    OdooConnectionError,
    OdooCredentials,
    fetch_active_support_contracts,
    fetch_ticket_sample_raw,
    fetch_tickets,
)

st.set_page_config(page_title="Tablero de Soporte — Firefly", page_icon="🎫", layout="wide")
ui.inject_css()


# ---------------------------------------------------------------------------
# Conexión a Odoo — credenciales SIEMPRE desde st.secrets["odoo"] (nunca en
# disco propio, nunca pedidas por formulario): configúralas en
# .streamlit/secrets.toml para desarrollo local, o en Streamlit Cloud →
# Manage app → Settings → Secrets para producción.
# ---------------------------------------------------------------------------

st.sidebar.markdown("## ⚡ Firefly Support")
st.sidebar.caption("Tablero ejecutivo de soporte")


@st.cache_resource(show_spinner="Conectando con Odoo…")
def get_odoo_client() -> OdooClient:
    try:
        s = st.secrets["odoo"]
        creds = OdooCredentials(url=s["url"], db=s["db"], username=s["username"], api_key=s["api_key"])
    except Exception as exc:  # noqa: BLE001
        raise OdooConnectionError(
            "Faltan credenciales de Odoo. Configura la tabla [odoo] (url, db, username, api_key) "
            "en .streamlit/secrets.toml (local) o en Manage app → Settings → Secrets (Streamlit Cloud)."
        ) from exc
    client = OdooClient(creds)
    client.authenticate()
    return client


@st.cache_data(ttl=600, show_spinner="Consultando tickets en Odoo…")
def load_tickets_cached(_client: OdooClient, date_from: str, date_to: str) -> pd.DataFrame:
    return fetch_tickets(_client, date_from=date_from, date_to=date_to)


@st.cache_data(ttl=600, show_spinner="Consultando contratos de soporte activos…")
def load_active_contracts_cached(_client: OdooClient) -> int | None:
    return fetch_active_support_contracts(_client)


try:
    odoo_client = get_odoo_client()
    connection_error = None
except OdooConnectionError as exc:
    odoo_client = None
    connection_error = str(exc)

using_demo = True
df_all = None
active_contracts = None

if connection_error:
    st.sidebar.error(connection_error)
else:
    st.sidebar.success(f"Conectado: {odoo_client.creds.username}\n\n{odoo_client.creds.url}")
    st.sidebar.markdown("##### Rango a consultar en Odoo")
    today = dt.date.today()
    # Por defecto, últimos 6 meses (lineamiento del tablero gerencial).
    fetch_from = st.sidebar.date_input("Desde", value=today - dt.timedelta(days=182))
    fetch_to = st.sidebar.date_input("Hasta", value=today)
    if st.sidebar.button("🔄 Refrescar datos", type="primary"):
        st.cache_data.clear()
        st.rerun()

    try:
        df_all = load_tickets_cached(odoo_client, fetch_from.isoformat(), fetch_to.isoformat())
        active_contracts = load_active_contracts_cached(odoo_client)
        using_demo = False
    except OdooConnectionError as exc:
        st.sidebar.error(str(exc))

    with st.sidebar.expander("🔍 Diagnóstico de conexión"):
        st.caption("Ticket(s) tal cual los devuelve Odoo, sin transformar — útil para depurar "
                   "campos que se ven mal (técnico, cliente, fechas...).")
        if st.button("Consultar muestra cruda"):
            try:
                st.json(fetch_ticket_sample_raw(odoo_client, limit=2))
            except OdooConnectionError as exc:
                st.error(str(exc))

if using_demo:
    if df_all is None:
        df_all = build_demo_dataframe()
    if active_contracts is None:
        # Sin conexión real no hay forma de consultar suscripciones: se
        # aproxima con una fracción de los clientes de ejemplo, marcado
        # explícitamente como dato de ejemplo más abajo.
        active_contracts = max(1, df_all["partner"].nunique() // 3)
elif df_all.empty:
    st.warning("La consulta a Odoo no devolvió tickets para ese rango de fechas.")
    st.stop()


# ---------------------------------------------------------------------------
# Filtros
# ---------------------------------------------------------------------------

st.sidebar.markdown("---")
st.sidebar.markdown("### Filtros")

# El rango de fechas ya se define una sola vez arriba ("Rango a consultar en
# Odoo"): los datos cargados YA vienen acotados a ese período, así que no
# hace falta un segundo selector de fechas aquí para filtrarlos de nuevo.
valid_dates = df_all["create_date"].dropna()
min_d = valid_dates.min().date() if len(valid_dates) else None
max_d = valid_dates.max().date() if len(valid_dates) else None


def _options(col: str, exclude: str | None = None) -> list[str]:
    vals = sorted(v for v in df_all[col].dropna().unique() if v != exclude)
    return vals

f_team = st.sidebar.multiselect("Equipo", _options("team"))
f_client = st.sidebar.multiselect("Cliente", _options("partner"))
f_user = st.sidebar.multiselect("Técnico", _options("user"))
f_priority = st.sidebar.multiselect("Prioridad", metrics.priority_order(df_all))
f_stage = st.sidebar.multiselect("Etapa", _options("stage"))

sla_policy_options = sorted({p.strip() for s in df_all["sla_ids"] for p in str(s).split(",") if p.strip()})
f_sla = st.sidebar.multiselect("Política de SLA", sla_policy_options)


def apply_filters(df: pd.DataFrame) -> pd.DataFrame:
    mask = pd.Series(True, index=df.index)
    if f_team:
        mask &= df["team"].isin(f_team)
    if f_client:
        mask &= df["partner"].isin(f_client)
    if f_user:
        mask &= df["user"].isin(f_user)
    if f_priority:
        mask &= df["priority"].isin(f_priority)
    if f_stage:
        mask &= df["stage"].isin(f_stage)
    if f_sla:
        pattern = "|".join(re.escape(p) for p in f_sla)
        mask &= df["sla_ids"].str.contains(pattern, regex=True, na=False)
    return df[mask]


df = apply_filters(df_all)

if using_demo:
    st.info(
        "📊 Mostrando **datos de ejemplo sintéticos** (no son datos reales de ningún cliente). "
        "Revisa las credenciales de Odoo en `st.secrets` (ver el mensaje en la barra lateral) "
        "para ver tu operación real.",
        icon="ℹ️",
    )

st.title("Tablero de Soporte")
period_txt = f" · {min_d.strftime('%d/%m/%Y')} — {max_d.strftime('%d/%m/%Y')}" if min_d else ""
st.caption(f"{len(df)} tickets en el filtro actual (de {len(df_all)} totales){period_txt}")

order = metrics.priority_order(df)
prio_colors = metrics.priority_color_map(order)


# ---------------------------------------------------------------------------
# Pestañas
# ---------------------------------------------------------------------------

tab_overview, tab_sla, tab_tech, tab_clients, tab_heatmap = st.tabs(
    ["📊 Resumen", "🎯 SLA", "👥 Técnicos", "🏢 Clientes", "🗓️ Heatmap"]
)

# --- Resumen ---------------------------------------------------------------
with tab_overview:
    k = metrics.kpis(df)
    ui.kpi_row([
        {"label": "Tickets abiertos actualmente", "value": k["open"], "sub": f"de {k['total']} creados en el periodo", "color": C.STATUS["warning"]},
        {"label": "Cerrados / mes (prom.)", "value": f"{k['closed_avg_per_month']:.1f}", "sub": f"sobre {k['months_in_range']} meses", "color": C.STATUS["good"]},
        {"label": "Horas equipo / mes (prom.)", "value": ui.fmt_hours(k["hours_avg_per_month"]), "sub": "suma de todo el equipo", "color": C.CATEGORICAL[6]},
        {"label": "Horas equipo — mes actual", "value": ui.fmt_hours(k["hours_current_month"]), "sub": f"{C.MESES_ES[dt.date.today().month]} {dt.date.today().year}", "color": C.CATEGORICAL[0]},
        {"label": "Clientes con contrato activo", "value": active_contracts if active_contracts is not None else "N/D", "sub": "suscripción de soporte en curso", "color": C.CATEGORICAL[1]},
    ])

    st.write("")
    ui.chart_header("Tickets creados vs. cerrados vs. pendientes", "Cola/backlog = tickets abiertos al cierre de cada mes (independiente de cuándo se crearon)")
    trend_df = metrics.monthly_trend(df)
    st.plotly_chart(charts.created_vs_closed(trend_df), width='stretch', config={"displayModeBar": False}, key="ov_monthly")

    c1, c2 = st.columns([1, 2])
    with c1:
        ui.chart_header("Etapa de los tickets abiertos", "Solo tickets actualmente sin cerrar")
        stage_df = metrics.by_stage(df, only_open=True)
        stage_colors = {s: C.CATEGORICAL[i % len(C.CATEGORICAL)] for i, s in enumerate(stage_df["stage"])}
        st.plotly_chart(charts.donut_by_category(stage_df, "stage", "count", stage_colors), width='stretch', config={"displayModeBar": False}, key="ov_stage")
    with c2:
        ui.chart_header("Prioridad de tickets creados, por mes", "Cuántos de cada criticidad entraron cada mes")
        st.plotly_chart(charts.stacked_bar_by_month_group(metrics.monthly_priority_stack(df), prio_colors), width='stretch', config={"displayModeBar": False}, key="ov_priority_monthly")

    c3, c4 = st.columns(2)
    with c3:
        ui.chart_header("Tasa de efectividad de cierre", "% de tickets creados en el mes que YA está cerrado (a hoy)")
        rate_df = metrics.monthly_close_rate(df)
        st.plotly_chart(charts.line_series(rate_df, "label", "tasa_pct", "Tasa", color=C.CATEGORICAL[6], y_suffix="%", y_range=(0, 100)), width='stretch', config={"displayModeBar": False}, key="ov_close_rate")
        st.caption("Los meses más recientes salen más bajos porque todavía no ha pasado tiempo suficiente para resolver "
                   "todo lo que entró — no es una caída real del desempeño, es el efecto normal de mirar meses en curso.")
    with c4:
        ui.chart_header("Top clientes por volumen de tickets", "Promedio mensual — no acumulado, para no penalizar a clientes con menos tiempo en soporte")
        st.plotly_chart(charts.horizontal_bar(metrics.top_clients_chart_data(df, 8), "partner", "tickets_prom_mes", color=C.CATEGORICAL[0]), width='stretch', config={"displayModeBar": False}, key="ov_top_clients")

    ui.chart_header("Top 3 clientes con más tickets abiertos", "Al corte del filtro actual")
    top3 = metrics.top3_clients_open(df)
    if top3.empty:
        st.caption("No hay tickets abiertos en el filtro actual.")
    else:
        cols = st.columns(len(top3))
        for col, (_, row) in zip(cols, top3.iterrows()):
            with col:
                st.metric(row["partner"], int(row["abiertos"]))


# --- SLA ---------------------------------------------------------------
with tab_sla:
    ui.section_title("Cumplimiento y tiempos por criticidad")
    compliance = metrics.sla_compliance_by_priority(df)
    ui.kpi_row([
        {"label": f"Cumplimiento SLA — {p}", "value": ui.fmt_pct(compliance.get(p)), "sub": "sobre tickets con SLA resuelto", "color": prio_colors.get(p, C.CATEGORICAL[0])}
        for p in order
    ])
    resolution_kpi = metrics.resolution_avg_by_priority(df)
    ui.kpi_row([
        {"label": f"Resolución promedio — {p}", "value": ui.fmt_hours(resolution_kpi.get(p)), "sub": "horas por ticket cerrado", "color": prio_colors.get(p, C.CATEGORICAL[0])}
        for p in order
    ])

    st.write("")
    ui.chart_header("Incumplimiento de SLA por criticidad, por mes", "Cuántos tickets incumplieron su SLA cada mes, por nivel de urgencia")
    st.plotly_chart(charts.stacked_bar_by_month_group(metrics.monthly_incompliance_by_priority(df), prio_colors), width='stretch', config={"displayModeBar": False}, key="sla_incompliance_monthly")

    ui.chart_header("Cumplimiento de SLA por mes", "% cumplido por criticidad — el punto marca el porcentaje exacto")
    st.plotly_chart(charts.multi_line_by_group(metrics.monthly_compliance_by_priority(df), prio_colors, value_suffix="%", y_range=(0, 100)), width='stretch', config={"displayModeBar": False}, key="sla_compliance_monthly")

    ui.chart_header("Detalle histórico de cumplimiento", "% de cumplimiento por mes y prioridad")
    detail = metrics.monthly_compliance_by_priority(df)
    st.dataframe(detail.map(ui.fmt_pct), width='stretch')

    ui.section_title("Horas y tiempos de respuesta por criticidad")
    c1, c2 = st.columns(2)
    with c1:
        ui.chart_header("Promedio de horas por mes", "Horas por ticket con horas registradas, por criticidad")
        st.plotly_chart(charts.multi_line_by_group(metrics.monthly_hours_by_priority(df), prio_colors, value_suffix="h"), width='stretch', config={"displayModeBar": False}, key="sla_hours_monthly")
    with c2:
        ui.chart_header("Primera respuesta promedio", "Horas hasta la primera respuesta, por criticidad")
        st.plotly_chart(charts.multi_line_by_group(metrics.monthly_first_response_by_priority(df), prio_colors, value_suffix="h"), width='stretch', config={"displayModeBar": False}, key="sla_first_response_monthly")

    ui.chart_header("Resolución promedio por prioridad", "Horas promedio hasta el cierre, histórico mensual por criticidad")
    st.plotly_chart(charts.multi_line_by_group(metrics.monthly_resolution_by_priority(df), prio_colors, value_suffix="h"), width='stretch', config={"displayModeBar": False}, key="sla_resolution_monthly")


# --- Técnicos ---------------------------------------------------------------
with tab_tech:
    tech_df = metrics.by_technician(df)
    ui.section_title("Desempeño del equipo técnico — comparativo mensual")
    ui.kpi_row([
        {"label": "Técnicos activos", "value": metrics.kpis(df)["techs_active"], "sub": "con al menos 1 ticket", "color": C.CATEGORICAL[0]},
        {"label": "Tickets / técnico / mes (prom.)", "value": f"{tech_df['tickets_prom_mes'].mean():.1f}" if len(tech_df) else "—", "sub": "promedio de carga", "color": C.CATEGORICAL[2]},
        {"label": "Horas / técnico / mes (prom.)", "value": ui.fmt_hours(tech_df["horas_prom_mes"].mean()) if len(tech_df) else "—", "sub": "tiempo registrado", "color": C.CATEGORICAL[6]},
    ])

    ui.chart_header("Tickets por técnico, por mes", "Quién resolvió cuántos tickets cada mes")
    st.plotly_chart(charts.multi_line_by_group(metrics.technician_monthly(df)), width='stretch', config={"displayModeBar": False}, key="tech_tickets_monthly")

    ui.chart_header("Horas por técnico, por mes", "Cuántas horas trabajó cada técnico en soporte, por mes")
    st.plotly_chart(charts.multi_line_by_group(metrics.technician_hours_monthly(df), value_suffix="h"), width='stretch', config={"displayModeBar": False}, key="tech_hours_monthly")

    ui.chart_header("Ranking de técnicos", "Promedios mensuales — no acumulado")
    show = tech_df.copy()
    show["resolucion_prom_horas"] = show["resolucion_prom_horas"].map(ui.fmt_hours)
    show["cumplimiento_sla_pct"] = show["cumplimiento_sla_pct"].map(ui.fmt_pct)
    show["tickets_prom_mes"] = show["tickets_prom_mes"].round(1)
    show["horas_prom_mes"] = show["horas_prom_mes"].round(1)
    show.columns = ["Técnico", "Meses activos", "Tickets/mes", "Horas/mes", "Cerrados", "Resolución prom.", "Cumplimiento SLA"]
    st.dataframe(show, width='stretch', hide_index=True)


# --- Clientes ---------------------------------------------------------------
with tab_clients:
    client_df = metrics.by_client(df)
    ui.section_title("Análisis de clientes — promedio mensual")
    ui.kpi_row([
        {"label": "Clientes activos", "value": metrics.kpis(df)["clients_active"], "sub": "con al menos 1 ticket", "color": C.CATEGORICAL[0]},
        {"label": "Tickets / cliente / mes (prom.)", "value": f"{client_df['tickets_prom_mes'].mean():.1f}" if len(client_df) else "—", "sub": "promedio de volumen", "color": C.CATEGORICAL[2]},
        {"label": "Horas / cliente / mes (prom.)", "value": ui.fmt_hours(client_df["horas_prom_mes"].mean()) if len(client_df) else "—", "sub": "tiempo invertido", "color": C.CATEGORICAL[6]},
    ])

    c1, c2 = st.columns(2)
    with c1:
        ui.chart_header("Top clientes por tickets", "Promedio mensual")
        st.plotly_chart(charts.horizontal_bar(client_df, "partner", "tickets_prom_mes", color=C.CATEGORICAL[0], top_n=12), width='stretch', config={"displayModeBar": False}, key="client_top_tickets")
    with c2:
        ui.chart_header("Top clientes por horas invertidas", "Promedio mensual")
        st.plotly_chart(charts.horizontal_bar(client_df, "partner", "horas_prom_mes", color=C.CATEGORICAL[6], top_n=12, value_suffix="h"), width='stretch', config={"displayModeBar": False}, key="client_top_hours")

    ui.chart_header("Detalle por cliente", "Promedios mensuales — no acumulado")
    show = client_df.copy()
    show["resolucion_prom_horas"] = show["resolucion_prom_horas"].map(ui.fmt_hours)
    show["cumplimiento_sla_pct"] = show["cumplimiento_sla_pct"].map(ui.fmt_pct)
    show["tickets_prom_mes"] = show["tickets_prom_mes"].round(1)
    show["horas_prom_mes"] = show["horas_prom_mes"].round(1)
    show.columns = ["Cliente", "Meses activo", "Tickets/mes", "Horas/mes", "Cerrados", "Resolución prom.", "Cumplimiento SLA"]
    st.dataframe(show, width='stretch', hide_index=True)


# --- Heatmap ---------------------------------------------------------------
with tab_heatmap:
    ui.chart_header("Mapa de calor — tickets por cliente y mes", "Top 15 clientes por volumen · claro = pocos, oscuro = muchos")
    pivot = metrics.heatmap_client_month(df, top_n=15)
    st.plotly_chart(charts.heatmap(pivot), width='stretch', config={"displayModeBar": False}, key="heatmap_client_month")

    ui.chart_header("Tabla pivote — clientes × meses", "Con totales por mes en la última fila")
    pivot_with_total = pivot.copy()
    pivot_with_total.loc["Total"] = pivot_with_total.sum(numeric_only=True)
    st.dataframe(pivot_with_total, width='stretch')
