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

Fuentes actuales:

```text
argenprop, cabaprop, mudafy, properati, remax, zonaprop
```
