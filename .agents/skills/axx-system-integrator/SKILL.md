---
name: axx-system-integrator
description: Protocolo maestro y ejecutor técnico para Axx Desktop. Contiene las reglas inviolables de identidad, ejecución de cada componente, router de inferencia resiliente, integración con Tauri 2/Rust y protocolo de recuperación cuando se pierde el rumbo.
---

# Axx Desktop · Skill del Integrador de Sistema

Este skill es la **fuente de autoridad operativa** para cualquier agente que trabaje en el repositorio de **Axx**. Regula la preservación de la identidad visual 3D, la ejecución del router de inferencia, la integración nativa en Windows y el protocolo de recuperación.

---

## 1. Reglas Inviolables (P0)

1. **Identidad Intocable:** Jamás sustituir el avatar 3D líquido por un chat genérico, una imagen PNG o una ventana web estándar. Las 24 formas geométricas, las 9 paletas, la iluminación procedural y los controles físicos de volumen son obligatorios.
2. **Autoridad de Ajustes:** `axx-studio-v2` en `localStorage` es la única autoridad de forma y acabado. Un cambio de estado de tarea (`thinking`, `error`, `music`) **nunca** sobrescribe la forma guardada de forma permanente.
3. **Cero Secretos en Frontend:** Ninguna API key, token o cabecera privada debe residir en el código cliente de `Axx.html`. La resolución de credenciales se realiza estrictamente en el backend / sidecar mediante variables de entorno o DPAPI de Windows.
4. **Sin Alucinaciones de APIs:** No declarar completada una tarea por haber escrito una especificación o un mock. Distinguir siempre entre:
   - `ESPECIFICADO`: Documentado pero sin código.
   - `IMPLEMENTADO_LOCAL`: Código presente con tests unitarios offline pasando.
   - `INTEGRADO_DEV`: Conectado y probado mediante IPC.
   - `VALIDADO_WINDOWS`: Probado como binario nativo en Windows 11.
5. **No Compras ni Pagos:** El router debe configurarse siempre con `allow_paid: false`. Cualquier error que requiera pago debe abortar inmediatamente.

---

## 2. Forma de Ejecución de Cada Componente

Cada componente del sistema tiene un entorno, comando y criterio de verificación estricto:

### A. Prototipo Web y Pruebas de Frontend (v20)
- **Directorio:** `1.AXX/`
- **Arranque en desarrollo local:**
  ```powershell
  # Servidor local loopback (Node 22+)
  node scripts/server20.mjs
  # O doble clic en INICIAR-AXX.cmd
  ```
  - *Puerto:* `http://127.0.0.1:4173`
  - *Verificación:* Inspeccionar que `Axx.html` cargue sin errores en la consola DevTools.
- **Suite de Pruebas DOM / Playwright:**
  ```powershell
  python scripts/identity20-browser.py
  python scripts/chat20-browser.py
  python scripts/jitter20.py
  python scripts/layout20-browser.py
  python scripts/polish20.py
  ```
  - *Criterio de éxito:* 268 pruebas unitarias aprobadas, 0 excepciones no capturadas.

---

### B. Router de Inferencia Python (Baseline y Endurecimiento)
- **Directorio:** `2.analisis e integracion profunda/baseline/axx-api-router/`
- **Ejecución de la Suite de Pruebas Offline:**
  ```powershell
  python -m unittest discover -s tests -p "test_*.py" -v
  ```
  - *Precondición:* Python 3.11+ instalado. Cero paquetes externos requeridos (solo biblioteca estándar).
  - *Criterio de éxito:* 20 tests pasados (o suite ampliada con H01–H10 pasando al 100%).
- **Ejecución del CLI en modo interactivo/prueba:**
  ```powershell
  python router.py --config providers.example.json --state state.db chat < request.example.json
  ```
- **Inspección de Estado y Métricas:**
  ```powershell
  python router.py --config providers.example.json --state state.db status
  ```
- **Reset de Enfriamiento (Cooldown):**
  ```powershell
  python router.py --config providers.example.json --state state.db reset-cooldown <provider_name>
  ```

---

### C. Script de Verificación de Integridad de la Base
- **Directorio:** `2.analisis e integracion profunda/`
- **Comando:**
  ```powershell
  powershell -ExecutionPolicy Bypass -File .\scripts\verify_baseline.ps1
  ```
  - *Salida esperada:* Validación de SHA256, sintaxis Python, compilación de tests y salida limpia con exit code 0.

---

### D. Shell Nativo Windows (Tauri 2 / Rust)
- **Directorio de compilación:** Raíz del proyecto (donde resida `src-tauri/`)
- **Inicialización:**
  ```powershell
  npm install --save-dev --save-exact @tauri-apps/cli@2
  npx tauri init
  ```
- **Desarrollo en vivo:**
  ```powershell
  npx tauri dev
  ```
- **Pruebas de Rust:**
  ```powershell
  cargo test --manifest-path src-tauri/Cargo.toml
  ```
- **Compilación del instalador de producción:**
  ```powershell
  npx tauri build --bundles nsis
  ```
  - *Criterio de éxito:* Generación del ejecutable `.exe` y del instalador NSIS sin errores de enlace.

---

