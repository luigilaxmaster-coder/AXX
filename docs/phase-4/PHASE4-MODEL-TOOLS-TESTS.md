# Herramientas de modelo · fase 4

Código evaluado en 7eb0f792b5db127b843f3e4b18c047daea8a3481.

Activa «Herramientas de Axx en el chat local» en ajustes. El chat nativo con conexión API configurada y selección manual usa la ruta estructurada. Ollama directo en streaming era una ruta de solo texto. Con la opción activa, el chat pasa por el router y el perfil elegido debe declarar tools. Axx Connect conserva su ruta de Codex y sus propias herramientas.

El catálogo del chat se limita deliberadamente a telemetría, estado de arquitectura y creación de texto en artifacts a partir del registro activo. En el editor existente de proveedores, el propietario declara «Llamadas a herramientas» cuando el perfil las admite y activa después la opción del chat. El soporte se decide por el perfil exacto elegido. Las declaraciones de capacidades de otros modelos requieren su propia verificación. Un turno admite una llamada estrictamente estructurada. El resultado recorre ConnectService, CommandService y ActionExecutor. El recibo queda en Comandos. El chat conserva el texto y una indicación de estado sin reenviar los datos del recibo al modelo. La cancelación correlaciona el request_id y protege contra admisión tardía.

| Prueba | Evidencia |
|---|---|
| OpenAI compatible, proveedor simulado | POST de chat real autenticado. Telemetría ejecutada y verificada. Shell, campos de autoridad, ruta fuera de artifacts y JSON duplicado rechazados. |
| Escritura propuesta por modelo | Solicita revisión incluso desde un chat Unrestricted. Cancelación consultada en el recibo de Connect. Sin archivo creado. |
| Anthropic simulado | Se verifica conversión a input_schema y retorno de tool_use con texto preservado. |
| Perfil sin tools | Estado unsupported y conversación de texto. |
| Chromium | Activación explícita desde la interfaz. El recibo conserva datos locales y el texto del chat excluye esos datos. |
| Ollama local, llama3.2:1b | PASS de extremo a extremo. El modelo solicitó axx_system_telemetry con {} y el ejecutor devolvió succeeded y postconditions_passed=true. La misma sonda bloqueó un turno con dos llamadas y distinguió otro de solo texto. |

Para reproducir las pruebas principales:

    python -m unittest backend.tests.test_commands_http backend.inference.tests.test_spatial_transport -q
    python -m unittest discover -s backend/connect/tests -q
    node 1.AXX/scripts/test-desktop-frontend.cjs

La sonda real se reproduce con build/phase4/real-provider.ps1. El recibo en build/phase4/real-provider.json tiene SHA-256 1185a28916409f86f64ea190df18dde3b5e0964959b6597b7045974ad7e936b3. Se usaron datos sintéticos y un proceso Ollama de loopback aislado con el modelo ya instalado.
