# Ares Pathfinder 🚀

Mapa de planificación para una caminata de superficie (EVA) en Marte, desarrollado para el **NASA Space Apps Challenge 2026**: *Interplanetary Survival Guide: Martian Map*.

> **Importante:** proyecto de participantes del NASA Space Apps Challenge. No es un producto oficial de la NASA ni una recomendación de seguridad operacional: es un prototipo educativo y de planificación.

## 🎯 Problema y solución

**Problema.** Un astronauta en caminata sobre la superficie de Marte debe llegar a un objetivo científico valioso y regresar al hábitat sin exponerse a pendientes que su traje no permite ni a exposición evitable, y necesita poder cambiar de plan si el clima espacial empeora durante la salida.

**Región de estudio.** Cráter Gale, flanco noroeste del Monte Sharp (Aeolis Mons), donde Curiosity ha estudiado formaciones *boxwork*. La ventana usada (≈ 47 × 41 km) es provisional y **no marca la ubicación de formaciones *boxwork***: sus coordenadas no están verificadas en este repositorio.

**Solución.** Una API (FastAPI + A*) y un mapa interactivo (Leaflet) que calculan rutas sobre una cuadrícula de 600 m de la región y muestran de dónde viene cada capa:

| Capa | Etiqueta | Origen |
|---|---|---|
| Elevación | MEDIDO | DEM MOLA+HRSC de 200 m (USGS), agregado a 600 m |
| Pendiente | DERIVADO | Calculada a 200 m desde la elevación; se guarda la máxima del bloque |
| Índice de apantallamiento topográfico | MODELADO | Fracción de cielo visible desde el DEM; **no es una dosis** |
| Costo total de la ruta | ÍNDICE DEL PROYECTO | Combinación con pesos ajustables; **no es una probabilidad ni una garantía** |

- **Alerta solar:** `POST /api/v1/routes/shelter` calcula la ruta de menor costo hasta la «zona candidata de espera» más cercana (poca pendiente y relieve que tapa parte del cielo, según el modelo). Si no hay ninguna cerca, responde `NO_SHELTER`: es un resultado del modelo, no un fallo.
- **Imagen óptica de contexto:** mosaico Viking MDIM 2.1 de NASA Mars Trek (capa opcional, requiere Internet).
- **Pesos ajustables** de pendiente y radiación modelada por solicitud.

**Lo que este prototipo todavía NO incluye** (para no sobrestimarlo): datos térmicos (THEMIS), mapa geológico de la USGS, la ruta propuesta de Curiosity georreferenciada, terreno blando, la elevación en el modelo de radiación, ni datos de clima espacial en tiempo real. La radiación es un modelo educativo con supuestos documentados en `docs/FUENTES_DE_DATOS.md`, anclado conceptualmente en las mediciones del instrumento RAD de Curiosity (cuyas cifras no se verificaron contra el artículo completo y no se usan en el cálculo).

## 👥 Equipo

| Integrante | Responsabilidad |
|---|---|
| **Jesús** | Backend, algoritmo A*, procesamiento de datos, pruebas y documentación |
| **Aldo** | Frontend (interfaz web con Leaflet) |

## 🤖 Uso de IA

Este proyecto se desarrolló con asistencia de IA, y lo declaramos como pide NASA Space Apps:

- **Código, pruebas y documentación** se escribieron con ayuda de Claude (Anthropic), mediante chat y Claude Code. Los commits hechos con esa asistencia llevan la línea `Co-Authored-By: Claude` en su mensaje.
- El equipo definió el problema, eligió la región y los recursos, revisó los resultados y es responsable del contenido.
- Los **datos científicos** provienen de las fuentes citadas en `docs/FUENTES_DE_DATOS.md`, no de la IA.
- Las imágenes del mapa (`frontend/assets/`) se generan con scripts a partir del raster MOLA (`data/render_mola_preview.py`, `data/process_mola_global.py`), no con IA generativa.
- Hay un agente de apoyo para GitHub Copilot en `.github/agents/`.

## 🧰 Tecnologías

