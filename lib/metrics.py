"""Agregaciones (KPIs, series de tiempo, rankings) sobre el DataFrame de tickets.

Todas las funciones reciben el DataFrame ya normalizado/derivado por
`data_loader.derive_ticket_fields` y devuelven estructuras livianas
(dict / DataFrame) listas para graficar en `charts.py`.
"""

from __future__ import annotations

import numpy as np
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


def kpis(df: pd.DataFrame) -> dict:
    total = len(df)
    closed = int(df["is_closed"].sum())
    open_ = total - closed
    close_rate = (closed / total * 100) if total else 0.0

    hours_series = df["total_hours_spent"].dropna()
    hours_total = float(hours_series.sum()) if len(hours_series) else 0.0
    hours_avg = _safe_mean(df.loc[df["total_hours_spent"] > 0, "total_hours_spent"]) if total else None

    resolution_avg = _safe_mean(df.loc[df["is_closed"], "resolution_hours"])
    first_response_avg = _safe_mean(df.loc[df["first_response_hours"] > 0, "first_response_hours"]) if "first_response_hours" in df else None

    order = priority_order(df)
    critical_labels = set(order[: min(2, len(order))])
    critical_count = int(df["priority"].isin(critical_labels).sum()) if order else 0

    sla_known = df[df["sla_status"].isin(SLA_KNOWN_OUTCOME)]
    sla_compliance = (sla_known["sla_status"].eq("Cumplida").mean() * 100) if len(sla_known) else None
    sla_overdue = int((df["sla_status"] == "Vencida").sum())

    clients_active = int(df.loc[df["partner"] != "Sin cliente", "partner"].nunique())
    techs_active = int(df.loc[df["user"] != "Sin asignar", "user"].nunique())

    return {
        "total": total,
        "closed": closed,
        "open": open_,
        "close_rate": close_rate,
        "hours_total": hours_total,
        "hours_avg_per_ticket": hours_avg,
        "resolution_avg_hours": resolution_avg,
        "first_response_avg_hours": first_response_avg,
        "critical_count": critical_count,
        "critical_pct": (critical_count / total * 100) if total else 0.0,
        "sla_compliance_pct": sla_compliance,
        "sla_known_count": len(sla_known),
        "sla_overdue": sla_overdue,
        "clients_active": clients_active,
        "techs_active": techs_active,
    }


def _month_axis(df: pd.DataFrame, extra: pd.Series | None = None) -> list[pd.Period]:
    periods = set(df["create_month"].dropna().tolist())
    if extra is not None:
        periods |= set(extra.dropna().tolist())
    return sorted(periods)


def monthly_trend(df: pd.DataFrame) -> pd.DataFrame:
    """Entrantes por mes de creación vs cerrados por mes de cierre."""
    close_month = df.loc[df["is_closed"], "close_date"].dt.to_period("M")
    months = _month_axis(df, close_month)
    if not months:
        return pd.DataFrame(columns=["month", "label", "creados", "cerrados"])

    created = df.groupby("create_month").size()
    closed = close_month.value_counts()

    rows = [{
        "month": m,
        "label": f"{C.MESES_ES.get(m.month, m.month)} {m.year}",
        "creados": int(created.get(m, 0)),
        "cerrados": int(closed.get(m, 0)),
    } for m in months]
    return pd.DataFrame(rows)


def monthly_close_rate(df: pd.DataFrame) -> pd.DataFrame:
    """Tasa de cierre por cohorte de creación: de los tickets CREADOS en cada
    mes, qué % ya está cerrado a la fecha de la consulta.

    Nota: a propósito NO se calcula como (cerrados-en-el-mes / creados-en-el-mes)
    con "cerrados" por fecha de cierre — esas son poblaciones distintas de
    tickets y la división puede superar 100% (p.ej. un mes donde se destraba
    backlog viejo), lo que se ve como un gráfico recortado/raro contra un eje
    0-100%. Aquí "cerrados" siempre es un subconjunto de "creados" del mismo
    mes, así que la tasa queda garantizada entre 0 y 100%.
    """
    months = _month_axis(df)
    rows = []
    for m in months:
        part = df[df["create_month"] == m]
        creados = len(part)
        cerrados = int(part["is_closed"].sum())
        rows.append({
            "month": m,
            "label": f"{C.MESES_ES.get(m.month, m.month)} {m.year}",
            "creados": creados,
            "cerrados": cerrados,
            "tasa_pct": (cerrados / creados * 100) if creados else 0.0,
        })
    return pd.DataFrame(rows, columns=["month", "label", "creados", "cerrados", "tasa_pct"])


