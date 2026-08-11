"""Paleta visual del tablero (tema claro, fondo blanco — lineamiento de marca)."""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Paleta (light mode) — fondo blanco, misma familia usada por el resto de
# tableros de control de Firefly.
# ---------------------------------------------------------------------------

SURFACE = "#fcfcfb"
PAGE_PLANE = "#f9f9f7"
INK_PRIMARY = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
GRIDLINE = "#e1e0d9"
AXIS = "#c3c2b7"

# Orden categórico fijo (nunca se reordena por rango/tamaño de dato).
CATEGORICAL = [
    "#2a78d6",  # 1 azul
    "#eb6834",  # 2 naranja
    "#1baf7a",  # 3 aqua
    "#eda100",  # 4 amarillo
    "#e87ba4",  # 5 magenta
    "#008300",  # 6 verde
    "#4a3aa7",  # 7 violeta
    "#e34948",  # 8 rojo
]

# Estado (reservados, nunca se reusan como color de serie) — fijo en ambos modos.
STATUS = {
    "good": "#0ca30c",
    "warning": "#fab219",
    "serious": "#ec835a",
    "critical": "#d03b3b",
}

# Secuencial (una sola tonalidad, para el heatmap): claro = pocos, oscuro = muchos.
SEQUENTIAL_BLUE = [
    "#fcfcfb", "#cde2fb", "#b7d3f6", "#9ec5f4", "#86b6ef",
    "#6da7ec", "#5598e7", "#3987e5", "#2a78d6", "#256abf",
    "#1c5cab", "#184f95", "#104281", "#0d366b",
]

STAGE_FALLBACK = CATEGORICAL

PRIORITY_ORDER_HINTS = [
    "urgente", "urgent", "alta", "high", "media", "medium", "normal", "baja", "low",
]

# Rampa fija por severidad, usada en todo el tablero para que "Urgente" y
# "Baja" siempre tengan el mismo color sin importar el gráfico.
PRIORITY_SEVERITY_RAMP = [STATUS["critical"], STATUS["serious"], STATUS["warning"], STATUS["good"]]

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
