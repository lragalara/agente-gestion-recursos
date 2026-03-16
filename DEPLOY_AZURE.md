# Guía de Despliegue en Azure

Pasos para desplegar el agente en producción con Azure Container Apps y Azure Bot Service.

---

## Prerrequisitos

- Suscripción de Azure activa
- [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli) instalado y autenticado (`az login`)
- Docker instalado localmente
- Acceso al BC On-Premise con OData v4 habilitado

---

## 1. Variables de entorno de Azure

Define estas variables para reutilizarlas en los comandos:

```bash
export RG=rg-agente-recursos
export LOCATION=westeurope
export ACR_NAME=acragenterecursos          # Nombre único sin guiones
export APP_ENV=env-agente-recursos
export APP_NAME=orchestrator
export BOT_NAME=bot-agente-recursos
```

---

## 2. Crear Resource Group

```bash
az group create --name $RG --location $LOCATION
```

---

## 3. Crear Azure Container Registry (ACR)

```bash
az acr create \
  --resource-group $RG \
  --name $ACR_NAME \
  --sku Basic \
  --admin-enabled true

# Login al registry
az acr login --name $ACR_NAME
```

---

## 4. Build y push de la imagen

```bash
# Build local
docker build -t $ACR_NAME.azurecr.io/orchestrator:latest ./orchestrator

# Push al registry
docker push $ACR_NAME.azurecr.io/orchestrator:latest
```

O usando ACR Tasks (sin Docker local):

```bash
az acr build \
  --registry $ACR_NAME \
  --image orchestrator:latest \
  ./orchestrator
```

---

## 5. Crear el entorno de Container Apps

```bash
az containerapp env create \
  --name $APP_ENV \
  --resource-group $RG \
  --location $LOCATION
```

---

## 6. Crear el Container App

```bash
# Obtener credenciales del ACR
ACR_SERVER=$(az acr show --name $ACR_NAME --query loginServer -o tsv)
ACR_USER=$(az acr credential show --name $ACR_NAME --query username -o tsv)
ACR_PASS=$(az acr credential show --name $ACR_NAME --query "passwords[0].value" -o tsv)

az containerapp create \
  --name $APP_NAME \
  --resource-group $RG \
  --environment $APP_ENV \
  --image $ACR_SERVER/orchestrator:latest \
  --registry-server $ACR_SERVER \
  --registry-username $ACR_USER \
  --registry-password $ACR_PASS \
  --target-port 8000 \
  --ingress external \
  --min-replicas 1 \
  --max-replicas 3 \
  --cpu 0.5 \
  --memory 1.0Gi
```

Anota la URL del Container App:

```bash
APP_URL=$(az containerapp show \
  --name $APP_NAME \
  --resource-group $RG \
  --query properties.configuration.ingress.fqdn -o tsv)
echo "URL: https://$APP_URL"
```

---

## 7. Configurar variables de entorno en el Container App

```bash
az containerapp update \
  --name $APP_NAME \
  --resource-group $RG \
  --set-env-vars \
    BC_MODE=live \
    BC_TENANT_MODE=fixed \
    BC_COMPANY_ID=NOMBRE_EMPRESA \
    AZURE_OPENAI_ENDPOINT=https://tu-recurso.openai.azure.com/ \
    AZURE_OPENAI_KEY=secretref:openai-key \
    AZURE_OPENAI_DEPLOYMENT=gpt-4o-mini \
    AZURE_OPENAI_API_VERSION=2024-02-01 \
    BOT_APP_ID=tu-app-id \
    BOT_APP_PASSWORD=secretref:bot-password \
    BC_GATEWAY_URL=https://tu-gateway/ODataV4 \
    BC_ODATA_USER=tu_usuario \
    BC_ODATA_PASSWORD=secretref:bc-password \
    PA_NOTIFY_FLOW_URL=secretref:pa-notify-url
```

> **Nota:** Para los secretos usa `secretref:nombre-secreto` y configúralos con:
> ```bash
> az containerapp secret set \
>   --name $APP_NAME \
>   --resource-group $RG \
>   --secrets \
>     openai-key=valor_real \
>     bot-password=valor_real \
>     bc-password=valor_real \
>     pa-notify-url=url_completa_del_flow_notificaciones
> ```
> La URL de Power Automate contiene una firma SAS en los query params. Trátarla como un secreto.

