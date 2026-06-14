# Inmob

Defensive ETL/data platform for Argentine real estate listing intelligence.

---

## 1. Configuración de Entorno desde Cero

Para correr este proyecto necesitás **Python 3.12+** y **Poetry** instalado en tu sistema.

### Paso 1: Instalar dependencias y crear el entorno virtual
Ejecutá el siguiente comando en la raíz del proyecto:
```bash
poetry install
```

### Paso 2: Activar el entorno virtual en tu terminal
Siempre que vayas a trabajar en el proyecto o correr scripts/tests, tenés que entrar al contexto del entorno virtual:
```bash
poetry shell
```
*(Alternativamente, podés ejecutar comandos anteponiendo `poetry run <comando>`)*.

---

## 2. CLI de Ingestión (Ejecutar el Scraper)

El CLI permite ejecutar la ingesta de avisos inmobiliarios a demanda. Los datos se persisten bajo la carpeta `data/raw/{fuente}/{propiedad_id}/` conteniendo exactamente `{fuente}_{propiedad_id}_raw_payload.html` (o `.json`) y `{fuente}_{propiedad_id}_raw_metadata.json`.

### Requisito Obligatorio
Debés indicar **o bien** el número de publicaciones (`--limit` / `-l`), **o bien** el número de páginas (`--pages` / `-p`). Si pasás ambos, la cantidad de publicaciones toma prioridad.

### Comandos de Ejemplo

* **Scrappear 50 publicaciones de todas las fuentes (CABA, más recientes):**
  ```bash
  poetry run inmob ingest --limit 50
  ```

* **Scrappear exactamente 2 páginas de listado de Properati:**
  ```bash
  poetry run inmob ingest --source properati --pages 2
  ```

* **Guardar resultados en una carpeta de destino personalizada:**
  ```bash
  poetry run inmob ingest --source mudafy --limit 10 --target-dir data/mi_carpeta
  ```

* **Ejecutar usando un archivo JSON de configuración con filtros de búsqueda personalizados:**
  ```bash
  poetry run inmob ingest --source zonaprop --limit 20 --config mis_filtros.json
  ```

### Opciones del CLI (`inmob ingest --help`)
* `-s, --source TEXT`: Portales a scrappear (`argenprop`, `cabaprop`, `remax`, `mudafy`, `properati`, `zonaprop` o `all`). [default: `all`]
* `-l, --limit INTEGER`: Límite máximo de propiedades por fuente.
* `-p, --pages INTEGER`: Cantidad de páginas de búsqueda a recorrer por fuente.
* `-d, --target-dir PATH`: Directorio raíz donde se guardarán los resultados. [default: `data/raw`]
* `-c, --config PATH`: Archivo JSON para sobreescribir la configuración interna de criterios.

---

## 3. Ejecución de Tests de Ingestión (Bronze)

La suite de pruebas automatizadas verifica el funcionamiento del scraper sobre las 6 fuentes integradas (usando directorios de prueba autolimpiables que no ensucian el repositorio).

Correlos usando pytest con import-mode:
```bash
poetry run pytest --import-mode=importlib
```

---

## 4. ¿Cómo sigue el ETL? De Bronze a Silver (Standardization)

Los datos crudos descargados por el scraper o acumulados en `data/raw/` representan el punto de partida de la etapa **Silver** del ETL.

### ¿Dónde se desarrolla la Capa Silver?
Toda la lógica de estandarización, limpieza, tipado y parseo semántico se escribe dentro de la carpeta:
📂 `src/inmob/standardization/`

### Tu Misión en la Capa Silver:
1. **Leer los archivos crudos** generados en `data/raw/{fuente}/`.
2. **Parsear el HTML o JSON**:
   - *Tip en RE/MAX:* En el HTML de RE/MAX, hay un tag `<script id="ng-state" type="application/json">` que contiene un JSON gigante con todos los datos estructurados por su servidor Angular (coordenadas, precio en USD/ARS, dormitorios, baños, expensas, etc.). Parseá ese JSON en lugar de hacer regexs complejas sobre el DOM HTML.
3. **Estandarizar los datos**: Transformar esos datos crudos a los modelos estructurados de tu negocio (normalización de nulos, monedas, metros cuadrados).
4. **Persistir en Silver**: Guardar los datos limpios en la capa Silver estructurada.
