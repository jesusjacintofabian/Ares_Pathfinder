# Plan de fases

> Este plan es una **propuesta interna** del proyecto. No es un requisito de NASA.
> Se puede ajustar. Aquí se conserva el contenido técnico de cada fase; el reparto por
> carpetas del equipo está en `docs/FLUJO_GIT.md`.

**Total: 7 fases (0 a 6).** Cada fase termina con una entrega verificable.

| Fase | Nombre | Estado | Entregable verificable |
|------|--------|--------|------------------------|
| 0 | Preparación | ✅ Hecha | Repositorio clonado, entorno funcionando, primer Pull Request integrado |
| 1 | Datos GIS | ✅ Hecha | Datos sintéticos reproducibles y topografía MOLA documentada en `docs/FUENTES_DE_DATOS.md` |
| 2 | Backend base | ✅ Hecha | API con `/health`, `/map` y `/routes`; fuente sintética o MOLA |
| 3 | Frontend base | ✅ Hecha | Mapa Leaflet con relieve MOLA global colorizado, detalle de región para rutas y capas opcionales |
| 4 | Ruta y riesgo | ✅ Hecha | A* con costo por pendiente y riesgo simulado o proxy topográfico MOLA; ruta dibujada en el mapa |
| 5 | Pruebas y documentación | 🔄 En curso | Pytest, pruebas jsdom de la interfaz e integración sintético/MOLA/Gale hechas; falta actualizar la guía técnica (.docx) |
| 6 | Cierre y lecciones aprendidas | ⏳ Pendiente | Documento `docs/LECCIONES_APRENDIDAS.md` para llegar preparado al reto real |

## Detalle por fase

### Fase 0: Preparación
- Repositorio en GitHub, entorno virtual y proyecto base funcionando.
- Practicar el flujo: commit, push y, para cambios grandes, rama y Pull Request.

### Fase 1: Datos GIS
- Zona de estudio pequeña. Se usan dos fuentes: una cuadrícula **sintética** (aprendizaje) y un recorte
  de la topografía real **MOLA** (producto `megt90n000eb`).
- Fuentes, enlaces oficiales, formato y condiciones de uso en `docs/FUENTES_DE_DATOS.md`.

### Fase 2: Backend base
- Estructura FastAPI, modelos Pydantic, errores con formato único y selección de fuente de datos.
- Pendiente a partir de la elevación (en MOLA se calcula con diferencias finitas).

### Fase 3: Frontend base
- Mapa Leaflet, selector de capas, marcadores de origen y destino, consumo de los endpoints reales.

### Fase 4: Ruta y riesgo
- A* sobre una cuadrícula con costo por pendiente y riesgo; heurística admisible verificada contra Dijkstra.
- El riesgo sintético es simulado; MOLA ofrece un proxy topográfico educativo basado solo en pendiente, no un modelo de peligro real.

### Fase 5: Pruebas y documentación
- Pruebas del backend, del algoritmo y de MOLA con rasters pequeños temporales.
- `tests/integration_check.py` contra servidores reales (`--mola` para MOLA, `--gale` para Gale).
- Pruebas de la interfaz con jsdom (`frontend/tests/`) y lista de comprobación manual en el README.
- Pendiente: guía técnica extendida (cómo se construyó, F6 y la interfaz de Gale). La versión
  anterior de la guía se retiró por estar desactualizada.
- Que cualquier persona nueva pueda levantar el proyecto solo con el README.

### Fase 6: Cierre
- Retrospectiva: qué funcionó, qué tardó más, qué se haría distinto.
- Lista de habilidades y patrones aprendidos para el reto real.
