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
from lib.odoo_client import OdooConnectionError, OdooCredentials, load_from_odoo

st.set_page_config(page_title="Tablero de Soporte — Firefly", page_icon="🎫", layout="wide")
ui.inject_css()


# ---------------------------------------------------------------------------
# Conexión a Odoo
# ---------------------------------------------------------------------------

st.sidebar.markdown("## ⚡ Firefly Support")
st.sidebar.caption("Tablero ejecutivo de soporte")
st.sidebar.markdown("### Conexión a Odoo")


def _secret_defaults() -> dict[str, str]:
    """Valores presentes (y no vacíos) en st.secrets['odoo'], si existe."""
    try:
        s = st.secrets["odoo"]
    except Exception:  # noqa: BLE001 - no hay secrets.toml configurado, es opcional
        return {}
    return {k: str(s[k]).strip() for k in ("url", "db", "username", "api_key") if s.get(k)}


if "odoo_creds" not in st.session_state:
    defaults = _secret_defaults()
    if {"url", "db", "username", "api_key"} <= defaults.keys():
        # Los 4 campos vienen completos en secrets: se conecta directo, sin pedir login
        # (una sola identidad de Odoo compartida por todos los que abran el tablero).
        st.session_state.odoo_creds = OdooCredentials(**defaults)
    else:
        st.session_state.odoo_creds = None
    st.session_state.odoo_secret_defaults = defaults
if "odoo_tickets_df" not in st.session_state:
    st.session_state.odoo_tickets_df = None
    st.session_state.odoo_timesheets_df = None

if st.session_state.odoo_creds is None:
    defaults = st.session_state.get("odoo_secret_defaults", {})
    with st.sidebar.form("odoo_login"):
        st.caption("Credenciales de sesión: no se guardan en disco.")
        url_in = st.text_input("URL de Odoo", value=defaults.get("url", ""), placeholder="https://tuempresa.odoo.com")
        db_in = st.text_input("Base de datos", value=defaults.get("db", ""))
        user_in = st.text_input("Usuario (correo)", value=defaults.get("username", ""))
        key_in = st.text_input(
            "Contraseña o API key", type="password", value=defaults.get("api_key", ""),
            help="Recomendado: crea una API key en Odoo → tu usuario → Preferencias → "
                 "Seguridad de la cuenta → Nueva clave API, en vez de usar tu contraseña real.",
        )
        connect_clicked = st.form_submit_button("🔌 Conectar")
    if connect_clicked:
        if not (url_in and db_in and user_in and key_in):
            st.sidebar.error("Completa URL, base de datos, usuario y contraseña/API key.")
        else:
            st.session_state.odoo_creds = OdooCredentials(url=url_in, db=db_in, username=user_in, api_key=key_in)
            st.session_state.odoo_tickets_df = None
            st.rerun()
else:
    creds = st.session_state.odoo_creds
    st.sidebar.success(f"Conectado: {creds.username}\n\n{creds.url}")
    if st.sidebar.button("Cerrar sesión / cambiar instancia"):
        st.session_state.odoo_creds = None
        st.session_state.odoo_tickets_df = None
        st.session_state.odoo_timesheets_df = None
        st.rerun()

    st.sidebar.markdown("##### Rango a consultar en Odoo")
    today = dt.date.today()
    fetch_from = st.sidebar.date_input("Desde", value=today - dt.timedelta(days=365))
    fetch_to = st.sidebar.date_input("Hasta", value=today)
    if st.sidebar.button("🔄 Cargar / actualizar datos", type="primary"):
        with st.spinner("Consultando Odoo…"):
            try:
                tickets_df, timesheets_df = load_from_odoo(creds, date_from=fetch_from, date_to=fetch_to)
                st.session_state.odoo_tickets_df = tickets_df
                st.session_state.odoo_timesheets_df = timesheets_df
            except OdooConnectionError as exc:
                st.sidebar.error(str(exc))

using_demo = st.session_state.odoo_tickets_df is None
if using_demo:
    df_all = build_demo_dataframe()
    ts_df = None
else:
    df_all = st.session_state.odoo_tickets_df
    ts_df = st.session_state.odoo_timesheets_df
    if df_all.empty:
        st.warning("La consulta a Odoo no devolvió tickets para ese rango de fechas.")
        st.stop()


# ---------------------------------------------------------------------------
# Filtros
# ---------------------------------------------------------------------------

st.sidebar.markdown("---")
st.sidebar.markdown("### Filtros")

valid_dates = df_all["create_date"].dropna()
if len(valid_dates):
    min_d, max_d = valid_dates.min().date(), valid_dates.max().date()
    date_range = st.sidebar.date_input("Fecha de creación", value=(min_d, max_d), min_value=min_d, max_value=max_d)
else:
    date_range = None

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
    if date_range and isinstance(date_range, tuple) and len(date_range) == 2:
        start = pd.Timestamp(date_range[0])
        end = pd.Timestamp(date_range[1]) + pd.Timedelta(days=1)
        mask &= df["create_date"].between(start, end, inclusive="left")
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
        "Conéctate a tu instancia de Odoo en la barra lateral y presiona **Cargar / actualizar datos** "
        "para ver tu operación real.",
        icon="ℹ️",
    )

st.title("Tablero de Soporte")
period_txt = ""
if len(valid_dates):
    period_txt = f" · {date_range[0].strftime('%d/%m/%Y')} — {date_range[1].strftime('%d/%m/%Y')}" if date_range else ""
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
        rate_df = metrics.monthly_close_rate(metrics.monthly_trend(df))
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
