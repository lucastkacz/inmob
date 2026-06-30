from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from inmob.cli.cli import app


LISTING_URL = (
    "/casas-departamentos-venta-recoleta-mas-de-2-banos-mas-de-1-garage-"
    "menos-300000-dolar.html"
)
PUBLIC_URL = f"https://www.zonaprop.com.ar{LISTING_URL}"
TARGET_DIR = Path("data/bronze")
LOG_DIR = Path("logs")
FILTERS = {
    "ambientesmaximo": 0,
    "ambientesminimo": 0,
    "banos": "2",
    "city": "1003675",
    "garages": "1",
    "moneda": 2,
    "preciomax": "300000",
    "preTipoDeOperacion": "1",
    "province": None,
    "sort": "relevance",
    "subZone": None,
    "superficieCubierta": 1,
    "tipoAnunciante": "ALL",
    "tipoDeOperacion": "1",
    "tipoDePropiedad": "2,1",
    "valueZone": None,
    "zone": None,
}


def test_cli_live_casas_departamentos_venta_recoleta_usd_300000_mas_de_2_banos_mas_de_1_cochera_pagina_1(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "zonaprop-recoleta-filters.json"
    config_path.write_text(
        json.dumps(
            {
                "zonaprop": {
                    "filters": FILTERS,
                    "label": (
                        "zonaprop-recoleta-casas-deptos-venta-usd-300k-"
                        "2banos-1garage"
                    ),
                    "public_url": PUBLIC_URL,
                }
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    existing_run_dirs = _run_dirs(TARGET_DIR)

    result = CliRunner().invoke(
        app,
        [
            "ingest",
            "--source",
            "zonaprop",
            "--pages",
            "1",
            "--target-dir",
            str(TARGET_DIR),
            "--config",
            str(config_path),
            "--log-dir",
            str(LOG_DIR),
            "--log-level",
            "INFO",
            "--log-file-level",
            "INFO",
        ],
    )

    assert result.exit_code == 0, result.output

    new_run_dirs = _run_dirs(TARGET_DIR) - existing_run_dirs
    assert len(new_run_dirs) == 1
    run_dir = new_run_dirs.pop()

    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "completed"
    assert manifest["totals"]["search_targets_planned"] == 1
    assert manifest["totals"]["search_artifacts_persisted"] == 1
    assert manifest["totals"]["listing_targets_discovered"] > 0
    assert manifest["totals"]["listing_targets_selected"] <= 30
    assert manifest["totals"]["search_items_persisted"] > 0
    assert manifest["totals"]["listing_artifacts_persisted"] == 0
    assert manifest["totals"]["listing_details_succeeded"] == 0

    search_metadata_path = next(
        (run_dir / "zonaprop" / "search_results").glob("*/metadata.json")
    )
    search_metadata = json.loads(search_metadata_path.read_text(encoding="utf-8"))
    assert search_metadata["payload_path"] is None
    assert search_metadata["payload_size_bytes"] > 0
    assert search_metadata["payload_sha256"]
    assert search_metadata["target_metadata"]["public_url"] == PUBLIC_URL
    request_body = json.loads(search_metadata["target_metadata"]["request_body"])
    assert request_body["pagina"] == 1
    assert request_body["city"] == "1003675"
    assert request_body["moneda"] == 2
    assert request_body["preciomax"] == "300000"
    assert request_body["banos"] == "2"
    assert request_body["garages"] == "1"
    assert request_body["tipoDeOperacion"] == "1"
    assert request_body["tipoDePropiedad"] == "2,1"
    assert request_body["sort"] == "relevance"
    assert not list((run_dir / "zonaprop" / "search_results").glob("*/payload.json"))

    search_item_paths = sorted((run_dir / "zonaprop" / "search_items").glob("*.json"))
    assert len(search_item_paths) > 0
    assert len(search_item_paths) <= 30
    assert manifest["totals"]["search_items_persisted"] == len(search_item_paths)
    first_search_item = json.loads(search_item_paths[0].read_text(encoding="utf-8"))
    assert isinstance(first_search_item, dict)
    assert first_search_item.get("postingId") is not None
    assert not (run_dir / "zonaprop" / "listing_detail").exists()
    assert not (run_dir / "zonaprop" / "events.jsonl").exists()
    assert not list((run_dir / "zonaprop" / "search_items").glob("*/metadata.json"))

    print(f"\nBronze run: {run_dir}")
    print(f"Search metadata: {search_metadata_path}")
    print(f"Search items: {run_dir / 'zonaprop' / 'search_items'}")
    print("Primeras publicaciones:")
    for path in search_item_paths[:5]:
        posting = json.loads(path.read_text(encoding="utf-8"))
        print(
            "- "
            f"{posting.get('postingId')} | "
            f"{posting.get('title')} | "
            f"https://www.zonaprop.com.ar{posting.get('url')}"
        )


def _run_dirs(target_dir: Path) -> set[Path]:
    runs_dir = target_dir / "runs"
    if not runs_dir.exists():
        return set()
    return {path for path in runs_dir.iterdir() if path.is_dir()}
