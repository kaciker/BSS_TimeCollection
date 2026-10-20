# Estado actual

Actualizado: 20 de octubre de 2026.

## Objetivo y despliegue
Captura RFID/manual local y transmisión asíncrona auditable a Oracle; CORP Oracle false. Historial y configuración preservados. Alembic 0011_action_visibility, PostgreSQL y volúmenes originales; Compose requiere docker-compose.yml, docker-compose.issue2.yml y docker-compose.perimeter-corp.yml.

## Administración, terminales e identidad

 Admin ofrece estado por tarjeta, logs paginados/filtrables, JSON histórico y refresh 15 s, sin interpretación de asistencia Oracle. Edición de terminal/actions atómica, duplicados claros, ENTER único y al menos una salida por terminal activo; clone copia configuración pero no identidad/tokens/eventos; remove es baja lógica y conserva históricos/códigos reservados.

Identidad mediante cookie HttpOnly/SameSite=Strict, activation link de un uso y pairing temporal; reprovisión revoca sesión anterior. En HTTP local: . Configuración de terminal/action se mezcla en el fichaje; UNKNOWN/REJECTED bloquean reintento ciego. Salida de fábrica abre subacciones; solo la razón final crea evento. MEDICAL directo legado es compatible. Idiomas de interfaz en/es/fr/pl; API/eventos en inglés. Database presenta PostgreSQL sin contraseña; test externo apagado por defecto;  intacta.

## Ilustraciones y RFID

Siete PNG originales (720×720 RGBA) publicados en main , 12/10; claves estables end-work, break, factory, medical, personal, legal, no-work;  opcional. FACTORY_EXIT usa factory, otras asignaciones preservadas. Backup/evidencia: , . Build y 320–1920 px validados; eventos históricos preservados y 5 fichajes de operación añadidos.

RFID conserva ; lectores USB HID funcionan en RFID/BOTH con ventana activa. Captura/validación: . Terminal ocupa 90% del viewport; teclado adaptable hasta 620 px y controles táctiles; 320×568 requiere scroll vertical. Admin sidebar con scroll propio en desktop y navegación horizontal móvil.

## Políticas de salida

Base GitHub main ; Alembic , sin DDL al importar API; upserts atómicos y advisory locks serializan fichajes por tarjeta. Global Disabled sigue predeterminado, sin overrides residuales. Policies conserva el ajuste global; override y  se editan por terminal, también al crearlo. Modos Disabled/Same Terminal/Same Work Cell e INHERIT. Célula recortada, sensible a mayúsculas, máx. 64 caracteres; blanco elimina. Se rechaza Same Work Cell si falta o difiere la célula. Scan y salida final revalidan; HTTP 409 no crea evento/intento/cola Oracle. Snapshots históricos intactos.

Override Compose ; backup previo a migración: ; validación/cómo operar: , . Ajustes por terminal y global desplegados 13/10 sin cambiar políticas existentes: 47 tests pasados, build y réplica/producción 320–1280 px correctos; DB/datos preservados.

## Reloj de terminal

Desde 13/10 se muestra reloj HH:MM:SS de 24 h, centrado y del ancho del teclado (máx. 620 px) en identificación, selección de salida y confirmación; hora local viva, confirmación congela 2,2 s el  real de API. Sin cambios de backend, Oracle ni DB. Verificado en 21 escenarios 320–3200 px y sin fichajes reales. Evidencia: ; backups  y .

## Despliegue CORP

Rama , base main , GitLab A0H84018/bss_timecollection_corp; README operativo en inglés. Imágenes/proxy solo build validados, puerto 8080, Oracle/seed desactivados. Conservar volumen anónimo PostgreSQL 16 (PGDATA). Guía: .

## Factory Perimeter CORP (20/10/2026)

Desplegado commit local `0d7d3e55fc2453be31c5a969f6971b912069cc10`, merge de GitHub `a414089` con CORP `6635652`; sin push. Conserva límites Oracle 40 caracteres y conciliación UNKNOWN. Alembic `0010_factory_perimeter`; correcciones de FK/flush atómico, snapshots de entrada, downgrade/constraint, dedup BOTH, clones y feedback traducido. Factory Perimeter disponible en Admin pero DESACTIVADO; sin ajustes persistidos. Terminales existentes CELL/DEFAULT y asignaciones/sesiones intactas; 30 eventos y 0 intentos conservados. Oracle/seed false. API/web/db saludables, worker operativo sin envío. PostgreSQL y ambos volúmenes originales intactos.

