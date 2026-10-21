# Tablero de ejecución

Esta plantilla controla trabajo futuro. Ninguna tarea está integrada en Axx todavía.

| ID | Entregable | Dependencia | Estado inicial | Evidencia de cierre |
|---|---|---|---|---|
| T0 | Mapa real y baseline del proyecto | Acceso a repo | NOT_RUN | PROJECT_MAP |
| T1 | Endurecimiento y regresiones | T0 | NOT_RUN | Tests H01–H10 aplicables |
| T2 | Adaptador, secretos y deadline | T1 | NOT_RUN | Tests de IPC y proceso |
| T3 | Selección y estado/progreso | T2 | NOT_RUN | Failover sin incompatibilidad |
| T4 | Chat Axx y Esc | T3 | NOT_RUN | UI y cancelación |
| T5 | Dos cuentas live | T4 + claves locales | NOT_RUN | Validación por modelo |
| T6 | Windows y rollback | T4; release requiere T5 | NOT_RUN | Build empaquetado |
| M1 | Memoria procedural | Release base + ejecutor | FUTURE | Documento 09 |
| Q1 | Cuota real por cuenta | Release base | FUTURE | Documento 10 |
| Q2 | Cola durable | Q1 + idempotencia | FUTURE | Documento 10 |
