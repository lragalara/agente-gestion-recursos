"""Tool de consulta de licencias."""

import json
import logging
from typing import TYPE_CHECKING, Optional

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from bc_client import BCClient

logger = logging.getLogger(__name__)


class GetLicenseStockInput(BaseModel):
    item_no: Optional[str] = Field(
        None,
        description="Número de artículo de licencia (ej: LIC-M365). Si no se indica, devuelve todas.",
    )


def make_get_license_stock(bc: "BCClient") -> StructuredTool:
    async def _run(item_no: str | None = None) -> str:
        try:
            licenses = await bc.get_license_stock(item_no)
            if not licenses:
                msg = "No se encontraron licencias"
                if item_no:
                    msg += f" para el artículo '{item_no}'"
                return msg + "."
            return json.dumps(licenses, ensure_ascii=False, indent=2)
        except RuntimeError as exc:
            return f"Error consultando licencias: {exc}"

    return StructuredTool.from_function(
        coroutine=_run,
        name="get_license_stock",
        description=(
            "Consulta el stock de licencias disponibles. "
            "Si se indica item_no, filtra por ese artículo. "
            "Sin item_no devuelve todas las licencias."
        ),
        args_schema=GetLicenseStockInput,
    )
