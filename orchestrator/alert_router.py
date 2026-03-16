"""
Enrutador de alertas BC -> destinatarios Teams y correo.

La codeunit 50102 de BC genera 12 tipos de alerta. Cada tipo va a un rol
distinto dentro de la empresa. Este modulo resuelve:
  - Teams user_ids para el bot
  - emails para Power Automate

Fuentes de configuracion:
  1. Fichero del proyecto: orchestrator/config/alert_roles.json
  2. Variables de entorno ALERT_ROLE_* y ALERT_ROLE_*_EMAILS como override o fallback
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

_ROLE_EMAIL_ENV: dict[str, str] = {
    "COMPRAS": "ALERT_ROLE_COMPRAS_EMAILS",
    "RRHH": "ALERT_ROLE_RRHH_EMAILS",
    "FLOTA": "ALERT_ROLE_FLOTA_EMAILS",
    "TECNICO": "ALERT_ROLE_TECNICO_EMAILS",
    "RESPONSABLE": "ALERT_ROLE_RESPONSABLE_EMAILS",
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


def _split_csv(raw_value: str) -> list[str]:
    return [item.strip() for item in raw_value.split(",") if item.strip()]


def _append_unique(values: list[str], new_values: list[str]) -> list[str]:
    merged = values.copy()
    for value in new_values:
        if value not in merged:
            merged.append(value)
    return merged


def _normalize_role_entry(value: object) -> dict[str, list[str]]:
    """
    Soporta dos formatos de config:
      "ROL": ["teams-user-id-1", "teams-user-id-2"]
      "ROL": {"teamsUserIds": [...], "emails": [...]}
    """
    if isinstance(value, list):
        return {"teamsUserIds": [str(item).strip() for item in value if str(item).strip()], "emails": []}

    if isinstance(value, dict):
        teams_user_ids = value.get("teamsUserIds", [])
        emails = value.get("emails", [])
        return {
            "teamsUserIds": [
                str(item).strip() for item in teams_user_ids if str(item).strip()
            ] if isinstance(teams_user_ids, list) else [],
            "emails": [
                str(item).strip() for item in emails if str(item).strip()
            ] if isinstance(emails, list) else [],
        }

    return {"teamsUserIds": [], "emails": []}


def _load_role_config() -> dict[str, dict[str, list[str]]]:
    """Carga la tabla rol -> teams user ids y emails desde el proyecto y el entorno."""
    configured: dict[str, dict[str, list[str]]] = {}

    if _CONFIG_PATH.exists():
        try:
            raw = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
            for role, value in raw.items():
                configured[role.strip().upper()] = _normalize_role_entry(value)
        except Exception as exc:
            logger.warning("No se pudo cargar %s: %s", _CONFIG_PATH, exc)

    for role, env_key in _ROLE_ENV.items():
        env_value = os.getenv(env_key, "").strip()
        if not env_value:
            continue
        entry = configured.get(role, {"teamsUserIds": [], "emails": []})
        entry["teamsUserIds"] = _append_unique(entry["teamsUserIds"], _split_csv(env_value))
        configured[role] = entry

    for role, env_key in _ROLE_EMAIL_ENV.items():
        env_value = os.getenv(env_key, "").strip()
        if not env_value:
            continue
        entry = configured.get(role, {"teamsUserIds": [], "emails": []})
        entry["emails"] = _append_unique(entry["emails"], _split_csv(env_value))
        configured[role] = entry

    return configured


def get_routing_context(
    alert_type: str,
    direct_target: str = "",
    direct_target_email: str = "",
) -> dict:
    """Resuelve roles, destinatarios Teams, emails y trazabilidad de una alerta."""
    recipients: list[str] = []
    recipient_emails: list[str] = []

    if direct_target:
        recipients.append(direct_target)
    if direct_target_email:
        recipient_emails.append(direct_target_email)

    normalized = alert_type.upper().replace(" ", "_")
    roles = ALERT_ROLE_MAP.get(normalized, ["RESPONSABLE"])
    role_config = _load_role_config()
    role_targets: dict[str, list[str]] = {}
    role_emails: dict[str, list[str]] = {}

    configured = 0
    for role in roles:
        entry = role_config.get(role, {"teamsUserIds": [], "emails": []})
        team_targets = entry.get("teamsUserIds", [])
        email_targets = entry.get("emails", [])

        if team_targets:
            role_targets[role] = team_targets
        if email_targets:
            role_emails[role] = email_targets

        for user_id in team_targets:
            if user_id not in recipients:
                recipients.append(user_id)
                configured += 1

        for email in email_targets:
            if email not in recipient_emails:
                recipient_emails.append(email)

    if configured == 0 and not direct_target and not direct_target_email:
        logger.warning(
            "Alerta '%s': ningun destinatario configurado. "
            "Completa orchestrator/config/alert_roles.json o define ALERT_ROLE_*.",
            alert_type,
        )

    return {
        "alert_type_normalized": normalized,
        "roles": roles,
        "role_targets": role_targets,
        "role_emails": role_emails,
        "recipients": recipients,
        "recipient_emails": recipient_emails,
        "direct_target": direct_target,
        "direct_target_email": direct_target_email,
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
