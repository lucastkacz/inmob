"""Lean source parsers for Silver canonical listings."""

from __future__ import annotations

import html
import json
import re
from collections.abc import Callable, Iterable
from datetime import datetime
from html.parser import HTMLParser
from typing import Any

from inmob.standardization.contracts import (
    CanonicalListing,
    CommercialTerms,
    FeatureSet,
    Location,
    RawArtifactMetadata,
    SellerContact,
    Surface,
)

PARSER_VERSION = "v1"


class ParserError(ValueError):
    """Raised when a raw artifact cannot be parsed into a canonical listing."""


class _HtmlDataParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.scripts: list[tuple[dict[str, str], str]] = []
        self.metas: list[dict[str, str]] = []
        self.inputs: list[dict[str, str]] = []
        self._script_attrs: dict[str, str] | None = None
        self._script_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key: value or "" for key, value in attrs}
        if tag == "script":
            self._script_attrs = attr_map
            self._script_parts = []
        elif tag == "meta":
            self.metas.append(attr_map)
        elif tag == "input":
            self.inputs.append(attr_map)

    def handle_data(self, data: str) -> None:
        if self._script_attrs is not None:
            self._script_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._script_attrs is not None:
            self.scripts.append((self._script_attrs, "".join(self._script_parts).strip()))
            self._script_attrs = None
            self._script_parts = []


def parse_listing(metadata: RawArtifactMetadata, payload: bytes) -> CanonicalListing:
    parsers: dict[str, Callable[[RawArtifactMetadata, bytes], CanonicalListing]] = {
        "argenprop": _parse_argenprop,
        "cabaprop": _parse_cabaprop,
        "mudafy": _parse_mudafy,
        "properati": _parse_properati,
        "remax": _parse_remax,
        "zonaprop": _parse_zonaprop,
    }
    try:
        parser = parsers[metadata.source_id]
    except KeyError as exc:
        raise ParserError(f"unsupported source_id={metadata.source_id}") from exc
    listing = parser(metadata, payload)
    if not listing.has_business_anchor():
        raise ParserError("listing missing business anchor: price, location, or surface")
    return listing


def _base(
    metadata: RawArtifactMetadata,
    *,
    parser_id: str,
    source_listing_id: str | None = None,
    canonical_url: str | None = None,
    **values: Any,
) -> CanonicalListing:
    listing_id = source_listing_id or metadata.target_metadata.get("listing_id")
    if not listing_id:
        listing_id = metadata.target_metadata.get("slug") or metadata.target_id
    return CanonicalListing(
        source_id=metadata.source_id,
        source_listing_id=listing_id,
        canonical_url=canonical_url or metadata.final_uri or metadata.requested_uri,
        raw_artifact_id=metadata.artifact_id,
        captured_at=metadata.captured_at,
        payload_sha256=metadata.payload_sha256,
        parser_id=parser_id,
        parser_version=PARSER_VERSION,
        **values,
    )


