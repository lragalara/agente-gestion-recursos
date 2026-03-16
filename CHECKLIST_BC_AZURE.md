# Checklist BC y Azure

Checklist operativa para cerrar el proyecto de gestion de recursos en dos momentos:

1. cuando BC/consultoria confirme el modelo funcional
2. cuando se despliegue en Azure y se valide extremo a extremo

---

## Bloqueado por BC

Estas decisiones no pueden cerrarse solo desde Python, Teams o Power Automate.

### Multiempresa

- [ ] Confirmar si la gestion de recursos vive en una sola empresa BC o en varias
- [ ] Confirmar la lista exacta de `company_id` reales de BC
- [ ] Confirmar si existe una empresa centralizadora para recursos
- [ ] Confirmar si cada jefe de obra trabaja sobre una sola empresa o varias
- [ ] Confirmar si un mismo usuario puede operar sobre varias empresas

### Relacion usuario -> empresa

- [ ] Confirmar si BC puede resolver `correo corporativo -> empleado -> empresa`
- [ ] Confirmar si el email de Teams coincide con el email del empleado en BC
- [ ] Confirmar si el mismo correo puede existir en varias empresas
- [ ] Confirmar que debe pasar si un usuario pertenece a varias empresas
- [ ] Confirmar si la fuente de verdad del tenancy debe estar en BC o en Entra ID

### Entra ID

- [ ] Confirmar si existen grupos por empresa BC
- [ ] Confirmar si la estructura real de grupos esta organizada por empresa o por obra
- [ ] Confirmar si existe una equivalencia formal `obra -> empresa`
- [ ] Confirmar si el modo `auto` debe apoyarse en Entra ID o en consulta a BC

### Alertas

- [ ] Confirmar la lista definitiva de tipos de alerta
- [ ] Confirmar para cada alerta quien debe recibirla
- [ ] Confirmar si el destinatario cambia por empresa
- [ ] Confirmar si ademas del responsable debe recibirla tambien el usuario afectado
- [ ] Confirmar donde debe mantenerse la configuracion de responsables:
  BC, Entra o configuracion externa
- [ ] Confirmar si BC enviara `target_user_email` cuando la alerta afecte a un usuario concreto
- [ ] Confirmar si BC enviara siempre `company_id` en el webhook de alertas

### Integracion BC

- [ ] Confirmar la URL real de OData/Gateway
- [ ] Confirmar autenticacion y credenciales del acceso a BC
- [ ] Confirmar que BC puede devolver la lista de `companies`
- [ ] Confirmar que BC puede buscar empleados por email
- [ ] Confirmar el payload final del webhook de alertas

---

## Listo para Azure

Estas tareas se ejecutan cuando el modelo BC ya este decidido y se vaya a desplegar.

### Configuracion

- [ ] Completar `.env` o secretos reales con credenciales BC
- [ ] Configurar `AZURE_OPENAI_ENDPOINT`
- [ ] Configurar `AZURE_OPENAI_KEY`
- [ ] Configurar `BOT_APP_ID`
- [ ] Configurar `BOT_APP_PASSWORD`
- [ ] Configurar `PA_NOTIFY_FLOW_URL_OPERATIONS`
- [ ] Configurar `PA_NOTIFY_FLOW_URL_ALERTS`
- [ ] Desactivar `PA_TEST_EMAIL_OVERRIDE` si se pasa a destinatarios reales

### Alertas

- [ ] Sustituir `orchestrator/config/alert_roles.json` de pruebas por responsables reales
- [ ] Confirmar emails reales por rol
- [ ] Confirmar `teamsUserIds` reales por rol si se van a usar proactivos del bot

### Docker / Container App

- [ ] Construir imagen Docker del orchestrator
- [ ] Subir imagen al registry
- [ ] Crear o actualizar Container App
- [ ] Montar secretos en Container App
- [ ] Verificar que el servicio arranca correctamente

### Bot y Teams

- [ ] Crear o configurar App Registration del bot
- [ ] Crear o configurar Azure Bot Service
- [ ] Configurar endpoint `/api/messages`
- [ ] Habilitar canal Microsoft Teams
- [ ] Publicar / permitir la app en Teams

---

## Validacion Post Azure

### Salud tecnica

- [ ] `GET /health` devuelve OK
- [ ] `GET /companies` funciona contra BC real
- [ ] Las variables de entorno reales estan cargadas
- [ ] Los secretos reales estan montados correctamente

### Bot en Teams

- [ ] Un usuario puede escribir al bot y recibir respuesta
- [ ] El bot guarda `ConversationReference` al primer mensaje
- [ ] El bot responde usando la empresa correcta

### Tenant / multiempresa

- [ ] Validar modo `fixed`, `select` o `auto` segun la decision final
- [ ] Si el modo es `auto`, validar resolucion real de empresa
- [ ] Si un usuario tiene varias empresas, validar el comportamiento esperado

### Operaciones

- [ ] Ejecutar un `Delivery` real o de prueba
- [ ] Confirmar create -> release -> post en BC
- [ ] Confirmar disparo del flow `gestion_recursos_operaciones`
- [ ] Confirmar correo al empleado

- [ ] Ejecutar un `Return` real o de prueba
- [ ] Confirmar disparo del flow `gestion_recursos_operaciones`
- [ ] Confirmar correo al empleado

- [ ] Ejecutar un `Transfer` real o de prueba
- [ ] Confirmar disparo del flow `gestion_recursos_operaciones`
- [ ] Confirmar correo al destinatario definido

### Alertas

- [ ] Forzar una alerta real o de prueba desde BC
- [ ] Confirmar llamada a `/webhook/alerts`
- [ ] Confirmar resolucion correcta de roles y destinatarios
- [ ] Confirmar disparo del flow `gestion_recursos_alertas`
- [ ] Confirmar correo al responsable correcto
- [ ] Confirmar correo al usuario afectado si aplica

### Bot proactivo

- [ ] Confirmar que los destinatarios han iniciado chat con el bot al menos una vez
- [ ] Confirmar envio proactivo correcto en Teams
- [ ] Confirmar comportamiento tras reinicio del servicio

---

## Pendiente para produccion

Estos puntos no bloquean la fase 1, pero deben valorarse antes de dar el sistema por maduro.

- [ ] Decidir si la configuracion de responsables de alertas seguira en JSON o se movera a BC
- [ ] Decidir si el modo `auto` definitivo vivira en Entra ID o en BC
- [ ] Valorar persistencia de `ConversationReference` para mensajes proactivos estables
- [ ] Valorar logs/auditoria de alertas y operaciones
- [ ] Valorar estrategia multiempresa definitiva para usuarios con acceso a varias empresas
