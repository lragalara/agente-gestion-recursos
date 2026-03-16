"""Tools de asignaciones: entregas, devoluciones, transferencias e historial."""

import json
import logging
from typing import TYPE_CHECKING, Literal, Optional

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from bc_client import BCClient

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Schemas
# ─────────────────────────────────────────────────────────────────────────────

class GetEmployeeAssetsInput(BaseModel):
    employee_no: str = Field(..., description="Número del empleado (ej: EMP001)")


class DeliveryLine(BaseModel):
    resource_no: Optional[str] = Field(None, description="Número del recurso (activo fijo)")
    item_no: Optional[str] = Field(None, description="Número de artículo (licencia)")
    quantity: float = Field(1, description="Cantidad")


class CreateDeliveryInput(BaseModel):
    employee_no: str = Field(..., description="Número del empleado que recibe el recurso")
    lines: list[DeliveryLine] = Field(..., description="Líneas del documento de entrega")


class ReturnLine(BaseModel):
    resource_no: str = Field(..., description="Número del recurso a devolver")
    condition: Literal["Good", "Damaged", "Needs Review"] = Field(
        "Good", description="Estado del recurso en la devolución"
    )


class CreateReturnInput(BaseModel):
    employee_no: str = Field(..., description="Número del empleado que devuelve el recurso")
    lines: list[ReturnLine] = Field(..., description="Líneas del documento de devolución")


class TransferLine(BaseModel):
    resource_no: str = Field(..., description="Número del recurso a transferir")


class CreateTransferInput(BaseModel):
    from_employee_no: str = Field(..., description="Número del empleado que cede el recurso")
    to_employee_no: str = Field(..., description="Número del empleado que recibe el recurso")
    lines: list[TransferLine] = Field(..., description="Recursos a transferir")


class GetAssignmentHistoryInput(BaseModel):
    resource_no: Optional[str] = Field(None, description="Número del recurso")
    employee_no: Optional[str] = Field(None, description="Número del empleado")


# ─────────────────────────────────────────────────────────────────────────────
# Factories
# ─────────────────────────────────────────────────────────────────────────────

def make_get_employee_assets(bc: "BCClient") -> StructuredTool:
    async def _run(employee_no: str) -> str:
        try:
            assets = await bc.get_employee_assets(employee_no)
            if not assets:
                return f"El empleado '{employee_no}' no tiene activos asignados actualmente."
            return json.dumps(assets, ensure_ascii=False, indent=2)
        except RuntimeError as exc:
            return f"Error obteniendo activos: {exc}"

    return StructuredTool.from_function(
        coroutine=_run,
        name="get_employee_assets",
        description=(
            "Obtiene los recursos actualmente asignados a un empleado. "
            "Devuelve las entradas activas de asignación."
        ),
        args_schema=GetEmployeeAssetsInput,
    )


def make_create_delivery(bc: "BCClient") -> StructuredTool:
    """
    REQUIERE CONFIRMACIÓN del usuario antes de ejecutar.
    Crea un documento Delivery (asignación de recurso a empleado).
    """

    async def _run(employee_no: str, lines: list[dict]) -> str:
        try:
            # Crear y contabilizar en un solo flujo
            parsed_lines = [
                {
                    "resourceNo": line.get("resource_no", ""),
                    "item_no": line.get("item_no", ""),
                    "quantity": line.get("quantity", 1),
                }
                for line in lines
            ]
            header = await bc.create_assignment_header(
                document_type="Delivery",
                employee_no=employee_no,
                lines=parsed_lines,
            )
            doc_no = header["documentNo"]
            await bc.release_document(doc_no)
            result = await bc.post_document(doc_no)
            return (
                f"Entrega contabilizada correctamente.\n"
                f"Documento: {result['documentNo']}\n"
                f"Estado: {result['status']}"
            )
        except RuntimeError as exc:
            return f"Error creando entrega: {exc}"

    return StructuredTool.from_function(
        coroutine=_run,
        name="create_delivery",
        description=(
            "Crea una entrega (asignación de recurso a empleado). "
            "IMPORTANTE: Esta acción modifica datos. El agente DEBE pedir confirmación "
            "al usuario antes de ejecutarla."
        ),
        args_schema=CreateDeliveryInput,
    )


