# Power Automate — Flow de notificaciones

Guía para crear el flow de notificaciones que se dispara cada vez que el
orquestador procesa un documento de asignación en Business Central.

---

## Qué hace este flow y qué no hace

**Sí hace:**
- Recibe el contexto de una operación BC completada (entrega, devolución, transferencia)
- Publica un mensaje en el canal de Teams del equipo (ej: "Almacén" o "Gestión de Recursos")
- Envía un correo al responsable o buzón de control

**No hace:**
- No toca BC en ningún momento
- No necesita el conector BC ni el On-premises Data Gateway
- No es bloqueante: si falla, la operación BC ya está completada y el usuario ya recibió la respuesta del bot

**Quién llama a este flow:**
El orquestador Python (`pa_client.py`) hace un POST al trigger HTTP después de que `bc_client.py`
ha completado con éxito el ciclo create → release → post en BC.

---

## Arquitectura de notificaciones

```
Usuario en Teams
      │ "Entrega el portátil a Juan García"
      ▼
Orquestador (Python)
      │
      ├─ bc_client.py → OData → BC  (create + release + post)
      │       ✅ Operación completada en BC
      │
      └─ pa_client.py → HTTP POST → Power Automate flow
                                          │
                              ┌───────────┴───────────┐
                              ▼                       ▼
                     Teams (canal equipo)     Outlook (correo responsable)
                     "📦 Entrega procesada    "Asunto: [BC Recursos]
                      Doc: ASG-00023          Entrega ASG-00023..."
                      Empleado: EMP001"
```

---

## Payload que recibe el flow

El orquestador envía este JSON al trigger HTTP:

```json
{
  "operationType": "Delivery",
  "operationLabel": "Entrega",
  "documentNo": "ASG-00023",
  "employeeNo": "EMP001",
  "resourceNos": "REC-001, REC-005",
  "companyId": "CRONUS",
  "triggeredBy": "pedro.lopez@empresa.com",
  "timestamp": "2026-03-16T10:30:00Z",
  "teamsMessage": "📦 **Entrega** procesada\nDocumento: `ASG-00023`\nEmpleado: EMP001\nRecursos: REC-001, REC-005\nEmpresa: CRONUS\nGestionado por: pedro.lopez@empresa.com",
  "emailSubject": "[BC Recursos] Entrega ASG-00023 — CRONUS"
}
```

Los campos `teamsMessage` y `emailSubject` vienen preformateados desde Python, listos para usar directamente en el flow sin necesidad de expresiones complejas.

---

## Crear el flow paso a paso

### Nombre sugerido
`BC-Recursos-Notificacion-Operacion`

---

### Paso 1 — Trigger: When an HTTP request is received

Selecciona el trigger **"When an HTTP request is received"** (conector: Request).

En **Request Body JSON Schema** pega el siguiente schema:

```json
{
  "type": "object",
  "properties": {
    "operationType":   { "type": "string" },
    "operationLabel":  { "type": "string" },
    "documentNo":      { "type": "string" },
    "employeeNo":      { "type": "string" },
    "resourceNos":     { "type": "string" },
    "companyId":       { "type": "string" },
    "triggeredBy":     { "type": "string" },
    "timestamp":       { "type": "string" },
    "teamsMessage":    { "type": "string" },
    "emailSubject":    { "type": "string" }
  }
}
```

Deja el método en **POST**. Guarda el flow aquí para que PA genere la URL del trigger.

> **Copia la URL** que aparece en este paso — es la que va en `PA_NOTIFY_FLOW_URL`.
> Contiene una firma SAS. Trátala como una contraseña.

---

### Paso 2 — Acción: Post message in a chat or channel (Teams)

Conector: **Microsoft Teams**
Acción: **Post message in a chat or channel**

Configuración:
- **Post as**: Flow bot
- **Post in**: Channel
- **Team**: Selecciona el equipo (ej: "Almacén" o "Recursos")
- **Channel**: Selecciona el canal (ej: "General" o "Operaciones")
- **Message**: `@{triggerBody()?['teamsMessage']}`

Con esto el mensaje llega al canal con el formato Markdown que ya viene preparado desde Python.

---

### Paso 3 — Acción: Send an email (Outlook)

Conector: **Office 365 Outlook**
Acción: **Send an email (V2)**

Configuración:
- **To**: buzón o lista de distribución del responsable (ej: `almacen@empresa.com`)
- **Subject**: `@{triggerBody()?['emailSubject']}`
- **Body**:

```
Se ha procesado una operación en Business Central.

Tipo: @{triggerBody()?['operationLabel']}
Documento: @{triggerBody()?['documentNo']}
Empleado: @{triggerBody()?['employeeNo']}
Recursos: @{triggerBody()?['resourceNos']}
Empresa: @{triggerBody()?['companyId']}
Fecha: @{triggerBody()?['timestamp']}
Gestionado por: @{triggerBody()?['triggeredBy']}
```

---

### Paso 4 — Respuesta: Response

Conector: **Request**
Acción: **Response**

- **Status code**: `200`
- **Body**:
```json
{
  "status": "notified",
  "documentNo": "@{triggerBody()?['documentNo']}"
}
```

---

## Añadir la URL al proyecto

Una vez guardado el flow:

### Desarrollo local

En el fichero `.env`:
```env
PA_NOTIFY_FLOW_URL=https://prod-XX.westeurope.logic.azure.com:443/workflows/.../triggers/manual/...
```

Reinicia el orchestrador: `docker-compose restart orchestrator`

### Container App en Azure

```bash
az containerapp secret set \
  --name orchestrator \
  --resource-group rg-agente-recursos \
  --secrets pa-notify-url="URL_COMPLETA_DEL_FLOW"

az containerapp update \
  --name orchestrator \
  --resource-group rg-agente-recursos \
  --set-env-vars PA_NOTIFY_FLOW_URL=secretref:pa-notify-url
```

---

## Extensiones posibles (sin tocar el orquestador)

Al tener todo el contexto en el payload, puedes añadir pasos al flow en cualquier momento:

- **Guardar log en SharePoint** — acción "Create item" en una lista con las columnas del payload
- **Notificación diferente por tipo de operación** — añade una condición `operationType eq 'Return'` para enviar el correo de devolución a un destinatario distinto
- **Mensaje de Teams adaptativo** — usa una Adaptive Card en lugar de texto plano para un formato más visual
- **Filtrar por empresa** — si hay múltiples empresas BC, enrutar notificaciones a canales o buzones distintos según `companyId`

Ninguna de estas extensiones requiere tocar el código Python.

---

## Verificación

Una vez configurado, prueba el flow manualmente desde PA con el botón "Test":

1. Selecciona **"Manually"** → **"With a payload"**
2. Pega este JSON de prueba:

```json
{
  "operationType": "Delivery",
  "operationLabel": "Entrega",
  "documentNo": "ASG-TEST-001",
  "employeeNo": "EMP001",
  "resourceNos": "REC-001",
  "companyId": "CRONUS",
  "triggeredBy": "test@empresa.com",
  "timestamp": "2026-03-16T10:00:00Z",
  "teamsMessage": "📦 **Entrega** procesada\nDocumento: `ASG-TEST-001`\nEmpleado: EMP001\nRecursos: REC-001\nEmpresa: CRONUS",
  "emailSubject": "[BC Recursos] Entrega ASG-TEST-001 — CRONUS"
}
```

3. Verifica que llega el mensaje al canal de Teams y el correo al buzón configurado.
