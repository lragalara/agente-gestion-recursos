"""
Cliente de notificaciones via Power Automate.

Responsabilidad unica: enviar notificaciones a PA tras eventos del orquestador.
Las operaciones sobre BC (create, release, post) las realiza bc_client.py via OData.
Este cliente no interactua con BC en ningun momento.

Dos tipos de notificacion:
  notify_operation -> post-operacion (Delivery/Return/Transfer completado)
                     PA envia: mensaje al canal Teams + email al empleado
  notify_alert     -> alerta proactiva de BC Job Queue
                     PA envia: email al responsable correcto segun el routing

Configuracion:
  PA_NOTIFY_FLOW_URL_OPERATIONS -> flow de operaciones
  PA_NOTIFY_FLOW_URL_ALERTS     -> flow de alertas
  PA_NOTIFY_FLOW_URL            -> fallback legado si aun no se han separado
  PA_TEST_EMAIL_OVERRIDE        -> si existe, redirige todos los correos a ese email

Modos:
  mock -> registra en logs, sin llamar a PA
  live -> hace POST al flow correspondiente con el contexto
"""

import logging
import os
from datetime import datetime, timezone

import httpx

logger = logging.getLogger(__name__)

_OP_EMOJI = {"Delivery": "📦", "Return": "↩️", "Transfer": "🔄"}
_OP_LABEL = {"Delivery": "Entrega", "Return": "Devolucion", "Transfer": "Transferencia"}


class PAClient:
    """Cliente de notificaciones para Power Automate."""

    def __init__(self) -> None:
        self._mode = os.getenv("BC_MODE", "mock").lower()
        legacy_url = os.getenv("PA_NOTIFY_FLOW_URL", "")
        self._operations_url = os.getenv("PA_NOTIFY_FLOW_URL_OPERATIONS", "") or legacy_url
        self._alerts_url = os.getenv("PA_NOTIFY_FLOW_URL_ALERTS", "") or legacy_url
        self._test_email_override = os.getenv("PA_TEST_EMAIL_OVERRIDE", "").strip()

        if self._mode == "live":
            if not self._operations_url:
                logger.info("PA flow de operaciones no configurado. Notificaciones de operaciones omitidas.")
            if not self._alerts_url:
                logger.info("PA flow de alertas no configurado. Notificaciones de alertas omitidas.")
            if self._test_email_override:
                logger.info("PA_TEST_EMAIL_OVERRIDE activo. Todos los correos se redirigiran a %s", self._test_email_override)

    async def notify_operation(
        self,
        operation_type: str,
        document_no: str,
        employee_no: str,
        employee_email: str,
        resource_nos: list[str],
        company_id: str,
        triggered_by: str = "",
    ) -> None:
        """Notifica a PA que se ha contabilizado un documento de asignacion en BC."""
        resources_str = ", ".join(r for r in resource_nos if r) or "-"
        emoji = _OP_EMOJI.get(operation_type, "📋")
        label = _OP_LABEL.get(operation_type, operation_type)
        timestamp = datetime.now(timezone.utc).isoformat()

        payload = {
            "notificationType": "operation",
            "operationType": operation_type,
            "operationLabel": label,
            "documentNo": document_no,
            "employeeNo": employee_no,
            "employeeEmail": self._test_email_override or employee_email,
            "originalEmployeeEmail": employee_email,
            "resourceNos": resources_str,
            "companyId": company_id,
            "triggeredBy": triggered_by,
            "timestamp": timestamp,
            "teamsMessage": (
                f"{emoji} **{label}** procesada\n"
                f"Documento: `{document_no}`\n"
                f"Empleado: {employee_no}\n"
                f"Recursos: {resources_str}\n"
                f"Empresa: {company_id}"
                + (f"\nGestionado por: {triggered_by}" if triggered_by else "")
            ),
            "emailSubjectEmployee": f"Albaran de {label.lower()} - {document_no}",
            "emailSubjectTeam": f"[BC Recursos] {label} {document_no} - {company_id}",
        }

        if self._mode == "mock":
            logger.info(
                "[MOCK PA] notify_operation | op=%s doc=%s employee=%s (%s) resources=%s",
                operation_type,
                document_no,
                employee_no,
                employee_email,
                resources_str,
            )
            return

        await self._call_flow(
            url=self._operations_url,
            payload=payload,
            context=f"operation/{document_no}",
        )

    async def notify_alert(
        self,
        alert_type: str,
        resource_no: str,
        criticality: str,
        details: str,
        company_id: str,
        teams_message: str,
        recipients: list[str] | None = None,
        recipient_emails: list[str] | None = None,
        roles: list[str] | None = None,
        role_targets: dict[str, list[str]] | None = None,
        role_emails: dict[str, list[str]] | None = None,
    ) -> None:
        """
        Notifica a PA de una alerta proactiva de BC Job Queue.

        PA dispara email al responsable segun el tipo de alerta.
        El mensaje Teams ya lo envia el bot directamente.
        """
        from alert_router import ALERT_LABEL

        label = ALERT_LABEL.get(alert_type.upper(), alert_type)
        timestamp = datetime.now(timezone.utc).isoformat()
        recipients = recipients or []
        recipient_emails = recipient_emails or []
        roles = roles or []
        role_targets = role_targets or {}
        role_emails = role_emails or {}
        effective_recipient_emails = (
            [self._test_email_override] if self._test_email_override else recipient_emails
        )

        payload = {
            "notificationType": "alert",
            "alertType": alert_type,
            "alertLabel": label,
            "resourceNo": resource_no,
            "criticality": criticality,
            "details": details,
            "companyId": company_id,
            "timestamp": timestamp,
            "teamsMessage": teams_message,
            "recipients": recipients,
            "recipientEmails": effective_recipient_emails,
            "originalRecipientEmails": recipient_emails,
            "roles": roles,
            "roleTargets": role_targets,
            "roleEmails": role_emails,
            "emailSubject": f"[BC Alertas] {label} - {resource_no} ({company_id})",
            "emailBody": (
                f"Se ha generado una alerta en Business Central.\n\n"
                f"Tipo: {label}\n"
                f"Recurso: {resource_no}\n"
                f"Criticidad: {criticality}\n"
                f"Empresa: {company_id}\n"
                f"Fecha: {timestamp}\n"
                f"Roles: {', '.join(roles) or '-'}\n"
                f"Destinatarios Teams: {', '.join(recipients) or '-'}\n\n"
                f"Destinatarios email: {', '.join(effective_recipient_emails) or '-'}\n\n"
                f"Detalle:\n{details}"
            ),
        }

        if self._mode == "mock":
            logger.info(
                "[MOCK PA] notify_alert | type=%s resource=%s criticality=%s recipients=%s",
                alert_type,
                resource_no,
                criticality,
                ",".join(recipients) or "-",
            )
            return

        await self._call_flow(
            url=self._alerts_url,
            payload=payload,
            context=f"alert/{alert_type}/{resource_no}",
        )

    async def _call_flow(self, url: str, payload: dict, context: str = "") -> None:
        """Llama al HTTP trigger del flow de PA sin bloquear la operacion principal."""
        if not url:
            logger.debug("Flow PA no configurado, notificacion omitida (%s).", context)
            return

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(url, json=payload)
                if response.status_code in (200, 202):
                    logger.info("Notificacion PA enviada: %s", context)
                else:
                    logger.warning("PA respondio %s para %s", response.status_code, context)
        except httpx.TimeoutException:
            logger.warning("Timeout enviando notificacion PA (%s)", context)
        except httpx.HTTPError as exc:
            logger.warning("Error enviando notificacion PA (%s): %s", context, exc)