def _parse_cabaprop(metadata: RawArtifactMetadata, payload: bytes) -> CanonicalListing:
    data = _json_payload(payload)
    location = _as_dict(data.get("location"))
    price = _as_dict(data.get("price"))
    surface = _as_dict(data.get("surface"))
    characteristics = _as_dict(data.get("characteristics"))
    garage = _as_dict(characteristics.get("garage"))
    real_estate = _as_dict(data.get("real_estate"))
    branch = _as_dict(data.get("branch_office"))
    extras = _as_dict(data.get("extras"))
    ambiences = _as_dict(data.get("ambiences_types"))
    return _base(
        metadata,
        parser_id="cabaprop_json_v1",
        source_listing_id=_str(data.get("_id")),
        canonical_url=metadata.target_metadata.get("public_url") or metadata.final_uri,
        title=_str(data.get("title")),
        commercial=CommercialTerms(
            price_amount=_num(price.get("total")),
            currency=_currency(price.get("currency")),
            expenses_amount=_num(price.get("expenses")),
            expenses_currency=_currency(price.get("expensesCurrency")),
            price_visible=price.get("total") is not None,
        ),
        surface=Surface(
            total_m2=_num(surface.get("totalSurface")),
            covered_m2=_num(surface.get("coveredSurface")),
            uncovered_m2=_num(surface.get("uncoveredSurface")),
            semicovered_m2=_num(surface.get("semiCoveredSurface")),
            exclusive_m2=_num(surface.get("exclusiveSurface")),
        ),
        location=Location(
            address=_join_address(location.get("street"), location.get("number")),
            street=_str(location.get("street")),
            city=_str(location.get("locality") or location.get("area_level_2")),
            province=_str(location.get("area_level_1")),
            postal_code=_str(location.get("cp")),
            commune=_str(location.get("area_level_2")),
            latitude=_num(location.get("lat")),
            longitude=_num(location.get("lng")),
        ),
        seller=SellerContact(
            seller_name=_str(real_estate.get("name")),
            agency_name=_str(real_estate.get("name")),
            agency_license=_str(real_estate.get("matricula")),
            office_name=_str(branch.get("branch_office_name")),
            phone=_str(branch.get("phoneNumber")),
            email=_str(branch.get("email") or real_estate.get("email")),
            whatsapp=_str(branch.get("whatsapp")),
            contact_url=_str(branch.get("whatsapp")),
        ),
        features=FeatureSet(
            rooms=_int(characteristics.get("ambience")),
            bedrooms=_int(characteristics.get("bedrooms")),
            bathrooms=_int(characteristics.get("bathrooms")),
            toilettes=_int(characteristics.get("toilettes")),
            parking_spaces=_int(garage.get("quantity")),
            age_years=_extract_years(data.get("antiquity")),
            property_type=_str(data.get("property_type")),
            property_subtype=_str(data.get("sub_property_type")),
            operation_type=_str(data.get("operation_type")),
            building_floors=_int(characteristics.get("buildingQuantityFloors") or characteristics.get("floors")),
            orientation=_str(characteristics.get("buildingOrientation")),
            disposition=_str(characteristics.get("buildingDisposition")),
            brightness=_str(characteristics.get("buildingBrightness")),
            condition=_str(characteristics.get("buildingState")),
            is_new_build=_int(characteristics.get("buildingAntiquity")) == 1
            if characteristics.get("buildingAntiquity") is not None
            else None,
            accepts_credit=_bool(characteristics.get("aptCredito")),
            accepts_pets=_bool(characteristics.get("aptMascota")),
            professional_use=_bool(characteristics.get("aptProfesional")),
            booleans=_boolean_features(characteristics, extras, ambiences),
            attributes=_feature_attributes(characteristics, extras, ambiences),
            raw_features={"characteristics": characteristics, "extras": extras, "ambiences_types": ambiences},
        ),
        published_at=_dt(data.get("created_at")),
        source_specific={
            "source_status": data.get("status"),
            "source_created_at": data.get("created_at"),
            "source_updated_at": data.get("updated_at"),
            "source_agency_id": data.get("real_estate_id"),
            "source_branch_id": data.get("branch_office_id"),
            "external_reference": data.get("external_reference"),
            "location_barrios": location.get("barrios"),
            "branch_barrio": branch.get("barrio"),
        },
    )


