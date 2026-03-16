"""Tools de mantenimiento de recursos."""

import json
import logging
from typing import TYPE_CHECKING, Literal

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from bc_client import BCClient

logger = logging.getLogger(__name__)


class CreateMaintenanceRecordInput(BaseModel):
    resource_no: str = Field(..., description="Número del recurso")
    category: Literal["Preventive", "Corrective", "Mandatory"] = Field(
        ..., description="Tipo de mantenimiento"
    )
    planned_date: str = Field(..., description="Fecha planificada en formato YYYY-MM-DD")
    description: str = Field(..., description="Descripción del mantenimiento")


class GetMaintenanceScheduleInput(BaseModel):
    resource_no: str = Field(..., description="Número del recurso")


def make_create_maintenance_record(bc: "BCClient") -> StructuredTool:
    async def _run(
        resource_no: str,
        category: str,
        planned_date: str,
        description: str,
    ) -> str:
        try:
            record = await bc.create_maintenance_record(resource_no, category, planned_date, description)
            return (
                f"Registro de mantenimiento creado correctamente.\n"
                f"Número: {record.get('entryNo')}\n"
                f"Recurso: {resource_no}\n"
                f"Categoría: {category}\n"
                f"Fecha planificada: {planned_date}"
            )
        except RuntimeError as exc:
            return f"Error creando registro de mantenimiento: {exc}"

    return StructuredTool.from_function(
        coroutine=_run,
        name="create_maintenance_record",
        description=(
            "Crea un registro de mantenimiento planificado para un recurso. "
            "Categorías: Preventive (preventivo), Corrective (correctivo), Mandatory (obligatorio)."
        ),
        args_schema=CreateMaintenanceRecordInput,
    )


def make_get_maintenance_schedule(bc: "BCClient") -> StructuredTool:
    async def _run(resource_no: str) -> str:
        try:
            schedule = await bc.get_maintenance_schedule(resource_no)
            if not schedule:
                return f"No hay registros de mantenimiento para el recurso '{resource_no}'."
            return json.dumps(schedule, ensure_ascii=False, indent=2)
        except RuntimeError as exc:
            return f"Error obteniendo calendario de mantenimiento: {exc}"

    return StructuredTool.from_function(
        coroutine=_run,
        name="get_maintenance_schedule",
        description="Obtiene el calendario de mantenimiento planificado de un recurso.",
        args_schema=GetMaintenanceScheduleInput,
    )
