"""
Mock Business Central OData v4 Server.

Simula los endpoints de BC On-Premise para desarrollo local.
Carga fixtures JSON al arrancar y mantiene estado mutable en memoria.
"""

import json
import logging
import re
import copy
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Mock BC OData v4", version="1.0.0")

# Estado global mutable por company_id
state: dict[str, dict[str, list]] = {}

DATA_DIR = Path(__file__).parent / "data"


def load_fixtures() -> None:
    """Carga todos los fixtures JSON organizados por company_id."""
    for company_dir in DATA_DIR.iterdir():
        if not company_dir.is_dir():
            continue
        company_id = company_dir.name
        state[company_id] = {
            "resources": [],
            "employees": [],
            "assignments": [],
            "insurance": [],
            "maintenance": [],
            "assignment_headers": [],
            "maintenance_records": [],
        }
        file_map = {
            "resources.json": "resources",
            "employees.json": "employees",
            "assignments.json": "assignments",
            "insurance.json": "insurance",
            "maintenance.json": "maintenance",
        }
        for filename, key in file_map.items():
            filepath = company_dir / filename
            if filepath.exists():
                with open(filepath, encoding="utf-8") as f:
                    state[company_id][key] = json.load(f)
        logger.info("Cargada empresa '%s' con %d recursos", company_id, len(state[company_id]["resources"]))


@app.on_event("startup")
async def startup_event() -> None:
    load_fixtures()
    logger.info("Mock BC arrancado. Empresas disponibles: %s", list(state.keys()))


def get_company_state(company_id: str) -> dict[str, list]:
    """Devuelve el estado de la empresa o lanza 404."""
    if company_id not in state:
        raise HTTPException(status_code=404, detail=f"Empresa '{company_id}' no encontrada")
    return state[company_id]


def apply_filter(items: list[dict], filter_str: str | None) -> list[dict]:
    """
    Aplica filtros OData básicos sobre una lista de dicts.
    Soporta: eq, ne, contains(), and.
    """
    if not filter_str:
        return items

    result = list(items)

    # Dividir por 'and'
    conditions = re.split(r"\s+and\s+", filter_str, flags=re.IGNORECASE)

    for condition in conditions:
        condition = condition.strip()

        # contains(field, 'value')
        contains_match = re.match(r"contains\((\w+),\s*'([^']*)'\)", condition, re.IGNORECASE)
        if contains_match:
            field, value = contains_match.group(1), contains_match.group(2).lower()
            result = [item for item in result if value in str(item.get(field, "")).lower()]
            continue

        # field eq 'value' o field eq true/false/number
        eq_match = re.match(r"(\w+)\s+eq\s+'?([^']+)'?", condition, re.IGNORECASE)
        if eq_match:
            field, value = eq_match.group(1), eq_match.group(2).strip("'")
            # Intentar comparar como bool primero
            if value.lower() == "true":
                typed_value: Any = True
            elif value.lower() == "false":
                typed_value = False
            else:
                try:
                    typed_value = int(value)
                except ValueError:
                    typed_value = value
            result = [item for item in result if item.get(field) == typed_value]
            continue

        # field ne 'value'
        ne_match = re.match(r"(\w+)\s+ne\s+'?([^']+)'?", condition, re.IGNORECASE)
        if ne_match:
            field, value = ne_match.group(1), ne_match.group(2).strip("'")
            result = [item for item in result if item.get(field) != value]

    return result


def odata_response(items: list) -> dict:
    """Envuelve la lista en formato OData."""
    return {"@odata.context": "$metadata", "value": items}


# ─────────────────────────────────────────────────────────────────────────────
# COMPANIES
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/api/v2.0/companies")
async def get_companies() -> dict:
    companies = [{"id": cid, "name": cid, "displayName": cid} for cid in state.keys()]
    return odata_response(companies)


# ─────────────────────────────────────────────────────────────────────────────
# RESOURCES
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/api/v2.0/companies/{company_id}/resources")
async def get_resources(
    company_id: str,
    filter: str | None = Query(None, alias="$filter"),
) -> dict:
    cs = get_company_state(company_id)
    items = apply_filter(cs["resources"], filter)
    return odata_response(items)


@app.get("/api/v2.0/companies/{company_id}/resources/{no}")
async def get_resource(company_id: str, no: str) -> dict:
    cs = get_company_state(company_id)
    for item in cs["resources"]:
        if item["no"] == no:
            return item
    raise HTTPException(status_code=404, detail=f"Recurso '{no}' no encontrado")


# ─────────────────────────────────────────────────────────────────────────────
# EMPLOYEES
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/api/v2.0/companies/{company_id}/employees")
async def get_employees(
    company_id: str,
    filter: str | None = Query(None, alias="$filter"),
) -> dict:
    cs = get_company_state(company_id)
    items = apply_filter(cs["employees"], filter)
    return odata_response(items)


@app.get("/api/v2.0/companies/{company_id}/employees/{no}")
async def get_employee(company_id: str, no: str) -> dict:
    cs = get_company_state(company_id)
    for item in cs["employees"]:
        if item["no"] == no:
            return item
    raise HTTPException(status_code=404, detail=f"Empleado '{no}' no encontrado")


