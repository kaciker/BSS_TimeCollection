# Estado y decisiones actuales

Actualizado: 13 de octubre de 2026.

## Objetivo y referencia

Proporcionar la captura de fichajes de fábrica mediante terminales RFID/tarjeta o identificación manual, persistir cada evento localmente y transmitirlo a Oracle HCM Time and Labor de forma asíncrona y auditable. Oracle conserva la responsabilidad sobre la interpretación funcional y el procesamiento T&A.

Los hechos y límites vigentes están en [FACTS.md](FACTS.md). Referencia de producto y arquitectura: [BSS_TimeCollection_Project_Context_Codex.pdf](docs/BSS_TimeCollection_Project_Context_Codex.pdf), MVP v0.1, 9 de octubre de 2026; leído completo, incluidas sus 11 páginas y dos diagramas.

## Decisiones pendientes según la referencia

Lector RFID, autenticación/gateway, tenant/credenciales/mappings Oracle, conciliación/idempotencia, retención y semántica de transferencias/exportaciones siguen pendientes. Inspeccionar repositorio e infraestructura antes de implementar: la referencia es histórica.

## Administración, identidad y operación

Decisiones y detalles conservados en `docs/administration-decisions.md`; arquitectura y validaciones en README y `docs/deployment-validation-2026-10-09.md` / `docs/deployment-validation-2026-10-12.md`.

Administración ofrece estado global por tarjeta, logs/paginación/filtros, JSON históricos y refresh de 15 s; no interpreta asistencia Oracle. Configuración de terminales/actions atómica, duplicados claros, un ENTER y al menos una salida en terminal activo, snapshots preservados y seed sin sobrescribir asignaciones. Clone copia configuración/asignaciones, no identidad/tokens/eventos; requiere provisión nueva. Remove es baja lógica, revoca identidad y conserva históricos/códigos reservados (0005).

Identidad por cookie HttpOnly/SameSite=Strict, activation link de un uso y pairing temporal; reprovisión revoca sesión anterior. HTTP local usa TERMINAL_COOKIE_SECURE=false. reporterIdType y atributos terminal/action se copian/mezclan al fichaje; UNKNOWN/REJECTED bloquean retry ciego. Factory exit abre subacciones y solo la razón final genera evento; MEDICAL directo legado compatible. Database muestra PostgreSQL sin contraseña; test externo deshabilitado por defecto, DATABASE_URL intacta. Idiomas en/es/fr/pl por navegador; APIs/eventos en inglés, interfaz multilingüe.

Marca Hutchinson BSS en Admin/terminal/pairing y favicon común; recursos locales en frontend/img. Terminal operativo ocupa 90 % del viewport, teclado adaptable hasta 620 px y botones táctiles; verificado 320–1920 px. A 320×568 necesita scroll vertical para mantener botones utilizables.

## Ilustraciones configurables

Los siete PNG originales de Marcos (720×720 RGBA) se publicaron en main `d66c88a` y desplegaron el 12/10. Claves locales estables: end-work, break, factory, medical, personal, legal, no-work; visual_key opcional en Actions/Sub-actions. Se conservan proporciones, transparencia, fondos claros y configuración. FACTORY_EXIT usa factory; otras asignaciones intactas. ZIP original local sin versionar, archivos HTTP idénticos al ZIP. Backup y evidencia: `docs/action-png-validation-2026-10-12.md`; respaldo `/opt/backups/BSS_TimeCollection/20261012-original-png-illustrations/`. Backend 27 passed/1 skipped y build correcto; matriz desktop/táctil emulada 320–1920 px. Los 60 eventos previos quedaron intactos y aparecieron 5 más durante operación.

RFID mantiene `/img/rfid-card.svg` grande y centrado con aviso de hardware pendiente. Administración tiene scroll vertical propio de sidebar desktop y navegación horizontal móvil; corrección de admin.css incluida.

## Policies / Same Terminal Exit

