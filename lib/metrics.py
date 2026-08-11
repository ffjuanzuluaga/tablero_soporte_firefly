"""Agregaciones (KPIs, series de tiempo, rankings) sobre el DataFrame de tickets.

Todas las funciones reciben el DataFrame ya normalizado/derivado por
`data_loader.derive_ticket_fields` y devuelven estructuras livianas
(dict / DataFrame) listas para graficar en `charts.py`.

Todo lo que compara clientes/técnicos usa promedio MENSUAL sobre sus propios
meses activos (no el total acumulado del período), para no penalizar a quien
lleva menos tiempo en soporte. Todo lo relacionado con SLA/resolución/horas
se puede desglosar por prioridad (criticidad) en vez de una sola cifra
global, porque los 4 niveles de urgencia no se deben mezclar en una bolsa.
"""

from __future__ import annotations

import pandas as pd

from lib import constants as C

SLA_KNOWN_OUTCOME = ("Cumplida", "Incumplida")


def _safe_mean(series: pd.Series) -> float | None:
    s = series.dropna()
    return float(s.mean()) if len(s) else None


def priority_order(df: pd.DataFrame) -> list[str]:
    """Ordena las etiquetas de prioridad de más crítica a menos, por heurística de texto."""
    labels = [p for p in df["priority"].dropna().unique().tolist()]

    def severity(label: str) -> int:
        norm = label.lower()
        for rank, hint in enumerate(C.PRIORITY_ORDER_HINTS):
            if hint in norm:
                # los hints ya están ordenados de más a menos crítico
                return rank
        return len(C.PRIORITY_ORDER_HINTS)

    return sorted(labels, key=severity)


def priority_color_map(order: list[str]) -> dict[str, str]:
    ramp = C.PRIORITY_SEVERITY_RAMP
    return {label: ramp[i] if i < len(ramp) else C.CATEGORICAL[i % len(C.CATEGORICAL)] for i, label in enumerate(order)}


def _month_axis(df: pd.DataFrame) -> list[pd.Period]:
    return sorted(df["create_month"].dropna().unique().tolist())


def _month_label(m: pd.Period) -> str:
    return f"{C.MESES_ES.get(m.month, m.month)} {m.year}"


def _pivot_by_month_and_priority(df: pd.DataFrame, values: str, aggfunc, months: list[pd.Period],
                                  order: list[str]) -> pd.DataFrame:
    pivot = df.pivot_table(index="create_month", columns="priority", values=values, aggfunc=aggfunc)
    pivot = pivot.reindex(months)
    pivot = pivot.reindex(columns=order)
    pivot.index = [_month_label(m) for m in pivot.index]
    return pivot


# ---------------------------------------------------------------------------
# KPIs
# ---------------------------------------------------------------------------

def kpis(df: pd.DataFrame) -> dict:
    total = len(df)
    closed = int(df["is_closed"].sum())
    open_now = total - closed
    close_rate = (closed / total * 100) if total else 0.0

    hours_series = df["total_hours_spent"].dropna()
    hours_total = float(hours_series.sum()) if len(hours_series) else 0.0
    hours_avg_per_ticket = _safe_mean(df.loc[df["total_hours_spent"] > 0, "total_hours_spent"]) if total else None
    resolution_avg = _safe_mean(df.loc[df["is_closed"], "resolution_hours"])

    clients_active = int(df.loc[df["partner"] != "Sin cliente", "partner"].nunique())
    techs_active = int(df.loc[df["user"] != "Sin asignar", "user"].nunique())

    months_in_range = len(_month_axis(df)) or 1
    current_month = pd.Timestamp.now().to_period("M")
    hours_current_month = float(df.loc[df["create_month"] == current_month, "total_hours_spent"].dropna().sum())

    return {
        "total": total,
        "closed": closed,
        "open": open_now,
        "close_rate": close_rate,
        "hours_total": hours_total,
        "hours_avg_per_ticket": hours_avg_per_ticket,
        "resolution_avg_hours": resolution_avg,
        "clients_active": clients_active,
        "techs_active": techs_active,
        "months_in_range": months_in_range,
        "created_avg_per_month": total / months_in_range,
        "closed_avg_per_month": closed / months_in_range,
        "hours_avg_per_month": hours_total / months_in_range,
        "hours_current_month": hours_current_month,
    }