def _parse_remax(metadata: RawArtifactMetadata, payload: bytes) -> CanonicalListing:
    envelope = _json_payload(payload)
    data = _as_dict(envelope.get("data")) or envelope
    currency = _as_dict(data.get("currency"))
    expenses_currency = _as_dict(data.get("expensesCurrency"))
    geo = _as_dict(data.get("geo"))
    location = _as_dict(data.get("location"))
    coordinates = _as_list(location.get("coordinates"))
    associate = _as_dict(data.get("associate"))
    office = _as_dict(associate.get("office"))
    features = _as_list(data.get("features"))
    return _base(
        metadata,
        parser_id="remax_json_v1",
        source_listing_id=_str(data.get("slug") or data.get("id")),
        canonical_url=metadata.target_metadata.get("public_url") or metadata.final_uri,
        title=_str(data.get("title")),
        commercial=CommercialTerms(
            price_amount=_num(data.get("price")),
            currency=_str(currency.get("value")),
            expenses_amount=_num(data.get("expensesPrice")),
            expenses_currency=_str(expenses_currency.get("value")),
            price_visible=_bool(data.get("priceExposure")),
        ),
        surface=Surface(
            total_m2=_num(data.get("dimensionTotalBuilt") or data.get("dimensionLand")),
            covered_m2=_num(data.get("dimensionCovered")),
            uncovered_m2=_num(data.get("dimensionUncovered")),
            semicovered_m2=_num(data.get("dimensionSemicovered")),
        ),
        location=Location(
            address=_str(data.get("displayAddress")),
            neighborhood=_str(geo.get("neighborhood") or geo.get("citie") or geo.get("label")),
            city=_str(geo.get("citie")),
            province=_str(geo.get("state")),
            latitude=_num(coordinates[1]) if len(coordinates) >= 2 else None,
            longitude=_num(coordinates[0]) if len(coordinates) >= 2 else None,
        ),
        seller=SellerContact(
            seller_name=_str(associate.get("name")),
            agency_name=_str(office.get("name")),
            agency_license=_str(associate.get("license")),
            office_name=_str(office.get("name")),
            seller_slug=_str(associate.get("slug")),
            phone=_first_contact(associate.get("phones")),
            email=_first_contact(associate.get("emails")),
            whatsapp=_first_contact(associate.get("phones")),
        ),
        features=FeatureSet(
            rooms=_int(data.get("totalRooms") or data.get("studio")),
            bedrooms=_int(data.get("bedrooms")),
            bathrooms=_int(data.get("bathrooms")),
            toilettes=_int(data.get("toilets")),
            parking_spaces=_int(data.get("parkingSpaces")),
            property_type=_str(_as_dict(data.get("type")).get("value")),
            operation_type=_str(_as_dict(data.get("operation")).get("value")),
            construction_year=_int(data.get("yearBuilt")),
            building_floors=_int(data.get("floors")),
            is_new_build=_bool(data.get("pozo")),
            accepts_credit=_bool(data.get("aptCredit")),
            professional_use=_bool(data.get("professionalUse")),
            commercial_use=_bool(data.get("commercialUse")),
            reduced_mobility_access=_bool(data.get("reducedMovility")),
            financing=_bool(data.get("financing")),
            furnished=_bool(data.get("furnished")),
            booleans={
                **_feature_list_booleans(features),
                **_known_booleans(
                    data,
                    "pozo",
                    "professionalUse",
                    "commercialUse",
                    "remaxCollection",
                    "financing",
                    "aptCredit",
                    "reducedMovility",
                    "inPrivateCommunity",
                    "furnished",
                    "appliances",
                    "showLendarBanner",
                ),
            },
            attributes=_feature_attributes({"features": _feature_list_booleans(features)}),
            raw_features={"features": features},
        ),
        source_specific={
            "id": data.get("id"),
            "source_internal_id": data.get("internalId"),
            "source_status": _as_dict(data.get("listingStatus")).get("value"),
            "source_office_id": associate.get("officeId"),
            "source_advertiser_id": associate.get("id"),
            "source_agency_id": office.get("id"),
            "opportunity": _as_dict(data.get("oportunity")).get("value"),
        },
    )


def _parse_argenprop(metadata: RawArtifactMetadata, payload: bytes) -> CanonicalListing:
    text = payload.decode("utf-8", errors="replace")
    parsed = _html_data(text)
    ld = _first_json_ld(parsed, "Apartment")
    address = _as_dict(ld.get("address"))
    floor_size = _as_dict(ld.get("floorSize"))
    return _base(
        metadata,
        parser_id="argenprop_html_v1",
        source_listing_id=_input_value(parsed, "IdAviso") or metadata.target_metadata.get("listing_id"),
        canonical_url=_meta_content(parsed, "og:url") or metadata.final_uri,
        title=_str(ld.get("name") or _meta_content(parsed, "og:title")),
        commercial=CommercialTerms(
            price_amount=_num(_input_value(parsed, "Precio")),
            currency=_str(_input_value(parsed, "Moneda")),
            price_visible=_input_value(parsed, "Precio") is not None,
        ),
        surface=Surface(covered_m2=_num(floor_size.get("value"))),
        location=Location(
            address=_str(address.get("streetAddress")),
            neighborhood=_str(address.get("addressRegion")),
            city=_str(address.get("addressLocality")),
            latitude=_num(_regex(text, r'data-latitude="([^"]+)"')),
            longitude=_num(_regex(text, r'data-longitude="([^"]+)"')),
        ),
        seller=SellerContact(
            agency_name=_extract_argenprop_agency(parsed),
            whatsapp=_whatsapp_href(text),
            whatsapp_contact_enabled=_input_bool(parsed, "WhatsAppContact"),
            contact_url=_whatsapp_href(text),
        ),
        features=FeatureSet(
            rooms=_int(ld.get("numberOfRooms")),
            bedrooms=_int(ld.get("numberOfBedrooms")),
            property_type=_str(ld.get("@type")),
            raw_features={"json_ld": ld},
        ),
        source_specific={
            "source_advertiser_id": _input_value(parsed, "IdAnunciante"),
            "source_internal_id": _input_value(parsed, "IdVisibilidad"),
            "source_posting_code": _input_value(parsed, "IdAviso"),
            "analytics_url": _input_value(parsed, "UrlAnalytics"),
            "position_url": _input_value(parsed, "PositionUrl"),
        },
    )


