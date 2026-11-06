# Estado actual de BSS Time Collection

Actualizado: 6 de noviembre de 2026. GitHub main incluye PR #48 (recuperación SQL Server ODBC), merge `12aaee8b835ec6c959a1140b13ad9547d65d3669`. La imagen productiva de API/worker es `bsstimecollection-api:odbc-oracle-safe-20261106` (digest `sha256:aa142b948cd813cedd594cd4f8715ab2a91015121476d6d796aa0f007a2340b1`). Validado: Microsoft ODBC Driver 18 disponible, pyodbc 5.2.0 operativo y API healthy. Registro: [ODBC runtime restoration](docs/deployment/odbc-runtime-restoration-20261106.md).

## Objetivo y arquitectura

Captura RFID/teclado local, eventos conservados en PostgreSQL y transmisión asíncrona/auditable a Oracle HCM Time and Labor. Oracle interpreta asistencia; BSS no calcula nómina/asistencia. API FastAPI, web React/TypeScript, worker y PostgreSQL.

## Oracle e integraciones

CORP transmite eventos operativos a Oracle (`ORACLE_ENABLED=true` en el worker, verificado el 5-nov-2026). La sobrecarga activa es `docker-compose.oracle-dev2-poc.yml`. Al renderizar Compose o recrear el worker, incluir esta sobrecarga además de los archivos operativos existentes; preservar `ORACLE_ENABLED=true`, mantener el worker en servicio y verificar que procesa la cola. No apagar Oracle ni dejar el worker detenido como precaución de despliegue. No crear ni transmitir eventos de prueba en producción: validaciones con UIDs sintéticos o mocks. No inventar mappings ni atributos Oracle; solo se usan los configurados explícitamente. Solo eventos de célula son elegibles para Oracle. Movimientos perimetrales son locales (`LOCAL_ONLY`), sin payload ni intentos Oracle.

Conector SQL Server de ARGANDA: la configuración habilitada y el SQL se validan con credencial SELECT-only; secretos de conector solo por montaje protegido. Eventos externos necesitan identidad canónica resoluble; reconciliación no resuelta debe quedar como aviso, sin inventar identidad/estado. Seguridad DB validada antes de activar lecturas productivas.

## PostgreSQL y despliegues

PostgreSQL 16 conserva datos/volumen originales; la base de producción quedó en Alembic `0026_securitydb_clock_correction` tras el despliegue del 5-nov. PR #47 añadió `0027_oracle_mapping_recovery_audit` a GitHub main; su migración requiere despliegue planificado con backup verificable. No cambiar volumen ni ejecutar `down -v`; preservar `.env`, configuración, terminales, acciones, sesiones e históricos. Antes de despliegues con API/migraciones, generar backup verificable. DDL no se ejecuta importando API.

Despliegue PR #46: API/web en revisión `6dc848753328ba25c411ce3ed3440a7a4dc5ebba`, healthy. Se aplicó Alembic 0026 tras backup verificable; logs y multi-clock verificados. Worker y PostgreSQL no recreados.

## Recuperación SQL Server ODBC — 6-nov-2026

PR #48 restaura runtime reproducible con manifiesto SHA-256 y recetas Docker offline/recovery que instalan unixODBC, Microsoft ODBC Driver 18 y pyodbc; API y worker comparten la imagen de recuperación. Los 20 binarios offline permanecen como inputs locales ignorados por Git; preparar el bundle antes del build. La imagen indicada arriba fue verificada en producción con driver disponible, import pyodbc operativo y API healthy. No crear fichajes de prueba.

## Incidente React 2026-11-03 — cerrado

PR #33 fijó las siete dependencias React/Vite/TypeScript al lockfile y Docker usa `npm ci`. CI y build pasaron; Chromium verificó `/terminal` y `/admin/events` sin errores. Web `frontend-reproducible-main-4da92de`; rollback `factory-presence-official-504b655`.

## Terminales e identidad