def open_tickets_by_priority(df: pd.DataFrame) -> pd.DataFrame:
    order = priority_order(df)
    open_df = df[~df["is_closed"]]
    counts = open_df["priority"].value_counts()
    rows = [{"priority": p, "count": int(counts.get(p, 0))} for p in order]
    return pd.DataFrame(rows, columns=["priority", "count"])


def sla_compliance_by_priority(df: pd.DataFrame) -> dict[str, float | None]:
    """% de cumplimiento por criticidad, sobre tickets con resultado de SLA conocido."""
    order = priority_order(df)
    known = df[df["sla_status"].isin(SLA_KNOWN_OUTCOME)]
    result = {}
    for p in order:
        part = known[known["priority"] == p]
        result[p] = (part["sla_status"].eq("Cumplida").mean() * 100) if len(part) else None
    return result


def resolution_avg_by_priority(df: pd.DataFrame) -> dict[str, float | None]:
    order = priority_order(df)
    closed = df[df["is_closed"]]
    return {p: _safe_mean(closed.loc[closed["priority"] == p, "resolution_hours"]) for p in order}


def top3_clients_open(df: pd.DataFrame) -> pd.DataFrame:
    open_df = df[(~df["is_closed"]) & (df["partner"] != "Sin cliente")]
    counts = open_df["partner"].value_counts().head(3)
    return pd.DataFrame({"partner": counts.index, "abiertos": counts.values})


def oldest_open_ticket(df: pd.DataFrame) -> dict | None:
    open_df = df[~df["is_closed"]]
    if open_df.empty:
        return None
    row = open_df.loc[open_df["create_date"].idxmin()]
    return {
        "ticket_label": row["ticket_label"],
        "name": row["name"],
        "partner": row["partner"],
        "create_date": row["create_date"],
        "days_open": int((pd.Timestamp.now() - row["create_date"]).days),
    }


# ---------------------------------------------------------------------------
# Series mensuales (Resumen)
# ---------------------------------------------------------------------------

def monthly_trend(df: pd.DataFrame) -> pd.DataFrame:
    """Creados (por fecha de creación) vs. cerrados (por fecha de cierre) vs.
    backlog: tickets abiertos "en la foto" al cierre de cada mes (creados hasta
    esa fecha y todavía sin cerrar en ese momento), para ver la cola acumulada."""
    close_month = df.loc[df["is_closed"], "close_date"].dt.to_period("M")
    months = sorted(set(_month_axis(df)) | set(close_month.dropna().tolist()))
    if not months:
        return pd.DataFrame(columns=["month", "label", "creados", "cerrados", "backlog"])

    created = df.groupby("create_month").size()
    closed = close_month.value_counts()

    rows = []
    for m in months:
        month_end = m.to_timestamp(how="end")
        created_by_then = df["create_date"] <= month_end
        still_open_then = df["close_date"].isna() | (df["close_date"] > month_end)
        rows.append({
            "month": m,
            "label": _month_label(m),
            "creados": int(created.get(m, 0)),
            "cerrados": int(closed.get(m, 0)),
            "backlog": int((created_by_then & still_open_then).sum()),
        })
    return pd.DataFrame(rows)