def monthly_avg_hours(df: pd.DataFrame) -> pd.DataFrame:
    months = _month_axis(df)
    sub = df[df["total_hours_spent"] > 0]
    means = sub.groupby("create_month")["total_hours_spent"].mean()
    rows = [{"month": m, "label": f"{C.MESES_ES.get(m.month, m.month)} {m.year}", "horas_prom": float(means.get(m, 0.0) or 0.0)} for m in months]
    return pd.DataFrame(rows)


def monthly_first_response(df: pd.DataFrame) -> pd.DataFrame:
    months = _month_axis(df)
    sub = df[df["first_response_hours"] > 0]
    means = sub.groupby("create_month")["first_response_hours"].mean()
    rows = [{"month": m, "label": f"{C.MESES_ES.get(m.month, m.month)} {m.year}", "resp_prom": float(means.get(m, 0.0) or 0.0)} for m in months]
    return pd.DataFrame(rows)


def monthly_sla_compliance(df: pd.DataFrame) -> pd.DataFrame:
    months = _month_axis(df)
    known = df[df["sla_status"].isin(SLA_KNOWN_OUTCOME)]
    grp = known.groupby("create_month")["sla_status"].apply(lambda s: (s == "Cumplida").mean() * 100)
    rows = [{"month": m, "label": f"{C.MESES_ES.get(m.month, m.month)} {m.year}", "cumplimiento_pct": float(grp.get(m, np.nan))} for m in months]
    return pd.DataFrame(rows)


def by_stage(df: pd.DataFrame) -> pd.DataFrame:
    counts = df["stage"].value_counts()
    return pd.DataFrame({"stage": counts.index, "count": counts.values})


def by_priority(df: pd.DataFrame) -> pd.DataFrame:
    order = priority_order(df)
    counts = df["priority"].value_counts()
    rows = [{"priority": p, "count": int(counts.get(p, 0))} for p in order]
    return pd.DataFrame(rows, columns=["priority", "count"])


def sla_status_summary(df: pd.DataFrame) -> pd.DataFrame:
    order = ["Cumplida", "Incumplida", "Vencida", "En curso", "Sin SLA"]
    counts = df["sla_status"].value_counts()
    rows = [{"status": s, "count": int(counts.get(s, 0))} for s in order if counts.get(s, 0) > 0 or s in ("Cumplida", "Incumplida")]
    return pd.DataFrame(rows)


def by_sla_policy(df: pd.DataFrame) -> pd.DataFrame:
    sub = df[df["has_sla_policy"]].copy()
    if sub.empty:
        return pd.DataFrame(columns=["policy", "count", "cumplidas", "incumplidas", "cumplimiento_pct"])
    sub["policy_list"] = sub["sla_ids"].str.split(",")
    exploded = sub.explode("policy_list")
    exploded["policy_list"] = exploded["policy_list"].str.strip()
    exploded = exploded[exploded["policy_list"] != ""]

    grp = exploded.groupby("policy_list")
    rows = []
    for policy, part in grp:
        known = part[part["sla_status"].isin(SLA_KNOWN_OUTCOME)]
        cumplidas = int((known["sla_status"] == "Cumplida").sum())
        incumplidas = int((known["sla_status"] == "Incumplida").sum())
        pct = (cumplidas / len(known) * 100) if len(known) else None
        rows.append({
            "policy": policy, "count": len(part),
            "cumplidas": cumplidas, "incumplidas": incumplidas,
            "cumplimiento_pct": pct,
        })
    out = pd.DataFrame(rows).sort_values("count", ascending=False).reset_index(drop=True)
    return out


