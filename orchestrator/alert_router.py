"""
Enrutador de alertas BC -> destinatarios Teams.

La codeunit 50102 de BC genera 12 tipos de alerta. Cada tipo va a un rol
distinto dentro de la empresa. Este modulo resuelve que Teams user_ids
deben recibir cada alerta.

Fuentes de configuracion del rol -> Teams user_id:
  1. Fichero del proyecto: orchestrator/config/alert_roles.json
  2. Variables de entorno ALERT_ROLE_* como override o fallback
"""

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

ALERT_ROLE_MAP: dict[str, list[str]] = {
    "LICENSE_EXPIRING": ["COMPRAS"],
    "LICENSE_EXPIRED": ["RESPONSABLE"],
    "LICENSE_STOCK_LOW": ["COMPRAS"],
    "ITV_EXPIRING": ["FLOTA"],
    "ITV_EXPIRED": ["FLOTA"],
    "INSURANCE_EXPIRING": ["COMPRAS"],
    "TACHOGRAPH_EXPIRING": ["FLOTA"],
    "SERVICE_DUE": ["FLOTA"],
    "RENTAL_EXPIRING": ["COMPRAS"],
    "MAINTENANCE_OVERDUE": ["TECNICO"],
    "OFFBOARDING_PENDING": ["RRHH"],
    "RETURN_OVERDUE": ["RESPONSABLE"],
}

_ROLE_ENV: dict[str, str] = {
    "COMPRAS": "ALERT_ROLE_COMPRAS",
    "RRHH": "ALERT_ROLE_RRHH",
    "FLOTA": "ALERT_ROLE_FLOTA",
    "TECNICO": "ALERT_ROLE_TECNICO",
    "RESPONSABLE": "ALERT_ROLE_RESPONSABLE",
}

_CONFIG_PATH = Path(__file__).with_name("config") / "alert_roles.json"

ALERT_ICON: dict[str, str] = {
    "critical": "critical",
    "critica": "critical",
    "crítica": "critical",
    "high": "high",
    "alta": "high",
    "medium": "medium",
    "media": "medium",
}

ALERT_LABEL: dict[str, str] = {
    "LICENSE_EXPIRING": "Licencia proxima a vencer",
    "LICENSE_EXPIRED": "Licencia vencida con usuarios asignados",
    "LICENSE_STOCK_LOW": "Stock de licencias bajo",
    "ITV_EXPIRING": "ITV proxima a vencer",
    "ITV_EXPIRED": "ITV vencida",
    "INSURANCE_EXPIRING": "Seguro proximo a renovar",
    "TACHOGRAPH_EXPIRING": "Tacografo proximo a vencer",
    "SERVICE_DUE": "Revision mecanica proxima",
    "RENTAL_EXPIRING": "Contrato de renting por vencer",
    "MAINTENANCE_OVERDUE": "Mantenimiento obligatorio vencido",
    "OFFBOARDING_PENDING": "Empleado pendiente de offboarding",
    "RETURN_OVERDUE": "Devolucion prevista vencida",
}


def _load_role_config() -> dict[str, list[str]]:
    """Carga la tabla rol -> user_ids desde el proyecto y el entorno."""
    configured: dict[str, list[str]] = {}

    if _CONFIG_PATH.exists():
        try:
            raw = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
            for role, values in raw.items():
                if not isinstance(values, list):
                    continue
                configured[role.strip().upper()] = [
                    str(value).strip() for value in values if str(value).strip()
                ]
        except Exception as exc:
            logger.warning("No se pudo cargar %s: %s", _CONFIG_PATH, exc)

    for role, env_key in _ROLE_ENV.items():
        env_value = os.getenv(env_key, "").strip()
        if not env_value:
            continue
        merged = configured.get(role, []).copy()
        for user_id in [item.strip() for item in env_value.split(",") if item.strip()]:
            if user_id not in merged:
                merged.append(user_id)
        configured[role] = merged

    return configured


def get_routing_context(alert_type: str, direct_target: str = "") -> dict:
    """Resuelve roles, destinatarios y trazabilidad de una alerta."""
    recipients: list[str] = []
    if direct_target:
        recipients.append(direct_target)

    normalized = alert_type.upper().replace(" ", "_")
    roles = ALERT_ROLE_MAP.get(normalized, ["RESPONSABLE"])
    role_config = _load_role_config()
    role_targets: dict[str, list[str]] = {}

    configured = 0
    for role in roles:
        targets = role_config.get(role, [])
        if targets:
            role_targets[role] = targets
        for user_id in targets:
            if user_id not in recipients:
                recipients.append(user_id)
                configured += 1

    if configured == 0 and not direct_target:
        logger.warning(
            "Alerta '%s': ningun destinatario configurado. "
            "Completa orchestrator/config/alert_roles.json o define ALERT_ROLE_*.",
            alert_type,
        )

    return {
        "alert_type_normalized": normalized,
        "roles": roles,
        "role_targets": role_targets,
        "recipients": recipients,
        "direct_target": direct_target,
    }


def resolve_recipients(alert_type: str, direct_target: str = "") -> list[str]:
    """Devuelve la lista final de Teams user_ids para una alerta."""
    return get_routing_context(alert_type, direct_target)["recipients"]


def format_teams_message(
    alert_type: str,
    resource_no: str,
    criticality: str,
    details: str,
) -> str:
    """Formatea el mensaje Markdown para Teams segun tipo y criticidad."""
    label = ALERT_LABEL.get(alert_type.upper(), alert_type)

    return (
        f"[{ALERT_ICON.get(criticality.lower(), 'medium').upper()}] **{label}**\n"
        f"Recurso: `{resource_no}`\n"
        f"Criticidad: {criticality}\n"
        f"{details}"
    )
