# Código y capacidades revisadas de Axx

Axx puede proponer procedimientos con comandos existentes o escribir una función
Python para transformar datos. Una propuesta no registra herramientas ni concede
permisos. La versión exacta debe superar sus pruebas y recibir aprobación humana
antes de activarse.

## Elegir el tipo de propuesta

| Tipo | Uso | Activación |
| --- | --- | --- |
| `workflow` | Combinar comandos registrados con parámetros tipados. | Revisión, ejecución de una prueba vinculada y recibos reales con postcondiciones. Conserva la política de cada comando. |
| `python_transform` | Normalizar texto, calcular valores, ordenar listas y construir datos JSON. | Pruebas declarativas ejecutadas por el intérprete, revisión del código y digest, aprobación y activación explícitas. |
| `source_proposal` | Proponer una integración, API o adaptador que todavía requiere desarrollo. | Solo exportación y revisión técnica. Requiere integración, pruebas y reconstrucción de la aplicación; no se importa ni ejecuta automáticamente. |

Las llamadas de generación usan el modelo/proveedor seleccionado con
`allow_paid=false`. El objetivo, los contratos pertinentes y la definición previa
son datos enviados al modelo. Las instrucciones de un documento o la respuesta del
modelo no pueden conceder permisos ni aprobar una versión.

El taller permite hasta dos respuestas del modelo dentro de un plazo compartido
de 70 segundos. Si el JSON o su contrato son inválidos, devuelve el error del
validador y solicita una sola corrección con la misma selección de proveedor y
modelo. No reintenta errores de conexión, cancelación, autenticación ni solicitudes
de aclaración. Solo guarda la propuesta que supera la validación estática; registra
`generation_attempts` sin guardar credenciales. Las pruebas de código siguen siendo
un paso separado y no conceden aprobación. El ciclo de objetivos limita esta
generación a una llamada para conservar su presupuesto global existente.

Cuando el motor seleccionado es ChatGPT/Codex, el taller usa `@codex` y el modelo
explícito mediante el proveedor ya conectado. Cada propuesta abre una conversación
independiente con `purpose=capability`, sin herramientas dinámicas; las solicitudes
de herramientas o permisos del runtime se rechazan. Se conservan la comprobación
de identidad y el permiso de uso incluido de la cuenta. Si falla autenticación,
modelo, coste incluido o plazo, la propuesta falla: no cambia a otro proveedor.
Esta política del proveedor no equivale a una garantía sobre herramientas nativas
internas de versiones del runtime que ignoren sus flags; la ejecución local de una
`python_transform` sí se limita al intérprete descrito abajo.

## Uso en la aplicación

1. Abre **Crear y mejorar capacidades** en el perfil de Axx, o escribe
   `/capacidad` en el chat. Describe el objetivo y selecciona el tipo adecuado.
2. Crea la propuesta. Revisa código, contratos de entrada/salida, casos esperados
   y huella SHA256. La generación deja un borrador.
3. Para `python_transform`, pulsa **Ejecutar pruebas de esta versión**. Los
   resultados muestran el valor realmente calculado; una prueba fallida impide la
   aprobación. Corrige la definición guardando una nueva versión.
4. Pulsa **Aprobar este código y sus contratos** y después **Activar comando
   aprobado**. Cada aprobación corresponde a una revisión y digest concretos.
5. Pulsa **Usar comando**, completa sus parámetros tipados y prepara la operación
   en la biblioteca. Revisa y ejecuta la operación. El resultado conserva digest y
   evidencia del cálculo puro en el historial del ejecutor.
6. **Desactivar capacidad** retira su herramienta ejecutable. Las operaciones
   preparadas para un ID retirado quedan bloqueadas. Se conservan versiones y
   resultados anteriores.

Editar o pedir una mejora crea una revisión sin aprobación ni pruebas heredadas.
La revisión activa anterior sigue disponible hasta activar su reemplazo o
desactivarla. Restaurar una versión histórica crea otro borrador: vuelve a exigir
pruebas y aprobación. Al reiniciar, Axx reconstruye el catálogo desde las
revisiones activas guardadas en SQLite.

## Contrato de una transformación

La definición admite exactamente estas claves:

```json
{
  "kind": "python_transform",
  "title": "Calcular total",
  "objective": "Multiplicar cantidad y precio, redondeando a dos decimales",
  "source": "def run(inputs):\n    return round(inputs[\"quantity\"] * inputs[\"price\"], 2)",
  "schema": {
    "type": "object",
    "properties": {
      "quantity": {"type": "integer", "minimum": 0, "maximum": 100},
      "price": {"type": "number", "minimum": 0, "maximum": 1000}
    },
    "required": ["quantity", "price"],
    "additionalProperties": false
  },
  "output_schema": {"type": "number"},
  "tests": [{"inputs": {"quantity": 2, "price": 3.5}, "expected": 7.0}],
  "readme": "Cálculo puro. Revisar unidades y redondeo antes de activar."
}
```