def _parse_mudafy(metadata: RawArtifactMetadata, payload: bytes) -> CanonicalListing:
    text = payload.decode("utf-8", errors="replace")
    parsed = _html_data(text)
    product = _first_json_ld(parsed, "Product")
    apartment = _first_json_ld(parsed, "Apartment")
    offer = _as_dict(product.get("offers"))
    address = _as_dict(apartment.get("address"))
    floor_size = _as_dict(apartment.get("floorSize"))
    geo = _as_dict(apartment.get("geo"))
    amenities = _as_list(apartment.get("amenityFeature"))
    fields = _mudafy_fields(text)
    map_address = _mudafy_map_address(text)
    whatsapp = _regex_unescaped(text, r'"whatsappMessage":"([^"]+)"')
    return _base(
        metadata,
        parser_id="mudafy_html_v1",
        canonical_url=_meta_link(text, "canonical") or _str(offer.get("url")) or metadata.final_uri,
        title=_str(apartment.get("name") or product.get("name")),
        commercial=CommercialTerms(
            price_amount=_num(offer.get("price")),
            currency=_str(offer.get("priceCurrency")),
            price_visible=offer.get("price") is not None,
        ),
        surface=Surface(
            total_m2=_num(_field_value(fields, "total_area") or floor_size.get("value")),
            covered_m2=_num(_field_value(fields, "roofed_area") or _field_by_label(fields, "Superficie cubierta")),
        ),
        location=Location(
            address=_str(address.get("streetAddress") or apartment.get("name") or map_address),
            neighborhood=_str(address.get("addressLocality")),
            city=_str(address.get("addressLocality")),
            map_address=map_address,
            latitude=_num(geo.get("latitude")),
            longitude=_num(geo.get("longitude")),
        ),
        seller=SellerContact(agency_name="Mudafy", whatsapp=whatsapp, contact_url=whatsapp),
        features=FeatureSet(
            rooms=_int(apartment.get("numberOfRooms") or _field_value(fields, "rooms_total")),
            bedrooms=_int(apartment.get("numberOfBedrooms") or _field_value(fields, "bedrooms")),
            bathrooms=_int(apartment.get("numberOfBathroomsTotal") or _field_value(fields, "bathrooms")),
            orientation=_field_value(fields, "orientation"),
            operation_type=_regex_unescaped(text, r'"operationKindLabel":"([^"]+)"'),
            booleans=_amenity_booleans(amenities),
            attributes={**_amenity_booleans(amenities), **_mudafy_attribute_fields(fields)},
            raw_features={"json_ld": apartment, "fields": fields},
        ),
        source_specific={"source_internal_id": metadata.target_metadata.get("listing_id")},
    )


