# Biblioteca documental importada el 19 de octubre de 2026

El archivo `source/AXX_2026-10-18_08-00_REVISADO_v1.zip` se recuperó en modo
de lectura de Google Drive, ID `1iFeY3CBb8GjEqeTJs-uBYq-gd110pG0T`.
Su SHA256 coincide con la entrega autorizada:
`5d9445889c943cdfd22383ce43a719027c1c9698e218d487ba5ee7261f13d93d`.
El importador también verifica los tamaños y hashes declarados de los doce
miembros documentales del paquete. Ningún miembro se extrae o se ejecuta.

El mapa acumulado aporta 7.562 IDs únicos: 7.351 principales (2.447 revisados
documentalmente y 4.904 heredados sin recertificar) y 211 suplementos excluidos.
El ZIP de este lote contiene **cuatro recetas completas**, no 7.562 recetas
completas. Los demás registros solo aportan metadatos y frases documentadas.
Todos los registros importados conservan `DOCUMENTED_NOT_EXECUTED` y
`execution_enabled: false`; las frases no habilitan ejecución automática.

Los dos paquetes opcionales de `source/` se conservaron como especificaciones
de referencia. Sus programas y pruebas históricas no se ejecutaron, copiaron
como adaptadores ni confundieron con pruebas de esta integración:

| Archivo | SHA256 calculado al recuperar |
|---|---|
| `Axx_mecanismos_enlace_v1_2026-10-17.zip` | `0854d3299af18fe1fe13f2dd180ccef641069f07d8125e97cb71e815f8391dd0` |
| `Axx_voz_catalogo_completo_v1_2026-10-17.zip` | `d0c94eb0a644660fe0df125a9876ca363054133e0a22e4e16739b178e8cbdf96` |

Los hashes de los dos paquetes opcionales son evidencia de los bytes
recuperados, no una recertificación de su funcionamiento. Sus propios
documentos declaran adaptadores pendientes y ejecución desactivada.

Para reproducir el catálogo desde la raíz del proyecto:

```powershell
python scripts/import_command_library.py evidence/command-library-20261019/source/AXX_2026-10-18_08-00_REVISADO_v1.zip
python -m unittest scripts.test_import_command_library -v
```

El importador rechaza un SHA256 distinto al autorizado antes de escribir
resultados. Produce `resources/command-library.json` y
`resources/command-library.provenance.json`. La procedencia registra el hash
del catálogo y los conteos realmente importados.

Para revertir solo esta importación documental, retirar ambos JSON de
`resources/` y los scripts de importación/pruebas. No se modificó ningún
archivo de estado del usuario ni se ejecutó ninguna receta del catálogo.
