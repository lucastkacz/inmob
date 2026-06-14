# Inmob

Defensive ETL/data platform for Argentine real estate listing intelligence.

---

## ¡TOMAS, LEÉ ESTO ANTES DE TOCAR UNA SOLA LÍNEA DE CÓDIGO!

Este repositorio contiene la arquitectura base para la adquisición defensiva de datos inmobiliarios en Argentina. La estructura sigue el patrón clásico de capas de un Data Lake (Bronze -> Silver -> Gold). Actualmente, la capa **Bronze** (Ingestión de crudos) está funcional para RE/MAX.

---

## 1. Configuración de Entorno desde Cero

Para correr este proyecto necesitás **Python 3.12+** y **Poetry** instalado en tu sistema. No uses `pip` global ni crees entornos virtuales a mano; dejamos que Poetry maneje todo.

### Paso 1: Instalar dependencias y crear el entorno virtual
Ejecutá el siguiente comando en la raíz del proyecto. Esto leerá el archivo `pyproject.toml`, resolverá las dependencias y creará un entorno virtual localizado en `.venv/`:
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

## 2. Ejecución de Tests de Ingestión (Bronze)

La capa Bronze se encarga de ir a buscar datos a los portales, lidiar con límites de tráfico y guardar la evidencia cruda en disco **sin parsear semánticamente ningún dato**.

Para RE/MAX, tenemos tests de integración que simulan el scraping. Correlos con `pytest` indicando que muestre la salida estándar (`-s`):

### Ejecutar el test bulk de exportación cruda:
```bash
poetry run pytest -s tests/integration/ingestion/sources/remax/test_bulk_raw_export.py
```
**¿Qué hace este test exactamente?**
1. Consulta la API de búsqueda de RE/MAX para la primera página (24 publicaciones).
2. Descubre los 24 links únicos de publicaciones.
3. Descarga de forma educada (con rate limit y reusando la sesión para evitar bloqueos temporales de Cloudflare) el HTML completo de cada publicación.
4. Persiste los resultados en el directorio local:
   📂 `TOMAS_ACA_TENES_LOS_RAW_DE_REMAX/`
   Ahí vas a encontrar por cada propiedad:
   - Un archivo `.html` con el código fuente pre-renderizado del servidor.
   - Un archivo `.metadata.json` con metadatos de la descarga (URL final, timestamp, status code, headers).

---

## 3. ¿Cómo sigue el ETL? De Bronze a Silver (Standardization)

La carpeta temporal `TOMAS_ACA_TENES_LOS_RAW_DE_REMAX/` contiene la **evidencia Bronze**. Con esto arranca la etapa **Silver** del ETL.

### ¿Dónde se desarrolla Silver?
Toda la lógica de estandarización, limpieza, tipado y parseo semántico se escribe dentro de la carpeta:
📂 `src/inmob/standardization/`

### Tu Misión en la Capa Silver:
1. **Leer los archivos crudos** generados en `TOMAS_ACA_TENES_LOS_RAW_DE_REMAX/`.
2. **Parsear el HTML**:
   - *Tip Pro:* En el HTML pre-renderizado que bajamos de RE/MAX, hay un tag `<script id="ng-state" type="application/json">` que contiene un JSON gigante con todos los datos estructurados ya serializados por su servidor de Angular (coordenadas, precio en USD/ARS, dormitorios, baños, expensas, etc.). ¡No te vuelvas loco haciendo expresiones regulares complejas sobre el DOM! Parseá ese JSON.
3. **Estandarizar los datos**: Transformar esos datos crudos a los modelos estructurados de tu negocio (tipos de datos limpios, normalización de strings, manejo de nulos).
4. **Persistir en Silver**: Guardar los datos limpios en el almacén de datos estructurados correspondiente.
