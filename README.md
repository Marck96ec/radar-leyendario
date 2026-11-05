# Radar Leyendario IA

Radar Leyendario IA es un backend independiente en Python que ejecuta un grafo
LangGraph para recolectar fuentes, normalizar eventos, detectar señales,
validar evidencias, generar oportunidades y clasificarlas. El servicio está
preparado para ejecutarse en Docker junto a n8n y Automation Core; no contiene
un servidor MCP y no publica directamente en redes sociales.

## Arquitectura

```text
n8n (red Docker n8n_internal)
        |
        | http://radar:8000
        v
Radar / FastAPI
  ├─ API /health y /api/v1/radar
  ├─ LangGraph: collect -> normalize -> cluster -> signals
  │              -> evidence -> opportunities -> rank
  ├─ proveedores RSS configurados por RSS_FEEDS
  ├─ OpenAI opcional para ejecuciones con fuentes
  └─ SQLiteRunRepository (puerto reemplazable por PostgreSQL)
```

El grafo existente y sus fórmulas de ranking se conservan. La persistencia
guarda el estado completo de la ejecución y permite consultar resultados aun
después de reiniciar el contenedor. La implementación SQLite es adecuada para
una instancia; para varias réplicas se debe implementar el mismo puerto de
repositorio sobre PostgreSQL antes de escalar horizontalmente.

## Requisitos

- Python 3.12 para desarrollo local.
- Docker Engine y Compose v2 para despliegue.
- Una red Docker externa llamada `n8n_internal` si se integra con n8n.
- `OPENAI_API_KEY` solamente para ejecuciones con fuentes que necesiten el LLM.
- No se necesita una base de datos adicional para la primera versión.

## Variables de entorno

Copiar `.env.example` a `.env` y sustituir los valores de ejemplo. `.env` no
se versiona ni se incluye en la imagen.

| Variable | Requerida en producción | Descripción |
| --- | --- | --- |
| `OPENAI_API_KEY` | Sí para fuentes con LLM | Secreto de OpenAI; nunca se escribe en logs. |
| `LLM_MODEL` | Sí para fuentes con LLM | Modelo usado por el proveedor OpenAI. |
| `RSS_FEEDS` | Recomendada | Array JSON de objetos `name`, `url` y `source_type` (`OFFICIAL`, `MEDIA` o `COMMUNITY`). |
| `RSS_TIMEOUT_SECONDS` | No | Timeout por fuente, entre 0 y 120 segundos; por defecto 15. |
| `RADAR_API_KEY` | Sí | Clave interna enviada como `X-Radar-API-Key` para `/api/v1/radar/*`. |
| `ENVIRONMENT` | Sí | Usar `production` en VPS; producción sin `RADAR_API_KEY` queda bloqueada. |
| `RUNS_DATABASE_PATH` | No | Ruta SQLite; en Compose es `/app/data/radar_runs.sqlite3`. |
| `LOG_LEVEL` | No | Nivel de logging; por defecto `INFO`. |

Ejemplo de `RSS_FEEDS`:

```json
[
  {
    "name": "Google AI",
    "url": "https://blog.google/technology/ai/rss/",
    "source_type": "OFFICIAL"
  },
  {
    "name": "GitHub AI & ML",
    "url": "https://github.blog/ai-and-ml/feed/",
    "source_type": "OFFICIAL"
  }
]
```

Las URLs deben ser absolutas y usar HTTP o HTTPS. Una entrada inválida impide
construir el proveedor, en vez de iniciar silenciosamente con una fuente
incorrecta. Los errores de red, timeout y parser se registran por fuente y se
exponen en `metadata.source_failures` de la ejecución; no se fabrican noticias
ni evidencias.

## Desarrollo local

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

En desarrollo, si `RADAR_API_KEY` está vacío, la API permite las llamadas para
facilitar pruebas locales. En producción la clave es obligatoria. El endpoint
de salud no necesita autenticación.

## API

### Salud

```bash
curl -i http://localhost:8000/health
```

Respuesta estable:

```json
{"status":"ok","service":"radar-leyendario"}
```

### Ejecutar Radar