def monthly_close_rate(df: pd.DataFrame) -> pd.DataFrame:
    """Tasa de cierre por cohorte de creación: de los tickets CREADOS en cada
    mes, qué % ya está cerrado a la fecha de la consulta.

    Nota: a propósito NO se calcula como (cerrados-en-el-mes / creados-en-el-mes)
    con "cerrados" por fecha de cierre — esas son poblaciones distintas de
    tickets y la división puede superar 100% (p.ej. un mes donde se destraba
    backlog viejo), lo que se ve como un gráfico recortado/raro contra un eje
    0-100%. Aquí "cerrados" siempre es un subconjunto de "creados" del mismo
    mes, así que la tasa queda garantizada entre 0 y 100% — y por eso los
    meses más recientes salen más bajos: todavía no ha pasado tiempo suficiente
    para resolverlos, no es un error de cálculo.
    """
    months = _month_axis(df)
    rows = []
    for m in months:
        part = df[df["create_month"] == m]
        creados = len(part)
        cerrados = int(part["is_closed"].sum())
        rows.append({
            "month": m,
            "label": _month_label(m),
            "creados": creados,
            "cerrados": cerrados,
            "tasa_pct": (cerrados / creados * 100) if creados else 0.0,
        })
    return pd.DataFrame(rows, columns=["month", "label", "creados", "cerrados", "tasa_pct"])


def monthly_priority_stack(df: pd.DataFrame) -> pd.DataFrame:
    """Tickets creados por mes × prioridad (para la barra apilada de distribución)."""
    months = _month_axis(df)
    order = priority_order(df)
    return _pivot_by_month_and_priority(df, "name", "count", months, order).fillna(0).astype(int)


def by_stage(df: pd.DataFrame, only_open: bool = False) -> pd.DataFrame:
    sub = df[~df["is_closed"]] if only_open else df
    counts = sub["stage"].value_counts()
    return pd.DataFrame({"stage": counts.index, "count": counts.values})


# ---------------------------------------------------------------------------
# SLA / horas / resolución — histórico mensual por prioridad
# ---------------------------------------------------------------------------

def monthly_compliance_by_priority(df: pd.DataFrame) -> pd.DataFrame:
    """% de cumplimiento de SLA por mes × prioridad (4 líneas)."""
    months = _month_axis(df)
    order = priority_order(df)
    known = df[df["sla_status"].isin(SLA_KNOWN_OUTCOME)].copy()
    if known.empty:
        return pd.DataFrame(index=[_month_label(m) for m in months], columns=order, dtype=float)
    known["cumplida"] = known["sla_status"].eq("Cumplida") * 100
    return _pivot_by_month_and_priority(known, "cumplida", "mean", months, order)


def monthly_incompliance_by_priority(df: pd.DataFrame) -> pd.DataFrame:
    """Conteo de tickets INCUMPLIDOS por mes × prioridad (para la apilada)."""
    months = _month_axis(df)
    order = priority_order(df)
    incump = df[df["sla_status"] == "Incumplida"]
    return _pivot_by_month_and_priority(incump, "name", "count", months, order).fillna(0).astype(int)


def monthly_hours_by_priority(df: pd.DataFrame) -> pd.DataFrame:
    months = _month_axis(df)
    order = priority_order(df)
    sub = df[df["total_hours_spent"] > 0]
    return _pivot_by_month_and_priority(sub, "total_hours_spent", "mean", months, order)


def monthly_first_response_by_priority(df: pd.DataFrame) -> pd.DataFrame:
    months = _month_axis(df)
    order = priority_order(df)
    sub = df[df["first_response_hours"] > 0]
    return _pivot_by_month_and_priority(sub, "first_response_hours", "mean", months, order)


def monthly_resolution_by_priority(df: pd.DataFrame) -> pd.DataFrame:
    months = _month_axis(df)
    order = priority_order(df)
    sub = df[df["is_closed"]]
    return _pivot_by_month_and_priority(sub, "resolution_hours", "mean", months, order)


def monthly_total_hours(df: pd.DataFrame) -> pd.DataFrame:
    """Suma de horas de TODO el equipo, por mes (no por técnico ni prioridad)."""
    months = _month_axis(df)
    sums = df.groupby("create_month")["total_hours_spent"].sum()
    rows = [{"month": m, "label": _month_label(m), "horas": float(sums.get(m, 0.0) or 0.0)} for m in months]
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Técnicos / clientes — promedio mensual (÷ meses activos propios)
# ---------------------------------------------------------------------------