def _parse_properati(metadata: RawArtifactMetadata, payload: bytes) -> CanonicalListing:
    text = payload.decode("utf-8", errors="replace")
    parsed = _html_data(text)
    address = _regex(text, r'address:\s*"([^"]+)"')
    published = _regex(text, r'<div class="date">([^<]+)</div>')
    listing_price = _data_test_value(text, "listing-price")
    return _base(
        metadata,
        parser_id="properati_html_v1",
        canonical_url=_meta_content(parsed, "og:url") or metadata.final_uri,
        title=_meta_content(parsed, "og:title") or _meta_content(parsed, "description"),
        commercial=CommercialTerms(
            price_amount=_num(listing_price),
            currency=_regex(listing_price or "", r"\b(USD|ARS|U\$S|\$)\b"),
            price_visible=listing_price is not None,
        ),
        surface=Surface(
            total_m2=_num(_data_test_value(text, "area-value") or _data_test_value(text, "plot-area-value")),
            covered_m2=_num(_data_test_value(text, "covered-area-value")),
        ),
        location=Location(
            address=address,
            map_address=_regex(text, r'class="location-map__location-address-map">\s*([^<]+)'),
            latitude=_num(_regex(text, r'latitude:\s*"([^"]+)"')),
            longitude=_num(_regex(text, r'longitude:\s*"([^"]+)"')),
            province=_regex(text, r'province:\s*"([^"]+)"'),
            city=_regex(text, r'locality:\s*"([^"]+)"'),
        ),
        seller=SellerContact(
            agency_name=_regex(published or "", r"Publicado por\s+(.+)$"),
        ),
        publication_text=published,
        features=FeatureSet(
            bedrooms=_int(_regex(text, r'data-test="bedrooms-value">([^<]+)</')),
            bathrooms=_int(_regex(text, r'data-test="full-bathrooms-value">([^<]+)</')),
            toilettes=_int(_data_test_value(text, "half-bathrooms-value")),
            rooms=_int(_regex(text, r'data-test="rooms-value">([^<]+)</')),
            property_type=_data_test_value(text, "property-type-value"),
            operation_type=_data_test_value(text, "operation-type-value"),
            construction_year=_int(_data_test_value(text, "construction-year-value")),
            floor_number=_int(_data_test_value(text, "floor-value")),
            condition=_data_test_value(text, "condition-value"),
            attributes=_feature_attributes(
                {
                    "property_type": _data_test_value(text, "property-type-value"),
                    "operation_type": _data_test_value(text, "operation-type-value"),
                    "condition": _data_test_value(text, "condition-value"),
                }
            ),
        ),
    )


def _parse_zonaprop(metadata: RawArtifactMetadata, payload: bytes) -> CanonicalListing:
    text = payload.decode("utf-8", errors="replace")
    parsed = _html_data(text)
    ld = _first_json_ld(parsed, "Apartment")
    address = _as_dict(ld.get("address"))
    floor_size = _as_dict(ld.get("floorSize"))
    main_features = _json_after(text, "const mainFeatures =")
    general_features = _json_after(text, "'generalFeatures':")
    prices = _json_after(text, "'pricesData':", opener="[")
    geolocation = _json_after(text, '"postingGeolocation":')
    marker_latitude, marker_longitude = _zonaprop_marker_coordinates(text)
    latitude = _nested_num(geolocation, ("geolocation", "latitude"))
    longitude = _nested_num(geolocation, ("geolocation", "longitude"))
    price_amount, currency = _zonaprop_price(prices)
    publication_text = _regex(text, r"const antiquity =\s*'([^']+)'")
    posting_code = _regex(text, r"'postingCode':\s*\"([^\"]+)\"")
    return _base(
        metadata,
        parser_id="zonaprop_html_v1",
        canonical_url=_meta_content(parsed, "og:url") or _meta_link(text, "canonical") or metadata.final_uri,
        title=_str(ld.get("name") or _meta_content(parsed, "og:title")),
        commercial=CommercialTerms(
            price_amount=price_amount,
            currency=currency,
            expenses_amount=_num(_regex(text, r"'expenses':'([^']+)'")),
            price_visible=price_amount is not None,
        ),
        surface=Surface(
            total_m2=_feature_num(main_features, "CFT100") or _num(floor_size.get("value")),
            covered_m2=_feature_num(main_features, "CFT101"),
            uncovered_m2=_feature_num(main_features, "CFT102"),
            semicovered_m2=_feature_num(general_features, "Superficie Semicubierta (m²)"),
            terrace_m2=_feature_num(general_features, "Terraza"),
        ),
        location=Location(
            address=_str(address.get("streetAddress") or _regex(text, r'"postingLocation":\{"address":\{"name":"([^"]+)"')),
            neighborhood=_str(address.get("addressRegion")),
            city=_str(address.get("addressLocality")),
            latitude=latitude if latitude is not None else marker_latitude,
            longitude=longitude if longitude is not None else marker_longitude,
        ),
        seller=SellerContact(agency_name=_regex(text, r'publisherName\s*=\s*"([^"]*)"') or None),
        publication_text=publication_text,
        views_count=_int(_regex(text, r"const usersViews =\s*(\d+)")),
        features=FeatureSet(
            rooms=_feature_int(main_features, "CFT1") or _int(ld.get("numberOfRooms")),
            bedrooms=_feature_int(main_features, "CFT2") or _int(ld.get("numberOfBedrooms")),
            bathrooms=_feature_int(main_features, "CFT3"),
            toilettes=_feature_int(main_features, "CFT7"),
            parking_spaces=_feature_int(main_features, "CFT4"),
            age_years=_feature_int(main_features, "CFT5"),
            property_type=_str(ld.get("@type")),
            orientation=_feature_text(main_features, "Orientación"),
            disposition=_feature_text(main_features, "Disposición"),
            brightness=_feature_text(main_features, "Luminosidad"),
            is_new_build=_feature_text(main_features, "Antigüedad") == "A estrenar"
            if _feature_text(main_features, "Antigüedad")
            else None,
            booleans=_zonaprop_booleans(general_features),
            attributes={**_zonaprop_attributes(general_features), **_zonaprop_attributes(main_features)},
            raw_features={"mainFeatures": main_features, "generalFeatures": general_features},
        ),
        source_specific={
            "source_posting_code": posting_code,
            "posting_code": posting_code,
            "publisher_name": _regex(text, r'publisherName\s*=\s*"([^"]*)"'),
        },
    )


