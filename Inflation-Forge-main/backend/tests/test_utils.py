import json

from backend.models.domain import City
from backend.utils import write_json


def test_write_json_serializes_nested_domain_models(tmp_path):
    path = tmp_path / "manifest.json"
    write_json(path, {"cities": [City(
        id="austin", name="Austin", state="TX", latitude=30.2672,
        longitude=-97.7431, source_slug="Austin",
    )]})

    assert json.loads(path.read_text())["cities"][0]["id"] == "austin"
