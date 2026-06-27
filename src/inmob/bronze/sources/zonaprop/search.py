"""Zonaprop postings API search payload construction."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


ZONAPROP_HOME_URL = "https://www.zonaprop.com.ar/"
ZONAPROP_API_POSTINGS_URL = "https://www.zonaprop.com.ar/rplis-api/postings"

BASE_SEARCH_PAYLOAD: dict[str, Any] = {
    "q": None,
    "direccion": None,
    "moneda": None,
    "preciomin": None,
    "preciomax": None,
    "services": "",
    "general": "",
    "searchbykeyword": "",
    "amenidades": "",
    "caracteristicasprop": None,
    "comodidades": "",
    "disposicion": None,
    "roomType": "",
    "outside": "",
    "areaPrivativa": "",
    "areaComun": "",
    "multipleRets": "",
    "tipoDePropiedad": "",
    "subtipoDePropiedad": None,
    "tipoDeOperacion": "1",
    "garages": None,
    "antiguedad": None,
    "expensasminimo": None,
    "expensasmaximo": None,
    "withoutguarantor": None,
    "habitacionesminimo": 0,
    "habitacionesmaximo": 0,
    "ambientesminimo": "0",
    "ambientesmaximo": "0",
    "banos": None,
    "superficieCubierta": None,
    "idunidaddemedida": 1,
    "metroscuadradomin": None,
    "metroscuadradomax": None,
    "tipoAnunciante": "ALL",
    "grupoTipoDeMultimedia": "",
    "publicacion": None,
    "sort": "more_recent",
    "etapaDeDesarrollo": "",
    "auctions": None,
    "polygonApplied": None,
    "idInmobiliaria": None,
    "excludePostingContacted": "",
    "banks": "",
    "places": "",
    "condominio": "",
    "preTipoDeOperacion": "1",
    "city": None,
    "province": None,
    "zone": None,
    "valueZone": None,
    "subZone": None,
    "coordenates": None,
}


@dataclass(frozen=True, slots=True)
class ZonapropSearchCriteria:
    """Generic Zonaprop postings API search criteria.

    Bronze does not own Zonaprop business mappings. Callers pass API-ready
    filter values through ``filters`` and this class only builds the request.
    """

    filters: dict[str, Any] = field(default_factory=dict)
    label: str | None = None
    public_url: str = ZONAPROP_HOME_URL
    page_size: int = 30

    def target_key(self) -> str:
        """Return a stable source-local key for artifact names and lineage."""

        return self.label or "zonaprop-api-search"

    def build_url(self, *, page: int) -> str:
        """Return the public URL represented by this API search."""

        if page <= 0:
            raise ValueError("page must be greater than zero")
        return self.public_url

    def build_api_body(self, *, page: int) -> bytes:
        """Build Zonaprop's JSON POST body for one result page."""

        payload = self.build_api_payload(page=page)
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")

    def build_api_payload(self, *, page: int) -> dict[str, Any]:
        """Build Zonaprop's JSON POST payload for one result page."""

        if page <= 0:
            raise ValueError("page must be greater than zero")
        return {**BASE_SEARCH_PAYLOAD, **self.filters, "pagina": page}