# ─────────────────────────────────────────────────────────────────────────────
# RESOURCE ASSIGNMENT ENTRIES
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/api/v2.0/companies/{company_id}/resourceAssignmentEntries")
async def get_assignment_entries(
    company_id: str,
    filter: str | None = Query(None, alias="$filter"),
) -> dict:
    cs = get_company_state(company_id)
    items = apply_filter(cs["assignments"], filter)
    return odata_response(items)


@app.get("/api/v2.0/companies/{company_id}/resourceAssignmentEntries/history")
async def get_assignment_history(
    company_id: str,
    filter: str | None = Query(None, alias="$filter"),
) -> dict:
    cs = get_company_state(company_id)
    # El historial incluye todos los registros (activos e inactivos)
    items = apply_filter(cs["assignments"], filter)
    return odata_response(items)


# ─────────────────────────────────────────────────────────────────────────────
# ITEM LEDGER ENTRIES (licencias)
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/api/v2.0/companies/{company_id}/itemLedgerEntries")
async def get_item_ledger_entries(
    company_id: str,
    filter: str | None = Query(None, alias="$filter"),
) -> dict:
    cs = get_company_state(company_id)
    # Construir desde recursos de tipo licencia
    license_resources = [r for r in cs["resources"] if r.get("isLicense")]
    items = apply_filter(license_resources, filter)
    return odata_response(items)


# ─────────────────────────────────────────────────────────────────────────────
# INSURANCES
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/api/v2.0/companies/{company_id}/insurances")
async def get_insurances(
    company_id: str,
    filter: str | None = Query(None, alias="$filter"),
) -> dict:
    cs = get_company_state(company_id)
    items = apply_filter(cs["insurance"], filter)
    return odata_response(items)


@app.get("/api/v2.0/companies/{company_id}/insurances/{no}")
async def get_insurance(company_id: str, no: str) -> dict:
    cs = get_company_state(company_id)
    for item in cs["insurance"]:
        if item["no"] == no:
            return item
    raise HTTPException(status_code=404, detail=f"Seguro '{no}' no encontrado")


# ─────────────────────────────────────────────────────────────────────────────
# MAINTENANCE SCHEDULES
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/api/v2.0/companies/{company_id}/maintenanceSchedules")
async def get_maintenance_schedules(
    company_id: str,
    filter: str | None = Query(None, alias="$filter"),
) -> dict:
    cs = get_company_state(company_id)
    items = apply_filter(cs["maintenance"], filter)
    return odata_response(items)


# ─────────────────────────────────────────────────────────────────────────────
# RESOURCE ASSIGNMENT HEADERS (POST = crear documento)
# ─────────────────────────────────────────────────────────────────────────────

def _next_doc_no(cs: dict, doc_type: str) -> str:
    """Genera el siguiente número de documento."""
    prefix_map = {"Delivery": "DEL", "Return": "RET", "Transfer": "TRA"}
    prefix = prefix_map.get(doc_type, "DOC")
    existing = [h for h in cs["assignment_headers"] if h["documentNo"].startswith(prefix)]
    return f"{prefix}-{len(existing) + 1:05d}"


@app.post("/api/v2.0/companies/{company_id}/resourceAssignmentHeaders", status_code=201)
async def create_assignment_header(company_id: str, body: dict) -> dict:
    """Crea un documento de asignación (Delivery, Return o Transfer)."""
    cs = get_company_state(company_id)
    doc_type = body.get("documentType", "Delivery")
    doc_no = _next_doc_no(cs, doc_type)

    header = {
        "documentNo": doc_no,
        "documentType": doc_type,
        "employeeNo": body.get("employeeNo", ""),
        "fromEmployeeNo": body.get("fromEmployeeNo", ""),
        "toEmployeeNo": body.get("toEmployeeNo", ""),
        "status": "Open",
        "lines": body.get("lines", []),
        "postingDate": "",
    }
    cs["assignment_headers"].append(header)
    logger.info("[%s] Documento creado: %s (%s)", company_id, doc_no, doc_type)
    return header


@app.post("/api/v2.0/companies/{company_id}/resourceAssignmentHeaders/{no}/Microsoft.NAV.release")
async def release_document(company_id: str, no: str) -> dict:
    """Libera (valida) un documento."""
    cs = get_company_state(company_id)
    for header in cs["assignment_headers"]:
        if header["documentNo"] == no:
            if header["status"] != "Open":
                raise HTTPException(status_code=400, detail=f"El documento '{no}' no está en estado Open")
            header["status"] = "Released"
            logger.info("[%s] Documento liberado: %s", company_id, no)
            return header
    raise HTTPException(status_code=404, detail=f"Documento '{no}' no encontrado")


