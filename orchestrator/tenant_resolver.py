"""
Resuelve el company_id de Business Central para cada usuario.

Modos:
  fixed  — devuelve siempre BC_COMPANY_ID (desarrollo / empresa única)
  select — devuelve el company_id guardado en sesión, o None si el usuario no ha elegido
  auto   — consulta Microsoft Graph y detecta empresa por membresía en grupos "BC-*"
"""

import logging
import os
from typing import Union

import httpx

logger = logging.getLogger(__name__)

GRAPH_MEMBER_OF_URL = "https://graph.microsoft.com/v1.0/me/memberOf"


class TenantResolver:
    """Resuelve la empresa BC activa para un usuario dado."""

    def __init__(self) -> None:
        self._mode: str = os.getenv("BC_TENANT_MODE", "fixed").lower()
        self._default_company: str = os.getenv("BC_COMPANY_ID", "CRONUS")
        # Sesiones: user_id → company_id
        self._sessions: dict[str, str] = {}

    @property
    def mode(self) -> str:
        return self._mode

    def set_company(self, user_id: str, company_id: str) -> None:
        """Guarda la empresa seleccionada para un usuario (modo select)."""
        self._sessions[user_id] = company_id
        logger.info("Usuario '%s' seleccionó empresa '%s'", user_id, company_id)

    def clear_session(self, user_id: str) -> None:
        """Limpia la sesión de empresa de un usuario."""
        self._sessions.pop(user_id, None)

    async def resolve(
        self,
        user_id: str,
        user_token: str | None = None,
    ) -> Union[str, None, list[str]]:
        """
        Devuelve el company_id para el usuario.

        Returns:
            str   — company_id resuelto
            None  — modo select y el usuario aún no ha elegido empresa
            list  — modo auto con múltiples empresas posibles (el agente preguntará)
        """
        if self._mode == "fixed":
            return self._default_company

        if self._mode == "select":
            return self._sessions.get(user_id)

        if self._mode == "auto":
            return await self._resolve_auto(user_id, user_token)

        logger.warning("BC_TENANT_MODE desconocido: '%s'. Usando fixed.", self._mode)
        return self._default_company

    async def _resolve_auto(
        self,
        user_id: str,
        user_token: str | None,
    ) -> Union[str, None, list[str]]:
        """
        Autodetecta la empresa consultando los grupos del usuario en Microsoft Graph.
        Busca grupos cuyo displayName empiece por 'BC-'.
        Si falla o no hay token, hace fallback a modo select.
        """
        # Si ya hay empresa en sesión, devolverla directamente
        if user_id in self._sessions:
            return self._sessions[user_id]

        if not user_token:
            logger.warning(
                "BC_TENANT_MODE=auto pero no hay user_token para '%s'. Fallback a select.", user_id
            )
            return self._sessions.get(user_id)

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    GRAPH_MEMBER_OF_URL,
                    headers={"Authorization": f"Bearer {user_token}"},
                )
                response.raise_for_status()
                data = response.json()

        except httpx.HTTPError as exc:
            logger.error("Error consultando Graph API para '%s': %s", user_id, exc)
            return self._sessions.get(user_id)

        # Filtrar grupos BC-*
        bc_groups = []
        for group in data.get("value", []):
            display_name: str = group.get("displayName", "")
            if display_name.upper().startswith("BC-"):
                # Extrae company_id: "BC-GRUPO-BERTOLIN" → "GRUPO-BERTOLIN"
                company_id = display_name[3:]
                bc_groups.append(company_id)

        if not bc_groups:
            logger.info("Usuario '%s' no tiene grupos BC-*. Fallback a select.", user_id)
            return self._sessions.get(user_id)

        if len(bc_groups) == 1:
            self._sessions[user_id] = bc_groups[0]
            return bc_groups[0]

        # Múltiples empresas → el agente preguntará al usuario
        return bc_groups