def _json_payload(payload: bytes) -> dict[str, Any]:
    data = json.loads(payload.decode("utf-8"))
    if not isinstance(data, dict):
        raise ParserError("JSON payload root is not an object")
    return data


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _html_data(text: str) -> _HtmlDataParser:
    parser = _HtmlDataParser()
    parser.feed(text)
    return parser


def _first_json_ld(parsed: _HtmlDataParser, schema_type: str) -> dict[str, Any]:
    for attrs, body in parsed.scripts:
        if attrs.get("type") != "application/ld+json":
            continue
        try:
            data = json.loads(html.unescape(body))
        except json.JSONDecodeError:
            continue
        for item in _iter_json_items(data):
            if item.get("@type") == schema_type:
                return item
    return {}


def _iter_json_items(data: Any) -> Iterable[dict[str, Any]]:
    if isinstance(data, dict):
        yield data
        graph = data.get("@graph")
        if isinstance(graph, list):
            for item in graph:
                if isinstance(item, dict):
                    yield item
    elif isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                yield item


def _json_after(text: str, marker: str, *, opener: str = "{") -> Any:
    start = text.find(marker)
    if start < 0:
        return {} if opener == "{" else []
    open_at = text.find(opener, start + len(marker))
    if open_at < 0:
        return {} if opener == "{" else []
    closer = "}" if opener == "{" else "]"
    end = _balanced_end(text, open_at, opener, closer)
    if end is None:
        return {} if opener == "{" else []
    raw = text[open_at : end + 1]
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {} if opener == "{" else []


def _balanced_end(text: str, start: int, opener: str, closer: str) -> int | None:
    depth = 0
    in_string: str | None = None
    escape = False
    for idx in range(start, len(text)):
        char = text[idx]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == in_string:
                in_string = None
            continue
        if char in {'"', "'"}:
            in_string = char
        elif char == opener:
            depth += 1
        elif char == closer:
            depth -= 1
            if depth == 0:
                return idx
    return None


def _meta_content(parsed: _HtmlDataParser, key: str) -> str | None:
    for meta in parsed.metas:
        if meta.get("property") == key or meta.get("name") == key:
            return _clean(meta.get("content"))
    return None


def _meta_link(text: str, rel: str) -> str | None:
    return _regex(text, rf'<link[^>]+rel="{re.escape(rel)}"[^>]+href="([^"]+)"')


def _input_value(parsed: _HtmlDataParser, input_id: str) -> str | None:
    for input_tag in parsed.inputs:
        if input_tag.get("id") == input_id or input_tag.get("name") == input_id:
            return _clean(input_tag.get("value"))
    return None


def _input_bool(parsed: _HtmlDataParser, input_id: str) -> bool | None:
    return _bool(_input_value(parsed, input_id))


def _regex(text: str, pattern: str) -> str | None:
    match = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return None
    return _clean(match.group(1))


