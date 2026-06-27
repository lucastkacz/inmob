from inmob.ingestion.sources.browser import is_safe_reveal_candidate


def test_safe_reveal_candidate_accepts_map_and_expansion_controls() -> None:
    assert is_safe_reveal_candidate("static-map-container article-map")
    assert is_safe_reveal_candidate("Ver mas caracteristicas")
    assert is_safe_reveal_candidate("Servicios Escuelas Restaurantes")


def test_safe_reveal_candidate_rejects_navigation_and_contact_actions() -> None:
    assert not is_safe_reveal_candidate("Contactar por WhatsApp")
    assert not is_safe_reveal_candidate("Ver telefono")
    assert not is_safe_reveal_candidate("Mapa", tag_name="a", href="/otra-pagina")
    assert not is_safe_reveal_candidate("Buscar", tag_name="input", input_type="submit")