```bash
curl -X POST http://localhost:8000/api/v1/radar/run \
  -H 'Content-Type: application/json' \
  -H 'X-Radar-API-Key: <RADAR_API_KEY>' \
  -d '{}'
```

El body puede incluir un UUID generado por el cliente:

```json
{"run_id":"8d9f4f9a-3bd6-49bb-8e4d-b8c32e2bc320"}
```

Enviar el mismo `run_id` después de un timeout de red devuelve la ejecución
persistida en lugar de lanzar otra. Los estados son `running`, `completed` y
`failed`. En la ejecución síncrona normal se devuelve `completed`; el
identificador permite consultar el resultado de forma independiente.

### Recuperar una ejecución

```bash
curl -H 'X-Radar-API-Key: <RADAR_API_KEY>' \
  http://localhost:8000/api/v1/radar/runs/<run_id>
```

### Listar oportunidades

```bash
curl -H 'X-Radar-API-Key: <RADAR_API_KEY>' \
  http://localhost:8000/api/v1/radar/runs/<run_id>/opportunities
```

También se puede recuperar una oportunidad:

```bash
curl -H 'X-Radar-API-Key: <RADAR_API_KEY>' \
  http://localhost:8000/api/v1/radar/runs/<run_id>/opportunities/<opportunity_id>
```

Cada oportunidad devuelve el identificador, título, descripción, `why_now`,
categoría, puntuaciones del dominio, puntuación final, evidencias y fuentes
trazables. Si el dominio no tiene un dato, la API conserva `null` o una lista
vacía; no estima valores faltantes.

Errores relevantes:

- `401`: falta o no coincide `X-Radar-API-Key`.
- `404`: ejecución u oportunidad inexistente.
- `409`: la ejecución todavía no tiene estado final para consultar el detalle.
- `422`: UUID o body inválido.
- `500`: la ejecución falló; consultar los logs usando `run_id`.
- `503`: configuración insegura en producción, normalmente falta
  `RADAR_API_KEY`.

## Docker y Compose

La imagen usa Python 3.12, una etapa de construcción para dependencias, un
usuario no root (`radar`) y escucha internamente en el puerto 8000. Compose no
publica `8000` en el host: el servicio sólo es accesible por la red externa
`n8n_internal` con `http://radar:8000`. Los logs salen por stdout/stderr y
Compose reinicia el servicio con `unless-stopped`.

Prueba local:

```powershell
Copy-Item .env.example .env
docker compose build
docker compose up -d
docker compose ps
docker compose logs -f radar
```

Para una integración n8n local, crear la red antes de iniciar Compose:

```powershell
docker network create n8n_internal
docker compose up -d
```

Si la red ya pertenece al stack de n8n, no se debe recrear ni modificar ese
stack desde este repositorio.

## Workflow n8n recomendado

El flujo mínimo es:

```text
Manual Trigger
  -> HTTP Request (POST http://radar:8000/api/v1/radar/run)
  -> Consultar resultado (GET /api/v1/radar/runs/{run_id})
  -> Validar oportunidades (IF/status + campos requeridos)
```

Configuración del primer HTTP Request:

1. URL `http://radar:8000/api/v1/radar/run`.
2. Método `POST`.
3. Header `X-Radar-API-Key` desde una credencial/variable segura de n8n.
4. Body JSON `{}` o un `run_id` UUID generado una sola vez por ejecución.

Guardar `run_id` de la respuesta en el contexto del workflow. El nodo de
consulta debe tratar `running` como espera/reintento con backoff y detenerse
en `completed` o `failed`. Repetir el POST con el mismo `run_id` es seguro;
crear un UUID nuevo no lo es porque representa una ejecución nueva.

La validación debe comprobar al menos `status == completed`, que la respuesta
de oportunidades sea una lista y que cada evidencia tenga una fuente. La
publicación en redes sociales no forma parte de este flujo: cualquier acción
externa debe requerir aprobación humana y gestionarse posteriormente a través
de Social Core.

## Contratos para Automation Core y MCP futuro

Automation Core puede integrar estas capacidades sin duplicar la lógica del
grafo. El MCP existente será quien publique posteriormente las herramientas:

