"""
Orchestrator — API principal del agente de gestión de recursos BC.

Endpoints:
  POST /api/messages        — Bot Framework (Teams)
  POST /webhook/alerts      — Alertas proactivas desde BC Job Queue
  POST /chat                — Desarrollo sin Bot Framework (solo BC_MODE=mock)
  GET  /health              — Estado del sistema
  GET  /companies           — Lista de empresas BC disponibles
"""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from agent import Agent
from bc_client import BCClient
from bot_adapter import BotAdapter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Inicialización
# ─────────────────────────────────────────────────────────────────────────────

_agent: Agent | None = None
_bot_adapter: BotAdapter | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Inicializa el agente y el adaptador del bot al arrancar."""
    global _agent, _bot_adapter

    bc_mode = os.getenv("BC_MODE", "mock")
    tenant_mode = os.getenv("BC_TENANT_MODE", "fixed")
    openai_key = os.getenv("AZURE_OPENAI_KEY", "")
    bot_app_id = os.getenv("BOT_APP_ID", "")

    logger.info("=" * 60)
    logger.info("Agente de Gestión de Recursos BC")
    logger.info("  BC_MODE:         %s", bc_mode)
    logger.info("  BC_TENANT_MODE:  %s", tenant_mode)
    logger.info("  OpenAI:          %s", "configurado" if openai_key else "NO CONFIGURADO (modo demo)")
    logger.info("  Bot Framework:   %s", "configurado" if bot_app_id else "modo desarrollo")
    logger.info("=" * 60)

    if not openai_key:
        logger.warning(
            "AZURE_OPENAI_KEY no configurada. El endpoint /chat devolverá respuestas demo."
        )

    _agent = Agent()
    _bot_adapter = BotAdapter()

    yield

    logger.info("Orchestrator detenido.")


app = FastAPI(
    title="Agente Gestión Recursos BC",
    version="1.0.0",
    lifespan=lifespan,
)


def get_agent() -> Agent:
    if _agent is None:
        raise RuntimeError("Agente no inicializado")
    return _agent


def get_adapter() -> BotAdapter:
    if _bot_adapter is None:
        raise RuntimeError("BotAdapter no inicializado")
    return _bot_adapter


# ─────────────────────────────────────────────────────────────────────────────
# Schemas de request/response
# ─────────────────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    user_id: str = "test_user"


class ChatResponse(BaseModel):
    response: str
    company_id: str | None = None


class AlertRequest(BaseModel):
    alert_type: str
    resource_no: str
    criticality: str
    details: str
    target_user_id: str


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/api/messages")
async def api_messages(request: Request) -> JSONResponse:
    """
    Endpoint principal del Bot Framework.
    Recibe Activities de Teams y las procesa.
    """
    try:
        body = await request.json()
        auth_header = request.headers.get("Authorization", "")

        reply = await get_adapter().process_activity(body, auth_header, get_agent())

        if reply:
            return JSONResponse(content=reply.serialize() if hasattr(reply, "serialize") else reply.dict())
        return JSONResponse(content={}, status_code=200)

    except Exception as exc:
        logger.error("Error en /api/messages: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/webhook/alerts")
async def webhook_alerts(alert: AlertRequest) -> dict:
    """
    Recibe alertas de BC Job Queue y las reenvía proactivamente al usuario.
    """
    logger.info(
        "Alerta recibida: type=%s resource=%s criticality=%s target=%s",
        alert.alert_type,
        alert.resource_no,
        alert.criticality,
        alert.target_user_id,
    )

    adapter = get_adapter()
    ref = adapter.get_conversation_reference(alert.target_user_id)

    icon = "🔴" if alert.criticality.lower() == "critical" else "🟡"
    message = (
        f"{icon} **Alerta BC**: {alert.alert_type}\n"
        f"Recurso: {alert.resource_no}\n"
        f"Criticidad: {alert.criticality}\n"
        f"Detalle: {alert.details}"
    )

    if ref:
        sent = await adapter.send_proactive_message(
            alert.target_user_id, message, get_agent()
        )
        return {"status": "sent" if sent else "failed", "user_id": alert.target_user_id}
    else:
        logger.warning(
            "No hay conversation_reference para '%s'. Alerta no enviada.", alert.target_user_id
        )
        return {
            "status": "not_delivered",
            "reason": "Usuario no ha iniciado conversación con el bot",
            "message_logged": message,
        }


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    """
    Endpoint de desarrollo para probar el agente sin Bot Framework.
    Solo disponible cuando BC_MODE=mock.
    No requiere autenticación.
    """
    bc_mode = os.getenv("BC_MODE", "mock")
    if bc_mode != "mock":
        raise HTTPException(
            status_code=403,
            detail="El endpoint /chat solo está disponible en BC_MODE=mock",
        )

    agent = get_agent()
    response = await agent.process_message(req.message, req.user_id)

    session = agent._get_session(req.user_id)
    return ChatResponse(
        response=response,
        company_id=session.company_id,
    )


@app.get("/health")
async def health() -> dict:
    """Estado completo del sistema."""
    bc_mode = os.getenv("BC_MODE", "mock")
    tenant_mode = os.getenv("BC_TENANT_MODE", "fixed")
    openai_key = os.getenv("AZURE_OPENAI_KEY", "")
    bot_app_id = os.getenv("BOT_APP_ID", "")

    return {
        "status": "ok",
        "bc_mode": bc_mode,
        "tenant_mode": tenant_mode,
        "openai_configured": bool(openai_key),
        "bot_configured": bool(bot_app_id),
    }


@app.get("/companies")
async def get_companies() -> dict:
    """Proxy a bc_client.get_companies(). Verifica conectividad con BC."""
    bc_company_id = os.getenv("BC_COMPANY_ID", "CRONUS")
    try:
        bc = BCClient(bc_company_id)
        companies = await bc.get_companies()
        return {"companies": companies}
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=f"Error conectando con BC: {exc}")