- **Frontend:** HTML, CSS y JavaScript sin frameworks.
- **Mapa interactivo:** Leaflet 1.9.4 (incluido en `frontend/vendor/`, sin CDN).
- **Backend:** Python, FastAPI, Uvicorn y Pydantic.
- **Algoritmos:** A* para encontrar rutas (`algorithms/astar.py`, solo biblioteca estándar).
- **Datos:** cuadrícula sintética reproducible y topografía MOLA (PDS4/ENVI, leída con NumPy).
- **Control de versiones:** Git y GitHub.
- **Pruebas:** Pytest, un script de integración y pruebas de la interfaz con jsdom (`cd frontend && npm test`; ver `frontend/README.md`).

## 📁 Estructura del repositorio

```text
Ares_Pathfinder/
├── frontend/                 # Interfaz web y mapa Leaflet
│   ├── index.html
│   ├── css/styles.css
│   ├── js/ (config.js, api.js, map.js, app.js)
│   ├── assets/mola-global.png   # relieve MOLA global, vista previa 0,5°
│   └── vendor/leaflet/       # Leaflet 1.9.4 local
├── backend/                  # API FastAPI
│   ├── app/ (main.py, errors.py, api/, models/, services/)
│   ├── tests/
│   ├── pytest.ini
│   └── requirements.txt
├── algorithms/               # Algoritmo A* y costos de ruta
├── data/
│   ├── generate_synthetic_grid.py   # genera los datos sintéticos
│   ├── mola_reader.py               # lector de rasters MOLA (PDS4/ENVI)
│   ├── process_mola.py              # recorta una región MOLA a JSON
│   ├── geotiff_reader.py            # lector GeoTIFF int16 (local o por rangos HTTP)
│   ├── process_dem.py               # recorta el DEM MOLA+HRSC 200 m a JSON (Gale)
│   ├── render_mola_preview.py       # genera la vista global ligera del mapa
│   ├── raw/mola/                    # originales (.xml y .hdr versionados; .img se descarga)
│   ├── raw/gale/                    # recorte crudo del DEM de Gale (no versionado)
│   └── processed/                   # cuadrículas JSON listas para la API
├── docs/
│   ├── PLAN_DE_FASES.md
│   ├── ARQUITECTURA.md
│   ├── FUENTES_DE_DATOS.md
│   ├── CONTRATO_DE_DATOS.md
│   └── FLUJO_GIT.md
├── tests/                    # Comprobación de integración (servidores reales)
├── .github/agents/           # Agente Ares.AI para GitHub Copilot
├── .gitignore
└── README.md
```

## 🗺️ Funcionalidades

1. Mostrar una zona en un mapa interactivo (cuadrícula sintética o vista global de relieve MOLA con región de detalle).
2. Activar y desactivar capas de información.
3. Seleccionar un punto de origen y un destino en cualquier lugar del globo MOLA.
4. Calcular una ruta con A* en el backend: malla global aproximada de 1° o detalle local.
5. Considerar costos de distancia, pendiente y el proxy de pendiente MOLA (o riesgo simulado en el modo sintético).
6. Dibujar la ruta calculada sobre el mapa.
7. Mostrar un resumen: distancia, costo, pasos, pendiente máxima y riesgo.

El modo sintético identifica sus riesgos como simulados. En modo MOLA se muestra
un proxy educativo de riesgo topográfico derivado únicamente de la pendiente:
`min(pendiente / 20°, 1)`. Se calcula para la malla global y el detalle y también
penaliza rutas. No es una probabilidad ni modela peligros geológicos o condiciones
de misión; no debe interpretarse como evaluación de seguridad.

## 🛠️ Plan de trabajo y estado

| Fase | Nombre | Estado | Entregable |
|---|---|---|---|
| 0 | Preparación | ✅ Hecha | Repositorio organizado y entorno preparado. |
| 1 | Datos y mapa inicial | ✅ Hecha | Datos sintéticos y región MOLA documentadas en `docs/FUENTES_DE_DATOS.md`. |
| 2 | Backend básico | ✅ Hecha | API con `/health`, `/map` y `/routes`. |
| 3 | Frontend básico | ✅ Hecha | Mapa Leaflet con capas y controles. Pruebas jsdom y verificación en Firefox headless; queda la lista de comprobación manual (abajo) para otros navegadores y táctil. |
| 4 | Rutas y riesgos | ✅ Hecha | A* con costos de pendiente y riesgo simulado o proxy topográfico MOLA. |
| 5 | Pruebas e integración | 🔄 En curso | 445 pruebas Pytest, 29 pruebas jsdom e integración sintético/MOLA/Gale hechas; falta una guía técnica extendida. |
| 6 | Cierre y entrega | ⏳ Pendiente | Demostración, formulario de Space Apps y lecciones aprendidas. |

