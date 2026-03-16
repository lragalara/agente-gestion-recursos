"""
Orchestrator - API principal del agente de gestion de recursos BC.
"""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from agent import Agent
from alert_router import _ROLE_ENV, format_teams_message, get_routing_context
from bc_client import BCClient
from bot_adapter import BotAdapter
from pa_client import PAClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

_agent: Agent | None = None
_bot_adapter: BotAdapter | None = None
_pa_client: PAClient | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Inicializa el agente, el adaptador del bot y el cliente PA al arrancar."""
    global _agent, _bot_adapter, _pa_client

    bc_mode = os.getenv("BC_MODE", "mock")
    tenant_mode = os.getenv("BC_TENANT_MODE", "fixed")
    openai_key = os.getenv("AZURE_OPENAI_KEY", "")
    bot_app_id = os.getenv("BOT_APP_ID", "")
    pa_operations_url = os.getenv("PA_NOTIFY_FLOW_URL_OPERATIONS", "") or os.getenv("PA_NOTIFY_FLOW_URL", "")
    pa_alerts_url = os.getenv("PA_NOTIFY_FLOW_URL_ALERTS", "") or os.getenv("PA_NOTIFY_FLOW_URL", "")

    logger.info("=" * 60)
    logger.info("Agente de Gestion de Recursos BC")
    logger.info("  BC_MODE:         %s", bc_mode)
    logger.info("  BC_TENANT_MODE:  %s", tenant_mode)
    logger.info("  OpenAI:          %s", "configurado" if openai_key else "NO CONFIGURADO (modo demo)")
    logger.info("  Bot Framework:   %s", "configurado" if bot_app_id else "modo desarrollo")
    logger.info(
        "  PA Operations:   %s",
        "configurado" if pa_operations_url else "no configurado (opcional)",
    )
    logger.info(
        "  PA Alerts:       %s",
        "configurado" if pa_alerts_url else "no configurado (opcional)",
    )
    logger.info("=" * 60)

    _agent = Agent()
    _bot_adapter = BotAdapter()
    _pa_client = PAClient()

    yield

    logger.info("Orchestrator detenido.")


app = FastAPI(
    title="Agente Gestion Recursos BC",
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


def get_pa_client() -> PAClient:
    if _pa_client is None:
        raise RuntimeError("PAClient no inicializado")
    return _pa_client


class ChatRequest(BaseModel):
    message: str
    user_id: str = "test_user"


class ChatResponse(BaseModel):
    response: str
    company_id: str | None = None


class AlertRequest(BaseModel):
    """
    Payload enviado por BC Job Queue al endpoint /webhook/alerts.
    """

    alert_type: str
    resource_no: str
    criticality: str
    details: str
    target_user_id: str = ""
    target_user_email: str = ""
    company_id: str = ""


@app.post("/api/messages")
async def api_messages(request: Request) -> JSONResponse:
    """Endpoint principal del Bot Framework."""
    try:
        body = await request.json()
        auth_header = request.headers.get("Authorization", "")
        await get_adapter().process_activity(body, auth_header, get_agent())
        return JSONResponse(content={}, status_code=200)
    except Exception as exc:
        logger.error("Error en /api/messages: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/webhook/alerts")
async def webhook_alerts(alert: AlertRequest) -> dict:
    """
    Recibe alertas de BC Job Queue y las distribuye a los destinatarios correctos.
    """
    logger.info(
        "Alerta recibida: type=%s resource=%s criticality=%s",
        alert.alert_type,
        alert.resource_no,
        alert.criticality,
    )

    routing = get_routing_context(
        alert.alert_type,
        alert.target_user_id,
        alert.target_user_email,
    )
    recipients = routing["recipients"]

    if not recipients:
        logger.warning(
            "Alerta '%s' sin destinatarios. Configura alert_roles.json o ALERT_ROLE_* "
            "o asegúrate de que BC envíe target_user_id.",
            alert.alert_type,
        )
        return {
            "status": "no_recipients",
            "alert_type": alert.alert_type,
            "resource_no": alert.resource_no,
        }

    message = format_teams_message(
        alert_type=alert.alert_type,
        resource_no=alert.resource_no,
        criticality=alert.criticality,
        details=alert.details,
    )

    adapter = get_adapter()
    results: dict[str, str] = {}
    sent_count = 0

    for user_id in recipients:
        ok = await adapter.send_proactive_message(user_id, message, get_agent())
        results[user_id] = "sent" if ok else "not_delivered"
        if ok:
            sent_count += 1

    await get_pa_client().notify_alert(
        alert_type=alert.alert_type,
        resource_no=alert.resource_no,
        criticality=alert.criticality,
        details=alert.details,
        company_id=alert.company_id,
        teams_message=message,
        recipients=recipients,
        recipient_emails=routing["recipient_emails"],
        roles=routing["roles"],
        role_targets=routing["role_targets"],
        role_emails=routing["role_emails"],
    )

    return {
        "status": "processed",
        "alert_type": alert.alert_type,
        "resource_no": alert.resource_no,
        "recipients_total": len(recipients),
        "teams_sent": sent_count,
        "results": results,
    }


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    """Endpoint de desarrollo para probar el agente sin Bot Framework."""
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
    pa_operations_url = os.getenv("PA_NOTIFY_FLOW_URL_OPERATIONS", "") or os.getenv("PA_NOTIFY_FLOW_URL", "")
    pa_alerts_url = os.getenv("PA_NOTIFY_FLOW_URL_ALERTS", "") or os.getenv("PA_NOTIFY_FLOW_URL", "")

    alert_roles_configured = {
        role: bool(os.getenv(env_key, ""))
        for role, env_key in _ROLE_ENV.items()
    }

    return {
        "status": "ok",
        "bc_mode": bc_mode,
        "tenant_mode": tenant_mode,
        "openai_configured": bool(openai_key),
        "bot_configured": bool(bot_app_id),
        "pa_operations_configured": bool(pa_operations_url),
        "pa_alerts_configured": bool(pa_alerts_url),
        "alert_roles": alert_roles_configured,
    }


@app.get("/companies")
async def get_companies() -> dict:
    """Proxy a bc_client.get_companies()."""
    bc_company_id = os.getenv("BC_COMPANY_ID", "CRONUS")
    try:
        bc = BCClient(bc_company_id)
        companies = await bc.get_companies()
        return {"companies": companies}
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=f"Error conectando con BC: {exc}")