def _agent_rollup(df: pd.DataFrame, dimension: str, exclude_default: str, top_n: int | None = None) -> pd.DataFrame:
    """Promedios MENSUALES por técnico/cliente, divididos por los meses en que
    esa entidad tuvo actividad propia (no por los meses del rango global), para
    no poner en desventaja a quien lleva menos tiempo en soporte."""
    sub = df[df[dimension] != exclude_default]
    cols = [dimension, "meses_activos", "tickets_prom_mes", "horas_prom_mes",
            "abiertos", "cerrados", "incumplidas", "resolucion_prom_horas", "cumplimiento_sla_pct"]
    if sub.empty:
        return pd.DataFrame(columns=cols)

    rows = []
    for key, part in sub.groupby(dimension):
        meses_activos = part["create_month"].nunique() or 1
        known = part[part["sla_status"].isin(SLA_KNOWN_OUTCOME)]
        pct = (known["sla_status"].eq("Cumplida").mean() * 100) if len(known) else None
        rows.append({
            dimension: key,
            "meses_activos": meses_activos,
            "tickets_prom_mes": len(part) / meses_activos,
            "horas_prom_mes": float(part["total_hours_spent"].dropna().sum()) / meses_activos,
            "abiertos": int((~part["is_closed"]).sum()),
            "cerrados": int(part["is_closed"].sum()),
            "incumplidas": int((part["sla_status"] == "Incumplida").sum()),
            "resolucion_prom_horas": _safe_mean(part.loc[part["is_closed"], "resolution_hours"]),
            "cumplimiento_sla_pct": pct,
        })
    out = pd.DataFrame(rows, columns=cols).sort_values("tickets_prom_mes", ascending=False).reset_index(drop=True)
    if top_n:
        out = out.head(top_n)
    return out


def by_technician(df: pd.DataFrame, top_n: int | None = None) -> pd.DataFrame:
    return _agent_rollup(df, "user", "Sin asignar", top_n)


def by_client(df: pd.DataFrame, top_n: int | None = None) -> pd.DataFrame:
    return _agent_rollup(df, "partner", "Sin cliente", top_n)


def top_clients_chart_data(df: pd.DataFrame, top_n: int = 8) -> pd.DataFrame:
    return by_client(df, top_n=top_n)[["partner", "tickets_prom_mes"]]


def technician_monthly(df: pd.DataFrame, top_n: int = 6) -> pd.DataFrame:
    """Tickets por técnico y mes (top N técnicos por volumen prom./mes)."""
    top_techs = by_technician(df, top_n=top_n)["user"].tolist()
    sub = df[df["user"].isin(top_techs)]
    months = _month_axis(df)
    pivot = sub.pivot_table(index="create_month", columns="user", values="name", aggfunc="count", fill_value=0)
    pivot = pivot.reindex(months, fill_value=0)
    pivot.index = [_month_label(m) for m in pivot.index]
    return pivot[top_techs] if top_techs else pivot


def technician_hours_monthly(df: pd.DataFrame, top_n: int = 6) -> pd.DataFrame:
    """Horas por técnico y mes (top N técnicos por volumen prom./mes)."""
    top_techs = by_technician(df, top_n=top_n)["user"].tolist()
    sub = df[df["user"].isin(top_techs)]
    months = _month_axis(df)
    pivot = sub.pivot_table(index="create_month", columns="user", values="total_hours_spent", aggfunc="sum", fill_value=0)
    pivot = pivot.reindex(months, fill_value=0)
    pivot.index = [_month_label(m) for m in pivot.index]
    return pivot[top_techs] if top_techs else pivot


