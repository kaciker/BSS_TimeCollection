# Facts del proyecto

Confirmados por Marcos el 9 de octubre de 2026. Fuente: [contexto de producto y arquitectura](docs/BSS_TimeCollection_Project_Context_Codex.pdf), baseline MVP v0.1.

## Objetivo

BSS Time Collection es la capa de captura de fichajes de fábrica, como dispositivo externo de recogida de tiempos (TCD) para Oracle HCM Time and Labor. Permite registrar eventos mediante RFID/tarjeta o identificación manual en terminales configurables, conservarlos de forma duradera en PostgreSQL y entregarlos de forma fiable y asíncrona a Oracle, con trazabilidad de cada intento de transmisión.

## Límites y garantías

- BSS registra y transmite hechos; Oracle interpreta su significado funcional y es el sistema funcional de referencia.
- BSS no gestiona maestros de empleados, turnos, horarios, cálculo de horas, nómina, ausencias, aprobaciones, time cards, emparejamiento funcional IN/OUT ni corrección funcional de fichajes.
- Cada evento se persiste antes de mostrar éxito al trabajador. La indisponibilidad de Oracle no debe impedir el fichaje mientras BSS pueda persistirlo.
- Los hechos capturados, sus marcas de tiempo y las instantáneas de configuración se preservan; el historial técnico de transmisión se conserva por separado.
- INSIDE/OUTSIDE es un estado derivado de eventos locales compartidos entre terminales para simplificar la interfaz; no es una declaración funcional o legal de presencia.
- SENT acredita aceptación de transporte por Oracle, no validación funcional. Los resultados ambiguos se mantienen en UNKNOWN sin reenvío automático ciego.
- Contrato del tenant Oracle, autenticación, interfaz RFID, conciliación y retención siguen sujetos a decisiones explícitas; no se deben asumir ni introducir borrados destructivos.

## Idioma

Marcos establece inglés para todos los menús, mensajes y registros de eventos. La interfaz multilingüe se evaluará en el futuro; los eventos deben mantenerse en inglés.
