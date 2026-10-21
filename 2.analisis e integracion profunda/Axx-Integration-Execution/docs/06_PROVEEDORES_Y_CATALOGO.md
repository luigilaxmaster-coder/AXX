# 06 — Alta de proveedores, cuota y catálogo

## Activación controlada

Configurar primero dos cuentas/proveedores distintos. Completar `templates/PROVIDER_VALIDATION.json` para cada combinación cuenta/modelo. Los IDs de modelo de providers.example.json son marcadores desactivados: sustituirlos solo con valores comprobados. No se fija una lista de precios en este paquete porque depende de cuenta, región y fecha.

El operador inicia sesión en la consola del proveedor e introduce el secreto localmente. El agente puede verificar disponibilidad usando esa credencial en backend sin imprimirla. No crear cuentas nuevas, activar recarga ni añadir método de pago para obtener una prueba gratuita salvo instrucción específica del usuario.

Orden de comprobación: endpoint oficial → modelo visible en cuenta → precio/tier vigente → cuota y ámbito → tratamiento de datos → prueba mínima → capabilities → activar conexión. Registrar URLs primarias, fecha UTC y resultado. Si un atributo no está confirmado, mantenerlo desconocido; no convertir null en false ni una declaración comercial en un permiso implícito.

## Pruebas mínimas por capacidad

| Capacidad | Estímulo sintético | Aceptación |
|---|---|---|
| text | Responder una palabra de control | message assistant no vacío, salida válida |
| json | Pedir objeto con campo fijo bajo formato compatible | JSON parseable y esquema satisfecho |
| tools | Una función ficticia `test_echo` que no se ejecuta | tool_call estructurado con argumentos válidos, sin acción externa |
| vision | Imagen sintética pequeña con figura/color conocido | Evidencia de procesamiento visual, no solo respuesta genérica |

Un ensayo simple demuestra compatibilidad puntual, no calidad general. Registrar también un caso negativo y repetir tras cambiar modelo, endpoint o versión de API. La política local exige reverificación de evidencia a los 30 días y antes de release; no es una garantía del proveedor.

## Límite por cuenta

La cuota puede ser por organización, cuenta, clave, modelo, minuto, día, tokens o crédito. Registrar scope; no sumar límites de claves o modelos si comparten cuenta. En incremento 1 solo una entrada activa por cuenta, aunque el catálogo liste más modelos. Los contadores locales solo limitan lo enviado por este router, no solicitudes desde otras aplicaciones.

429 no revela por sí solo cuándo se restablece la cuota. Usar Retry-After normalizado si existe; si no, pausa local prudente y estado 'cuota remota no consultada'. No prometer que volverá a estar disponible en 60 segundos. El incremento de cuotas del documento 10 añade lectura oficial cuando exista.

## Catálogo reproducible y opcional

En la revisión del 2026-10-19, el repositorio se fijó al commit `90e4f43865e7fd1724c5f74227ba106ae01122cd`. Su MCP sigue documentado como no publicado. Ofrece consulta y configuración de muestra, no inferencia ni saldo de tu cuenta. Fuentes fijadas en 12.

Para usarlo, obtener checkout del commit fijado, validar su esquema y generar un registro candidato. Comparar con la revisión anterior, conservar hash y aprobar cambios antes de activarlos. No descargar una URL del catálogo y reenviarle una clave automáticamente. Las URLs de runtime permanecen bajo allowlist del host.

Si el catálogo falla, está ausente o está desactualizado, Axx inicia con la configuración aprobada más reciente. No consultar catálogo en cada turno. No depender del MCP para seleccionar entre dos conexiones ya configuradas.

Instalación opcional del MCP: seguir README del commit verificado; checkout local, dependencias bloqueadas con scripts desactivados y tests de su paquete. No usar npx como si existiera una publicación confirmada. Node solo se requiere para ese componente opcional, no para el router Python.

## Privacidad y coste cero

Revisar condiciones de uso y retención del proveedor real, no solo la licencia MIT del catálogo. Un modelo 'gratis' puede cambiar y una cuenta puede tener facturación habilitada. free_confirmed no limita el precio del lado del servidor. Configurar restricciones de gasto/modelo en la consola cuando existan; no considerar 'sin tarjeta' un control universal de coste.

Si la gratuidad o el tratamiento de datos dejan de estar confirmados, desactivar la entrada sin borrar su historial. Nunca registrar el secreto, ni siquiera un fragmento. Los informes usan un ID de cuenta interno no sensible y un fingerprint de configuración que excluya credenciales.
