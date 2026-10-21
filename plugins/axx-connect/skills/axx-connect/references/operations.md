# Operación local

Inicia Axx para Windows antes de invocar las herramientas. Usa `axx_status` para comprobar la instancia y el ejecutor. La instalación del plugin no inicia ni autentica el proveedor de inferencia.

En Axx, abre Conectar IA → Axx Connect y consulta el diagnóstico del motor. Codex gestiona sus credenciales mediante su interfaz oficial. La sesión de Codex no da acceso a conversaciones ajenas a los datos autorizados de Axx.

Si un módulo requiere interfaz abierta, permisos de micrófono, pantalla o selección de archivo, presenta el estado solicitado por el ejecutor. Conserva los parámetros y el ID; no simules una acción física.

Actualización y desinstalación se realizan con los scripts del proyecto o con `codex plugin add axx-connect@axx-local` y `codex plugin remove axx-connect@axx-local`. Desinstalar el plugin conserva las tareas, archivos, recetas y la cuenta de Codex.

Esta distribución es privada y local. No contiene credenciales ni expone un servidor en Internet. El transporte Codex App Server es experimental y está fijado a la versión examinada por la aplicación.
