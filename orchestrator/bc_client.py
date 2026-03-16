"""
Cliente HTTP para Business Central OData v4.

Soporta dos modos:
  mock — conecta al mock_bc server local
  live — conecta al BC On-Premise real vía gateway con autenticación Basic
"""

import logging
import os
from typing import Any
from urllib.parse import quote

import httpx

logger = logging.getLogger(__name__)


class BCClient:
    """Cliente asíncrono para la API OData v4 de Business Central."""

    def __init__(self, company_id: str) -> None:
        self.company_id = company_id
        self._mode = os.getenv("BC_MODE", "mock").lower()

        if self._mode == "mock":
            mock_url = os.getenv("MOCK_BC_URL", "http://mock_bc:8001")
            self._base_url = mock_url
            self._auth: tuple[str, str] | None = None
        else:
            gateway_url = os.getenv("BC_GATEWAY_URL", "")
            self._base_url = gateway_url.rstrip("/")
            user = os.getenv("BC_ODATA_USER", "")
            password = os.getenv("BC_ODATA_PASSWORD", "")
            self._auth = (user, password) if user else None

        self._company_base = f"{self._base_url}/api/v2.0/companies/{self.company_id}"

    def _build_filter(self, **kwargs: Any) -> str | None:
        """Construye un $filter OData a partir de kwargs (field=value)."""
        parts = []
        for field, value in kwargs.items():
            if value is None:
                continue
            if isinstance(value, bool):
                parts.append(f"{field} eq {str(value).lower()}")
            elif isinstance(value, str):
                parts.append(f"{field} eq '{value}'")
            else:
                parts.append(f"{field} eq {value}")
        return " and ".join(parts) if parts else None

    async def _get(self, url: str, params: dict | None = None) -> Any:
        """Realiza un GET y devuelve el campo 'value' de la respuesta OData."""
        try:
            async with httpx.AsyncClient(auth=self._auth, timeout=30.0) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                data = response.json()
                # OData devuelve {"value": [...]} para colecciones
                return data.get("value", data)
        except httpx.HTTPStatusError as exc:
            logger.error("HTTP %s en GET %s: %s", exc.response.status_code, url, exc.response.text)
            raise RuntimeError(
                f"Error {exc.response.status_code} consultando BC: {exc.response.text}"
            ) from exc
        except httpx.HTTPError as exc:
            logger.error("Error de conexión en GET %s: %s", url, exc)
            raise RuntimeError(f"No se pudo conectar con BC: {exc}") from exc

    async def _get_single(self, url: str) -> dict:
        """Realiza un GET a un recurso individual."""
        try:
            async with httpx.AsyncClient(auth=self._auth, timeout=30.0) as client:
                response = await client.get(url)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                raise RuntimeError(f"Recurso no encontrado: {url}") from exc
            logger.error("HTTP %s en GET %s", exc.response.status_code, url)
            raise RuntimeError(f"Error {exc.response.status_code}: {exc.response.text}") from exc
        except httpx.HTTPError as exc:
            raise RuntimeError(f"No se pudo conectar con BC: {exc}") from exc

    async def _post(self, url: str, body: dict) -> dict:
        """Realiza un POST y devuelve la respuesta."""
        try:
            async with httpx.AsyncClient(auth=self._auth, timeout=30.0) as client:
                response = await client.post(url, json=body)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as exc:
            logger.error("HTTP %s en POST %s: %s", exc.response.status_code, url, exc.response.text)
            raise RuntimeError(
                f"Error {exc.response.status_code} en BC: {exc.response.text}"
            ) from exc
        except httpx.HTTPError as exc:
            raise RuntimeError(f"No se pudo conectar con BC: {exc}") from exc

    # ─────────────────────────────────────────────────────────────────────────
    # COMPANIES
    # ─────────────────────────────────────────────────────────────────────────

    async def get_companies(self) -> list:
        """Lista todas las empresas disponibles en BC."""
        url = f"{self._base_url}/api/v2.0/companies"
        return await self._get(url)

    # ─────────────────────────────────────────────────────────────────────────
    # RESOURCES
    # ─────────────────────────────────────────────────────────────────────────

    async def get_resource(self, resource_no: str) -> dict:
        """Obtiene un recurso por su número."""
        url = f"{self._company_base}/resources/{quote(resource_no)}"
        return await self._get_single(url)

    async def search_resources(
        self,
        status: str | None = None,
        category: str | None = None,
        group: str | None = None,
    ) -> list:
        """Busca recursos con filtros opcionales."""
        filter_parts = []
        if status:
            filter_parts.append(f"resourceStatus eq '{status}'")
        if category:
            filter_parts.append(f"assetCategory eq '{category}'")
        if group:
            filter_parts.append(f"resourceGroup eq '{group}'")

        params = {}
        if filter_parts:
            params["$filter"] = " and ".join(filter_parts)

        url = f"{self._company_base}/resources"
        return await self._get(url, params=params)

    # ─────────────────────────────────────────────────────────────────────────
    # EMPLOYEES
    # ─────────────────────────────────────────────────────────────────────────

    async def get_employee(self, employee_no: str) -> dict:
        """Obtiene un empleado por su número."""
        url = f"{self._company_base}/employees/{quote(employee_no)}"
        return await self._get_single(url)

    async def search_employees(self, name: str) -> list:
        """Busca empleados por nombre (búsqueda parcial)."""
        params = {"$filter": f"contains(displayName, '{name}')"}
        url = f"{self._company_base}/employees"
        return await self._get(url, params=params)

    async def get_employee_assets(self, employee_no: str) -> list:
        """Obtiene los activos actualmente asignados a un empleado."""
        params = {
            "$filter": f"employeeNo eq '{employee_no}' and isActive eq true"
        }
        url = f"{self._company_base}/resourceAssignmentEntries"
        return await self._get(url, params=params)

    # ─────────────────────────────────────────────────────────────────────────
    # LICENSES
    # ─────────────────────────────────────────────────────────────────────────

    async def get_license_stock(self, item_no: str | None = None) -> list:
        """Obtiene el stock de licencias. Si item_no es None, devuelve todas."""
        params: dict = {"$filter": "isLicense eq true"}
        if item_no:
            params["$filter"] += f" and entityNo eq '{item_no}'"
        url = f"{self._company_base}/itemLedgerEntries"
        return await self._get(url, params=params)

    # ─────────────────────────────────────────────────────────────────────────
    # VEHICLES / FLEET
    # ─────────────────────────────────────────────────────────────────────────

    async def get_vehicle_fleet(self, filter: str | None = None) -> list:
        """
        Obtiene la flota de vehículos con sus datos de seguro.

        Args:
            filter: Filtro semántico: itv_expiring|insurance_expiring|
                    tachograph_expiring|service_due|rental_expiring|all
        """
        params = {"$filter": "vehicleInsurance eq true"}
        url = f"{self._company_base}/insurances"
        return await self._get(url, params=params)

    async def get_insurance(self, insurance_no: str) -> dict:
        """Obtiene los datos de seguro/ITV de un vehículo."""
        url = f"{self._company_base}/insurances/{quote(insurance_no)}"
        return await self._get_single(url)

    # ─────────────────────────────────────────────────────────────────────────
    # ASSIGNMENT DOCUMENTS
    # ─────────────────────────────────────────────────────────────────────────

    async def create_assignment_header(
        self,
        document_type: str,
        employee_no: str,
        lines: list[dict],
        from_employee_no: str = "",
        to_employee_no: str = "",
    ) -> dict:
        """
        Crea un documento de asignación (Delivery, Return o Transfer).

        Args:
            document_type: Delivery | Return | Transfer
            employee_no:   Empleado principal
            lines:         Lista de líneas del documento
            from_employee_no: Para Transfer, empleado origen
            to_employee_no:   Para Transfer, empleado destino
        """
        url = f"{self._company_base}/resourceAssignmentHeaders"
        body = {
            "documentType": document_type,
            "employeeNo": employee_no,
            "fromEmployeeNo": from_employee_no,
            "toEmployeeNo": to_employee_no,
            "lines": lines,
        }
        return await self._post(url, body)

    async def release_document(self, document_no: str) -> dict:
        """Libera (valida) un documento de asignación."""
        url = f"{self._company_base}/resourceAssignmentHeaders/{quote(document_no)}/Microsoft.NAV.release"
        return await self._post(url, {})

    async def post_document(self, document_no: str) -> dict:
        """Contabiliza un documento de asignación."""
        url = f"{self._company_base}/resourceAssignmentHeaders/{quote(document_no)}/Microsoft.NAV.post"
        return await self._post(url, {})

    # ─────────────────────────────────────────────────────────────────────────
    # MAINTENANCE
    # ─────────────────────────────────────────────────────────────────────────

    async def create_maintenance_record(
        self,
        resource_no: str,
        category: str,
        planned_date: str,
        description: str,
    ) -> dict:
        """Crea un registro de mantenimiento planificado."""
        url = f"{self._company_base}/maintenanceRecords"
        body = {
            "resourceNo": resource_no,
            "category": category,
            "plannedDate": planned_date,
            "description": description,
        }
        return await self._post(url, body)

    async def get_maintenance_schedule(self, resource_no: str) -> list:
        """Obtiene el calendario de mantenimiento de un recurso."""
        params = {"$filter": f"resourceNo eq '{resource_no}'"}
        url = f"{self._company_base}/maintenanceSchedules"
        return await self._get(url, params=params)

    # ─────────────────────────────────────────────────────────────────────────
    # HISTORY
    # ─────────────────────────────────────────────────────────────────────────

    async def get_assignment_history(
        self,
        resource_no: str | None = None,
        employee_no: str | None = None,
    ) -> list:
        """
        Obtiene el historial de asignaciones.
        Al menos uno de los dos parámetros debe proporcionarse.
        """
        filter_parts = []
        if resource_no:
            filter_parts.append(f"resourceNo eq '{resource_no}'")
        if employee_no:
            filter_parts.append(f"employeeNo eq '{employee_no}'")

        params = {}
        if filter_parts:
            params["$filter"] = " and ".join(filter_parts)

        url = f"{self._company_base}/resourceAssignmentEntries/history"
        return await self._get(url, params=params)