def monthly_compliance_by_technician(df: pd.DataFrame, top_n: int = 6) -> pd.DataFrame:
    """% de cumplimiento de SLA por mes × técnico (top N por volumen)."""
    top_techs = by_technician(df, top_n=top_n)["user"].tolist()
    months = _month_axis(df)
    known = df[df["sla_status"].isin(SLA_KNOWN_OUTCOME) & df["user"].isin(top_techs)].copy()
    if known.empty:
        return pd.DataFrame(index=[_month_label(m) for m in months], columns=top_techs, dtype=float)
    known["cumplida"] = known["sla_status"].eq("Cumplida") * 100
    pivot = known.pivot_table(index="create_month", columns="user", values="cumplida", aggfunc="mean")
    pivot = pivot.reindex(months)
    pivot = pivot.reindex(columns=top_techs)
    pivot.index = [_month_label(m) for m in pivot.index]
    return pivot


# ---------------------------------------------------------------------------
# Heatmap
# ---------------------------------------------------------------------------

def heatmap_client_month(df: pd.DataFrame, top_n: int = 15) -> pd.DataFrame:
    top_clients = by_client(df, top_n=top_n)["partner"].tolist()
    sub = df[df["partner"].isin(top_clients)]
    months = _month_axis(df)
    pivot = sub.pivot_table(index="partner", columns="create_month", values="name", aggfunc="count", fill_value=0)
    pivot = pivot.reindex(columns=months, fill_value=0)
    pivot = pivot.reindex(top_clients)
    pivot.columns = [_month_label(m) for m in pivot.columns]
    return pivot


# ---------------------------------------------------------------------------
# Contratos de soporte (addon `support_contract`, res.partner)
# ---------------------------------------------------------------------------

def active_contracts_count(contract_df: pd.DataFrame | None) -> int | None:
    """# de clientes con contrato de soporte activo ahora mismo. None si no
    hay datos de contrato disponibles (addon no instalado)."""
    if contract_df is None:
        return None
    if contract_df.empty or "support_contract_state" not in contract_df.columns:
        return 0
    return int((contract_df["support_contract_state"] == "active").sum())


def monthly_active_contracts(contract_df: pd.DataFrame | None, df: pd.DataFrame) -> pd.DataFrame:
    """Contratos cuya vigencia (inicio/fin) cubre cada mes del rango de
    tickets — así se compara mes a mes, no solo el estado de hoy."""
    months = _month_axis(df)
    labels = [_month_label(m) for m in months]
    if contract_df is None or contract_df.empty or "support_contract_start" not in contract_df.columns:
        return pd.DataFrame({"month": months, "label": labels, "contratos_activos": [0] * len(months)})

    start = pd.to_datetime(contract_df["support_contract_start"], errors="coerce")
    end = pd.to_datetime(contract_df.get("support_contract_end"), errors="coerce")
    rows = []
    for m in months:
        month_start, month_end = m.to_timestamp(how="start"), m.to_timestamp(how="end")
        active = (start <= month_end) & (end.isna() | (end >= month_start))
        rows.append({"month": m, "label": _month_label(m), "contratos_activos": int(active.sum())})
    return pd.DataFrame(rows)


def contracts_over_capacity(contract_df: pd.DataFrame | None) -> pd.DataFrame:
    """Clientes que ya superaron su límite mensual contratado (tickets y/o horas)."""
    cols = ["name", "support_tickets_used", "support_ticket_limit", "support_tickets_remaining",
            "support_hours_used", "support_hours_limit", "support_hours_remaining"]
    if contract_df is None or contract_df.empty:
        return pd.DataFrame(columns=cols)
    df = contract_df.copy()
    for c in cols[1:]:
        if c not in df.columns:
            df[c] = 0
    over_tickets = (df["support_ticket_limit"] > 0) & (df["support_tickets_remaining"] < 0)
    over_hours = (df["support_hours_limit"] > 0) & (df["support_hours_remaining"] < 0)
    out = df.loc[over_tickets | over_hours, cols]
    return out.sort_values("support_tickets_remaining").reset_index(drop=True)
