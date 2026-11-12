# Cierre visual de Codex · Fase 7

Fuente visual: `234ffa85743dbd16e6d0c5d0ab79d8460d4cd6e2`.
Baseline leído y ejecutado: `8371e010d588509a1f15a2fcde872449e2eca35f`.
Declaración propia: **DESIGN_FROZEN_FOR_NATIVE_ACCEPTANCE**. No es aprobación
de Claude ni aceptación nativa. Revisión propia, sin revisor independiente.

## Recuperación y alcance

El worktree original de Claude tenía WIP en tres scripts, documentos y capturas.
Se guardaron estado, hashes y patch binario en build/phase7/recovery, sin escribir
en él. Se recuperaron solo los tres scripts para revisar y terminar los tres
ajustes autorizados. El borrador fabricaba medidas al navegar; se sustituyó por
el uso de la clave efectiva de layout al resolver dimensiones por defecto.
Handy permanece intacto; bundle incremental verificado y handoff indexado en
esa carpeta privada, con requisito base a750362.

## Comprobaciones propias

| Comprobación | Resultado / alcance |
| --- | --- |
| Contratos phase7-ui-harness | 29 PASS; DOM único, propietarios, teclado, guardado, alcance, foco y tres ajustes |
| Medidas guardadas | RAM y localStorage sin cambios al navegar; resize/drag explícitos persisten tras recarga |
| Layout | Cada vista se abre realmente; normal y 380 px, incluida Forma; sin overflow |
| Apariencia | Seleccionar forma inicia prueba; Descartar recupera valores; avanzados alcanzables |
| Contraste | 16 bordes débiles de chat claro y 1 oscuro → 0; ámbitos reorganizados → 0 |
| Desktop frontend | 42 PASS en baseline y cierre con Chromium headless 1248 |
| Otras suites | 12 PASS: chat/usabilidad/grupos/workspace/composer, comandos, sonido, Computer Use, quick reply, misiones, procedencia, browser runtime y geometría; contar los scripts en el recibo |
| Magic Pen | PASS con captura/proveedor/IPC de fixture; no certifica visión o Windows físico |
| Gate PC/móvil | PASS: contrato 15, servicio 112 (1 omitida previa), navegador 58, selector 8 |

El listado de 12 suites del runner excluye desktop y Magic Pen; su recibo es
`build/phase7/regressions-ui/results.json`. Los errores iniciales de entorno se
conservan, y las repeticiones correctas están en desktop-*-headless y
magic-pen-final.log. Sin Playwright en NODE_PATH, Magic Pen no arrancaba; se usó
el runtime instalado, sin modificar la prueba. Chrome instalado se bloqueó en
el ensayo WebGL de desktop tanto en baseline como en cierre; con el Chromium
1248 original ambos pasan 42. No se desactivó la prueba ni se cambió el renderer.

## Cinco fallos preexistentes reproducidos

| Suite | Baseline y cierre | Evidencia distintiva |
| --- | --- | --- |
| test-tools-interaction | FAIL | L75, `Chat` frente a cadena vacía |
| test-providers | FAIL | L148, memoria de conversación cambió |
| test-skills | BLOCKED_ENV | dist/axx-backend.exe ausente; no se simuló un binario |
| test-capability-workshop | FAIL | espera de current en L16, timeout 30 s |
| test-goal-cycle | FAIL | clic de L23, timeout 30 s |

Comparación ejecutada con mismo Chrome, máquina y scripts, en worktrees propios.
Logs/JSON en regressions-baseline y regressions-finish. Estos fallos no excusan
una regresión nueva ni certifican la función afectada. El empaquetado posterior
debe verificar aparte la ruta real del backend; no cambiar fixtures para ocultarlo.

## Evidencia y límites

Capturas antes/después claras/oscuras: build/phase7/screenshots/baseline y finish;
38 finales, pliegue y contenido completo. Las capturas completas de navegador
amplían la superficie de prueba; no son geometría física de una ventana Windows.
La prueba de layout anterior tenía await open(v) dentro de un comentario; se
corrigió y se amplió a Forma. No se conserva ese falso positivo como validación.
Voces mantiene 18 alertas del medidor plano sobre gradientes, fuera del cierre.

Falta: candidata empaquetada aislada, WebView2 real, DPI disponible, conexiones
reales, preferencias y apariencia persistidas en el proceso nativo. Hasta esa
aceptación no se integra Handy, no se instala sobre AXX personal ni se publica.
