"""Tool de consulta de flota de vehículos."""

import json
import logging
from datetime import date
from typing import TYPE_CHECKING, Literal, Optional

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from bc_client import BCClient

logger = logging.getLogger(__name__)

VehicleFilter = Literal[
    "itv_expiring",
    "insurance_expiring",
    "tachograph_expiring",
    "service_due",
    "rental_expiring",
    "all",
]


class GetVehicleFleetInput(BaseModel):
    filter: Optional[VehicleFilter] = Field(
        "all",
        description=(
            "Filtro semántico: itv_expiring (ITV próxima a vencer o vencida), "
            "insurance_expiring (seguro próximo), tachograph_expiring (tacógrafo), "
            "service_due (revisión pendiente), rental_expiring (fin renting próximo), all (todo)."
        ),
    )


def _is_expiring_or_expired(date_str: str, alert_days: int) -> bool:
    """Devuelve True si la fecha está vencida o dentro del periodo de alerta."""
    if not date_str:
        return False
    try:
        target = date.fromisoformat(date_str)
        today = date.today()
        return (target - today).days <= alert_days
    except ValueError:
        return False


def _apply_vehicle_filter(vehicles: list[dict], filter_name: str | None) -> list[dict]:
    """Aplica filtros semánticos a la flota de vehículos."""
    if not filter_name or filter_name == "all":
        return vehicles

    result = []
    for v in vehicles:
        match filter_name:
            case "itv_expiring":
                if _is_expiring_or_expired(v.get("itvExpiryDate", ""), v.get("itvAlertDays", 30)):
                    result.append(v)
            case "insurance_expiring":
                if _is_expiring_or_expired(v.get("insuranceExpiryDate", ""), v.get("insuranceAlertDays", 45)):
                    result.append(v)
            case "tachograph_expiring":
                if _is_expiring_or_expired(v.get("tachographExpiryDate", ""), v.get("tachographAlertDays", 30)):
                    result.append(v)
            case "service_due":
                if _is_expiring_or_expired(v.get("nextServiceDate", ""), v.get("serviceAlertDays", 30)):
                    result.append(v)
            case "rental_expiring":
                if v.get("ownershipType") == "Rental" and _is_expiring_or_expired(
                    v.get("rentalEndDate", ""), v.get("rentalAlertDays", 60)
                ):
                    result.append(v)
    return result


def make_get_vehicle_fleet(bc: "BCClient") -> StructuredTool:
    async def _run(filter: str | None = "all") -> str:
        try:
            fleet = await bc.get_vehicle_fleet()
            filtered = _apply_vehicle_filter(fleet, filter)
            if not filtered:
                return f"No se encontraron vehículos con el filtro '{filter}'."
            return json.dumps(filtered, ensure_ascii=False, indent=2)
        except RuntimeError as exc:
            return f"Error consultando flota: {exc}"

    return StructuredTool.from_function(
        coroutine=_run,
        name="get_vehicle_fleet",
        description=(
            "Consulta la flota de vehículos con datos de ITV, seguro, revisión y renting. "
            "Usa filter='itv_expiring' para ver vehículos con ITV vencida o próxima a vencer, "
            "'insurance_expiring' para seguros, 'service_due' para revisiones, etc."
        ),
        args_schema=GetVehicleFleetInput,
    )
