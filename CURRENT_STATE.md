# Estado actual de BSS Time Collection

Actualizado: 21 de octubre de 2026. Consolidación desde `988a9261fdff87dc70505691bf875e42aadc69a9`, descendiente de `96ddb8b`; incluye UI localizada actual. CORP ejecuta componentes en revisiones distintas. Inventario: [full-state-reconciliation-20261021.md](docs/deployment/full-state-reconciliation-20261021.md).

## Objetivo y arquitectura

Captura RFID/teclado local con transmisión asíncrona auditable a Oracle HCM Time and Labor. Oracle interpreta asistencia; BSS no calcula nómina/asistencia.

API FastAPI, web React/TypeScript, worker y PostgreSQL. Configuración, sesiones y eventos con snapshots se guardan en PostgreSQL. Perímetro por UID, sin conciliación de identidad personal ni accionamiento de barreras.

## Oracle

CORP mantiene `ORACLE_ENABLED=false` y `APP_SEED_DEFAULTS=false`. Sin transmisión a Oracle. Solo los eventos de célula pertenecen a la cola de transmisión; los movimientos perimetrales son `LOCAL_ONLY`, sin payload ni intentos Oracle.

Mappings explícitos; identidades de dispositivo limitadas a 40 caracteres, también en clones. `UNKNOWN` requiere conciliación; `REJECTED`, corregir la causa. Sin reenvío ciego.

## PostgreSQL y Alembic

PostgreSQL 16 conserva la base de datos y los volúmenes originales. Alembic vigente: `0011_action_visibility`, con políticas, estructura y perímetro incluidos. Importar la API no ejecuta DDL.

Conservar PGDATA anónimo `/var/lib/postgresql/data` y volumen `bsstimecollection_postgres_data`. Cambiar configuración no reescribe históricos/snapshots.

## Terminales e identidad

Estado conocido en ARGANDA: cinco terminales `CELL` (`ID001-1`, `T0001`–`T0004`) y `T0005`, «Main Entry», con rol `PERIMETER_BOTH`. Baja lógica, con históricos/códigos reservados.

CELL activo: una entrada y al menos una salida activas/visibles. **Perimeter only** elimina configuración de célula, acciones, estructura y atributos Oracle; desactiva su política. Roles: `PERIMETER_ENTER`, `PERIMETER_EXIT`, `PERIMETER_BOTH`. Convertir a CELL exige configuración válida; las puertas no crean directamente eventos de célula.

Cookie HttpOnly/SameSite=Strict, activación de un uso y pairing temporal. Reprovisión revoca sesión previa. Clones conservan configuración/fábrica/rol, sin identidad, tokens ni eventos. Autenticación temporal de Administración activa en CORP; pendiente gateway/autenticación definitiva.

## Factory Perimeter

La activación es **por fábrica**: ARGANDA está activada; DEFAULT sigue desactivada. Estado por fábrica. Selección persistida por URL/localStorage (URL prioritaria); asignaciones guardadas explícitas y protección contra respuestas antiguas/avisos contradictorios.

Con el perímetro activado, una entrada de célula requiere que el UID haya entrado antes en esa misma fábrica. La presencia solo usa UID. `OPEN` es el origen operativo; el conector SECURITY_DB `EXTERNAL` está desplegado en la imagen API, pero requiere credenciales read-only verificadas antes de activar la fábrica. La interfaz no presenta presencia local como autoritativa en modo EXTERNAL.

Salida perimetral estando dentro de célula: EXIT automático de célula seguido de EXIT perimetral, transacción/timestamp/correlation ID compartidos. Conserva contexto de la entrada original. Acción automática EXIT activa sin subacciones obligatorias; puede estar oculta.

Acción interna automática de ARGANDA conservada. Deduplicación UID/terminal según fábrica: BOTH evita alternancias por repetición; EXIT dedicada omite cooldown estando dentro. Advisory locks serializan fichajes por tarjeta.

## Actions y Sub-actions

16 motivos EXIT directos activos: nombres españoles, supplier events BSS ingleses y `visual_key` correspondiente. Asignados a cinco CELL; entrada `START_WORK` conservada, Main Entry excluido. Salidas antiguas ocultas/inactivas salvo la interna perimetral activa/oculta. Configuración PostgreSQL, sin importación automática desde Git.

`active`/`show_on_terminal` independientes; ocultas activas disponibles internamente, no al operario. Última entrada/salida protegida. Subacciones compatibles: el menú no registra, solo la razón final. Los 16 motivos actuales no exigen subacciones.

## Exit policies

Modos `DISABLED`, `SAME_TERMINAL`, `SAME_WORK_CELL` y override `INHERIT`. El ajuste global está en Policies; el override y `work_cell` se editan con cada terminal, también al crearlo. El estado global conocido es `DISABLED`; las puertas mantienen su política desactivada.

`work_cell`: recortado, sensible a mayúsculas, 64 caracteres; vacío elimina. SAME_WORK_CELL rechaza ausentes/diferentes. Scan/salida final revalidan; HTTP 409 sin evento/intento/cola. Guardado atómico. Detalle: [docs/exit-policies.md](docs/exit-policies.md).

