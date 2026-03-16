# Alertas proactivas

Esta guía explica cómo funciona el envío de alertas cuando Business Central
llama al endpoint `/webhook/alerts`.

## Idea principal

El sistema resuelve dos cosas distintas:

1. Quién debería recibir la alerta
2. Si el bot puede enviarle un mensaje por Teams en ese momento

La primera parte se configura en `orchestrator/config/alert_roles.json`.
La segunda depende de que el usuario ya haya hablado con el bot y de que la
instancia actual conserve su `ConversationReference` en memoria.

## Routing por rol

BC no necesita saber el Teams user_id del responsable de Compras, RRHH,
Flota o Técnico. Solo envía el `alert_type`.

Python traduce:

- `ITV_EXPIRED` -> `FLOTA`
- `LICENSE_EXPIRING` -> `COMPRAS`
- `OFFBOARDING_PENDING` -> `RRHH`
- `MAINTENANCE_OVERDUE` -> `TECNICO`

Y luego consulta `alert_roles.json`:

```json
{
  "COMPRAS": {
    "teamsUserIds": ["11111111-1111-1111-1111-111111111111"],
    "emails": ["compras@empresa.com"]
  },
  "RRHH": {
    "teamsUserIds": ["22222222-2222-2222-2222-222222222222"],
    "emails": ["rrhh@empresa.com"]
  }
}
```

## Ejemplo real

BC envía:

```json
{
  "alert_type": "ITV_EXPIRED",
  "resource_no": "REC-00091",
  "criticality": "critical",
  "details": "La ITV del vehículo Ford Transit ha vencido el 2026-03-10.",
  "target_user_id": "66666666-6666-6666-6666-666666666666",
  "target_user_email": "juan@empresa.com",
  "company_id": "CRONUS"
}
```

Python hace esto:

1. `ITV_EXPIRED` -> rol `FLOTA`
2. `FLOTA` -> Sergio
3. `target_user_id` -> Juan
4. Destinatarios finales -> `Sergio + Juan`
5. El bot intenta mandarles Teams
6. Power Automate recibe el contexto completo para el correo, incluyendo los emails ya resueltos

## Qué pasa sin persistencia

Sin persistencia:

- el sistema sí sabe quién debería recibir la alerta
- pero el bot solo puede escribir por Teams si ya guarda la `ConversationReference`
- si el contenedor reinicia, esa referencia se pierde

Por eso, en el estado actual:

- `alert_roles.json` hace de tabla de configuración del bot
- Power Automate es el canal fiable para alertas
- el bot proactivo funciona mientras la instancia siga viva y conserve memoria

## Qué hay que rellenar

1. `orchestrator/config/alert_roles.json` con los Object IDs reales
2. Opcionalmente `ALERT_ROLE_*` en el entorno si quieres override
3. Si quieres proactivos por bot, cada usuario debe abrir chat con el bot al menos una vez

## Fase 1 de pruebas

Para pruebas funcionales iniciales se puede usar un unico correo de validacion.
En esta fase el proyecto queda preparado para redirigir todos los correos a:

- `lraga@grupobertolin.es`

Hay dos mecanismos activos:

1. `orchestrator/config/alert_roles.json` tiene ese correo en todos los roles
2. `PA_TEST_EMAIL_OVERRIDE` permite que tanto operaciones como alertas se redirijan a ese correo

Con esto:

- las alertas por correo llegan siempre al mismo buzón de pruebas
- las operaciones tambien pueden validarse sin depender del email real del empleado
