# Estado actual de BSS Time Collection

Actualizado: 20 de octubre de 2026. Baseline funcional: `98ea1f118166592be9376545cba292289b28acf7`, sincronizado entre CORP y GitHub `main`. Checkpoints históricos: [MEMORY.md](MEMORY.md) y [docs/deployment/](docs/deployment/).

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

Cookie HttpOnly/SameSite=Strict, activación de un uso y pairing temporal. Reprovisión revoca sesión previa. Clones conservan configuración/fábrica/rol, sin identidad, tokens ni eventos.

## Factory Perimeter

La activación es **por fábrica**: ARGANDA está activada; DEFAULT sigue desactivada. Estado por fábrica. Selección persistida por URL/localStorage (URL prioritaria); asignaciones guardadas explícitas y protección contra respuestas antiguas/avisos contradictorios.

Con el perímetro activado, una entrada de célula requiere que el UID haya entrado antes en esa misma fábrica. La presencia solo usa UID. `OPEN` es el origen disponible; `EXTERNAL` permanece sin implementar y se rechaza.

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

Interfaz en/es/fr/pl, etiquetas del catálogo. Reloj HH:MM:SS local; confirmación congela `event_datetime` 2,2 s. Teclado hasta 620 px y administración responsive.

## Ilustraciones

**23 PNG locales** en `frontend/public/action-visuals/`: 16 motivos nuevos y 7 legacy. Catálogo compartido Admin/terminal, transparencia sobre cards claras. Compatibilidad anterior conservada; no eliminar visuales referenciables.

Claves nuevas: `bocadillo`, `comida`, `medico-empresa`, `formacion`, `no-productivo`, `comite-empresa`, `trabajo-fuera-fabrica`, `medico`, `viaje-empresa`, `examenes`, `mutua-accidente`, `comite-seguridad-salud`, `formacion-fuera-jornada`, `salida-sindical`, `huelga`, `acompanamiento-medico`.

Claves legacy: `end-work`, `break`, `factory`, `medical`, `personal`, `legal`, `no-work`. `visual_key` es opcional. Sin imágenes remotas.

## Despliegue CORP y guardrails

CORP `/opt/BSSTimeCollection`, web `http://10.33.137.103:8080`; baseline publicado en `main`, sin correcciones pendientes. Compose: `docker-compose.yml`, `docker-compose.issue2.yml` y `docker-compose.perimeter-corp.yml`, con Dockerfiles offline y dependencias existentes.

Validación del baseline: backend 79/1 opcional omitido, frontend 40/build; JS/CSS y 23 PNG coinciden con CORP. Evidencia: [docs/deployment/corp-github-sync-20261020.md](docs/deployment/corp-github-sync-20261020.md).

Preservar `.env`, configuración, terminales, sesiones, acciones, históricos y volúmenes. Backup verificable antes de cambios o migraciones. No usar `reset --hard`, borrar/recrear la base, renovar volúmenes anónimos ni ejecutar `down -v`. Validaciones con UIDs simulados en réplicas o APIs mockeadas; no generar fichajes reales ni transmitir a Oracle. No reasignar terminales ni activar fábricas implícitamente. Administración limitada a la red/gateway corporativo; no tiene autenticación propia.

## Siguiente riesgo / backlog

**Monitoring multi-factory hardening:** actualmente `cell_state` se calcula por `reporter_id` en monitoring. Si una misma tarjeta puede operar en varias fábricas dentro de la misma instancia, deberá calcularse por `(reporter_id, factory_code)`. No es un bug operativo urgente para ARGANDA actual. El estado perimetral ya se calcula por UID/fábrica.

Pendientes: pruebas físicas, autenticación/gateway definitivo e identidad externa. Antes de habilitar Oracle: validar credenciales, mappings, conciliación/idempotencia y retención; CORP sin transmisión.