La entrada es un objeto JSON tipado; la salida puede ser un objeto, array, texto,
número, entero, booleano o `null`. Los objetos declaran `properties` y `required`;
no admiten propiedades adicionales. Los arrays requieren `items` tipados. Se
admiten `description`, `enum`, límites de longitud/items y límites numéricos.
No se admiten referencias, expresiones regulares, valores por defecto ni tipos
implícitos. Los tests deben cubrir casos representativos: aprobar unos ejemplos
no demuestra la corrección para todas las entradas posibles.

## Sintaxis de código admitida

El archivo contiene únicamente `def run(inputs):`, sin decoradores, anotaciones,
argumentos adicionales ni funciones anidadas. Axx analiza el AST y lo interpreta;
no usa `exec`, `eval` ni carga el código como un módulo Python.

- Asignaciones a variables locales, `+=` y operaciones equivalentes, `return`,
  `if/else` y `for` sobre colecciones acotadas. No existe `while` ni `for/else`.
- Valores JSON, listas, diccionarios con claves de texto, índices y slices.
- Aritmética `+ - * / // %`, comparaciones, pertenencia, booleanos y expresiones
  condicionales. No se admiten potencias ni operadores bit a bit.
- Funciones: `len`, `str`, `int`, `float`, `round`, `abs`, `sum`, `min`, `max`,
  `sorted`, `range` y `bool`.
- Métodos exclusivamente sobre texto: `strip`, `lstrip`, `rstrip`, `lower`,
  `upper`, `title`, `capitalize`, `replace`, `split`, `join`, `startswith`,
  `endswith` y `count`.

No hay imports, comprehensions, lambdas, recursión, argumentos por nombre,
expansiones, introspección ni acceso arbitrario a atributos. No hay acceso a
archivos, red, procesos, reloj, variables de entorno ni credenciales. La entrada
se copia y no puede modificarse mediante asignaciones a índices ni métodos de
mutación. El texto recibido se trata como datos.

## Presupuestos reales

| Recurso | Límite |
| --- | --- |
| Fuente UTF-8 | 16.000 bytes |
| AST | 600 nodos; profundidad 32 |
| Instrucciones por ejecución/test | 12.000 pasos del intérprete |
| Tiempo por ejecución/test | 2 segundos de reloj monotónico |
| Tiempo de la batería de tests | 10 segundos compartidos por todos los casos |
| Valor JSON | 64.000 bytes; 3.000 nodos; profundidad 16 |
| Colección/rango | 1.000 elementos |
| Texto | 16.000 caracteres, sujeto también al límite de bytes JSON |
| Número | Finito; valor absoluto máximo 10^12 |
| Precisión de `round` | De -16 a 16 |
| Esquemas | Profundidad 8; 32 propiedades por objeto |
| Tests por revisión | De 1 a 32 |
| Definición completa | 64.000 caracteres serializados, según el límite del taller |

Cada paso consulta la cancelación y el plazo monotónico. El plazo de una prueba
individual se recorta al tiempo restante de la batería. Los plazos se comprueban
entre operaciones acotadas; no son una interrupción del proceso en tiempo real.
Al cancelar o agotar los 10 segundos, los casos restantes figuran como no
ejecutados y fallidos; la revisión no puede aprobarse con resultados parciales.
Se limitan concatenaciones, repeticiones,
rangos y reemplazos antes de sus asignaciones grandes. Rebasar un presupuesto,
cancelar, producir un número no finito o incumplir el esquema genera un error,
sin efecto externo que revertir. Los presupuestos son límites del intérprete,
no una promesa de latencia constante.

## Registro, evidencia y validación

El ID tiene la forma `axx.generated.<capacidad>.r<revision>.<digest16>` y cambia
con cada revisión. El registro guarda fuente, esquemas, SHA256 de la fuente y
digest de la definición. Activación, sustitución y desactivación usan el catálogo
dinámico de `CommandService`; la ejecución vuelve a comprobar registro vigente,
entrada, fuente, presupuesto y esquema de salida.

Pruebas del intérprete y ciclo persistente:

```powershell
.\.venv\Scripts\python.exe -m unittest backend.tests.test_generated_commands backend.tests.test_capability_workshop
```

Prueba de interfaz con Edge aislado, servidor HTTP autenticado real, SQLite y el
ejecutor real; solo el transporte Tauri y la respuesta del modelo son fixtures:

```powershell
$env:AXX_TEST_BROWSER_NATIVE = '1'
.\.venv\Scripts\python.exe -m unittest backend.tests.test_capability_workshop_ui
```

Esta prueba de navegador no sustituye la validación visual/funcional de la
aplicación Tauri instalada ni acredita acceso a aplicaciones externas nuevas.