## Monitoring

`/admin/cards` muestra estados independientes de célula y fábrica. El estado de célula procede del último TimeEvent; sin fichajes de célula es OUTSIDE. El estado de fábrica procede de la última dirección perimetral por UID/fábrica: sin entrada es OUTSIDE, y con perímetro desactivado es «No activado».

Columna/filtro de fábrica visibles si hay alguna activada. Filtros combinables, inicialmente Todos. Puede estar fuera de célula/dentro de fábrica. Último reloj/detalle y filtro de reloj corresponden a la última lectura combinada.

Eventos célula/perímetro con filtros, paginación y JSON histórico; perímetro «Solo local», sin preview Oracle. Registro propio de intentos. Refresh 15 s, sin asistencia validada por Oracle.

## RFID e interfaz de terminal

USB HID keyboard-wedge en `RFID`/`BOTH`, ventana activa; `KEYPAD` manual. UID cadena, conserva ceros iniciales; separadores espacio/Tab del lector se omiten. UID/método conservados en salida/subacción, debounce y bloqueo; sin captura en segundo plano. Detalle: [docs/rfid.md](docs/rfid.md). Fix de separadores desplegado en CORP 2026-10-21 solo en web; prueba RFID 26 pasada, API/worker/DB y volúmenes intactos, Oracle desactivado.

Interfaz en/es/fr/pl, con traducciones ampliadas de Administración y terminal incluidas en esta consolidación. Reloj HH:MM:SS local; confirmación congela `event_datetime` 2,2 s. Teclado hasta 620 px y administración responsive.

## Ilustraciones

**23 PNG locales** en `frontend/public/action-visuals/`: 16 motivos nuevos y 7 legacy. Catálogo compartido Admin/terminal, transparencia sobre cards claras. Compatibilidad anterior conservada; no eliminar visuales referenciables.

Claves nuevas: `bocadillo`, `comida`, `medico-empresa`, `formacion`, `no-productivo`, `comite-empresa`, `trabajo-fuera-fabrica`, `medico`, `viaje-empresa`, `examenes`, `mutua-accidente`, `comite-seguridad-salud`, `formacion-fuera-jornada`, `salida-sindical`, `huelga`, `acompanamiento-medico`.

Claves legacy: `end-work`, `break`, `factory`, `medical`, `personal`, `legal`, `no-work`. `visual_key` es opcional. Sin imágenes remotas.

## Despliegue CORP y guardrails

CORP `/opt/BSSTimeCollection`, web `http://10.33.137.103:8080`; GitHub main no incluye todavía todo el estado. PR #6 continúa abierto/draft; checkpoint `988a926` desciende de `96ddb8b` e incluye hardening, ODBC offline, autenticación temporal y etiquetado de imágenes. API source label `22ce771`, web `10df7ce`, worker `a414089+corp-corrections`; la web no incluye las traducciones actuales. Compose: `docker-compose.yml`, `docker-compose.issue2.yml`, `docker-compose.perimeter-corp.yml` y overlays temporales.

Backend actual 77/7 omitidos; frontend 41/build. API/web saludables, worker activo, PostgreSQL/volumen conservados. Evidencia histórica baseline: [docs/deployment/corp-github-sync-20261020.md](docs/deployment/corp-github-sync-20261020.md).

Preservar `.env`, configuración, terminales, sesiones, acciones, históricos y volúmenes. Backup verificable antes de cambios o migraciones. No usar `reset --hard`, borrar/recrear la base, renovar volúmenes anónimos ni ejecutar `down -v`. Validaciones con UIDs simulados en réplicas o APIs mockeadas; no generar fichajes reales ni transmitir a Oracle. No reasignar terminales ni activar fábricas implícitamente. Mantener fuera de GitHub credenciales, CSV personales, dumps y archivos locales de configuración.

Conector Arganda: servicio y ODBC Driver 18/pyodbc en la imagen API. Producción continúa en `OPEN` y desactivada; Oracle desactivado. El login SECURITY_DB probado tiene permisos DML y no sirve para montaje read-only. Obtener credenciales verificadas antes de activar `EXTERNAL`. `acc_zone_code` es `nvarchar`; timestamps naive en `Europe/Madrid`. EXIT físico requiere reconciliación aprobada para crear EXIT de célula. Véase [arganda-external-sqlserver.md](docs/arganda-external-sqlserver.md).

Métricas operativas: migración `0012_operational_metrics` y endpoint de agregados están en una rama local separada; no están en imagen ni base desplegadas. Mantener para revisión independiente, sin migrar en esta consolidación.

## Siguiente riesgo / backlog

**Monitoring multi-factory hardening:** actualmente `cell_state` se calcula por `reporter_id` en monitoring. Si una misma tarjeta puede operar en varias fábricas dentro de la misma instancia, deberá calcularse por `(reporter_id, factory_code)`. No es un bug operativo urgente para ARGANDA actual. El estado perimetral ya se calcula por UID/fábrica.

Pendientes: pruebas físicas, gateway/autenticación definitivos e identidad externa. Antes de habilitar Oracle: validar credenciales, mappings, conciliación/idempotencia y retención; CORP sin transmisión.