Las fases pueden modificarse si aparecen dificultades técnicas o si hace falta aprender alguna tecnología antes de continuar.

## 🚀 Cómo comenzar

### 1. Clonar el repositorio

```bash
git clone https://github.com/<usuario>/Ares_Pathfinder.git
cd Ares_Pathfinder
```

### 2. Preparar el backend (desde la raíz, una sola vez)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
```

`requirements.txt` incluye FastAPI, Uvicorn, Pydantic, Pytest, httpx2 y **NumPy** (necesario para el lector MOLA; se importa incluso en modo sintético). Las versiones están fijadas; se verificaron con Python 3.12.3 (el entorno del autor usa Python 3.14).

### 3. Comprobar que todo funciona

```bash
cd backend
python -m pytest -q          # deben pasar 445 pruebas
```

Pruebas de la interfaz (jsdom, requieren Node.js 22.22+ o 24.15+):

```bash
cd frontend
npm install                  # una vez; jsdom es solo dependencia de desarrollo
npm test                     # deben pasar 29 pruebas
```

### 4. Ejecutar backend y frontend

```bash
# Terminal 1 — backend (desde backend/, con el entorno activado)
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# Terminal 2 — frontend (desde frontend/)
python3 -m http.server 5500 --bind 127.0.0.1
# Abrir http://127.0.0.1:5500
```

Documentación interactiva de la API en http://127.0.0.1:8000/docs.

### 5. Comprobación de integración (desde la raíz, con ambos servidores activos)

```bash
python3 tests/integration_check.py            # modo sintético: 26 comprobaciones
python3 tests/integration_check.py --mola     # backend con MARS_DATA_SOURCE=mola (Valles Marineris): 30 comprobaciones
python3 tests/integration_check.py --gale     # backend con MARS_DATA_SOURCE=mola MARS_MOLA_REGION=gale: 39 comprobaciones
```

Cada modo comprueba que el backend se inició como se espera: por ejemplo, `--mola` contra un
backend de Gale falla a propósito.

### 6. Lista de comprobación manual en el navegador

Las pruebas automáticas (jsdom) no pintan, y la verificación en Firefox headless no cubre
pantallas reales, táctil ni otros navegadores. Antes de una demostración, revisa a mano, con
ambos servidores activos (marca cada punto):

**Modo sintético** (backend sin variables)
- [ ] El banner dice «DATOS SIMULADOS» y no aparecen etiquetas de procedencia, pesos ni alerta solar.
- [ ] Origen en fila 2, col 1 y destino en fila 2, col 12 → «Ruta calculada: 14 pasos, 1772.8 m».
- [ ] Un clic en una celda bloqueada muestra el aviso y no la selecciona.

**MOLA, Valles Marineris** (`MARS_DATA_SOURCE=mola`)
- [ ] Las capas llevan etiquetas (MEDIDO, DERIVADO, ÍNDICE DEL PROYECTO) y al pasar el cursor se ve la fuente.
- [ ] «Ir a zona MOLA»: un clic en una celda la selecciona; un clic fuera de la zona usa la malla global.
- [ ] Pendiente y cuadrícula se activan y desactivan; el zoom y el arrastre van fluidos.
- [ ] Capa de Perseverance: el clic en un marcador abre su ventana y al pasar por la trayectoria se ve su tooltip.
- [ ] Con Internet: imagen Viking y nombres de lugares.

**MOLA, Gale** (`MARS_DATA_SOURCE=mola MARS_MOLA_REGION=gale`)
- [ ] Aparecen «Pesos del costo», «Alerta solar» y la casilla «Índice de apantallamiento» (MODELADO).
- [ ] El deslizador y el campo numérico de cada peso se sincronizan; 150 muestra un error y deshabilita «Calcular ruta»; «Restablecer» vuelve a 0,05 y 0.
- [ ] Una ruta muestra «Pesos aplicados»; con radiación 5 el costo sube.
- [ ] La capa de apantallamiento pinta la zona y su leyenda explica `1 − radiation_modeled` y sus límites.
- [ ] Alerta solar desde un origen libre: ruta ámbar discontinua, marcador «Zona candidata de espera», distancia, criterio y aviso educativo.
- [ ] Con distancia máxima 5 km desde lat −4.79°, lon E 137.75° aparece el mensaje informativo de que no hay zona candidata (no un error).
- [ ] Un origen fuera de la zona de detalle explica que la alerta solar solo funciona dentro.
- [ ] Capa de Curiosity: los marcadores dentro de Gale abren su ventana sin seleccionar la celda.
- [ ] En ningún texto aparece «refugio» ni se promete protección.

**General**
- [ ] Chrome, Firefox y Safari (o los que vayas a usar en la demostración).
- [ ] Móvil o pantalla táctil: tocar celdas, arrastrar y hacer zoom con dos dedos.
- [ ] Pantalla de alta densidad: las capas en canvas se ven nítidas.
- [ ] `?perf=1` en la URL muestra el recuadro de medición con `canvases` y el tiempo de pintado.

## 🌐 Datos geoespaciales

Antes de utilizar datos reales:

1. Seleccionar una zona de estudio pequeña.
2. Registrar la fuente, el formato, la fecha de consulta y la licencia o condiciones de uso.
3. Comprobar que pueden procesarse con las herramientas del proyecto.
4. Documentar cómo se prepararon.

Los archivos grandes no se incorporan al repositorio: el raster MOLA `megt90n000eb.img` (33 MB) está en `.gitignore` y se descarga desde PDS (ver más abajo). El label `.xml`, el header `.hdr`, las regiones procesadas (JSON pequeños) y la vista global optimizada (PNG) sí se versionan.

## 🛰️ Modo topográfico MOLA

La fuente es el producto `megt90n000eb` del archivo PDS4 de MOLA MEGDR: una matriz global de 2880 × 5760 elevaciones `SignedMSB2` (int16 big-endian), en metros respecto al areoide. Su resolución es 1/16°; 3.704461 km/píxel es la escala nominal en el ecuador marciano. El lector usa memoria mapeada y solo extrae la ventana geográfica solicitada para rutas.

El mapa incluye una imagen global de contexto (0,5°/píxel) y una malla MOLA
global de navegación de 1° (180 × 360), guardada comprimida en
`data/processed/mola_global_1deg.json.gz`. Al seleccionar dos puntos dentro del
recorte activo (Valles Marineris por defecto), A* usa el detalle local; si uno
queda fuera, usa la malla global aproximada. La malla global bloquea celdas con
pendiente máxima nativa de 20° o más. Es una regla educativa y no representa
una evaluación de seguridad o transitabilidad real. El mapa muestra también
una máscara de esos bloqueos sobre el planeta.
La API comprime automáticamente la respuesta JSON global con gzip para reducir
el tráfico; el navegador la descomprime sin pasos adicionales.

La vista colorizada se regenera con `python3 data/render_mola_preview.py`. La
malla de rutas y la máscara se generan juntas con `python3 -m data.process_mola_global`; requieren el raster MOLA original, y el generador
no sobrescribe archivos existentes.

### Regiones incluidas

| Archivo | Región (lat. / lon. este) | Celdas | Pendiente máx. | Celdas bloqueadas | Uso |
|---|---|---|---|---|---|
| `data/processed/mola_valles_marineris.json` | −14° a −12° / 291° a 293° | 32 × 32 | 32.2° | 96 (umbral 20°) | **Predeterminada en modo MOLA.** Tiene unos 9 km de desnivel, así que A* debe rodear obstáculos. |
| `data/processed/mola_region.json` | −1° a 1° / 179° a 181° | 32 × 32 | 2.5° | 0 (umbral 30°) | Muestra ecuatorial plana, útil como control. |
| `data/processed/gale_monte_sharp_600m.json` | −5.31° a −4.50° / 137.30° a 138.01° | 80 × 70 (600 m) | 34.9° | 15 (umbral 30°) | Cráter Gale, flanco noroeste del Monte Sharp. **DEM MOLA+HRSC de 200 m**, agregado a 600 m (pendiente máxima del bloque). Ventana provisional. Incluye la capa de radiación **MODELADA** (cielo visible desde el DEM; no es una medición). |

`POST /api/v1/routes` acepta los pesos opcionales `slope_weight` y `radiation_weight` (entre 0 y 100).
En regiones con `sky_view_factor` (hoy, Gale), `POST /api/v1/routes/shelter` (modo «alerta solar») calcula
la ruta a la **zona candidata de espera** más cercana por costo. En MOLA, `GET /api/v1/map` publica
`provenance` con la etiqueta de cada capa. El frontend muestra esas etiquetas y, en Gale, los pesos, la capa de
índice de apantallamiento y la alerta solar (ver `frontend/README.md`). Detalles en `docs/CONTRATO_DE_DATOS.md`. Es planificación educativa: ninguna
ruta ni zona se presenta como segura.

### Descargar el raster original (solo si quieres procesar otras regiones)

Obtén el `.img`, `.xml` y `.hdr` desde el [directorio oficial de PDS Geosciences Node](https://pds-geosciences.wustl.edu/mgs/urn-nasa-pds-mgs_mola_topography_derived/meg016/) y guárdalos sin modificar en `data/raw/mola/` (el `.xml` y el `.hdr` ya están en el repositorio; solo falta el `.img`). Comprueba el MD5 indicado en `docs/FUENTES_DE_DATOS.md`.

### Procesar una región nueva

```bash
python data/process_mola.py \
  --bounds -14 -12 291 293 \
  --max-slope-deg 20 \
  --output data/processed/mola_mi_region.json
