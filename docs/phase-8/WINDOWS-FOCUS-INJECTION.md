# Windows: foco e inserción

Implementado en src-tauri/src/dictation.rs. Un hilo COM MTA conserva UIA y sus
objetos; AddFocusChangedEventHandler incrementa un epoch. El renderer solicita
un destino cada 200 ms; el host vuelve a observarlo inmediatamente al insertar.
Se comprueban foreground HWND, PID y creación del proceso, CompareElements,
IsPassword, IsEnabled, IsOffscreen, HasKeyboardFocus y ValuePattern.IsReadOnly.
Falla cerrado si falta una de esas pruebas. Procesos elevados, terminales
conocidos y escritorio distinto de Default quedan bloqueados.

La sesión nace solo por acción deliberada. Token UUID opaco por destino/epoch,
heartbeat máximo 3 s, secuencias consumidas antes del efecto, límite 100000.
Escape invalida el permiso nativo incluso si el renderer responde tarde.
Bloqueo/escritorio seguro cancela la sesión en el watchdog; no se reafirma sola.
Un cambio de destino da pending. SendInput parcial o readback no concluyente da
uncertain. No reintentar esos efectos automáticamente.

Entrada Unicode sin Enter/control chars, SetValue, atajos de pegado ni cambios de
foreground. Se espera hasta 300 ms a que se suelten modificadores y se revalida.
Readback ValuePattern hasta 32 KiB, comparación de inserción exacta; nunca se
reemplaza el contenido completo del control. El clipboard no se toca al insertar.
Copiar es una salida explícita independiente y sí sustituye el clipboard.

Prueba nativa real, datos sintéticos, aprobada: ventana Win32 propia con dos
Edit, password y readonly. Inserción+readback, duplicado sin segunda escritura,
cambio rápido de campo => pending, password/readonly => bloqueados, cancelación.
Comando: cargo test --offline --locked --lib native_edit_fixture -- --ignored --nocapture --test-threads=1
La prueba es opt-in porque abre una ventana; se ejecutó expresamente, no se omitió.

Compatibilidad pendiente: Notepad moderno, Word, Chrome/ChatGPT/WhatsApp,
Telegram y Obsidian. Muchos documentos/contenteditable no exponen ValuePattern;
se declaran incompatibles hasta añadir una prueba de edición segura, no se
infiere edición solo porque permitan selección. No hay pegado transaccional:
la estrategia inicial Unicode evita el riesgo de restaurar clipboard incorrecto.
No hay atomicidad OS entre observar foco y SendInput; se estrecha esa ventana,
se reporta incertidumbre y se exige aceptación física antes de distribución.

El fixture espera hasta 30 s a que Windows conceda foreground y comprueba HWND/PID propios antes de escribir. Cuando foreground no se concede, falla; no se relaja TargetGuard. La prueba final se activó mediante sky.activate_window y pasó dos ejecuciones controladas. Los intentos que aún observaban la ventana subyacente no se cuentan como PASS.

La captura PCM global ahora pertenece a WASAPI en un hilo nativo separado. Un
epoch nuevo deja de emitir audio hasta revalidación; campo protegido cierra la
captura y 3 s sin latido cierran aunque no responda el renderer. Escape incrementa
cancelación atómica desde el hook. No certifica el driver ni bloqueo/suspensión
reales: esas pruebas siguen pendientes. El fixture se repitió tras este cambio y
pasó sin activación asistida (1.41 s); no abrió micrófono.
