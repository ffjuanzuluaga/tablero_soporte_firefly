"""Conexión en vivo a Odoo vía XML-RPC para leer `helpdesk.ticket` y horas.

Usa únicamente los campos técnicos reales del modelo (ver los módulos
`helpdesk` / `helpdesk_timesheet` / `sale_subscription` en el código fuente
de Odoo 19), así que no depende del idioma de la interfaz.

Credenciales: siempre desde `st.secrets["odoo"]` (ver `streamlit_app.py`),
nunca escritas a disco por esta app. Se recomienda usar una API key de Odoo
(Ajustes de usuario → Seguridad de la cuenta → Nueva clave API) en vez de la
contraseña real.
"""

from __future__ import annotations

import threading
import xmlrpc.client
from dataclasses import dataclass

import pandas as pd

from lib.data_loader import derive_ticket_fields

# Campos que existen en cualquier instalación de `helpdesk` (módulo base):
# se piden siempre, sin verificar disponibilidad antes.
CORE_TICKET_FIELDS = [
    "id", "ticket_ref", "name", "team_id", "partner_id", "user_id", "stage_id",
    "priority", "create_date", "close_date", "assign_date", "kanban_state",
]

# Campos que dependen de módulos opcionales (helpdesk_timesheet, SLA
# configurado, etc.): se piden solo si `fields_get` confirma que existen,
# para que su ausencia nunca tumbe ni recorte la consulta de los campos core.
OPTIONAL_TICKET_FIELDS = [
    "close_hours", "assign_hours", "open_hours",
    "first_response_hours", "avg_response_hours",
    "sla_ids", "sla_deadline", "sla_deadline_hours",
    "sla_reached", "sla_reached_late", "sla_fail", "sla_success",
    "total_hours_spent",
]

# xmlrpc.client.ServerProxy no es thread-safe sobre una misma conexión: si
# Streamlit llega a invocar el cliente cacheado desde más de un hilo/sesión al
# tiempo, dos respuestas pueden entrelazarse en el mismo socket. Se serializan
# las llamadas para evitar datos corruptos o cruzados entre tickets.
_rpc_lock = threading.Lock()


class OdooConnectionError(RuntimeError):
    """Error de red, autenticación o permisos al hablar con Odoo."""


@dataclass(frozen=True)
class OdooCredentials:
    url: str
    db: str
    username: str
    api_key: str


def _m2o_name(value, default=None):
    if isinstance(value, (list, tuple)) and len(value) == 2:
        return value[1]
    return default


class OdooClient:
    def __init__(self, creds: OdooCredentials):
        self.creds = creds
        base = creds.url.strip().rstrip("/")
        if not base.startswith(("http://", "https://")):
            base = f"https://{base}"
        self._common = xmlrpc.client.ServerProxy(f"{base}/xmlrpc/2/common")
        self._models = xmlrpc.client.ServerProxy(f"{base}/xmlrpc/2/object")
        self.uid: int | None = None

    def authenticate(self) -> int:
        try:
            self._common.version()
        except Exception as exc:  # noqa: BLE001
            raise OdooConnectionError(f"No se pudo contactar la URL de Odoo: {exc}") from exc
        try:
            uid = self._common.authenticate(self.creds.db, self.creds.username, self.creds.api_key, {})
        except Exception as exc:  # noqa: BLE001
            raise OdooConnectionError(f"Error de autenticación: {exc}") from exc
        if not uid:
            raise OdooConnectionError("Usuario, base de datos o contraseña/API key incorrectos.")
        self.uid = uid
        return uid

    def _execute(self, model: str, method: str, *args, **kwargs):
        if not self.uid:
            self.authenticate()
        try:
            with _rpc_lock:
                return self._models.execute_kw(
                    self.creds.db, self.uid, self.creds.api_key, model, method, list(args), kwargs
                )
        except xmlrpc.client.Fault as exc:
            raise OdooConnectionError(exc.faultString) from exc
        except Exception as exc:  # noqa: BLE001
            raise OdooConnectionError(f"Error consultando Odoo ({model}.{method}): {exc}") from exc

    def available_fields(self, model: str) -> set[str]:
        return set(self._execute(model, "fields_get", [], attributes=[]).keys())

    def priority_labels(self) -> dict[str, str]:
        info = self._execute("helpdesk.ticket", "fields_get", ["priority"], attributes=["selection"])
        return dict(info.get("priority", {}).get("selection", []))

    def search_read(self, model: str, domain: list, fields: list[str], order: str | None = None) -> list[dict]:
        kwargs = {"fields": fields}
        if order:
            kwargs["order"] = order
        return self._execute(model, "search_read", domain, **kwargs)

    def read(self, model: str, ids: list[int], fields: list[str]) -> list[dict]:
        if not ids:
            return []
        return self._execute(model, "read", ids, **{"fields": fields})


