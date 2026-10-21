# Delta UI V2.1

Aplicar después del snapshot V2. Cambia únicamente axx-connect.js y su prueba de navegador.
El parche se reconstruyó contra las fuentes V2 y sus hashes coinciden. No sustituir HTML,
CSS, Rust, backend, voz ni documentos del integrador. Los otros 45 archivos V2
conservan sus hashes. Revisar por hunks si el stage tiene cambios propios.

Los resultados son de navegador/IPC controlado. Este delta no ejecuta inferencia ni
demuestra el funcionamiento de la aplicación Windows instalada. El ZIP V2 original
permanece inmutable; el ensayo de aislamiento es un addendum separado aún sin ejecutar.