def _regex_unescaped(text: str, pattern: str) -> str | None:
    value = _regex(text, pattern)
    if value is None:
        return None
    try:
        decoded = json.loads(f'"{value}"')
    except json.JSONDecodeError:
        decoded = value.replace("\\/", "/")
    return _clean(decoded)


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = html.unescape(str(value))
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def _str(value: Any) -> str | None:
    return _clean(value)


def _num(value: Any) -> float | None:
    text = _clean(value)
    if text is None:
        return None
    normalized = text.replace(" ", "")
    if "," in normalized:
        normalized = normalized.replace(".", "").replace(",", ".")
    elif re.search(r"\d+\.\d{3}(?:\D|$)", normalized):
        normalized = normalized.replace(".", "")
    matches = re.findall(r"-?\d+(?:\.\d+)?", normalized)
    if not matches:
        return None
    try:
        return float(matches[0])
    except ValueError:
        return None


def _int(value: Any) -> int | None:
    number = _num(value)
    return int(number) if number is not None else None


def _bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    text = _clean(value)
    if text is None:
        return None
    if text.lower() in {"true", "1", "si", "sí", "yes"}:
        return True
    if text.lower() in {"false", "0", "no"}:
        return False
    return None


def _dt(value: Any) -> datetime | None:
    text = _clean(value)
    if text is None:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _currency(value: Any) -> str | None:
    mapping = {1: "USD", 2: "ARS", "1": "USD", "2": "ARS"}
    if value in mapping:
        return mapping[value]
    return _str(value)


def _join_address(street: Any, number: Any) -> str | None:
    parts = [_clean(street), _clean(number)]
    return " ".join(part for part in parts if part) or None


def _first_contact(items: Any) -> str | None:
    if isinstance(items, list):
        for item in items:
            if isinstance(item, dict) and item.get("value"):
                return _str(item.get("value"))
    return None


def _whatsapp_href(text: str) -> str | None:
    return _regex(text, r'href="(https://wa\.me/[^"]+)"')


def _extract_years(value: Any) -> int | None:
    if isinstance(value, dict):
        return _int(value.get("years"))
    return _int(value)


def _boolean_features(*objects: dict[str, Any]) -> dict[str, bool]:
    result: dict[str, bool] = {}
    for obj in objects:
        for key, value in obj.items():
            if isinstance(value, bool):
                result[key] = value
            elif isinstance(value, dict):
                for inner_key, inner_value in value.items():
                    if isinstance(inner_value, bool):
                        result[f"{key}.{inner_key}"] = inner_value
    return result


def _known_booleans(data: dict[str, Any], *keys: str) -> dict[str, bool]:
    result: dict[str, bool] = {}
    for key in keys:
        value = _bool(data.get(key))
        if value is not None:
            result[key] = value
    return result