def _agent_rollup(df: pd.DataFrame, dimension: str, exclude_default: str, top_n: int | None = None) -> pd.DataFrame:
    sub = df[df[dimension] != exclude_default]
    if sub.empty:
        return pd.DataFrame(columns=[dimension, "tickets", "cerrados", "horas", "resolucion_prom_horas", "cumplimiento_sla_pct"])

    rows = []
    for key, part in sub.groupby(dimension):
        known = part[part["sla_status"].isin(SLA_KNOWN_OUTCOME)]
        pct = (known["sla_status"].eq("Cumplida").mean() * 100) if len(known) else None
        rows.append({
            dimension: key,
            "tickets": len(part),
            "cerrados": int(part["is_closed"].sum()),
            "horas": float(part["total_hours_spent"].dropna().sum()),
            "resolucion_prom_horas": _safe_mean(part.loc[part["is_closed"], "resolution_hours"]),
            "cumplimiento_sla_pct": pct,
        })
    out = pd.DataFrame(rows).sort_values("tickets", ascending=False).reset_index(drop=True)
    if top_n:
        out = out.head(top_n)
    return out


def by_technician(df: pd.DataFrame, top_n: int | None = None) -> pd.DataFrame:
    return _agent_rollup(df, "user", "Sin asignar", top_n)


def by_client(df: pd.DataFrame, top_n: int | None = None) -> pd.DataFrame:
    return _agent_rollup(df, "partner", "Sin cliente", top_n)


def top_clients_chart_data(df: pd.DataFrame, top_n: int = 8) -> pd.DataFrame:
    return by_client(df, top_n=top_n)[["partner", "tickets"]]


def by_dow(df: pd.DataFrame) -> pd.DataFrame:
    counts = df["create_dow"].value_counts()
    rows = [{"dow": d, "count": int(counts.get(d, 0))} for d in C.DOW_ES]
    return pd.DataFrame(rows)


def resolution_by_priority(df: pd.DataFrame) -> pd.DataFrame:
    order = priority_order(df)
    closed = df[df["is_closed"]]
    means = closed.groupby("priority")["resolution_hours"].mean()
    rows = [{"priority": p, "horas_prom": float(means.get(p, np.nan))} for p in order]
    return pd.DataFrame(rows, columns=["priority", "horas_prom"])


def technician_monthly(df: pd.DataFrame, top_n: int = 6) -> pd.DataFrame:
    top_techs = by_technician(df, top_n=top_n)["user"].tolist()
    sub = df[df["user"].isin(top_techs)]
    months = _month_axis(df)
    pivot = sub.pivot_table(index="create_month", columns="user", values="name", aggfunc="count", fill_value=0)
    pivot = pivot.reindex(months, fill_value=0)
    pivot.index = [f"{C.MESES_ES.get(m.month, m.month)} {m.year}" for m in pivot.index]
    return pivot[top_techs] if top_techs else pivot


def technician_hours_from_timesheets(ts_df: pd.DataFrame) -> pd.DataFrame:
    """Horas por empleado a partir de un export detallado de hojas de horas."""
    if "employee" not in ts_df.columns or "unit_amount" not in ts_df.columns:
        return pd.DataFrame(columns=["user", "horas", "tickets"])
    sub = ts_df.dropna(subset=["employee"])
    if sub.empty:
        return pd.DataFrame(columns=["user", "horas", "tickets"])
    agg = {"unit_amount": "sum"}
    if "ticket_ref" in sub.columns:
        agg["ticket_ref"] = "nunique"
    grp = sub.groupby("employee").agg(agg).reset_index()
    grp = grp.rename(columns={"employee": "user", "unit_amount": "horas", "ticket_ref": "tickets"})
    if "tickets" not in grp.columns:
        grp["tickets"] = 0
    return grp.sort_values("horas", ascending=False).reset_index(drop=True)


def heatmap_client_month(df: pd.DataFrame, top_n: int = 15) -> pd.DataFrame:
    top_clients = by_client(df, top_n=top_n)["partner"].tolist()
    sub = df[df["partner"].isin(top_clients)]
    months = _month_axis(df)
    pivot = sub.pivot_table(index="partner", columns="create_month", values="name", aggfunc="count", fill_value=0)
    pivot = pivot.reindex(columns=months, fill_value=0)
    pivot = pivot.reindex(top_clients)
    pivot.columns = [f"{C.MESES_ES.get(m.month, m.month)} {m.year}" for m in pivot.columns]
    return pivot