| Herramienta | Entrada | Salida | Permiso/condición |
| --- | --- | --- | --- |
| `radar.run` | `run_id` UUID opcional, configuración ya validada | `run_id`, estado y conteos | `radar:run`; operación costosa, requiere API key |
| `radar.get_run` | `run_id` UUID | estado, duración, trazabilidad y errores | `radar:read` |
| `radar.list_opportunities` | `run_id` UUID | oportunidades con evidencias y fuentes | `radar:read`; sólo estado final |
| `radar.get_opportunity` | `run_id`, `opportunity_id` UUID | oportunidad trazable | `radar:read` |

Errores deben conservar el status HTTP y un `detail` seguro. Las credenciales
se inyectan en Automation Core/n8n; no se pasan al LLM ni se escriben en
prompts. No se debe implementar otro servidor MCP dentro de Radar.

## Observabilidad y fallos

Los logs son JSON y contienen timestamp UTC, nivel, logger y, cuando existe,
`run_id`, duración, conteos y fuente. Las claves y otros secretos no se
incluyen. Cada ejecución persiste duración, trace de nodos, conteos, errores y
fallos RSS. El estado del proveedor RSS se reinicia por fetch para que el
diagnóstico corresponda a esa ejecución.

El healthcheck sólo confirma que el proceso HTTP responde. No declara que
OpenAI o todas las fuentes RSS estén disponibles; esos fallos aparecen en la
ejecución y sus logs.

## Pruebas y CI

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m compileall -q app
docker build -t radar-leyendario:local .
```

GitHub Actions instala las dependencias, ejecuta `compileall` y pytest, y
construye la imagen. Un `workflow_dispatch` puede habilitar publicación en
GHCR con el `GITHUB_TOKEN`; no despliega a producción ni cambia credenciales.

## Despliegue en Hetzner

Comandos concretos en el VPS:

```bash
cd /home/deploy/apps/radar-leyendario
git pull --ff-only origin main
cp .env.example .env  # sólo la primera vez; editar con secretos reales
mkdir -p data
docker network inspect n8n_internal >/dev/null 2>&1 || docker network create n8n_internal
docker compose build --pull
docker compose up -d --remove-orphans
docker compose ps
curl -fsS http://radar:8000/health
docker compose logs --tail=100 radar
```

El `curl` anterior debe ejecutarse desde un contenedor conectado a
`n8n_internal` (por ejemplo, n8n). Desde el host, se puede comprobar el estado
con `docker compose ps` y `docker inspect --format '{{.State.Health.Status}}'`
sobre el contenedor.

Para una actualización:

```bash
cd /home/deploy/apps/radar-leyendario
git fetch origin
git pull --ff-only origin main
docker compose build --pull
docker compose up -d --remove-orphans
docker compose ps
```

Rollback manual:

```bash
cd /home/deploy/apps/radar-leyendario
git log --oneline -5
git checkout <commit-conocido>
docker compose build --pull
docker compose up -d --remove-orphans
```

Antes de un rollback se debe respaldar `data/radar_runs.sqlite3` y confirmar
que el esquema sea compatible. No hay despliegue automático ni rollback
automático en este repositorio.

## Limitaciones conocidas y próximos pasos

- SQLite funciona para una instancia y persiste en el volumen `./data`; para
  varias réplicas se requiere un adaptador PostgreSQL y estrategia de
  migraciones.
- El endpoint de ejecución es síncrono: n8n debe aplicar timeout y reintentos
  con el mismo `run_id`. Un worker/cola es una evolución posterior, no se
  simula en esta versión.
- El dominio actual no tiene un campo separado para un “problema”; la API
  expone el título como `problem_or_opportunity` y no inventa un problema.
- La disponibilidad real de cada RSS depende del proveedor externo. No se
  sustituyen fuentes sin resultados por contenido generado.
- No hay publicación social, MCP duplicado ni despliegue productivo automático.

Siguientes pasos recomendados: probar fuentes reales desde el VPS, integrar
Automation Core con los cuatro contratos, añadir aprobación humana en Social
Core y decidir la migración del repositorio de ejecuciones a PostgreSQL antes
de desplegar más de una réplica.
