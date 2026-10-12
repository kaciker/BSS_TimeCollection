# Memoria del proyecto

## 2026-10-09 — Objetivo confirmado y referencia leída

Marcos pidió guardar el objetivo en la memoria y en los facts del proyecto. Se crearon FACTS.md y CURRENT_STATE.md con el objetivo y los límites acordados: BSS es la capa de captura de fichajes de fábrica (TCD externo), persiste eventos antes de confirmar éxito y los entrega a Oracle HCM Time and Labor de forma asíncrona y auditable. Oracle interpreta los hechos y conserva la responsabilidad funcional de T&A. No convertir BSS en un segundo motor de asistencia, no alterar silenciosamente eventos históricos y no reenviar ciegamente entregas ambiguas.

Se leyó completo docs/BSS_TimeCollection_Project_Context_Codex.pdf: 11 páginas, 13 secciones, dos diagramas y apéndices A/B. Documento baseline MVP v0.1 del 9 de octubre de 2026; consultar FACTS.md para hechos vigentes y CURRENT_STATE.md para decisiones pendientes. La disponibilidad operativa debe comprobarse contra la infraestructura real.

## 2026-10-09 — Vistas de supervisión

A petición de Marcos se añadieron vistas separadas de estado de tarjetas, fichajes y transmisiones a /admin. Filtros por reloj primero y tarjeta; estado local global antes de filtrar terminal, paginación y detalle de evento con datos Oracle previstos frente a payloads reales guardados de cada intento. Backend: 5 tests pasan; frontend TypeScript/Vite compila. Cambio desplegado sobre la instalación existente sin modificar los registros históricos ni activar Oracle. Referencia: README.md, Administration monitoring.

Validación en navegador del despliegue: filtros por reloj/tarjeta y fechas, estado fuera para 12345, detalle de payload previsto sin intentos e historial de tarjeta funcionan sin errores JavaScript. Endpoint ready y configuración del terminal responden; ORACLE_ENABLED sigue false. Se ajustó la cabecera para evitar desbordamiento en móvil. Cambios aún sin commit/push.

## 2026-10-09 — Inglés como idioma del producto

Marcos solicita todos los menús y registros de eventos en inglés, dejando posibles menús multilingües para el futuro. Se tradujeron supervisión, filtros, detalle, mensajes de API y formato de fechas (en-GB). Se verificó en DB que acciones y etiquetas históricas ya estaban en inglés; no fue necesario cambiar eventos guardados.

## 2026-10-09 — Reorganización profesional de administración

Marcos solicita separar eventos, terminales y acciones, corregir alta de terminal y permitir crear/editar acciones. Diagnóstico: deviceId duplicado producía IntegrityError/HTTP 500; formulario accedía a event.currentTarget después de await y podía fallar antes de refrescar. Se sustituyó por navegación lateral con páginas separadas, listas filtrables y diálogos de edición con validación y feedback. Nuevos PUT de terminales/acciones, alta con asignaciones atómicas y conflictos 409 legibles; se preservan snapshots históricos. Se corrigió bootstrap para no reasignar acciones demo en cada arranque.

Validación: 10 tests backend; frontend TypeScript/Vite compila. Instalación temporal aislada en 8093: alta/edición terminal, deviceId duplicado, alta/edición acción, JSON inválido, asignación nueva, persistencia tras reinicio, fichajes alternados y salida en otro reloj, historial filtrado y móvil 390px sin desbordamiento. Datos de prueba separados de la DB real. Sin commit/push.

Despliegue final verificado en 8092: cinco secciones separadas, diálogos de terminal/acción, detalle de eventos y recarga directa de rutas funcionan sin errores JavaScript. API/DB/web saludables, ready correcto y Oracle sigue desactivado. Instalación de validación temporal retirada al completar las pruebas.

## 2026-10-09 — Despliegue de identidad de terminal y contexto Oracle

Marcos autoriza actualizar a main (referencia 544883e), respaldar, migrar y validar end-to-end, corrigiendo/confirmando/publicando el bloque estable. Backup DB/config/.env en /opt/backups/BSS_TimeCollection/20261009T204740Z-terminal-identity. Migración 0002 aplicada sin recrear DB. .env original conservado, añadidos Secure=false y sesión 365 días; Oracle sigue false.

Se reprodujo doble consumo concurrente de token (2 éxitos/8 peticiones) y corrigió con lock PostgreSQL en activación/provisión. Se corrigió copia de enlace en HTTP mediante fallback. 15 tests pasan contra entorno PostgreSQL aislado, incluyendo 5 rondas concurrentes; frontend build/Compose correctos. Navegador real: edición de atributos, activación one-shot, cookie HttpOnly, URL /terminal, revocación previa, entrada/salida y monitoring. Payload generado incluye atributos fusionados y reporterIdType de terminal. Se compararon las 18 filas históricas y configuración original sin diferencias. Informe: docs/deployment-validation-2026-10-09.md.