def _feature_attributes(*objects: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for obj in objects:
        _flatten_attributes("", obj, result)
    return result


def _flatten_attributes(prefix: str, value: Any, result: dict[str, Any]) -> None:
    if isinstance(value, dict):
        for key, inner_value in value.items():
            next_prefix = f"{prefix}.{key}" if prefix else str(key)
            _flatten_attributes(next_prefix, inner_value, result)
    elif isinstance(value, bool | int | float | str) and prefix and _clean(value) is not None:
        result[prefix] = value


def _feature_list_booleans(features: list[Any]) -> dict[str, bool]:
    result: dict[str, bool] = {}
    for feature in features:
        if isinstance(feature, dict):
            key = _str(feature.get("lang") or feature.get("value"))
            if key:
                result[key] = True
    return result


def _amenity_booleans(items: list[Any]) -> dict[str, bool]:
    result: dict[str, bool] = {}
    for item in items:
        if isinstance(item, dict):
            key = _str(item.get("name"))
            if key:
                result[key] = bool(item.get("value", True))
    return result


def _mudafy_fields(text: str) -> list[dict[str, Any]]:
    match = re.search(r'\\"fields\\":(\[.*?\]),\\"operationKindLabel', text, flags=re.DOTALL)
    if not match:
        return []
    raw = match.group(1).encode("utf-8").decode("unicode_escape")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def _field_value(fields: list[dict[str, Any]], name: str) -> str | None:
    for field in fields:
        if field.get("field") == name:
            return _str(field.get("rawValue") or field.get("displayValue"))
    return None


def _field_by_label(fields: list[dict[str, Any]], label: str) -> str | None:
    for field in fields:
        if field.get("label") == label:
            return _str(field.get("rawValue") or field.get("displayValue"))
    return None


def _mudafy_attribute_fields(fields: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for field in fields:
        key = _str(field.get("field"))
        if key:
            result[key] = _str(field.get("rawValue") or field.get("displayValue"))
    return result


def _mudafy_map_address(text: str) -> str | None:
    iframe_src = _regex_unescaped(text, r'"src":"(https://www\.google\.com/maps/embed/v1/place[^"]+)"')
    if not iframe_src:
        return None
    match = re.search(r"[?&]q=([^&]+)", iframe_src)
    if not match:
        return None
    return _clean(match.group(1).replace("%20", " ").replace("%2C", ","))


def _zonaprop_marker_coordinates(text: str) -> tuple[float | None, float | None]:
    match = re.search(
        r"""position=["'](?P<lat>-?\d+(?:\.\d+)?),\s*(?P<lng>-?\d+(?:\.\d+)?)["']""",
        text,
    )
    if not match:
        return None, None
    return _num(match.group("lat")), _num(match.group("lng"))


def _data_test_value(text: str, key: str) -> str | None:
    pattern = rf'<[^>]+data-test="{re.escape(key)}"[^>]*>\s*([^<]+)'
    for match in re.finditer(pattern, text, flags=re.IGNORECASE | re.DOTALL):
        value = _clean(match.group(1))
        if value:
            return value
    return None


def _extract_argenprop_agency(parsed: _HtmlDataParser) -> str | None:
    title = _meta_content(parsed, "og:description") or _meta_content(parsed, "og:title")
    if title and " - " in title:
        return title.split(" - ")[-1].strip(" -") or None
    return None


def _feature_num(features: Any, key_or_label: str) -> float | None:
    item = _feature_item(features, key_or_label)
    return _num(item.get("value")) if isinstance(item, dict) else None


def _feature_text(features: Any, key_or_label: str) -> str | None:
    item = _feature_item(features, key_or_label)
    return _str(item.get("value")) if isinstance(item, dict) else None


def _feature_int(features: Any, key_or_label: str) -> int | None:
    value = _feature_num(features, key_or_label)
    return int(value) if value is not None else None


def _feature_item(features: Any, key_or_label: str) -> dict[str, Any]:
    if not isinstance(features, dict):
        return {}
    item = features.get(key_or_label)
    if isinstance(item, dict):
        return item
    for group in features.values():
        if isinstance(group, dict):
            for maybe in group.values():
                if isinstance(maybe, dict) and maybe.get("label") == key_or_label:
                    return maybe
    return {}


def _nested_num(data: Any, keys: tuple[str, ...]) -> float | None:
    current = data
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return _num(current)


def _zonaprop_price(prices_data: Any) -> tuple[float | None, str | None]:
    if not isinstance(prices_data, list):
        return None, None
    for operation in prices_data:
        if not isinstance(operation, dict):
            continue
        prices = operation.get("prices")
        if not isinstance(prices, list) or not prices:
            continue
        first = prices[0]
        if isinstance(first, dict):
            return _num(first.get("amount")), _str(first.get("currency") or first.get("isoCode"))
    return None, None


def _zonaprop_booleans(features: Any) -> dict[str, bool]:
    result: dict[str, bool] = {}
    if not isinstance(features, dict):
        return result
    for group in features.values():
        if not isinstance(group, dict):
            continue
        for item in group.values():
            if isinstance(item, dict):
                label = _str(item.get("label"))
                value = item.get("value")
                if label and value in (None, "", "true", True):
                    result[label] = True
    return result


def _zonaprop_attributes(features: Any) -> dict[str, Any]:
    result: dict[str, Any] = {}
    if not isinstance(features, dict):
        return result
    for key, item in _zonaprop_feature_items(features):
        label = _str(item.get("label") or key)
        if not label:
            continue
        value = item.get("value")
        result[label] = True if value in (None, "", "true", True) else value
    return result


def _zonaprop_feature_items(features: dict[str, Any]) -> Iterable[tuple[str, dict[str, Any]]]:
    for key, value in features.items():
        if isinstance(value, dict) and ("value" in value or "label" in value):
            yield str(key), value
        elif isinstance(value, dict):
            for inner_key, inner_value in value.items():
                if isinstance(inner_value, dict):
                    yield str(inner_key), inner_value