@app.post("/api/v2.0/companies/{company_id}/resourceAssignmentHeaders/{no}/Microsoft.NAV.post")
async def post_document(company_id: str, no: str) -> dict:
    """
    Contabiliza un documento.
    Actualiza el estado de los recursos y crea Assignment Entries.
    """
    cs = get_company_state(company_id)
    header = None
    for h in cs["assignment_headers"]:
        if h["documentNo"] == no:
            header = h
            break

    if not header:
        raise HTTPException(status_code=404, detail=f"Documento '{no}' no encontrado")
    if header["status"] not in ("Open", "Released"):
        raise HTTPException(status_code=400, detail=f"El documento '{no}' ya está contabilizado")

    from datetime import date
    posting_date = date.today().isoformat()
    header["status"] = "Posted"
    header["postingDate"] = posting_date

    doc_type = header["documentType"]
    next_entry_no = max((e["entryNo"] for e in cs["assignments"]), default=0) + 1

    for line in header.get("lines", []):
        resource_no = line.get("resourceNo", "")
        item_no = line.get("item_no", "")

        # Actualizar estado del recurso
        for resource in cs["resources"]:
            if resource["no"] == resource_no:
                if doc_type == "Delivery":
                    employee_no = header.get("employeeNo", "")
                    # Buscar nombre del empleado
                    emp_name = next(
                        (e["displayName"] for e in cs["employees"] if e["no"] == employee_no), ""
                    )
                    resource["resourceStatus"] = "Assigned"
                    resource["currentEmployeeNo"] = employee_no
                    resource["currentEmployeeName"] = emp_name
                    resource["assignmentDate"] = posting_date

                    # Crear Assignment Entry
                    cs["assignments"].append({
                        "entryNo": next_entry_no,
                        "entryType": "Assigned",
                        "lineType": "Resource" if resource_no else "Item",
                        "resourceNo": resource_no,
                        "employeeNo": employee_no,
                        "employeeName": emp_name,
                        "documentNo": no,
                        "postingDate": posting_date,
                        "quantity": line.get("quantity", 1),
                        "isActive": True,
                        "serialNo": resource.get("serialNo", ""),
                        "shortcutDimension1": "",
                    })
                    next_entry_no += 1

                elif doc_type == "Return":
                    resource["resourceStatus"] = "Available"
                    resource["currentEmployeeNo"] = ""
                    resource["currentEmployeeName"] = ""
                    resource["assignmentDate"] = ""

                    # Marcar entry activa como inactiva
                    for entry in cs["assignments"]:
                        if entry.get("resourceNo") == resource_no and entry.get("isActive"):
                            entry["isActive"] = False

                    # Crear Assignment Entry de devolución
                    cs["assignments"].append({
                        "entryNo": next_entry_no,
                        "entryType": "Returned",
                        "lineType": "Resource",
                        "resourceNo": resource_no,
                        "employeeNo": header.get("employeeNo", ""),
                        "employeeName": "",
                        "documentNo": no,
                        "postingDate": posting_date,
                        "quantity": line.get("quantity", 1),
                        "isActive": False,
                        "condition": line.get("condition", "Good"),
                        "serialNo": resource.get("serialNo", ""),
                    })
                    next_entry_no += 1

                elif doc_type == "Transfer":
                    to_employee_no = header.get("toEmployeeNo", "")
                    emp_name = next(
                        (e["displayName"] for e in cs["employees"] if e["no"] == to_employee_no), ""
                    )
                    resource["currentEmployeeNo"] = to_employee_no
                    resource["currentEmployeeName"] = emp_name
                    resource["assignmentDate"] = posting_date

                    # Marcar entry anterior como inactiva
                    for entry in cs["assignments"]:
                        if entry.get("resourceNo") == resource_no and entry.get("isActive"):
                            entry["isActive"] = False

                    # Nueva entry
                    cs["assignments"].append({
                        "entryNo": next_entry_no,
                        "entryType": "Transferred",
                        "lineType": "Resource",
                        "resourceNo": resource_no,
                        "employeeNo": to_employee_no,
                        "employeeName": emp_name,
                        "documentNo": no,
                        "postingDate": posting_date,
                        "quantity": line.get("quantity", 1),
                        "isActive": True,
                        "serialNo": resource.get("serialNo", ""),
                    })
                    next_entry_no += 1
                break

    logger.info("[%s] Documento contabilizado: %s (%s)", company_id, no, doc_type)
    return header


# ─────────────────────────────────────────────────────────────────────────────
# MAINTENANCE RECORDS
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/api/v2.0/companies/{company_id}/maintenanceRecords", status_code=201)
async def create_maintenance_record(company_id: str, body: dict) -> dict:
    """Crea un registro de mantenimiento."""
    cs = get_company_state(company_id)
    next_no = max((r["entryNo"] for r in cs["maintenance_records"]), default=0) + 1
    record = {
        "entryNo": next_no,
        "resourceNo": body.get("resourceNo", ""),
        "maintenanceCategory": body.get("category", "Preventive"),
        "plannedDate": body.get("plannedDate", ""),
        "description": body.get("description", ""),
        "status": "Planned",
    }
    cs["maintenance_records"].append(record)
    logger.info("[%s] Mantenimiento creado: %s para %s", company_id, next_no, record["resourceNo"])
    return record


# ─────────────────────────────────────────────────────────────────────────────
# HEALTH
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "companies": list(state.keys()),
        "resources_loaded": {cid: len(s["resources"]) for cid, s in state.items()},
    }