Base GitHub main `5535e70`, con mejoras desplegadas el 12–13/10/2026 e incluidas en la publicación de este estado. Alembic `0008_exit_policies`, sin DDL al importar API; tabla con FK/checks, unicidad global/terminal y upserts atómicos. PostgreSQL serializa fichajes por tarjeta con advisory locks; entradas y salidas concurrentes no duplican eventos. Políticas Disabled/Same Terminal/Same Work Cell e INHERIT por terminal; predeterminado global sigue Disabled, sin overrides de pruebas residuales.

Terminals → Edit → Exit policy permite editar la política individual, elegir INHERIT y configurar work_cell (string recortada, sensible a mayúsculas, hasta 64 caracteres; blanco elimina). Preserva otros atributos; compara células configuradas actuales de ambos terminales y rechaza si faltan/difieren. Scan y salida/subacción final revalidan; 409 muestra terminal/célula origen o configuración ausente y ningún rechazo crea evento/intento ni cola Oracle. No altera snapshots históricos. Se corrigió interpolación de URL codificada en Alembic.

Backup verificado previo y justo antes de migrar: `/opt/backups/BSS_TimeCollection/20261012-exit-policies/`. API/worker/web recreados mediante docker compose, DB/volumen conservados, health checks correctos, .env intacto y Oracle desactivado. 45 tests passed (incluye PostgreSQL/migraciones/concurrencia; ninguno skipped), build TypeScript/Vite correcto. Réplica PostgreSQL restaurada y pruebas HTTP/UI repetidas en producción a 320–1280 px sin errores JS/overflow. Conservados 72 eventos históricos y configuración original; 16 eventos de validación aceptados añadidos (88 total), 0 intentos, 12 actions, 14 terminales/69 asignaciones. Tres terminales de validación retirados, eventos auditables conservados. Infraestructura temporal eliminada. Evidencia y procedimiento: `docs/deployment-policies-validation-2026-10-12.md`, `docs/exit-policies.md`.

Corrección de ubicación solicitada el 13/10/2026: Policies conserva exclusivamente el ajuste global. Opciones individuales y work_cell están en el editor de cada terminal, también al crear uno. Terminal POST/PUT guarda configuración y override en la misma transacción; omitir exit_policy_mode preserva overrides de clientes antiguos. Cancelar no aplica cambios. No nueva migración ni cambios de políticas existentes; global Disabled intacto. Backup: `/opt/backups/BSS_TimeCollection/20261013-terminal-policy-options/`. 47 tests passed (incluidos PostgreSQL y concurrencia), build y navegador 320/390/768/1280 px correctos en réplica y producción. API/worker/web recreados y saludables; datos/configuración preservados, terminal UI de pruebas retirado sin fichajes. Implementación y validaciones incluidas en main con este estado.

## Reloj del terminal

Present your badge sustituido el 13/10 por reloj HH:MM:SS de 24 h. Tras corrección de Marcos, reloj centrado con el mismo ancho que el teclado (máximo 620 px), tanto KEYPAD/BOTH como solo RFID; cifras hasta 104 px, sin ocupar toda la tarjeta/pantalla. Visible en identificación, selección de salida y confirmación. Hora viva local del navegador, actualizada al segundo y al volver a la pestaña; confirmación congela 2,2 s el event_datetime real de API en hora local. Backend, fichajes, Oracle y DB intactos. Build correcto; validación inicial de avance/confirmación con API/reloj simulados y 15 escenarios a 320–1920 px. Corrección de tamaño verificada en producción con 21 escenarios (3 modos × 320/390/620/768/1280/1920/3200): mismo ancho/centrado del teclado, RFID idéntico, sin overflow, cero fichajes reales. Solo web recreado y sano. Backups: `/opt/backups/BSS_TimeCollection/20261013-terminal-clock/` y `/opt/backups/BSS_TimeCollection/20261013-clock-keypad-width/`. Screenshot actual: `docs/terminal-clock-keypad-validation.png`. Implementación incluida en main con este estado.
