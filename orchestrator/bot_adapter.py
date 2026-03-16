"""
Adaptador de Bot Framework para Azure Bot Service.

Integra botbuilder-core con el agente de gestión de recursos.
Si BOT_APP_ID está vacío, opera en modo desarrollo sin validación de credenciales.
"""

import logging
import os
from typing import TYPE_CHECKING, Callable

from botbuilder.core import (
    BotFrameworkAdapter,
    BotFrameworkAdapterSettings,
    TurnContext,
)
from botbuilder.schema import Activity, ActivityTypes

if TYPE_CHECKING:
    from agent import Agent

logger = logging.getLogger(__name__)


class BotAdapter:
    """Gestiona la comunicación con Azure Bot Service."""

    def __init__(self) -> None:
        bot_app_id = os.getenv("BOT_APP_ID", "")
        bot_app_password = os.getenv("BOT_APP_PASSWORD", "")

        self._dev_mode = not bool(bot_app_id)
        if self._dev_mode:
            logger.info(
                "BOT_APP_ID vacío — modo desarrollo: sin validación de credenciales del bot."
            )

        settings = BotFrameworkAdapterSettings(
            app_id=bot_app_id,
            app_password=bot_app_password,
        )
        self._adapter = BotFrameworkAdapter(settings)

        # conversation_reference por user_id para mensajes proactivos
        self._conv_refs: dict[str, dict] = {}

    def _extract_user_token(self, activity: Activity) -> str | None:
        """Extrae el token SSO del Activity si está disponible."""
        if activity.channel_data and isinstance(activity.channel_data, dict):
            return activity.channel_data.get("userToken")
        return None

    def _save_conversation_reference(self, turn_context: TurnContext) -> None:
        """Guarda la referencia de conversación para mensajes proactivos."""
        user_id = turn_context.activity.from_property.id if turn_context.activity.from_property else ""
        if user_id:
            ref = TurnContext.get_conversation_reference(turn_context.activity)
            self._conv_refs[user_id] = ref.serialize() if hasattr(ref, "serialize") else {}

    async def process_activity(
        self,
        activity_json: dict,
        auth_header: str,
        agent: "Agent",
    ) -> Activity | None:
        """
        Procesa una Activity entrante del Bot Framework.

        Args:
            activity_json: Cuerpo JSON del Activity
            auth_header:   Cabecera Authorization de la request
            agent:         Instancia del agente

        Returns:
            Activity de respuesta, o None si no hay respuesta que enviar.
        """
        try:
            activity = Activity().deserialize(activity_json)
        except Exception as exc:
            logger.error("Error deserializando Activity: %s", exc)
            return None

        if activity.type != ActivityTypes.message:
            logger.debug("Activity ignorada de tipo: %s", activity.type)
            return None

        text = (activity.text or "").strip()
        user_id = (
            activity.from_property.id
            if activity.from_property
            else "unknown"
        )
        user_token = self._extract_user_token(activity)

        logger.info("Mensaje de '%s': %s", user_id, text[:100])

        response_text = await agent.process_message(text, user_id, user_token)

        # Guardar conversation_reference para futuros mensajes proactivos
        agent.set_conversation_reference(
            user_id,
            {"activity": activity_json, "user_id": user_id},
        )
        self._conv_refs[user_id] = {"activity": activity_json, "user_id": user_id}

        # Construir respuesta
        reply = Activity(
            type=ActivityTypes.message,
            text=response_text,
            conversation=activity.conversation,
            from_property=activity.recipient,
            recipient=activity.from_property,
            reply_to_id=activity.id,
        )
        return reply

    def get_conversation_reference(self, user_id: str) -> dict | None:
        """Devuelve la referencia de conversación guardada para un usuario."""
        return self._conv_refs.get(user_id)

    async def send_proactive_message(
        self,
        user_id: str,
        message: str,
        agent: "Agent",
    ) -> bool:
        """
        Envía un mensaje proactivo a un usuario.

        Returns:
            True si se envió correctamente, False si no hay referencia guardada.
        """
        ref = self._conv_refs.get(user_id)
        if not ref:
            logger.warning(
                "No hay conversation_reference para '%s'. El usuario no ha iniciado conversación.",
                user_id,
            )
            return False

        # En modo desarrollo, simplemente logueamos el mensaje
        logger.info(
            "Mensaje proactivo para '%s': %s",
            user_id,
            message[:200],
        )
        return True
