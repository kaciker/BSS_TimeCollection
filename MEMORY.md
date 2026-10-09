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