```

El destino debe ser nuevo: el procesador no sobrescribe archivos existentes. `--bounds` recibe `sur norte oeste este` en grados (latitud planetocéntrica, longitud positiva este entre 0° y 360°). La ventana no puede cruzar el meridiano 0 y está limitada a 250.000 celdas. Las celdas sin dato se marcan inválidas y bloqueadas. El umbral de bloqueo por pendiente (30° por defecto) es demostrativo.

### Procesar una ventana del DEM MOLA+HRSC (200 m)

El GeoTIFF global del USGS ocupa unos 11 GB y **no se descarga**. `data/process_dem.py` lee por rangos
HTTP solo la ventana pedida y guarda un recorte crudo pequeño para reprocesar sin red. No añade
dependencias: solo usa NumPy.

```bash
python data/process_dem.py \
  --dem https://planetarymaps.usgs.gov/mosaic/Mars/HRSC_MOLA_Blend/Mars_HRSC_MOLA_BlendDEM_Global_200mp_v2.tif \
  --bounds -5.3 -4.5 137.3 138.0 --aggregate 3 \
  --save-raw data/raw/gale/mi_recorte.tif \
  --output data/processed/gale_mi_ventana.json

# Radiación MODELADA: el horizonte se busca hasta 10 km (también es el margen de lectura).
# --horizon-radius-km 0 la desactiva.