def make_create_return(bc: "BCClient") -> StructuredTool:
    """
    REQUIERE CONFIRMACIÓN del usuario antes de ejecutar.
    Crea un documento Return (devolución de recurso).
    """

    async def _run(employee_no: str, lines: list[dict]) -> str:
        try:
            parsed_lines = [
                {
                    "resourceNo": line.get("resource_no", ""),
                    "quantity": 1,
                    "condition": line.get("condition", "Good"),
                }
                for line in lines
            ]
            header = await bc.create_assignment_header(
                document_type="Return",
                employee_no=employee_no,
                lines=parsed_lines,
            )
            doc_no = header["documentNo"]
            await bc.release_document(doc_no)
            result = await bc.post_document(doc_no)
            return (
                f"Devolución contabilizada correctamente.\n"
                f"Documento: {result['documentNo']}\n"
                f"Estado: {result['status']}"
            )
        except RuntimeError as exc:
            return f"Error creando devolución: {exc}"

    return StructuredTool.from_function(
        coroutine=_run,
        name="create_return",
        description=(
            "Registra la devolución de un recurso por parte de un empleado. "
            "IMPORTANTE: Esta acción modifica datos. El agente DEBE pedir confirmación "
            "al usuario antes de ejecutarla."
        ),
        args_schema=CreateReturnInput,
    )


def make_create_transfer(bc: "BCClient") -> StructuredTool:
    """
    REQUIERE CONFIRMACIÓN del usuario antes de ejecutar.
    Crea un documento Transfer (transferencia entre empleados).
    """

    async def _run(
        from_employee_no: str,
        to_employee_no: str,
        lines: list[dict],
    ) -> str:
        try:
            parsed_lines = [{"resourceNo": line.get("resource_no", "")} for line in lines]
            header = await bc.create_assignment_header(
                document_type="Transfer",
                employee_no=from_employee_no,
                lines=parsed_lines,
                from_employee_no=from_employee_no,
                to_employee_no=to_employee_no,
            )
            doc_no = header["documentNo"]
            await bc.release_document(doc_no)
            result = await bc.post_document(doc_no)
            return (
                f"Transferencia contabilizada correctamente.\n"
                f"Documento: {result['documentNo']}\n"
                f"Estado: {result['status']}"
            )
        except RuntimeError as exc:
            return f"Error creando transferencia: {exc}"

    return StructuredTool.from_function(
        coroutine=_run,
        name="create_transfer",
        description=(
            "Transfiere un recurso de un empleado a otro. "
            "IMPORTANTE: Esta acción modifica datos. El agente DEBE pedir confirmación "
            "al usuario antes de ejecutarla."
        ),
        args_schema=CreateTransferInput,
    )


def make_get_assignment_history(bc: "BCClient") -> StructuredTool:
    async def _run(
        resource_no: str | None = None,
        employee_no: str | None = None,
    ) -> str:
        if not resource_no and not employee_no:
            return "Debes indicar al menos un número de recurso o de empleado."
        try:
            history = await bc.get_assignment_history(resource_no, employee_no)
            if not history:
                return "No se encontró historial de asignaciones con los filtros indicados."
            return json.dumps(history, ensure_ascii=False, indent=2)
        except RuntimeError as exc:
            return f"Error obteniendo historial: {exc}"

    return StructuredTool.from_function(
        coroutine=_run,
        name="get_assignment_history",
        description=(
            "Obtiene el historial completo de asignaciones de un recurso o empleado. "
            "Al menos uno de los dos parámetros es obligatorio."
        ),
        args_schema=GetAssignmentHistoryInput,
    )
