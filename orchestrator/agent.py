"""
Núcleo del agente conversacional de gestión de recursos.

Usa LangChain con AzureChatOpenAI y function calling.
Mantiene historial de conversación por usuario (máx 20 mensajes).
"""

import logging
import os
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnableConfig

from bc_client import BCClient
from prompts.system_prompt import SYSTEM_PROMPT
from tenant_resolver import TenantResolver
from tools import get_all_tools

logger = logging.getLogger(__name__)

MAX_HISTORY = 20
CONFIRMATION_WORDS = {"sí", "si", "yes", "confirmar", "confirmo", "ok", "adelante", "procede", "proceder"}
DEMO_RESPONSE = (
    "⚠️ Modo demo: Azure OpenAI no está configurado (AZURE_OPENAI_KEY vacía).\n"
    "Configura las variables de entorno en el fichero .env para activar el agente real."
)


class Session:
    """Sesión de conversación de un usuario."""

    def __init__(self) -> None:
        self.history: list[BaseMessage] = []
        self.company_id: str | None = None
        self.conversation_reference: dict | None = None
        self.pending_action: dict | None = None  # Acción esperando confirmación

    def add_human(self, text: str) -> None:
        self.history.append(HumanMessage(content=text))
        self._trim()

    def add_ai(self, text: str) -> None:
        self.history.append(AIMessage(content=text))
        self._trim()

    def _trim(self) -> None:
        if len(self.history) > MAX_HISTORY:
            self.history = self.history[-MAX_HISTORY:]


