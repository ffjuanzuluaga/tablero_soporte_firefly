"""Normalización de tickets de `helpdesk.ticket` a un esquema canónico.

`derive_ticket_fields` es el punto de entrada: toma un DataFrame con columnas
canónicas (id, ticket_ref, name, team, partner, user, stage, priority,
create_date, close_date, ...) —ya sea leído en vivo desde Odoo vía
`odoo_client`, o construido sintéticamente por `demo_data`— y calcula los
campos derivados que usa el resto del tablero: si está cerrado, horas de
resolución, estado de SLA, mes/día de creación, etc.
"""

from __future__ import annotations

import pandas as pd

from lib import constants as C

TRUE_TOKENS = {"true", "yes", "si", "sí", "verdadero", "1", "x", "activo"}
FALSE_TOKENS = {"false", "no", "falso", "0", ""}


def to_bool_or_none(value) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, float) and pd.isna(value):
        return None
    text = str(value).strip().lower()
    if text in TRUE_TOKENS and text != "":
        return True
    if text in FALSE_TOKENS:
        return False if text != "" else None
    return None


def to_hours(value) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value) if pd.notna(value) else None
    text = str(value).strip()
    if not text:
        return None
    text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def parse_datetime(series: pd.Series) -> pd.Series:
    """Odoo (XML-RPC) siempre entrega fechas en ISO `YYYY-MM-DD HH:MM:SS`."""
    return pd.to_datetime(series, errors="coerce", format="mixed")


def derive_ticket_fields(df: pd.DataFrame) -> pd.DataFrame:
    n = len(df)

    if "ticket_ref" in df.columns:
        df["ticket_label"] = df["ticket_ref"].fillna(df.get("id", pd.Series([""] * n)))
    elif "id" in df.columns:
        df["ticket_label"] = df["id"]
    else:
        df["ticket_label"] = [f"#{i + 1}" for i in range(n)]

    if "name" not in df.columns:
        df["name"] = "(sin asunto)"
    df["name"] = df["name"].fillna("(sin asunto)")

    for col, default in [("partner", "Sin cliente"), ("user", "Sin asignar"),
                          ("team", "Sin equipo"), ("stage", "Sin etapa"),
                          ("priority", "Sin prioridad")]:
        if col not in df.columns:
            df[col] = default
        df[col] = df[col].fillna(default).replace("", default)

    # Fechas
    for col in ["create_date", "close_date", "assign_date", "sla_deadline"]:
        if col in df.columns:
            df[col] = parse_datetime(df[col])
        else:
            df[col] = pd.NaT

    # Horas (numéricas)
    for col in ["close_hours", "assign_hours", "open_hours", "first_response_hours",
                "avg_response_hours", "total_hours_spent", "sla_deadline_hours"]:
        if col in df.columns:
            df[col] = df[col].map(to_hours)
        else:
            df[col] = pd.NA

    # Booleanos
    for col in ["sla_reached", "sla_reached_late", "sla_fail", "sla_success", "active"]:
        if col in df.columns:
            df[col] = df[col].map(to_bool_or_none)
        else:
            df[col] = None

    if "sla_ids" not in df.columns:
        df["sla_ids"] = ""
    df["sla_ids"] = df["sla_ids"].fillna("")
    df["has_sla_policy"] = df["sla_ids"].str.strip() != ""

    # Cerrado = tiene fecha de cierre (así es como Odoo la puebla al entrar
    # a una etapa "plegada"/fold, y la limpia si el ticket se reabre).
    df["is_closed"] = df["close_date"].notna()

    # Horas de resolución: preferir el campo calculado por Odoo (horas
    # laborables); si no vino en el export, aproximar con horas de reloj.
    calc_calendar = (df["close_date"] - df["create_date"]).dt.total_seconds() / 3600.0
    df["resolution_hours"] = df["close_hours"]
    df["resolution_hours_is_approx"] = df["close_hours"].isna() & df["close_date"].notna()
    df.loc[df["resolution_hours"].isna(), "resolution_hours"] = calc_calendar[df["resolution_hours"].isna()]

    # Estado de SLA por ticket
    now = pd.Timestamp.now()

    def _sla_status(row) -> str:
        if not row["has_sla_policy"] and pd.isna(row["sla_deadline"]) and row["sla_success"] is None and row["sla_fail"] is None:
            return "Sin SLA"
        if row["sla_success"] is True:
            return "Cumplida"
        if row["sla_fail"] is True or row["sla_reached_late"] is True:
            return "Incumplida"
        deadline = row["sla_deadline"]
        if pd.notna(deadline):
            if pd.notna(row["close_date"]):
                return "Cumplida" if row["close_date"] <= deadline else "Incumplida"
            return "En curso" if deadline > now else "Vencida"
        return "En curso"

    df["sla_status"] = df.apply(_sla_status, axis=1)

    # Periodo mensual (para tendencias)
    df["create_month"] = df["create_date"].dt.to_period("M")
    df["create_month_label"] = df["create_date"].apply(
        lambda d: f"{C.MESES_ES.get(d.month, d.month)} {d.year}" if pd.notna(d) else None
    )
    df["create_dow"] = df["create_date"].dt.dayofweek.map(
        lambda x: C.DOW_ES[int(x)] if pd.notna(x) else None
    )

    return df