# Reprocesar después sin red, desde el recorte crudo:
python data/process_dem.py --dem data/raw/gale/mi_recorte.tif \
  --bounds -5.3 -4.5 137.3 138.0 --aggregate 3 --output data/processed/otra.json
```

`--aggregate 3` agrupa 3 × 3 píxeles (celdas de 600 m): media de la elevación y máximo de la pendiente
calculada a 200 m. Ni la salida ni el recorte sobrescriben archivos existentes. La procedencia y la
verificación están en `docs/FUENTES_DE_DATOS.md`.

### Activar el modo MOLA en la API

```bash
cd backend
MARS_DATA_SOURCE=mola uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Sin más configuración se usa Valles Marineris. Para elegir una región incluida por su nombre, usa `MARS_MOLA_REGION=gale` (o `ecuatorial` o `valles_marineris`). Para otro archivo, añade `MARS_MOLA_GRID_FILE=../data/processed/mola_mi_region.json`, que tiene prioridad. Si falta el archivo, la API responde `503 DATASET_UNAVAILABLE`.

La sección **Imágenes de misiones NASA** consulta en tiempo real el catálogo público [NASA Image and Video Library](https://images.nasa.gov/) y permite explorar imágenes por Perseverance, HiRISE, THEMIS, CTX y HRSC. Requiere conexión a Internet. Las imágenes son resultados del catálogo y se abren en su recurso de vista previa; la atribución específica se conserva en los registros de NASA. Esta galería es independiente de la cuadrícula MOLA y no modifica los datos usados por A*.

En modo MOLA el frontend muestra el relieve global colorizado generado localmente desde el producto MOLA; no necesita Internet. Usa «Marte completo» para la vista global y «Ir a zona MOLA» para acercarte al recorte de mayor detalle. Es posible seleccionar puntos en todo el mapa y calcular rutas aproximadas globales; las rutas dentro del recorte usan su resolución de detalle. La imagen Viking MDIM 2.1 de [NASA Mars Trek](https://trek.nasa.gov/mars/) está disponible como capa opcional en línea. Las capas de misiones y la galería están plegadas inicialmente para mantener el panel más despejado.

Las solicitudes de ruta pueden usar índices locales `{row, col}` o coordenadas geográficas `{latitude, longitude}` en MOLA. La distancia usa un tamaño nominal de celda y es aproximada; las rutas globales tienen celdas de 1° (unos 59 km en el ecuador). El resultado **no** evalúa seguridad, riesgos geológicos ni condiciones de misión.

## 🔌 Integración entre frontend y backend

El frontend envía al backend coordenadas geográficas para MOLA y recibe la ruta georreferenciada lista para dibujar. El formato exacto está en `docs/CONTRATO_DE_DATOS.md`; cualquier cambio de campos debe reflejarse allí y en la documentación técnica.

## 🔀 Flujo de trabajo con Git y GitHub

Trabajo individual: `main` se mantiene estable y se avanza con commits pequeños y descriptivos (`tipo(ámbito): descripción`). Para cambios grandes o experimentales se recomienda una rama corta y un Pull Request hacia `main`. Detalles en `docs/FLUJO_GIT.md`.

## 📋 Reglas del proyecto

- No subir contraseñas, tokens, claves privadas ni credenciales (el `.gitignore` excluye `.env`, `*.pem` y `*.key`).
- No subir `.venv/`, `__pycache__/` ni archivos de datos grandes.
- Documentar las fuentes de los datos utilizados.
- Identificar claramente los datos sintéticos y los resultados simulados.
- No afirmar que una ruta es segura para una misión real: este prototipo es educativo.
- Mantener actualizada la documentación cuando cambie la arquitectura o el formato de los datos.
- Respetar las reglas del NASA Space Apps Challenge: listar todos los recursos externos usados y declarar el uso de IA.
- Los datos derivados del DEM MOLA+HRSC conservan su atribución y licencia (MOLA: CC0; HRSC: CC BY-SA 3.0 IGO; ver `docs/FUENTES_DE_DATOS.md`).

## 📚 Documentación

- **`docs/PLAN_DE_FASES.md`:** etapas y estado del trabajo.
- **`docs/ARQUITECTURA.md`:** componentes y flujo de datos, incluido MOLA.
- **`docs/FUENTES_DE_DATOS.md`:** procedencia y condiciones de uso de los datos.
- **`docs/CONTRATO_DE_DATOS.md`:** formato de intercambio de la API v1.
- **`docs/FLUJO_GIT.md`:** ramas, commits y Pull Requests.

## 🎓 Propósito

Ares Pathfinder es un prototipo educativo para mostrar cómo se pueden combinar datos de la NASA (topografía, imagen orbital y un modelo de exposición) para planificar una salida de superficie en Marte, dejando siempre claro qué es dato medido, qué es derivado y qué es modelado.

---

**Equipo:** Jesús (backend, datos y algoritmos) y Aldo (frontend)  
**Repositorio:** Ares_Pathfinder  
**Estado:** Prototipo funcional para NASA Space Apps Challenge 2026.


## Capas de trayectorias rover

En modo MOLA, el panel **Exploración de rovers** permite activar y desactivar capas para
Perseverance (Jezero), Curiosity (Gale), Opportunity (Meridiani), Spirit (Gusev) y
Zhurong (Utopia Planitia). Cada capa dibuja una polilínea de referencia, el sitio de
aterrizaje y puntos geográficos destacados. Al elegir una de estas misiones en el
selector, el mapa se centra en su región y activa su capa; la consulta de imágenes NASA
sigue disponible como función complementaria.

**Nota de rigor:** las coordenadas de las polilíneas incluidas en este prototipo son
trazados de referencia aproximados para interacción y demostración cartográfica; no
son registros de telemetría ni recorridos oficiales completos. Se representan sobre
la vista topográfica MOLA global, con la cuadrícula de detalle local cuando coincide
con la región disponible. La vista global no convierte esa cobertura local en una
cobertura topográfica de detalle para el cálculo de rutas.
