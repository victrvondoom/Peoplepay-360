from pathlib import Path
import shutil

from backend.config import ROOT, Settings
from backend.services.inflation.service import InflationForgeService


def test_empty_ephemeral_database_loads_real_bootstrap_snapshot(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    shutil.copy(ROOT / "data" / "bootstrap_snapshot.json", data_dir / "bootstrap_snapshot.json")

    service = InflationForgeService(Settings(
        root=tmp_path,
        db_path=tmp_path / "inflation.db",
        otel_mode="local",
    ))
    dashboard = service.dashboard()

    assert dashboard.snapshot is not None
    assert dashboard.snapshot.city_count == 16
    assert dashboard.snapshot.item_count == 9
    assert len(dashboard.comparisons) == 144
    assert len(dashboard.overall_comparisons) == 16
    assert service.source_catalog()
    assert len(service.collector.archive_cache) == 16
