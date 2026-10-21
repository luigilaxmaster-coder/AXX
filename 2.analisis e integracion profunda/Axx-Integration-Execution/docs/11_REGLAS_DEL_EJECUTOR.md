# 11 — Instrucciones operativas del agente integrador

Documento de proyecto para ejecutar esta integración; no es una skill instalada ni concede herramientas o permisos inexistentes.

## Antes de editar

Leer instrucciones locales y contratos. Verificar root y archivos reales. Registrar comandos que existen en manifiestos. Distinguir HECHO (observado), INFERENCIA (derivación), DECISIÓN (diseño) y PENDIENTE (no ejecutado). No afirmar que una ruta o endpoint existe porque aparece en un ejemplo de esta documentación.

El usuario solicita ejecución de integración, por lo que no hay que pedir permisos de nuevo para lecturas, cambios reversibles y pruebas ya autorizadas. Si falta el código real, preguntar por ruta/acceso una vez y completar lo independiente. Si faltan credenciales, dejar el smoke live bloqueado y seguir pruebas offline. No inventarlas ni pedir que se envíen en el chat.

## Durante el trabajo

1. Modificar el Axx existente. No crear otro asistente con una UI diferente.
2. Cada tarea tiene una prueba que reproduce el problema, implementación y salida de validación. No sustituir test live por mock.
3. Verificar SDKs, APIs y librerías contra documentación oficial de la versión real antes de utilizarlas. No copiar comandos Tauri de otra versión.
4. Nunca interpretar nombres del catálogo como modelos disponibles para la cuenta; comprobar el identificador exacto.
5. No activar capacidades que no se probaron ni mostrar saldo que no se consultó.
6. Guardar cambios del usuario y usar commits/revisiones pequeñas según el flujo real. No limpiar carpetas ajenas.
7. No lanzar shell con texto generado por usuario/modelo. IPC con argumentos separados; ejecutor de herramientas con registro y esquema.
8. No hacer optimizaciones que cambien política o UI sin relación con el objetivo. No añadir multiagentes, modelos locales pesados, voz permanente o APIs de pago para superar un bloqueo.
9. Ante error de pruebas, conservar evidencia y diagnosticar antes de tocar más piezas. No bajar expectativas del test solo para obtener verde.
10. No ejecutar recetas nuevas como verificadas; no aprender de un resultado no comprobado.

## Calidad y finalización

Revisar lógica, tipos, límites, unidades, concurrencia, cancelación, red, cuotas, credenciales y rollback. Cada assertion de 'funciona' debe apuntar a código y prueba ejecutada. Verificar release empaquetado, no solo dev server. Incluir fallos previos y pruebas no realizadas; no ocultarlos bajo una frase de éxito.

No usar TODO/FIXME como implementación terminada. Los formularios sin rellenar son plantillas, nunca pruebas. El estado final puede ser parcial si falta acceso al equipo/cuentas; señalar exactamente qué acción concreta queda y qué se completó realmente.

## Mensaje final esperado

Resultado concreto, archivos modificados, cómo ejecutar, pruebas con resultados, limitaciones y rollback. Si no se probó Windows o live, decirlo de forma explícita. No prometer disponibilidad continua, gratuidad futura o imposibilidad de alucinación.