---

## 8. Crear App Registration en Entra ID para el bot

```bash
# Crear la app registration
az ad app create \
  --display-name "Agente Gestión Recursos" \
  --sign-in-audience AzureADMultipleOrgs

# Anotar el appId generado
BOT_APP_ID=$(az ad app list --display-name "Agente Gestión Recursos" --query "[0].appId" -o tsv)
echo "BOT_APP_ID: $BOT_APP_ID"

# Crear secreto de cliente
az ad app credential reset --id $BOT_APP_ID --display-name "bot-secret"
# Copia la contraseña generada → BOT_APP_PASSWORD
```

---

## 9. Crear Azure Bot Service

```bash
az bot create \
  --resource-group $RG \
  --name $BOT_NAME \
  --kind registration \
  --app-type MultiTenant \
  --appid $BOT_APP_ID \
  --endpoint "https://$APP_URL/api/messages" \
  --sku F0
```

> El tier F0 (gratuito) tiene límite de 10.000 mensajes/mes. Usa S1 para producción.

---

## 10. Activar canal Microsoft Teams

Desde el [portal de Azure](https://portal.azure.com):

1. Navega a tu recurso **Azure Bot** (`bot-agente-recursos`)
2. En el menú lateral, selecciona **Channels**
3. Haz clic en **Microsoft Teams**
4. Acepta los términos y haz clic en **Apply**

### Aprobar la app en el catálogo corporativo de Teams

1. En el portal de Teams Admin Center, ve a **Teams apps > Manage apps**
2. Busca el bot por nombre o ID
3. Cambia el estado a **Allowed**
4. Para distribuir a toda la organización: **Publish > Publish to org**

---

## 11. Conectar con BC On-Premise real

Cuando el OData de BC esté disponible vía On-premises Data Gateway:

```bash
az containerapp update \
  --name $APP_NAME \
  --resource-group $RG \
  --set-env-vars \
    BC_MODE=live \
    BC_GATEWAY_URL=https://tu-gateway.azure.com/ruta/ODataV4 \
    BC_ODATA_USER=usuario_bc \
    BC_ODATA_PASSWORD=secretref:bc-password \
    BC_COMPANY_ID=NOMBRE_EMPRESA_REAL
```

Verifica conectividad:

```bash
curl https://$APP_URL/companies
```

---

## Multi-empresa

### Modo `select` (el bot pregunta al inicio)

```bash
az containerapp update \
  --name $APP_NAME \
  --resource-group $RG \
  --set-env-vars BC_TENANT_MODE=select
```

### Modo `auto` (por grupos de Entra ID)

1. Crea grupos en Entra ID con el prefijo `BC-`:
   - `BC-CRONUS` → acceso a empresa CRONUS
   - `BC-EMPRESA2` → acceso a empresa EMPRESA2

2. Asigna los empleados a sus grupos correspondientes

3. Actualiza la variable:

```bash
az containerapp update \
  --name $APP_NAME \
  --resource-group $RG \
  --set-env-vars BC_TENANT_MODE=auto
```

4. Asegúrate de que el Bot tiene permisos `GroupMember.Read.All` en la App Registration
   para poder leer los grupos del usuario vía Microsoft Graph.

---

## Verificación del despliegue

```bash
# Health check
curl https://$APP_URL/health

# Listar empresas
curl https://$APP_URL/companies

# Probar el agente (si BC_MODE=mock)
curl -X POST https://$APP_URL/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Hola, ¿qué recursos hay disponibles?", "user_id": "test"}'
```

---

## Actualizar la imagen

Para desplegar una nueva versión:

```bash
# Build y push
docker build -t $ACR_SERVER/orchestrator:latest ./orchestrator
docker push $ACR_SERVER/orchestrator:latest

# Forzar redeploy
az containerapp update \
  --name $APP_NAME \
  --resource-group $RG \
  --image $ACR_SERVER/orchestrator:latest
```
