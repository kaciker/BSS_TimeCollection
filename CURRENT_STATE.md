# Estado y decisiones actuales

Actualizado: 12 de octubre de 2026.

## Objetivo y referencia

Proporcionar la captura de fichajes de fábrica mediante terminales RFID/tarjeta o identificación manual, persistir cada evento localmente y transmitirlo a Oracle HCM Time and Labor de forma asíncrona y auditable. Oracle conserva la responsabilidad sobre la interpretación funcional y el procesamiento T&A.

Los hechos y límites vigentes están en [FACTS.md](FACTS.md). Referencia de producto y arquitectura: [BSS_TimeCollection_Project_Context_Codex.pdf](docs/BSS_TimeCollection_Project_Context_Codex.pdf), MVP v0.1, 9 de octubre de 2026; leído completo, incluidas sus 11 páginas y dos diagramas.

## Decisiones pendientes según la referencia

- Modelo e interfaz del lector RFID.
- Autenticación integrada/gateway o propia.
- Tenant Oracle, acceso de red, credenciales y mappings definitivos.
- Atributos Oracle y estrategia de conciliación/idempotencia.
- Retención y archivo/purga de eventos e intentos técnicos.
- Semántica de transferencias entre puestos y posibles exportaciones Oracle hacia dispositivos.

Inspeccionar el repositorio y el despliegue real antes de implementar cambios; el documento describe una baseline histórica, no garantiza el estado operativo actual.

## Supervisión implementada

Administración ofrece estado local por tarjeta, logs de fichajes y logs de transmisiones, con filtros por reloj/tarjeta, estado/entrega y fechas en fichajes, paginación y actualización cada 15 segundos. El estado se calcula globalmente antes de filtrar por último reloj. El detalle muestra el evento completo, preview Oracle y los JSON históricos reales de cada intento por separado. Véase README.md, «Administration monitoring». No modifica fichajes ni habilita Oracle.

## Idioma vigente

Toda la interfaz, los mensajes de API y los registros de eventos deben estar en inglés por decisión de Marcos. Posible interfaz multilingüe pendiente para el futuro; eventos siempre en inglés.

## Administración y configuración

Interfaz reorganizada con navegación lateral y cinco páginas independientes: cards, events, attempts, terminals, actions. Terminales: alta/edición de identidad, deviceId, método, disponibilidad y asignaciones en una operación. Acciones: alta/edición de etiquetas inglesas, código Oracle, efecto, orden, tipo de identificación, atributos y disponibilidad. Duplicados muestran errores claros. Se protege la configuración mínima de terminales activos (una entrada y al menos una salida) y se conservan snapshots históricos. El seed demo ya no sobrescribe asignaciones al reiniciar. Detalle en README.md, «Terminal and action configuration».

## Identidad web y contexto Oracle desplegados

Actualización desde 08808c0 a 544883e, con correcciones de activación atómica ante concurrencia y copia de enlaces en HTTP. Alembic: 0002_terminal_identity_context (head). Runtime por cookie HttpOnly/SameSite=Strict; activación de un uso por /terminal/activate#TOKEN y URL normal /terminal. Reprovisión revoca sesión anterior. Terminales incluyen reporterIdType y oracle_attributes extensibles, copiados/mezclados con atributos de acción al fichaje. UNKNOWN/REJECTED bloquean retry ciego. Oracle sigue desactivado; HTTP local mantiene TERMINAL_COOKIE_SECURE=false. Backup previo, 18 fichajes históricos y configuración preservados. Evidencia y registros de prueba: docs/deployment-validation-2026-10-09.md. Los navegadores físicos existentes requieren aprovisionamiento explícito.

## Clonación de terminales

Administración permite Clone en terminales, con edición inmediata. Código y deviceId reciben sufijo numérico libre; PK nueva. Copia atributos Oracle/taller, reporterIdType, método, disponibilidad y asignaciones de acciones. No copia identidad de navegador, tokens, diagnósticos ni eventos; requiere aprovisionamiento independiente. API POST /api/v1/admin/terminals/{code}/clone; sin migración.

## Pairing, DB, subacciones e idiomas desplegados

Rama `feat/browser-pairing-code`, HEAD `2237cbf`, desplegada el 12 de octubre de 2026. Alembic en `0004_action_subactions`; 0003 añade pairing y 0004 jerarquía EXIT. El pairing convive con activation link y usa cookie HttpOnly; códigos temporales de un uso. Administration > Database muestra PostgreSQL local sin contraseña; test externo deshabilitado (`DATABASE_ADMIN_TEST_ENABLED=false` por defecto), DATABASE_URL intacta. Oracle sigue desactivado. Factory exit abre segundo nivel y solo la subacción final genera evento; las asignaciones históricas de MEDICAL como salida directa se mantienen utilizables mediante corrección local pendiente de publicar. Idiomas en/es/fr/pl persistidos por navegador. Respaldo y validación: `docs/deployment-validation-2026-10-12.md`.

## Identidad visual web

Administración usa la marca horizontal Hutchinson BSS en la barra lateral; el símbolo Hutchinson es favicon común. La activación/pairing del navegador usa la marca horizontal y una tarjeta alineada con el diseño operativo. Formularios de pairing, activation link, Database e idioma tienen estilos y espaciados propios del sistema. Assets en `frontend/img/`, incluidos en la imagen web. Validación de frontend en navegador desktop/móvil el 12 de octubre de 2026.

La pantalla operativa del terminal muestra la marca Hutchinson BSS, identidad del reloj y teclado táctil. El 12/10 se amplió al 90 % del ancho de viewport, con altura mínima del 90 % y teclado adaptable hasta 620 px. Las teclas tienen fondo, borde y sombra más visibles; «Identification» queda arriba del panel. Comprobada a 320, 390, 768, 1280 y 1920 px sin desbordamiento horizontal; entrada simulada validada en 390 y 1280 px. En 320×568 el contenido necesita desplazamiento vertical para conservar botones táctiles utilizables. Solo se recreó `web`.

## Baja de terminales

Administration > Terminals ofrece Remove con confirmación. La baja lógica (`deleted_at`, Alembic 0005) oculta el terminal de configuración, lo desactiva y revoca cookie, activación y pairing aprobado; fichajes e intentos permanecen consultables. Código y deviceId quedan reservados para identidad histórica. API DELETE /api/v1/admin/terminals/{code}. Desplegado el 12/10/2026; copia previa en `/opt/backups/BSS_TimeCollection/20261012-terminal-removal/database.dump`.

## Ilustraciones configurables

`main` desde b6a5799, desplegado el 12/10/2026 con Alembic `0006_action_visuals`. Actions y Sub-actions admiten `visual_key` opcional; Admin ofrece seis escenas SVG provisionales, servidas localmente desde la imagen web sin red externa. Se corrigió el Dockerfile para incluirlas y se amplió su tamaño en las tarjetas táctiles. No son obras oficiales de unDraw. Pruebas: 27 passed, 1 skipped; compilación React/TypeScript correcta. Copia previa en `/opt/backups/BSS_TimeCollection/20261012-action-visuals/`. Datos anteriores: 50 eventos, 0 intentos, 10 actions y 10 terminales; conservados tras el despliegue.

En terminales configurados solo para RFID, la pantalla de identificación muestra una tarjeta SVG grande y centrada, servida localmente desde `/img/rfid-card.svg`. Desplegado recreando solo `web` el 12/10/2026; compilación TypeScript/Vite y comprobación visual a 390 px correctas. El aviso de integración de hardware pendiente permanece visible.
