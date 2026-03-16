"""
Adaptador de Bot Framework para Azure Bot Service.

Implementación correcta del pipeline de Bot Framework:
  - process_activity usa TurnContext (respuestas reactivas)
  - ConversationReference guardada correctamente para mensajes proactivos
  - send_proactive_message usa continue_conversation (Azure Bot Service + Teams)

Modos:
  dev  (BOT_APP_ID vacío) — sin validación de credenciales, proactivos solo en logs
  prod (BOT_APP_ID configurado) — pipeline completo con Azure Bot Service
"""

import logging
import os
from typing import TYPE_CHECKING

from botbuilder.core import (
    BotFrameworkAdapter,
    BotFrameworkAdapterSettings,
    TurnContext,
)
from botbuilder.schema import Activity, ActivityTypes, ConversationReference

if TYPE_CHECKING:
    from agent import Agent

logger = logging.getLogger(__name__)


class BotAdapter:
    """Gestiona la comunicación con Azure Bot Service."""

    def __init__(self) -> None:
        self._bot_app_id = os.getenv("BOT_APP_ID", "")
        bot_app_password = os.getenv("BOT_APP_PASSWORD", "")

        self._dev_mode = not bool(self._bot_app_id)
        if self._dev_mode:
            logger.info(
                "BOT_APP_ID vacío — modo desarrollo: sin validación de credenciales. "
                "Los mensajes proactivos solo se registran en logs."
            )

        settings = BotFrameworkAdapterSettings(
            app_id=self._bot_app_id,
            app_password=bot_app_password,
        )
        self._adapter = BotFrameworkAdapter(settings)

        # ConversationReference por user_id para mensajes proactivos
        # Clave: Teams user_id (Entra ID object ID)
        # Valor: ConversationReference completo del Bot Framework
        self._conv_refs: dict[str, ConversationReference] = {}

    # ─────────────────────────────────────────────────────────────────────────
    # Mensajes reactivos (usuario → bot)
    # ─────────────────────────────────────────────────────────────────────────

    async def process_activity(
        self,
        activity_json: dict,
        auth_header: str,
        agent: "Agent",
    ) -> None:
        """
        Procesa una Activity entrante del Bot Framework usando el pipeline
        oficial de TurnContext.

        A diferencia de construir la respuesta manualmente, aquí:
          1. Bot Framework autentica la request
          2. Crea el TurnContext con el canal correcto (Teams)
          3. El callback envía la respuesta via turn_context.send_activity
          4. La ConversationReference se guarda correctamente para proactivos

        Args:
            activity_json: Cuerpo JSON de la Activity recibida de Teams
            auth_header:   Cabecera Authorization de la request HTTP
            agent:         Instancia del agente para procesar el mensaje
        """
        try:
            activity = Activity().deserialize(activity_json)
        except Exception as exc:
            logger.error("Error deserializando Activity: %s", exc)
            return

        async def on_turn(turn_context: TurnContext) -> None:
            # Solo procesar mensajes de texto
            if turn_context.activity.type != ActivityTypes.message:
                logger.debug("Activity ignorada de tipo: %s", turn_context.activity.type)
                return

            user_id = (
                turn_context.activity.from_property.id
                if turn_context.activity.from_property
                else "unknown"
            )
            text = (turn_context.activity.text or "").strip()
            user_token = self._extract_user_token(turn_context.activity)

            logger.info("Mensaje de '%s': %.100s", user_id, text)

            # Guardar ConversationReference completa para mensajes proactivos
            # TurnContext.get_conversation_reference devuelve el objeto correcto
            # que continue_conversation necesita
            conv_ref = TurnContext.get_conversation_reference(turn_context.activity)
            self._conv_refs[user_id] = conv_ref
            agent.set_conversation_reference(user_id, conv_ref)

            # Procesar mensaje con el agente
            response_text = await agent.process_message(text, user_id, user_token)

            # Enviar respuesta via Bot Framework (gestiona el canal Teams)
            await turn_context.send_activity(response_text)

        try:
            await self._adapter.process_activity(activity, auth_header, on_turn)
        except Exception as exc:
            logger.error("Error en el pipeline de Bot Framework: %s", exc)
            raise

    # ─────────────────────────────────────────────────────────────────────────
    # Mensajes proactivos (bot → usuario, sin que el usuario haya escrito)
    # ─────────────────────────────────────────────────────────────────────────

    async def send_proactive_message(
        self,
        user_id: str,
        message: str,
        agent: "Agent",
    ) -> bool:
        """
        Envía un mensaje proactivo a un usuario de Teams.

        Requiere que el usuario haya iniciado conversación con el bot al menos
        una vez (para tener la ConversationReference guardada).

        En modo desarrollo (BOT_APP_ID vacío) solo registra en logs.

        Args:
            user_id: Teams user_id (Entra ID object ID)
            message: Texto del mensaje (admite Markdown de Teams)
            agent:   No usado, mantenido por compatibilidad

        Returns:
            True si se envió (o simuló en dev), False si no hay referencia guardada.
        """
        conv_ref = self._conv_refs.get(user_id)

        if not conv_ref:
            logger.warning(
                "No hay ConversationReference para '%s'. "
                "El usuario debe iniciar conversación con el bot primero.",
                user_id,
            )
            return False

        if self._dev_mode:
            logger.info(
                "[DEV] Mensaje proactivo para '%s' (simulado): %.200s",
                user_id,
                message,
            )
            return True

        # Producción: usa continue_conversation para reabrir el canal Teams
        async def callback(turn_context: TurnContext) -> None:
            await turn_context.send_activity(message)

        try:
            await self._adapter.continue_conversation(
                conv_ref,
                callback,
                self._bot_app_id,
            )
            logger.info("Mensaje proactivo enviado a '%s'", user_id)
            return True
        except Exception as exc:
            logger.error("Error enviando mensaje proactivo a '%s': %s", user_id, exc)
            return False

    # ─────────────────────────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────────────────────────

    def get_conversation_reference(self, user_id: str) -> ConversationReference | None:
        """Devuelve la ConversationReference guardada para un usuario."""
        return self._conv_refs.get(user_id)

    def _extract_user_token(self, activity: Activity) -> str | None:
        """Extrae el token SSO del Activity si está disponible (modo auto de tenant)."""
        if activity.channel_data and isinstance(activity.channel_data, dict):
            return activity.channel_data.get("userToken")
        return None
