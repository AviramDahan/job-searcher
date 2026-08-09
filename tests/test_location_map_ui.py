from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_public_dashboard_loads_leaflet_assets() -> None:
    html = read("docs/index.html")

    assert "leaflet@1.9.4/dist/leaflet.css" in html
    assert "leaflet@1.9.4/dist/leaflet.js" in html
    assert "leaflet.markercluster@1.5.3" in html


def test_local_dashboard_loads_leaflet_assets() -> None:
    html = read("src/dashboard_static/index.html")

    assert "leaflet@1.9.4/dist/leaflet.css" in html
    assert "leaflet@1.9.4/dist/leaflet.js" in html
    assert "leaflet.markercluster@1.5.3" in html


def test_public_map_uses_real_map_not_svg_outline() -> None:
    js = read("docs/assets/pages.js")

    assert "tile.openstreetmap.org" in js
    assert "markerClusterGroup" in js
    assert "scanState" in js
    assert "location-marker-cluster ${clusterState}" in js
    assert "data-location-map-canvas" in js
    assert "viewBox=\"0 0 100 100\"" not in js
    assert "israel-outline" not in js


def test_local_map_uses_real_map_not_svg_outline() -> None:
    js = read("src/dashboard_static/dashboard.js")

    assert "tile.openstreetmap.org" in js
    assert "markerClusterGroup" in js
    assert "scanState" in js
    assert "location-marker-cluster ${clusterState}" in js
    assert "data-location-map-canvas" in js
    assert "viewBox=\"0 0 100 100\"" not in js
    assert "israel-outline" not in js


def test_map_styles_are_responsive_and_clustered() -> None:
    for css_path in ("docs/assets/pages.css", "src/dashboard_static/dashboard.css"):
        css = read(css_path)

        assert ".leaflet-map" in css
        assert ".location-map-pin" in css
        assert ".location-marker-cluster" in css
        assert ".location-marker-cluster.mixed" in css
        assert ".map-fallback" in css
        assert "height: clamp(430px, 52vh, 620px)" in css
        assert ".israel-outline" not in css
