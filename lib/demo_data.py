"""Dataset sintético para previsualizar el tablero sin subir un export real.

Los nombres de clientes/técnicos son genéricos (Cliente A, Técnico 1, ...):
no representan datos reales de ningún cliente de Firefly.
"""

from __future__ import annotations

import random

import pandas as pd

from lib.data_loader import derive_ticket_fields

_CLIENTES = [f"Cliente {c}" for c in "ABCDEFGHIJKL"]
_TECNICOS = ["Técnico 1", "Técnico 2", "Técnico 3", "Técnico 4"]
_EQUIPOS = ["Soporte Firefly"]
_ETAPAS = ["Nuevo", "En proceso", "Bloqueado", "Resuelto", "Cancelado"]
_ETAPAS_CERRADAS = {"Resuelto", "Cancelado"}
_PRIORIDADES = ["Baja prioridad", "Prioridad media", "Alta prioridad", "Urgente"]
_SLAS = ["SLA Estándar 24h", "SLA Urgente 4h", "SLA Premium 8h"]
_ASUNTOS = [
    "Error al validar factura electrónica", "Ajuste de plantilla de reporte",
    "No carga el módulo de inventario", "Solicitud de nuevo usuario",
    "Diferencia en cambio de cliente", "Falla en orden de fabricación",
    "Duda sobre conciliación bancaria", "Bloqueo al imprimir documento",
    "Configuración de impuestos", "Error de sincronización con DIAN",
]


def build_demo_dataframe(n: int = 220, seed: int = 42) -> pd.DataFrame:
    rng = random.Random(seed)
    now = pd.Timestamp.now().normalize()
    start = now - pd.DateOffset(months=8)
    span_days = max((now - start).days, 1)

    rows = []
    for i in range(n):
        offset = int(rng.triangular(0, span_days, span_days * 0.85))
        create_date = start + pd.Timedelta(days=offset, hours=rng.randint(7, 19), minutes=rng.randint(0, 59))
        priority = rng.choices(_PRIORIDADES, weights=[35, 35, 20, 10])[0]
        stage = rng.choices(_ETAPAS, weights=[8, 20, 5, 58, 9])[0]
        is_closed = stage in _ETAPAS_CERRADAS
        close_date = pd.NaT
        close_hours = None
        if is_closed:
            resolve_days = max(0.05, rng.gauss(2.5, 2.2))
            close_date = create_date + pd.Timedelta(days=resolve_days)
            if close_date > now:
                close_date = now
            close_hours = round(max(0.1, resolve_days * rng.uniform(6, 9)), 2)

        sla_name = rng.choice(_SLAS)
        deadline_hours = {"SLA Urgente 4h": 4, "SLA Premium 8h": 8, "SLA Estándar 24h": 24}[sla_name]
        sla_deadline = create_date + pd.Timedelta(hours=deadline_hours * rng.uniform(1.0, 1.6))
        if is_closed:
            sla_success = bool(close_date <= sla_deadline)
        else:
            sla_success = None

        hours_spent = round(max(0.0, rng.gauss(2.0 if is_closed else 0.8, 1.6)), 2)
        first_response = round(max(0.05, rng.gauss(deadline_hours * 0.3, deadline_hours * 0.2)), 2)

        rows.append({
            "id": 1000 + i,
            "ticket_ref": f"T{1000 + i}",
            "name": rng.choice(_ASUNTOS),
            "team": rng.choice(_EQUIPOS),
            "partner": rng.choice(_CLIENTES),
            "user": rng.choice(_TECNICOS) if stage != "Nuevo" or rng.random() > 0.3 else "Sin asignar",
            "stage": stage,
            "priority": priority,
            "create_date": create_date,
            "close_date": close_date,
            "close_hours": close_hours,
            "first_response_hours": first_response,
            "total_hours_spent": hours_spent,
            "sla_ids": sla_name,
            "sla_deadline": sla_deadline if not is_closed else pd.NaT,
            "sla_reached": sla_success,
            "sla_reached_late": (sla_success is False) if is_closed else None,
            "sla_fail": (sla_success is False) if is_closed else None,
            "sla_success": sla_success,
        })

    df = pd.DataFrame(rows)
    return derive_ticket_fields(df)