Estado conocido ARGANDA: CELL `ID001-1`, `T0001`–`T0004`; `T0005` Main Entry con rol `PERIMETER_BOTH`. Históricos y códigos se reservan; baja lógica. `Perimeter only` retira configuración celular, acciones/estructura/atributos Oracle y desactiva política. Roles perimetrales `PERIMETER_ENTER`, `PERIMETER_EXIT`, `PERIMETER_BOTH`. Convertir a CELL requiere configuración válida.

Cookie HttpOnly/SameSite=Strict, activación de un uso, pairing temporal; reprovisión revoca sesión anterior. Clones conservan configuración/rol, no identidad, tokens ni eventos. Autenticación de Administración temporal en CORP; gateway definitivo pendiente.

RFID HID en `RFID`/`BOTH`, lector en ventana activa; `KEYPAD` permite escritura física/pegado de dígitos y Enter. UID se conserva como string, incluidos ceros iniciales; separadores espacio/Tab del lector se ignoran. Debounce/bloqueo activos, sin escucha en segundo plano. Ver `docs/rfid.md`.

## Perímetro y estado de fábrica

Activación por fábrica: ARGANDA conocida enabled con origen `EXTERNAL`; DEFAULT disabled con origen `OPEN`. No activar/asignar fábricas implícitamente. Selección por URL/localStorage (URL prioritaria). Entrada celular bajo perímetro requiere entrada previa del mismo UID y fábrica. Estado local BSS no es autoritativo para movimientos externos hasta sincronizar.

Estado por fábrica sale de última dirección de perímetro para UID/fábrica; sin entrada = OUTSIDE, desactivada = No activado. Estado celular sale de último TimeEvent; sin fichajes de célula = OUTSIDE. Salida perimetral estando en célula produce EXIT celular y perimetral atómicos con timestamp/correlation compartidos. Locks serializan fichajes.

## Actions, estructura y políticas

16 motivos directos EXIT activos con nombres españoles, supplier events BSS en inglés y `visual_key`; asignados a cinco CELL. Entrada START_WORK conservada; Main Entry excluido. Acciones antiguas EXIT ocultas/inactivas salvo auto-EXIT perimetral interno activo/oculto. Configuración en PostgreSQL; Git no importa acciones automáticamente. `active` y `show_on_terminal` son independientes. Subacciones compatibles; actuales no las exigen.

Exit policy global conocida `DISABLED`; override `INHERIT`, `DISABLED`, `SAME_TERMINAL`, `SAME_WORK_CELL`. `work_cell` recortado, case-sensitive, máximo 64; faltante/distinto rechaza en SAME_WORK_CELL sin evento/cola (`409`).

## Monitoring

`/admin/cards` muestra estados celular/fábrica separados y filtros combinables. Logs celular/perímetro paginados con JSON histórico; perímetro es Solo local, sin preview Oracle. Registro separado de intentos. Refresh 15 s. No hay asistencia validada por Oracle.

## Release y backlog

GitLab `main` y `corp` se sincronizaron con GitHub main en checkpoint `25b16e80389d6ca4ac169945846ea814ee9c030a`; PR #6 sigue en draft para consolidación. PR #8 contiene checkpoint separado de métricas `0012_operational_metrics`; no desplegar/migrar sin revisión independiente. Métricas no desplegadas. Referencia: `docs/deployment/full-state-reconciliation-20261021.md`.

No cambiar la transmisión Oracle durante despliegues rutinarios: registrar el valor previo, preservarlo en API/worker y comprobar que el worker retoma el procesamiento y que la cola existente sigue su curso. Cambios deliberados requieren instrucciones operativas específicas. Pendientes: raíz/publicación verificable del fallo React de 2026-11-03; gateway/auth definitiva; pruebas físicas; identidad externa. Riesgo multi-factory: `cell_state` usa `reporter_id`; si una tarjeta trabaja en varias fábricas, calcular por `(reporter_id, factory_code)`.

Guardrails: validaciones con UIDs simulados o API mockeada; nunca crear eventos de prueba en producción. Preservar la transmisión Oracle durante despliegues rutinarios. No `reset --hard`, borrar/recrear BD, cambiar volúmenes anónimos ni incluir credenciales/CSV/dumps/archivos locales en GitHub.
