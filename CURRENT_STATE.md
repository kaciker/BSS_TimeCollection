# Estado y decisiones actuales

Actualizado: 9 de octubre de 2026.

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