def _ticket_row(rec: dict, priority_map: dict[str, str], sla_name_map: dict[int, str]) -> dict:
    sla_names = [sla_name_map[i] for i in (rec.get("sla_ids") or []) if i in sla_name_map]
    return {
        "id": rec.get("id"),
        "ticket_ref": rec.get("ticket_ref") or rec.get("id"),
        "name": rec.get("name"),
        "team": _m2o_name(rec.get("team_id"), "Sin equipo"),
        "partner": _m2o_name(rec.get("partner_id"), "Sin cliente"),
        "user": _m2o_name(rec.get("user_id"), "Sin asignar"),
        "stage": _m2o_name(rec.get("stage_id"), "Sin etapa"),
        "priority": priority_map.get(str(rec.get("priority")), rec.get("priority") or "Sin prioridad"),
        "create_date": rec.get("create_date") or None,
        "close_date": rec.get("close_date") or None,
        "assign_date": rec.get("assign_date") or None,
        "close_hours": rec.get("close_hours"),
        "assign_hours": rec.get("assign_hours"),
        "open_hours": rec.get("open_hours"),
        "first_response_hours": rec.get("first_response_hours"),
        "avg_response_hours": rec.get("avg_response_hours"),
        "sla_ids": ", ".join(sla_names),
        "sla_deadline": rec.get("sla_deadline") or None,
        "sla_deadline_hours": rec.get("sla_deadline_hours"),
        "sla_reached": rec.get("sla_reached"),
        "sla_reached_late": rec.get("sla_reached_late"),
        "sla_fail": rec.get("sla_fail"),
        "sla_success": rec.get("sla_success"),
        "total_hours_spent": rec.get("total_hours_spent"),
        "kanban_state": rec.get("kanban_state"),
    }


def _ticket_fields(client: OdooClient) -> list[str]:
    available = client.available_fields("helpdesk.ticket")
    return CORE_TICKET_FIELDS + [f for f in OPTIONAL_TICKET_FIELDS if f in available]


def _ticket_domain(date_from=None, date_to=None) -> list:
    domain: list = []
    if date_from:
        domain.append(("create_date", ">=", f"{date_from} 00:00:00"))
    if date_to:
        domain.append(("create_date", "<=", f"{date_to} 23:59:59"))
    return domain


def fetch_ticket_sample_raw(client: OdooClient, limit: int = 2) -> list[dict]:
    """Trae N tickets tal cual los devuelve Odoo, sin transformar — para depurar
    en la app qué valores reales llegan en user_id/partner_id/create_date."""
    fields = _ticket_fields(client)
    return client.search_read("helpdesk.ticket", [], fields, order="create_date desc")[:limit]


def fetch_tickets(client: OdooClient, date_from=None, date_to=None) -> pd.DataFrame:
    fields = _ticket_fields(client)
    domain = _ticket_domain(date_from, date_to)

    records = client.search_read("helpdesk.ticket", domain, fields, order="create_date desc")
    if not records:
        return derive_ticket_fields(pd.DataFrame(columns=["id", "name", "partner", "user", "team", "stage", "priority", "create_date"]))

    priority_map = client.priority_labels()

    sla_ids_all = sorted({sid for rec in records for sid in (rec.get("sla_ids") or [])})
    sla_name_map: dict[int, str] = {}
    if sla_ids_all:
        for row in client.read("helpdesk.sla", sla_ids_all, ["name"]):
            sla_name_map[row["id"]] = row["name"]

    rows = [_ticket_row(rec, priority_map, sla_name_map) for rec in records]
    return derive_ticket_fields(pd.DataFrame(rows))


def fetch_active_support_contracts(client: OdooClient) -> int | None:
    """Clientes con un contrato de soporte activo = suscripción (`sale.order`)
    con `subscription_state = '3_progress'` (En curso). Requiere el módulo
    `sale_subscription`; si no está instalado devuelve None (la UI lo muestra
    como "N/D" en vez de un número engañoso)."""
    available = client.available_fields("sale.order")
    if "subscription_state" not in available:
        return None
    records = client.search_read(
        "sale.order", [("subscription_state", "=", "3_progress")], ["partner_id"]
    )
    partner_ids = {rec["partner_id"][0] for rec in records if isinstance(rec.get("partner_id"), (list, tuple))}
    return len(partner_ids)


def connect(creds: OdooCredentials) -> OdooClient:
    """Crea el cliente y autentica de una vez. Lanza OdooConnectionError si falla."""
    client = OdooClient(creds)
    client.authenticate()
    return client