## 2026-10-09 — Clonar terminal

Marcos solicita clonación con índices en IDs críticos y copia del taller/elecciones del reloj para edición posterior. Se implementa asignación servidor de sufijos -1, -2, etc. comprobando código/deviceId; copia configuración y asociaciones de acciones y abre editor. Sesión original intacta, clon sin tokens ni historial. Backup previo /opt/backups/BSS_TimeCollection/20261009T212241Z-terminal-clone. Tests: 17 pasan (integración de activación concurrente opt-in no ejecutada en esta suite); compilación frontend y Compose correctos. Sin migración.

Validación navegador en instancia real: Clone de TEST-PROVISION-20261009 generó código y deviceId TEST-PROVISION-20261009-1, abrió editor y guardó nombre/contexto propios. Asignaciones copiadas; fuente y sesión original sin cambios; clon no aprovisionado. Backend ready tras despliegue.

## 2026-10-12 — Despliegue de pairing y subacciones

Rama feat/browser-pairing-code en 2237cbf, backup /opt/backups/BSS_TimeCollection/20261012T175050Z-browser-pairing, migraciones 0003/0004 aplicadas sin recrear DB. 29 eventos y 6 terminales históricos preservados. Se corrigió localmente compatibilidad de MEDICAL como salida directa en terminales antiguos sin FACTORY_EXIT asignada. Tests 24 pass/1 skip, build frontend y smoke real satisfactorios. El cambio local y dos imágenes no versionadas quedan pendientes de revisión Git. Informe: docs/deployment-validation-2026-10-12.md.

Marcos pide pulir las pantallas nuevas con el estilo existente y aplicar logos `frontend/img/logobig.png` y `hutchinson_logo.png`. Se integraron en navegación, activación y favicon; se estilizaron pairing, enlace, idioma y DB. Build web y comprobación visual desktop/móvil correctos. No se modificó la DB ni la configuración runtime.

Marcos pide también rediseñar pantalla operativa del terminal. Se añade logobig en cabecera, tipografía y espaciados responsivos, teclado y opciones EXIT adaptados a móvil. Build web correcto; navegador a 320/390/768/1280 px sin overflow; entrada/salida real verificada con badge de prueba `1` en terminal de prueba. Solo web recreado.

Tras el fallo 403 de CodexLLM en el hilo anterior, se retomó la petición pendiente de ampliar el terminal al 90 % de pantalla. El CSS limita el ancho a 90vw y da al contenedor una altura mínima de 90dvh; el panel crece y el teclado llega a 620 px. Imagen web reconstruida y solo `web` recreado. Playwright con API simulada verificó 320×568, 390×844, 768×1024, 1280×720 y 1920×1080 sin desbordamiento horizontal; en móvil 390 y escritorio 1280 el botón Continuar está visible y el flujo simulado responde. En 320×568 hace falta scroll vertical por la altura de los controles.

Marcos pidió aumentar el contraste de las teclas y subir «Identification». Se cambió el fondo/borde/sombra de cada tecla y el panel dejó de centrar verticalmente su contenido. Build web y recreación exclusiva de `web` correctos. Playwright con configuración simulada verificó la posición superior de la etiqueta, el estilo efectivo de las teclas y ausencia de desbordamiento horizontal a 320, 390, 768 y 1280 px.
12/10/2026: Se añadió baja lógica de terminales (Remove, Alembic 0005), revocando identidad web y pairing aprobado, conservando eventos e intentos y reservando código/deviceId. Suite: 26 passed, 1 skipped. Backup previo: `/opt/backups/BSS_TimeCollection/20261012-terminal-removal/database.dump`.
2026-10-12: Despliegue de b6a5799 (ilustraciones Actions/Sub-actions). Backup de PostgreSQL y configuración en `/opt/backups/BSS_TimeCollection/20261012-action-visuals/`. Se corrigió `frontend/Dockerfile` para copiar los SVG a la imagen y se ampliaron imágenes/tarjetas. Alembic 0006 aplicado; 27 tests passed, 1 skipped; build TypeScript/Vite correcto. HTTP confirmó seis SVG locales y persistencia/reversión de `visual_key`. Los SVG son originales provisionales, no unDraw.
2026-10-12: A petición de Marcos se añadió dibujo SVG de tarjeta al centro de la pantalla RFID-only, empaquetado en web. Build TypeScript/Vite y HTTP 200 del asset confirmados; navegador a 390 px sin overflow. Solo se recreó web.