## 3. Matriz de Documentación (Dónde Tomar Referencia)

Cuando se necesite información sobre cualquier área, consultar el documento rector correspondiente:

| Tema / Dominio | Documento de Referencia Primario | Ubicación |
|---|---|---|
| **Identidad 3D, Paletas y Formas** | `IMPLEMENTACION.md` | `1.AXX/IMPLEMENTACION.md` |
| **Arquitectura de Interfaz y Prototipo** | `Axx.html` (comentarios y clases) | `1.AXX/Axx.html` |
| **Manual Completo de Usuario y Atajos** | `MANUAL-COMPLETO.md` | `1.AXX/MANUAL-COMPLETO.md` |
| **Plan Maestro de Migración Nativa** | `PLAN-MAESTRO.md` | `1.AXX/PLAN-MAESTRO.md` |
| **Entorno Windows y Preflight** | `05-WINDOWS.md` | `1.AXX/05-WINDOWS.md` |
| **Auditoría de Defectos del Router (H01-H10)**| `01_ESTADO_Y_AUDITORIA.md` | `2.analisis e integracion profunda/docs/` |
| **Límites, Autoridad y Seguridad** | `02_ESPECIFICACION.md` | `2.analisis e integracion profunda/docs/` |
| **Contratos IPC, Envelopes y Errores** | `03_CONTRATOS.md` | `2.analisis e integracion profunda/docs/` |
| **Plan de Ejecución por Tareas (T0-T6)** | `04_PLAN_IMPLEMENTACION.md` | `2.analisis e integracion profunda/docs/` |
| **Proveedores Gratuitos y Catálogo** | `06_PROVEEDORES_Y_CATALOGO.md` | `2.analisis e integracion profunda/docs/` |
| **Criterios de Aceptación (G0-G6)** | `07_ACEPTACION_Y_PRUEBAS.md` | `2.analisis e integracion profunda/docs/` |
| **Operación, Diagnóstico y Rollback** | `08_OPERACION_Y_ROLLBACK.md` | `2.analisis e integracion profunda/docs/` |
| **Instrucciones Obligatorias del Agente** | `11_REGLAS_DEL_EJECUTOR.md` | `2.analisis e integracion profunda/docs/` |

---

## 4. Protocolo: ¿Qué hacer cuando se pierde el rumbo?

Si el agente o el desarrollador se siente desorientado, encuentra errores recurrentes o duda del siguiente paso, debe seguir este **algoritmo de recuperación**:

```
[DESORIENTACIÓN DETECTADA]
  │
  ├─► PASO 1: DETENER TODO (Stop-the-line)
  │    No escribir más código. No añadir librerías. No improvisar endpoints.
  │
  ├─► PASO 2: VERIFICAR LA IDENTIDAD (Invariant Check 1)
  │    ¿Sigue existiendo Axx.html con sus 24 formas y shaders intactos?
  │    SI ──► Continuar a Paso 3.
  │    NO ──► ALERTA: Restaurar inmediatamente desde 1.AXX/Axx.html original.
  │
  ├─► PASO 3: CONSULTAR EL TABLERO DE TAREAS (Project Compass)
  │    Abrir `2.analisis e integracion profunda/docs/04_PLAN_IMPLEMENTACION.md`.
  │    Revisar en cuál tarea exacta se encuentra: T0, T1, T2, T3, T4, T5 o T6.
  │    ¿La tarea anterior pasó su puerta de aceptación (Gate G0-G6)?
  │    Si no hay evidencia de la puerta anterior, REGRESAR a la tarea anterior.
  │
  ├─► PASO 4: EJECUTAR DIAGNÓSTICO BASELINE
  │    Correr `python -m unittest discover -s tests` en el router.
  │    ¿Pasan las 20 pruebas fundamentales?
  │    SI ──► El núcleo de enrutamiento está sano.
  │    NO ──► Corregir la regresión antes de tocar cualquier otra capa.
  │
  └─► PASO 5: CONSULTAR LA DOCUMENTACIÓN RAÍZ
       - Si la duda es sobre datos/JSON/errores: Leer `docs/03_CONTRATOS.md`.
       - Si la duda es sobre Windows/Tauri/Procesos: Leer `docs/05_WINDOWS_Y_EMPAQUETADO.md`.
       - Si la duda es sobre reglas y conducta del agente: Leer `docs/11_REGLAS_DEL_EJECUTOR.md`.
```

---

## 5. Decisiones Arquitectónicas Congeladas

- **Transporte de Inferencia:** Síncrono por intento (`stream: false` en backend/router; streaming se delega si el host lo soporta).
- **Límites de Tiempo:** Timeout de socket = 20 s; Deadline de reloj de pared del adaptador = 70 s.
- **Concurrencia:** Máximo 1 solicitud en vuelo por conversación, máximo 2 globales. Si llega otra, responder `BUSY`.
- **Cancelación:** La tecla `Esc` emite señal inmediata de cancelación al proceso hijo (`TerminateProcess` / `SIGTERM`), descarta cualquier respuesta tardía y no marca el proveedor como averiado.
- **Wake Word ("Hey Axx"):** Permanece como trabajo `FUTURO` hasta que el runtime de escritorio esté empaquetado y estable.