Compose requiere `-f docker-compose.yml -f docker-compose.issue2.yml -f docker-compose.perimeter-corp.yml`; imágenes `perimeter-corp-20261020` construidas offline con dependencias existentes. Backend 65 passed/1 skipped opcional; frontend 27 passed/build; migración reversible y HTTP E2E solo réplica con UID ficticio. Backup completo restaurado/verificado: `/opt/BSSTimeCollection-backups/perimeter-20261020T072051Z`. Detalles: `docs/deployment/factory-perimeter-corp-20261020.md`. Lectores físicos/barreras requieren prueba manual antes de activar; BOTH aplica cooldown, salida dedicada lo omite estando dentro.

Factory Perimeter UI uniformada con estilos admin existentes el 20/10: tarjetas, fuentes, formularios, switches, botones y tabla responsive. Frontend 27 passed/build; solo web recreada, resto intacto. Backup `perimeter-style-20261020T073729Z`; desactivado/Oracle false.

## Action visibility CORP (20/10/2026)
Desplegado `ff32d3fca5ca3724c45ac4e231917624947ae061`, merge GitHub `7d280f6` con correcciones CORP preservadas. Alembic `0011_action_visibility`; acciones anteriores show_on_terminal=true. Selector EXIT activa/leaf incluye ocultas; ocultas no accesibles al operario pero sirven en cascada interna; protege última entrada/salida visible. Avisos excluyentes y estilos uniformes mantenidos. Backend 70 passed/1 optional skipped; frontend 29 passed/build; migración reversible en réplica restaurada y HTTP E2E con UID ficticio. Datos/config/sesiones y 30 eventos/0 intentos intactos; DB/volúmenes originales. Perímetro disabled, Oracle false. Backup y detalles `docs/deployment/action-visibility-corp-20261020.md`; sin push.

Corrección 20/10 `a575a5c`: selección factory persiste por URL y evita respuestas antiguas; 31 frontend tests/build, solo web. Usuario activó ARGANDA con END_WORK; DEFAULT sigue disabled con código previo no elegible. Configuración observada conservada; no asumir perímetro globalmente disabled. Oracle false.

Selección de fábrica: además del query, navegador recuerda última fábrica (localStorage); enlaces explícitos tienen prioridad. HTML no-cache. 33 frontend tests/build; solo web, datos intactos.

Terminales perimetrales `fdd56e4` (20/10): flag Perimeter only en New/Edit desactiva estructura/acciones/políticas/Oracle; alta sin célula, rol PERIMETER_BOTH existente (sin migración), asignar factory/dirección después. Clones compatibles, conversión CELL validada. 72 backend/1 optional skip; 34 frontend/build; réplica PG sin eventos de célula. Datos/config existentes intactos.

Registro unificado `427923e`: monitoring/events incluye perímetro LOCAL_ONLY/Solo local, filtros/detalle sin Oracle. Backend 74/1 skip; frontend 35/build. Células y T0005 en ARGANDA.

UI asignaciones: Saved factory/role explícitos, botón Assign to destino o Assignment saved; fila y lista se actualizan tras guardar. 36 frontend tests/build; solo web, sin cambiar asignaciones.

Motivos 20/10: CORP `38fb224`, main `a1b4de7`; 16 PNG + 7 legacy, tests/build/HTTP/browser OK. Salidas sustituidas por 16 EXIT directas: nombres españoles, BSS events ingleses; asignadas a 5 CELL, START_WORK conservada, T0005 excluido. Antiguas ocultas/inactivas salvo salida interna perimetral activa. Solo actions/terminal_actions cambiaron. Backup `reason-actions-20261020T102808Z`.

Cards `37a8e4f`: estados independientes célula (TimeEvent) y fábrica (perímetro por factory, solo enabled). Columna/filtro fábrica condicional; sin lecturas = fuera, disabled = no activado. Último reloj sigue combinado, filtro inicial Todos. Backend 79/1 skip, frontend 40/build; HTTP/browser 1440/390 confirma 6 fuera célula/dentro fábrica. Solo API/web, DB/env intactos, Oracle false; sincronizado en main.
