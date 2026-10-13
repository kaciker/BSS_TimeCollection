# Decisiones previas de administración e identidad

Detalles trasladados desde CURRENT_STATE el 12/10/2026 para conservar su límite. Las referencias a despliegues/rama anteriores son históricas; el estado vigente de Policies y esquema está en CURRENT_STATE y docs/deployment-policies-validation-2026-10-12.md.

## Supervisión implementada

Administración ofrece estado local por tarjeta, logs de fichajes y logs de transmisiones, con filtros por reloj/tarjeta, estado/entrega y fechas en fichajes, paginación y actualización cada 15 segundos. El estado se calcula globalmente antes de filtrar por último reloj. El detalle muestra el evento completo, preview Oracle y los JSON históricos reales de cada intento por separado. Véase README.md, «Administration monitoring». No modifica fichajes ni habilita Oracle.

## Idioma vigente

Toda la interfaz, los mensajes de API y los registros de eventos deben estar en inglés por decisión de Marcos. Posible interfaz multilingüe pendiente para el futuro; eventos siempre en inglés.

## Administración y configuración

Interfaz reorganizada con navegación lateral y cinco páginas independientes: cards, events, attempts, terminals, actions. Terminales: alta/edición de identidad, deviceId, método, disponibilidad y asignaciones en una operación. Acciones: alta/edición de etiquetas inglesas, código Oracle, efecto, orden, tipo de identificación, atributos y disponibilidad. Duplicados muestran errores claros. Se protege la configuración mínima de terminales activos (una entrada y al menos una salida) y se conservan snapshots históricos. El seed demo ya no sobrescribe asignaciones al reiniciar. Detalle en README.md, «Terminal and action configuration».

## Identidad web y contexto Oracle

Alembic 0002: cookie HttpOnly/SameSite=Strict, activation link /terminal/activate#TOKEN de un uso, ruta normal /terminal, reprovisión revoca sesión previa. reporterIdType y atributos Oracle extensibles se copian/mezclan al fichaje; UNKNOWN/REJECTED bloquean retry ciego. Oracle desactivado y TERMINAL_COOKIE_SECURE=false en HTTP local. Navegadores físicos requieren provisión explícita. Historial, backup y pruebas: `docs/deployment-validation-2026-10-09.md` (despliegue 544883e, 18 eventos preservados).

## Clonación de terminales

Administración permite Clone en terminales, con edición inmediata. Código y deviceId reciben sufijo numérico libre; PK nueva. Copia atributos Oracle/taller, reporterIdType, método, disponibilidad y asignaciones de acciones. No copia identidad de navegador, tokens, diagnósticos ni eventos; requiere aprovisionamiento independiente. API POST /api/v1/admin/terminals/{code}/clone; sin migración.

## Pairing, DB, subacciones e idiomas desplegados

Rama `feat/browser-pairing-code`, HEAD `2237cbf`, desplegada el 12 de octubre de 2026. Alembic en `0004_action_subactions`; 0003 añade pairing y 0004 jerarquía EXIT. El pairing convive con activation link y usa cookie HttpOnly; códigos temporales de un uso. Administration > Database muestra PostgreSQL local sin contraseña; test externo deshabilitado (`DATABASE_ADMIN_TEST_ENABLED=false` por defecto), DATABASE_URL intacta. Oracle sigue desactivado. Factory exit abre segundo nivel y solo la subacción final genera evento; las asignaciones históricas de MEDICAL como salida directa se mantienen utilizables. Idiomas en/es/fr/pl persistidos por navegador. Respaldo y validación: `docs/deployment-validation-2026-10-12.md`.

## Identidad visual web

Administración usa la marca horizontal Hutchinson BSS en la barra lateral; el símbolo Hutchinson es favicon común. La activación/pairing del navegador usa la marca horizontal y una tarjeta alineada con el diseño operativo. Formularios de pairing, activation link, Database e idioma tienen estilos y espaciados propios del sistema. Assets en `frontend/img/`, incluidos en la imagen web. Validación de frontend en navegador desktop/móvil el 12 de octubre de 2026.

La pantalla operativa del terminal muestra la marca Hutchinson BSS, identidad del reloj y teclado táctil. El 12/10 se amplió al 90 % del ancho de viewport, con altura mínima del 90 % y teclado adaptable hasta 620 px. Las teclas tienen fondo, borde y sombra más visibles; «Identification» queda arriba del panel. Comprobada a 320, 390, 768, 1280 y 1920 px sin desbordamiento horizontal; entrada simulada validada en 390 y 1280 px. En 320×568 el contenido necesita desplazamiento vertical para conservar botones táctiles utilizables. Solo se recreó `web`.

## Baja de terminales

Administration > Terminals ofrece Remove con confirmación. La baja lógica (`deleted_at`, Alembic 0005) oculta el terminal de configuración, lo desactiva y revoca cookie, activación y pairing aprobado; fichajes e intentos permanecen consultables. Código y deviceId quedan reservados para identidad histórica. API DELETE /api/v1/admin/terminals/{code}. Desplegado el 12/10/2026; copia previa en `/opt/backups/BSS_TimeCollection/20261012-terminal-removal/database.dump`.
