"""Tools de consulta de recursos y empleados."""

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

class GetResourceStatusInput(BaseModel):
    resource_no: str = Field(..., description="Número del recurso (ej: REC-00001)")


class SearchAvailableResourcesInput(BaseModel):
    category: Optional[Literal["Computing", "Communication", "Vehicle", "License", "Tool", "Other"]] = Field(
        None, description="Categoría del activo"
    )
    resource_group: Optional[Literal[
        "VEHÍCULOS", "ALQUILERES", "MAQUINARIA", "EQUIPOS INFORMÁTICOS", "LICENCIAS", "TARJETAS", "OTROS"
    ]] = Field(None, description="Grupo de recurso en BC")


class SearchEmployeesInput(BaseModel):
    name: str = Field(..., description="Nombre o parte del nombre del empleado")


# ─────────────────────────────────────────────────────────────────────────────
# Factories
# ─────────────────────────────────────────────────────────────────────────────

def make_get_resource_status(bc: "BCClient") -> StructuredTool:
    """Devuelve la tool get_resource_status ligada al BCClient dado."""

    async def _run(resource_no: str) -> str:
        try:
            resource = await bc.get_resource(resource_no)
            return json.dumps(resource, ensure_ascii=False, indent=2)
        except RuntimeError as exc:
            return f"Error obteniendo recurso: {exc}"

    return StructuredTool.from_function(
        coroutine=_run,
        name="get_resource_status",
        description=(
            "Obtiene el estado actual y los datos completos de un recurso por su número. "
            "Devuelve: nombre, estado, categoría, empleado asignado, fechas, etc."
        ),
        args_schema=GetResourceStatusInput,
    )


def make_search_available_resources(bc: "BCClient") -> StructuredTool:
    """Devuelve la tool search_available_resources ligada al BCClient dado."""

    async def _run(
        category: str | None = None,
        resource_group: str | None = None,
    ) -> str:
        try:
            resources = await bc.search_resources(
                status="Available",
                category=category,
                group=resource_group,
            )
            if not resources:
                return "No se encontraron recursos disponibles con los filtros indicados."
            return json.dumps(resources, ensure_ascii=False, indent=2)
        except RuntimeError as exc:
            return f"Error buscando recursos: {exc}"

    return StructuredTool.from_function(
        coroutine=_run,
        name="search_available_resources",
        description=(
            "Busca recursos disponibles (Available) con filtros opcionales de categoría y grupo. "
            "Útil para saber qué hay disponible antes de asignar."
        ),
        args_schema=SearchAvailableResourcesInput,
    )


def make_search_employees(bc: "BCClient") -> StructuredTool:
    """Devuelve la tool search_employees ligada al BCClient dado."""

    async def _run(name: str) -> str:
        try:
            employees = await bc.search_employees(name)
            if not employees:
                return f"No se encontraron empleados con nombre '{name}'."
            return json.dumps(employees, ensure_ascii=False, indent=2)
        except RuntimeError as exc:
            return f"Error buscando empleados: {exc}"

    return StructuredTool.from_function(
        coroutine=_run,
        name="search_employees",
        description=(
            "Busca empleados por nombre o apellido (búsqueda parcial). "
            "Devuelve: número de empleado, nombre completo, departamento, email."
        ),
        args_schema=SearchEmployeesInput,
    )
