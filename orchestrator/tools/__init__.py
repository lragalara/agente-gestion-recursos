"""
Módulo de tools del agente de gestión de recursos.

Exporta get_all_tools() que devuelve la lista completa de StructuredTools
ligadas a un BCClient y un PAClient dados.

Separación de responsabilidades:
  BCClient  — todas las operaciones BC: lecturas, create, release y post (OData directo)
  PAClient  — notificaciones post-operación: Teams y correo vía Power Automate (fire-and-forget)
"""

from typing import TYPE_CHECKING

from langchain_core.tools import StructuredTool

from tools.assignments import (
    make_create_delivery,
    make_create_return,
    make_create_transfer,
    make_get_assignment_history,
    make_get_employee_assets,
)
from tools.licenses import make_get_license_stock
from tools.maintenance import make_create_maintenance_record, make_get_maintenance_schedule
from tools.resources import (
    make_get_resource_status,
    make_search_available_resources,
    make_search_employees,
)
from tools.vehicles import make_get_vehicle_fleet

if TYPE_CHECKING:
    from bc_client import BCClient
    from pa_client import PAClient


def get_all_tools(bc_client: "BCClient", pa_client: "PAClient") -> list[StructuredTool]:
    """
    Devuelve las 12 tools del agente ligadas a BCClient y PAClient.

    Args:
        bc_client: Instancia de BCClient configurada para la empresa del usuario.
        pa_client: Instancia de PAClient para operaciones de release/post.

    Returns:
        Lista de StructuredTool listos para pasar al AgentExecutor.
    """
    return [
        # Recursos — lectura OData
        make_get_resource_status(bc_client),
        make_search_available_resources(bc_client),
        make_search_employees(bc_client),
        # Asignaciones — lectura OData
        make_get_employee_assets(bc_client),
        make_get_assignment_history(bc_client),
        # Asignaciones — escritura OData + notificación PA al finalizar
        make_create_delivery(bc_client, pa_client),
        make_create_return(bc_client, pa_client),
        make_create_transfer(bc_client, pa_client),
        # Licencias — lectura OData
        make_get_license_stock(bc_client),
        # Vehículos — lectura OData
        make_get_vehicle_fleet(bc_client),
        # Mantenimiento — OData
        make_create_maintenance_record(bc_client),
        make_get_maintenance_schedule(bc_client),
    ]
