"""
Módulo de tools del agente de gestión de recursos.

Exporta get_all_tools() que devuelve la lista completa de StructuredTools
ligadas a un BCClient dado.
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


def get_all_tools(bc_client: "BCClient") -> list[StructuredTool]:
    """
    Devuelve las 12 tools del agente ligadas al BCClient proporcionado.

    Args:
        bc_client: Instancia de BCClient ya configurada para la empresa del usuario.

    Returns:
        Lista de StructuredTool listos para pasar al AgentExecutor.
    """
    return [
        # Recursos
        make_get_resource_status(bc_client),
        make_search_available_resources(bc_client),
        make_search_employees(bc_client),
        # Asignaciones
        make_get_employee_assets(bc_client),
        make_create_delivery(bc_client),
        make_create_return(bc_client),
        make_create_transfer(bc_client),
        make_get_assignment_history(bc_client),
        # Licencias
        make_get_license_stock(bc_client),
        # Vehículos
        make_get_vehicle_fleet(bc_client),
        # Mantenimiento
        make_create_maintenance_record(bc_client),
        make_get_maintenance_schedule(bc_client),
    ]
