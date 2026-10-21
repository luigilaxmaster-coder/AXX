# Overlay de Axx Connect

Este parche se compara con la copia de fuentes previa a Connect. No es un commit ni certifica la instalación nativa.

El stage `build/phased-ux-20261020` tiene cambios propios. Revisar y combinar por hunks; no copiar `backend/server.py` ni `Axx.html` completos. `git apply --check source.patch` puede detectar diferencias antes de aplicar; no usar opciones de fuerza ni reset/clean. El manifiesto contiene hashes base/resultado y declara la excepción de `.gitignore`.

Archivos nuevos: proveedor, servicio y registro compartidos, servidor MCP, transporte HTTP, UI discreta, tests, plugin, scripts y documentación. El HTML cambia decoder, Nueva conversación, un script externo y tres hunks para que Escape no cancele tareas. No hay cambios de Rust, hotkeys OS, versión nativa ni instalador del otro stage.

El stage combinado C3 separa `axx-ui-escape` de `axx-cancel`: este último puede conservarse para Cancelar explícito con dueño. Esa variante nativa requiere revisión y pruebas propias; no copiar el retiro del listener HTML sobre un canal cuyo significado ya cambió. La raíz conserva Rust anterior, por lo que sus fuentes aisladas no acreditan el contrato nativo combinado de Escape.

Construcción posterior: `scripts/build-axx-connect.ps1` añade el SDK MCP a un entorno de build y delega al build existente. Instalar/probar desde el stage combinado con su propio contrato de foco/Esc y gate visual. La configuración y credenciales del usuario no forman parte del parche.
