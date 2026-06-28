# Inmob

Scraper de listings inmobiliarios de Argentina.

El objetivo del proyecto es bajar datos de portales inmobiliarios y guardar la
evidencia cruda en la capa Bronze para procesarla despues.

## Uso basico

```bash
poetry install
PYTHONPATH=src poetry run inmob ingest
```

Por defecto la bajada se guarda en:

```text
data/bronze
```

Layout Bronze por corrida:

```text
data/bronze/runs/{run_id}/manifest.json
data/bronze/runs/{run_id}/{source}/{target_kind}/{target_id}/payload.*
data/bronze/runs/{run_id}/{source}/{target_kind}/{target_id}/metadata.json
data/bronze/runs/{run_id}/{source}/events.jsonl
```

Bronze persiste tanto las respuestas de busqueda como los detalles crudos.

Fuentes actuales:

```text
argenprop, cabaprop, mudafy, properati, remax, zonaprop
```