class Agent:
    """Agente conversacional de gestión de recursos BC."""

    def __init__(self) -> None:
        self._openai_key = os.getenv("AZURE_OPENAI_KEY", "")
        self._openai_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "")
        self._deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini")
        self._api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-01")
        self._bc_mode = os.getenv("BC_MODE", "mock")

        self._sessions: dict[str, Session] = {}
        self._tenant_resolver = TenantResolver()
        self._llm: Any | None = None

        self._init_llm()

    def _init_llm(self) -> None:
        """Inicializa AzureChatOpenAI. Si la key está vacía, registra warning."""
        if not self._openai_key:
            logger.warning(
                "AZURE_OPENAI_KEY no configurada. El agente responderá en modo demo."
            )
            return

        try:
            from langchain_openai import AzureChatOpenAI

            self._llm = AzureChatOpenAI(
                azure_endpoint=self._openai_endpoint,
                api_key=self._openai_key,
                azure_deployment=self._deployment,
                api_version=self._api_version,
                temperature=0,
            )
            logger.info(
                "AzureChatOpenAI inicializado: endpoint=%s, deployment=%s",
                self._openai_endpoint,
                self._deployment,
            )
        except Exception as exc:
            logger.error("Error inicializando AzureChatOpenAI: %s", exc)
            self._llm = None

    def _get_session(self, user_id: str) -> Session:
        if user_id not in self._sessions:
            self._sessions[user_id] = Session()
        return self._sessions[user_id]

    def set_conversation_reference(self, user_id: str, ref: dict) -> None:
        """Guarda el conversation_reference para mensajes proactivos."""
        self._get_session(user_id).conversation_reference = ref

    def get_conversation_reference(self, user_id: str) -> dict | None:
        return self._get_session(user_id).conversation_reference

    async def _resolve_company(
        self,
        session: Session,
        user_id: str,
        user_token: str | None,
        bc_tenant_mode: str,
    ) -> tuple[str | None, str | None]:
        """
        Resuelve el company_id. Devuelve (company_id, pregunta_al_usuario).
        Si hay pregunta, el agente debe presentarla en lugar de continuar.
        """
        if session.company_id:
            return session.company_id, None

        result = await self._tenant_resolver.resolve(user_id, user_token)

        # Modo fixed → string directo
        if isinstance(result, str):
            session.company_id = result
            return result, None

        # Modo select / auto sin empresa → listar opciones
        if result is None:
            try:
                temp_bc = BCClient("")
                companies = await temp_bc.get_companies()
                names = [c.get("displayName", c.get("id", "")) for c in companies]
                question = (
                    "¿A qué empresa de Business Central quieres acceder?\n"
                    + "\n".join(f"{i+1}. {n}" for i, n in enumerate(names))
                    + "\n\nResponde con el número o el nombre de la empresa."
                )
            except Exception:
                question = (
                    "¿Cuál es el identificador de la empresa BC que quieres usar? (ej: CRONUS)"
                )
            return None, question

        # Auto → múltiples empresas detectadas
        if isinstance(result, list):
            question = (
                "Se han detectado varias empresas en tu cuenta:\n"
                + "\n".join(f"{i+1}. {c}" for i, c in enumerate(result))
                + "\n\nResponde con el número o el nombre de la empresa."
            )
            return None, question

        return None, None

    def _handle_company_selection(
        self, session: Session, user_id: str, text: str
    ) -> bool:
        """
        Intenta parsear el texto del usuario como selección de empresa.
        Devuelve True si se procesó como selección.
        """
        # Solo actuar si aún no hay empresa en sesión
        if session.company_id:
            return False

        text = text.strip()
        # Intentar por número
        if text.isdigit():
            # Guardar como company_id (el TenantResolver lo almacenará)
            # No podemos saber los nombres aquí, así que se trata como nombre directo
            pass

        # Guardar como company_id (puede ser nombre o número; el usuario lo sabe)
        self._tenant_resolver.set_company(user_id, text.upper())
        session.company_id = text.upper()
        return True

    async def process_message(
        self,
        text: str,
        user_id: str,
        user_token: str | None = None,
    ) -> str:
        """
        Procesa un mensaje del usuario y devuelve la respuesta del agente.

        Args:
            text:       Texto del mensaje del usuario
            user_id:    Identificador único del usuario
            user_token: Token SSO del usuario (para modo auto)

        Returns:
            Respuesta en texto del agente
        """
        # Modo demo si no hay OpenAI
        if not self._llm:
            return DEMO_RESPONSE

        session = self._get_session(user_id)
        bc_tenant_mode = self._tenant_resolver.mode

        # Resolver empresa
        company_id, question = await self._resolve_company(
            session, user_id, user_token, bc_tenant_mode
        )

        if question and not company_id:
            # Intentar ver si el texto es una selección de empresa
            if self._handle_company_selection(session, user_id, text):
                company_id = session.company_id
            else:
                session.add_human(text)
                session.add_ai(question)
                return question

        if not company_id:
            company_id = session.company_id or os.getenv("BC_COMPANY_ID", "CRONUS")

        # Instanciar BCClient para esta empresa
        bc = BCClient(company_id)

        # Obtener tools
        tools = get_all_tools(bc)

        # Construir el agente con LangChain
        try:
            from langchain.agents import AgentExecutor, create_openai_functions_agent

            prompt = ChatPromptTemplate.from_messages([
                SystemMessage(content=SYSTEM_PROMPT),
                MessagesPlaceholder(variable_name="chat_history"),
                ("human", "{input}"),
                MessagesPlaceholder(variable_name="agent_scratchpad"),
            ])

            agent = create_openai_functions_agent(
                llm=self._llm,
                tools=tools,
                prompt=prompt,
            )

            executor = AgentExecutor(
                agent=agent,
                tools=tools,
                verbose=True,
                max_iterations=10,
                handle_parsing_errors=True,
            )

            response = await executor.ainvoke({
                "input": text,
                "chat_history": session.history,
            })

            answer: str = response.get("output", "No pude generar una respuesta.")

        except Exception as exc:
            logger.error("Error ejecutando el agente para user '%s': %s", user_id, exc)
            answer = f"Ocurrió un error procesando tu solicitud: {exc}"

        # Actualizar historial
        session.add_human(text)
        session.add_ai(answer)

        return answer
