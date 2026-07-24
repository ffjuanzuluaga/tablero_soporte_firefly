"""Paleta visual y mapeo de columnas del export de Odoo `helpdesk.ticket`.

Los alias de columnas se basan en los campos reales del modelo
``helpdesk.ticket`` (y sus extensiones ``helpdesk_timesheet`` / ``helpdesk_sla``)
en Odoo 19 Enterprise, para poder reconocer un export de Excel/CSV sin importar
si el usuario de Odoo estaba en español o en inglés.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Paleta (dark mode) — misma familia usada por el resto de tableros Firefly.
# ---------------------------------------------------------------------------

SURFACE = "#1a1a19"
PAGE_PLANE = "#0d0d0d"
INK_PRIMARY = "#ffffff"
INK_SECONDARY = "#c3c2b7"
INK_MUTED = "#898781"
GRIDLINE = "#2c2c2a"
AXIS = "#383835"

# Orden categórico fijo (nunca se reordena por rango/tamaño de dato).
CATEGORICAL = [
    "#3987e5",  # 1 azul
    "#d95926",  # 2 naranja
    "#199e70",  # 3 aqua
    "#c98500",  # 4 amarillo
    "#d55181",  # 5 magenta
    "#008300",  # 6 verde
    "#9085e9",  # 7 violeta
    "#e66767",  # 8 rojo
]

# Estado (reservados, nunca se reusan como color de serie).
STATUS = {
    "good": "#0ca30c",
    "warning": "#fab219",
    "serious": "#ec835a",
    "critical": "#d03b3b",
}

# Secuencial (una sola tonalidad, para heatmaps).
SEQUENTIAL_BLUE = [
    "#1a1a19", "#0d366b", "#104281", "#184f95", "#1c5cab",
    "#256abf", "#2a78d6", "#3987e5", "#5598e7", "#6da7ec",
    "#86b6ef", "#9ec5f4", "#b7d3f6", "#cde2fb",
]

STAGE_FALLBACK = CATEGORICAL

PRIORITY_ORDER_HINTS = [
    "urgente", "urgent", "alta", "high", "media", "medium", "normal", "baja", "low",
]

PRIORITY_COLORS = {
    # se resuelve dinámicamente en metrics.py; estos son los valores por defecto
    # para las 4 etiquetas estándar del modelo TICKET_PRIORITY.
    0: STATUS["good"],
    1: CATEGORICAL[3],
    2: STATUS["serious"],
    3: STATUS["critical"],
}

SLA_STATUS_COLORS = {
    "Cumplida": STATUS["good"],
    "Incumplida": STATUS["critical"],
    "En curso": CATEGORICAL[0],
    "Sin SLA": INK_MUTED,
}

MESES_ES = {
    1: "Ene", 2: "Feb", 3: "Mar", 4: "Abr", 5: "May", 6: "Jun",
    7: "Jul", 8: "Ago", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dic",
}

DOW_ES = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
