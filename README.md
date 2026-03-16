# Agente de Gestión de Recursos BC

Agente conversacional sobre Microsoft Business Central On-Premise para gestión de recursos y activos.
Funciona en Teams (vía Azure Bot Service) y en consola/Postman durante el desarrollo.

## Stack

- **Azure Bot Service** — canal Teams (WhatsApp futuro)
- **Azure Container App** — Python 3.12 / FastAPI
- **Azure OpenAI** — GPT-4o mini con function calling (12 tools)
- **Business Central On-Premise** — OData v4, simulado localmente con mock server

---

## Requisitos previos

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) ≥ 4.x
- Python 3.12 (opcional, solo para desarrollo sin Docker)
- Git

---

## Inicio rápido

```bash
# 1. Clonar el repositorio
git clone <url-del-repo>
cd agente-gestion-recursos

# 2. Copiar las variables de entorno
cp .env.example .env
# Edita .env y rellena al menos AZURE_OPENAI_ENDPOINT y AZURE_OPENAI_KEY
# (sin ellas el agente funciona en modo demo)

# 3. Levantar los servicios
docker-compose up

# El mock BC arranca en http://localhost:8001
# El orchestrator arranca en http://localhost:8000
```

---

## Probar el agente sin Teams

Usa el endpoint `/chat` (solo disponible cuando `BC_MODE=mock`):

```bash
# Con curl
curl -s -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "¿Qué tiene asignado María López?", "user_id": "test"}' \
  | python -m json.tool

# Verificar estado del sistema
curl http://localhost:8000/health

# Ver empresas disponibles
curl http://localhost:8000/companies

# Ver recursos del mock directamente
curl http://localhost:8001/api/v2.0/companies/CRONUS/resources
```

También puedes usar [Postman](https://www.postman.com/) o cualquier cliente HTTP.

---

## Ejemplos de conversación de prueba

```
"¿Qué tiene asignado María López?"
→ Muestra los activos activos asignados a EMP001

"¿Qué vehículos tienen la ITV vencida?"
→ Lista vehículos con itvExpiryDate en el pasado o dentro del periodo de alerta

"Asigna el portátil REC-00001 a Ana Ruiz"
→ El agente presenta un resumen y pide confirmación antes de crear el Delivery

"¿Cuántas licencias de M365 hay disponibles?"
→ Consulta el stock de licencias Microsoft 365 E3

"¿Qué recursos hay disponibles en EQUIPOS INFORMÁTICOS?"
→ Filtra por resourceGroup='EQUIPOS INFORMÁTICOS' y status='Available'

"Muestra el calendario de mantenimiento de REC-00090"
→ Devuelve las revisiones programadas para la Renault Trafic

"Devuelve el teléfono REC-00002 de María López, estado: Bueno"
→ Crea un Return document tras confirmación del usuario

"Transfiere el Ford Transit REC-00091 de Pedro Martínez a Juan García"
→ Crea un Transfer document tras confirmación
```

---

## Cambiar de empresa

### Modo `fixed` (por defecto)
Edita `.env` y cambia `BC_COMPANY_ID`:

```env
BC_COMPANY_ID=EMPRESA2
```

Reinicia: `docker-compose restart orchestrator`

### Modo `select`
Cambia `BC_TENANT_MODE=select` en `.env`. El bot preguntará al usuario qué empresa quiere
usar al inicio de cada conversación.

### Modo `auto`
Requiere Azure Bot Service configurado y usuarios con grupos `BC-*` en Entra ID.
El bot detecta automáticamente la empresa por membresía en grupos AD.

---

## Estructura del proyecto

```
agente-gestion-recursos/
├── docker-compose.yml          — Orquestación de servicios
├── .env.example                — Plantilla de variables de entorno
├── .env                        — Variables reales (gitignored)
├── README.md
├── DEPLOY_AZURE.md             — Guía de despliegue en Azure
├── orchestrator/               — Servicio principal (puerto 8000)
│   ├── main.py                 — Endpoints FastAPI
│   ├── agent.py                — Núcleo LangChain + function calling
│   ├── bc_client.py            — Cliente OData BC (mock y live)
│   ├── bot_adapter.py          — Integración Bot Framework
│   ├── tenant_resolver.py      — Resolución de empresa por usuario
│   ├── prompts/
│   │   └── system_prompt.py    — Prompt del sistema
│   └── tools/                  — 12 tools del agente
│       ├── resources.py        — Consulta recursos y empleados
│       ├── assignments.py      — Entregas, devoluciones, transferencias
│       ├── licenses.py         — Stock de licencias
│       ├── vehicles.py         — Flota de vehículos
│       └── maintenance.py      — Mantenimiento
└── mock_bc/                    — Servidor BC simulado (puerto 8001)
    ├── main.py                 — OData v4 en memoria con estado mutable
    └── data/
        ├── CRONUS/             — Fixtures empresa CRONUS
        └── EMPRESA2/           — Fixtures empresa EMPRESA2
```

---

## Variables de entorno principales

| Variable | Descripción | Por defecto |
|---|---|---|
| `BC_MODE` | `mock` o `live` | `mock` |
| `BC_TENANT_MODE` | `fixed`, `select` o `auto` | `fixed` |
| `BC_COMPANY_ID` | Empresa activa en modo `fixed` | `CRONUS` |
| `AZURE_OPENAI_KEY` | Key de Azure OpenAI | vacío (modo demo) |
| `AZURE_OPENAI_ENDPOINT` | Endpoint de Azure OpenAI | vacío |
| `BOT_APP_ID` | App ID del bot en Entra ID | vacío (modo dev) |
| `MOCK_BC_URL` | URL del mock server | `http://mock_bc:8001` |

---

## Pasar a BC real

1. Configura el On-premises Data Gateway de Azure para exponer la OData de BC
2. En `.env` cambia:

```env
BC_MODE=live
BC_GATEWAY_URL=https://tu-gateway.azure.com/ruta/ODataV4
BC_ODATA_USER=tu_usuario
BC_ODATA_PASSWORD=tu_contraseña
BC_COMPANY_ID=NOMBRE_EMPRESA_REAL
```

3. Reinicia: `docker-compose restart orchestrator`
4. Verifica conectividad: `curl http://localhost:8000/companies`

Ver [DEPLOY_AZURE.md](DEPLOY_AZURE.md) para el despliegue completo en Azure.
