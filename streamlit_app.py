"""Tablero ejecutivo de soporte — Odoo `helpdesk.ticket` (+ registro de horas).

Se conecta en vivo a una instancia de Odoo 19 vía XML-RPC y muestra tickets
creados/cerrados, distribución por etapa y prioridad, cumplimiento de SLA
por nivel/política, tiempo invertido y desempeño por técnico/cliente.
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
    fetch_ticket_sample_raw,
    fetch_tickets,
    fetch_timesheets,
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


@st.cache_data(ttl=600, show_spinner="Consultando horas registradas…")
def load_timesheets_cached(_client: OdooClient, ticket_ids: tuple[int, ...]) -> pd.DataFrame:
    return fetch_timesheets(_client, list(ticket_ids))


try:
    odoo_client = get_odoo_client()
    connection_error = None
except OdooConnectionError as exc:
    odoo_client = None
    connection_error = str(exc)

using_demo = True
df_all = None
ts_df = None

if connection_error:
    st.sidebar.error(connection_error)
else:
    st.sidebar.success(f"Conectado: {odoo_client.creds.username}\n\n{odoo_client.creds.url}")
    st.sidebar.markdown("##### Rango a consultar en Odoo")
    today = dt.date.today()
    fetch_from = st.sidebar.date_input("Desde", value=today - dt.timedelta(days=365))
    fetch_to = st.sidebar.date_input("Hasta", value=today)
    if st.sidebar.button("🔄 Refrescar datos", type="primary"):
        st.cache_data.clear()
        st.rerun()

    try:
        df_all = load_tickets_cached(odoo_client, fetch_from.isoformat(), fetch_to.isoformat())
        ticket_ids = tuple(df_all["id"].dropna().astype(int).tolist()) if "id" in df_all.columns and len(df_all) else ()
        ts_df = load_timesheets_cached(odoo_client, ticket_ids)
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
    ts_df = None
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


def priority_color_map(order: list[str]) -> dict[str, str]:
    ramp = [C.STATUS["critical"], C.STATUS["serious"], C.STATUS["warning"], C.STATUS["good"]]
    return {label: ramp[i] if i < len(ramp) else C.CATEGORICAL[i % len(C.CATEGORICAL)] for i, label in enumerate(order)}


# ---------------------------------------------------------------------------
# Pestañas
# ---------------------------------------------------------------------------

tab_overview, tab_sla, tab_trends, tab_tech, tab_clients, tab_tickets, tab_heatmap = st.tabs(
    ["📊 Resumen", "🎯 SLA", "📈 Tendencias", "👥 Técnicos", "🏢 Clientes", "🎫 Tickets", "🗓️ Heatmap"]
)

# --- Resumen ---------------------------------------------------------------
with tab_overview:
    k = metrics.kpis(df)
    ui.kpi_row([
        {"label": "Tickets creados", "value": k["total"], "sub": "en el periodo filtrado", "color": C.CATEGORICAL[0]},
        {"label": "Tickets cerrados", "value": k["closed"], "sub": f"{k['open']} abiertos", "color": C.STATUS["good"]},
        {"label": "Tasa de cierre", "value": ui.fmt_pct(k["close_rate"]), "sub": "cerrados / creados", "color": C.CATEGORICAL[2]},
        {"label": "Horas invertidas", "value": ui.fmt_hours(k["hours_total"]), "sub": f"{ui.fmt_hours(k['hours_avg_per_ticket'])} prom./ticket", "color": C.CATEGORICAL[6]},
        {"label": "Resolución promedio", "value": ui.fmt_hours(k["resolution_avg_hours"]), "sub": "horas por ticket cerrado", "color": C.CATEGORICAL[4]},
        {"label": "Críticos/Urgentes", "value": k["critical_count"], "sub": f"{ui.fmt_pct(k['critical_pct'])} del total", "color": C.STATUS["critical"]},
        {"label": "Cumplimiento SLA", "value": ui.fmt_pct(k["sla_compliance_pct"]), "sub": f"sobre {k['sla_known_count']} con SLA resuelto", "color": C.STATUS["good"] if (k["sla_compliance_pct"] or 0) >= 85 else C.STATUS["warning"]},
        {"label": "Clientes activos", "value": k["clients_active"], "sub": f"{k['techs_active']} técnicos activos", "color": C.CATEGORICAL[1]},
    ])

    st.write("")
    c1, c2 = st.columns([2, 1])
    with c1:
        ui.chart_header("Tickets creados vs. cerrados por mes", "Creados por fecha de creación · cerrados por fecha de cierre")
        st.plotly_chart(charts.created_vs_closed(metrics.monthly_trend(df)), width='stretch', config={"displayModeBar": False}, key="ov_monthly")
    with c2:
        ui.chart_header("Distribución por etapa")
        stage_df = metrics.by_stage(df)
        stage_colors = {s: C.CATEGORICAL[i % len(C.CATEGORICAL)] for i, s in enumerate(stage_df["stage"])}
        st.plotly_chart(charts.donut_by_category(stage_df, "stage", "count", stage_colors), width='stretch', config={"displayModeBar": False}, key="ov_stage")

    c3, c4 = st.columns(2)
    with c3:
        ui.chart_header("Distribución por prioridad")
        prio_df = metrics.by_priority(df)
        order = metrics.priority_order(df)
        st.plotly_chart(charts.donut_by_category(prio_df, "priority", "count", priority_color_map(order)), width='stretch', config={"displayModeBar": False}, key="ov_priority")
    with c4:
        ui.chart_header("Tasa de efectividad de cierre", "% de tickets cerrados sobre los creados, por mes")
        rate_df = metrics.monthly_close_rate(df)
        st.plotly_chart(charts.line_series(rate_df, "label", "tasa_pct", "Tasa", color=C.CATEGORICAL[6], y_suffix="%", y_range=(0, 100)), width='stretch', config={"displayModeBar": False}, key="ov_close_rate")

    ui.chart_header("Top 8 clientes por volumen de tickets")
    st.plotly_chart(charts.horizontal_bar(metrics.top_clients_chart_data(df, 8), "partner", "tickets", color=C.CATEGORICAL[0]), width='stretch', config={"displayModeBar": False}, key="ov_top_clients")


# --- SLA ---------------------------------------------------------------
with tab_sla:
    k = metrics.kpis(df)
    ui.kpi_row([
        {"label": "Cumplimiento SLA", "value": ui.fmt_pct(k["sla_compliance_pct"]), "sub": "sobre tickets con SLA resuelto", "color": C.STATUS["good"]},
        {"label": "SLA cumplidas", "value": int((df["sla_status"] == "Cumplida").sum()), "sub": "tickets", "color": C.STATUS["good"]},
        {"label": "SLA incumplidas", "value": int((df["sla_status"] == "Incumplida").sum()), "sub": "tickets", "color": C.STATUS["critical"]},
        {"label": "Vencidos (abiertos)", "value": k["sla_overdue"], "sub": "pasaron la fecha límite y siguen abiertos", "color": C.STATUS["warning"]},
        {"label": "Sin política de SLA", "value": int((df["sla_status"] == "Sin SLA").sum()), "sub": "tickets sin SLA aplicada", "color": C.INK_MUTED},
    ])

    st.write("")
    c1, c2 = st.columns([1, 2])
    with c1:
        ui.chart_header("Estado de SLA")
        status_df = metrics.sla_status_summary(df)
        st.plotly_chart(charts.donut_by_category(status_df, "status", "count", C.SLA_STATUS_COLORS), width='stretch', config={"displayModeBar": False}, key="sla_status_donut")
    with c2:
        ui.chart_header("Cumplimiento por nivel/política de SLA", "Tickets con resultado conocido (cumplida/incumplida) por política aplicada")
        policy_df = metrics.by_sla_policy(df)
        st.plotly_chart(charts.stacked_sla_by_policy(policy_df), width='stretch', config={"displayModeBar": False}, key="sla_by_policy")

    ui.chart_header("Cumplimiento de SLA por mes", "% de tickets cumplidos sobre los resueltos con SLA conocido")
    st.plotly_chart(charts.line_series(metrics.monthly_sla_compliance(df), "label", "cumplimiento_pct", "Cumplimiento", color=C.STATUS["good"], y_suffix="%", y_range=(0, 100)), width='stretch', config={"displayModeBar": False}, key="sla_monthly")

    if not policy_df.empty:
        ui.chart_header("Detalle por política")
        show = policy_df.copy()
        show["cumplimiento_pct"] = show["cumplimiento_pct"].map(ui.fmt_pct)
        show.columns = ["Política de SLA", "Tickets", "Cumplidas", "Incumplidas", "% Cumplimiento"]
        st.dataframe(show, width='stretch', hide_index=True)


# --- Tendencias ---------------------------------------------------------------
with tab_trends:
    ui.section_title("Análisis de tendencias operativas")
    c1, c2 = st.columns(2)
    with c1:
        ui.chart_header("Promedio de horas por mes", "Horas utilizadas promedio por ticket con horas registradas")
        st.plotly_chart(charts.line_series(metrics.monthly_avg_hours(df), "label", "horas_prom", "Horas prom.", color=C.CATEGORICAL[6], y_suffix="h"), width='stretch', config={"displayModeBar": False}, key="trend_avg_hours")
    with c2:
        ui.chart_header("Primera respuesta promedio", "Horas promedio para la primera respuesta, por mes")
        st.plotly_chart(charts.line_series(metrics.monthly_first_response(df), "label", "resp_prom", "1ª respuesta", color=C.CATEGORICAL[0], y_suffix="h"), width='stretch', config={"displayModeBar": False}, key="trend_first_response")

    c3, c4 = st.columns(2)
    with c3:
        ui.chart_header("Tickets por día de la semana", "Distribución semanal de la carga entrante")
        st.plotly_chart(charts.vertical_bar(metrics.by_dow(df), "dow", "count", color=C.CATEGORICAL[2]), width='stretch', config={"displayModeBar": False}, key="trend_dow")
    with c4:
        ui.chart_header("Resolución promedio por prioridad", "Horas promedio hasta el cierre, según criticidad")
        order = metrics.priority_order(df)
        st.plotly_chart(charts.vertical_bar(metrics.resolution_by_priority(df), "priority", "horas_prom", color_by=priority_color_map(order)), width='stretch', config={"displayModeBar": False}, key="trend_resolution_priority")


# --- Técnicos ---------------------------------------------------------------
with tab_tech:
    tech_df = metrics.by_technician(df)
    ui.section_title("Desempeño del equipo técnico")
    ui.kpi_row([
        {"label": "Técnicos activos", "value": metrics.kpis(df)["techs_active"], "sub": "con al menos 1 ticket", "color": C.CATEGORICAL[0]},
        {"label": "Tickets / técnico (prom.)", "value": f"{tech_df['tickets'].mean():.1f}" if len(tech_df) else "—", "sub": "promedio de carga", "color": C.CATEGORICAL[2]},
        {"label": "Horas / técnico (prom.)", "value": ui.fmt_hours(tech_df["horas"].mean()) if len(tech_df) else "—", "sub": "tiempo registrado", "color": C.CATEGORICAL[6]},
    ])

    c1, c2 = st.columns(2)
    with c1:
        ui.chart_header("Tickets por técnico")
        st.plotly_chart(charts.horizontal_bar(tech_df, "user", "tickets", color=C.CATEGORICAL[0]), width='stretch', config={"displayModeBar": False}, key="tech_tickets")
    with c2:
        ui.chart_header("Horas trabajadas por técnico", "Según `Tiempo dedicado` de los tickets asignados")
        st.plotly_chart(charts.horizontal_bar(tech_df, "user", "horas", color=C.CATEGORICAL[6], value_suffix="h"), width='stretch', config={"displayModeBar": False}, key="tech_hours")

    if ts_df is not None and "employee" in ts_df.columns:
        ts_tech = metrics.technician_hours_from_timesheets(ts_df)
        if not ts_tech.empty:
            ui.chart_header("Horas por técnico — detalle de hojas de horas", "Del export de horas cargado (puede incluir horas de otros colaboradores en el ticket)")
            st.plotly_chart(charts.horizontal_bar(ts_tech, "user", "horas", color=C.CATEGORICAL[4], value_suffix="h"), width='stretch', config={"displayModeBar": False}, key="tech_hours_timesheet")

    ui.chart_header("Tickets por técnico y mes", "Evolución mensual de los técnicos con más volumen")
    st.plotly_chart(charts.stacked_area_or_bar_by_group(metrics.technician_monthly(df)), width='stretch', config={"displayModeBar": False}, key="tech_monthly")

    ui.chart_header("Ranking de técnicos")
    show = tech_df.copy()
    show["resolucion_prom_horas"] = show["resolucion_prom_horas"].map(ui.fmt_hours)
    show["cumplimiento_sla_pct"] = show["cumplimiento_sla_pct"].map(ui.fmt_pct)
    show["horas"] = show["horas"].round(1)
    show.columns = ["Técnico", "Tickets", "Cerrados", "Horas", "Resolución prom.", "Cumplimiento SLA"]
    st.dataframe(show, width='stretch', hide_index=True)


# --- Clientes ---------------------------------------------------------------
with tab_clients:
    client_df = metrics.by_client(df)
    ui.section_title("Análisis de clientes")
    ui.kpi_row([
        {"label": "Clientes activos", "value": metrics.kpis(df)["clients_active"], "sub": "con al menos 1 ticket", "color": C.CATEGORICAL[0]},
        {"label": "Tickets / cliente (prom.)", "value": f"{client_df['tickets'].mean():.1f}" if len(client_df) else "—", "sub": "promedio de volumen", "color": C.CATEGORICAL[2]},
        {"label": "Horas / cliente (prom.)", "value": ui.fmt_hours(client_df["horas"].mean()) if len(client_df) else "—", "sub": "tiempo invertido", "color": C.CATEGORICAL[6]},
    ])

    c1, c2 = st.columns(2)
    with c1:
        ui.chart_header("Top clientes por tickets")
        st.plotly_chart(charts.horizontal_bar(client_df, "partner", "tickets", color=C.CATEGORICAL[0], top_n=12), width='stretch', config={"displayModeBar": False}, key="client_top_tickets")
    with c2:
        ui.chart_header("Top clientes por horas invertidas")
        st.plotly_chart(charts.horizontal_bar(client_df, "partner", "horas", color=C.CATEGORICAL[6], top_n=12, value_suffix="h"), width='stretch', config={"displayModeBar": False}, key="client_top_hours")

    ui.chart_header("Detalle por cliente")
    show = client_df.copy()
    show["resolucion_prom_horas"] = show["resolucion_prom_horas"].map(ui.fmt_hours)
    show["cumplimiento_sla_pct"] = show["cumplimiento_sla_pct"].map(ui.fmt_pct)
    show["horas"] = show["horas"].round(1)
    show.columns = ["Cliente", "Tickets", "Cerrados", "Horas", "Resolución prom.", "Cumplimiento SLA"]
    st.dataframe(show, width='stretch', hide_index=True)


# --- Tickets ---------------------------------------------------------------
with tab_tickets:
    ui.chart_header(f"Listado completo de tickets ({len(df)})")
    search = st.text_input("Buscar por asunto, cliente o referencia", "")

    cols = ["ticket_label", "name", "partner", "team", "user", "stage", "priority",
            "create_date", "close_date", "resolution_hours", "total_hours_spent", "sla_status"]
    cols = [c for c in cols if c in df.columns]
    table = df[cols].copy()

    if search:
        needle = search.lower()
        table = table[table.apply(lambda r: needle in " ".join(str(v) for v in r.values).lower(), axis=1)]

    table = table.rename(columns={
        "ticket_label": "Ref.", "name": "Asunto", "partner": "Cliente", "team": "Equipo",
        "user": "Técnico", "stage": "Etapa", "priority": "Prioridad", "create_date": "Creado el",
        "close_date": "Cierre", "resolution_hours": "Horas resolución", "total_hours_spent": "Horas registradas",
        "sla_status": "SLA",
    })
    st.dataframe(table.sort_values("Creado el", ascending=False), width='stretch', hide_index=True, height=520)
    st.download_button("⬇ Descargar CSV filtrado", table.to_csv(index=False).encode("utf-8"), "tickets_filtrados.csv", "text/csv")


# --- Heatmap ---------------------------------------------------------------
with tab_heatmap:
    ui.chart_header("Mapa de calor — tickets por cliente y mes", "Top 15 clientes por volumen")
    pivot = metrics.heatmap_client_month(df, top_n=15)
    st.plotly_chart(charts.heatmap(pivot), width='stretch', config={"displayModeBar": False}, key="heatmap_client_month")

    ui.chart_header("Tabla pivote — clientes × meses")
    st.dataframe(pivot, width='stretch')
