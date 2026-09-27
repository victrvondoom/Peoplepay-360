from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    root: Path = ROOT
    db_path: Path = Path(os.getenv("INFLATIONFORGE_DB", str(ROOT / "artifacts" / "inflationforge.db")))
    bright_data_token: str = os.getenv("BRIGHT_DATA_API_TOKEN", "")
    bright_data_zone: str = os.getenv("BRIGHT_DATA_ZONE", "serp_api1")
    port_client_id: str = os.getenv("PORT_CLIENT_ID", "")
    port_client_secret: str = os.getenv("PORT_CLIENT_SECRET", "")
    port_api_token: str = os.getenv("PORT_API_TOKEN", "")
    port_api_url: str = os.getenv("PORT_API_URL", "https://api.port.io/v1")
    otel_endpoint: str = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")
    otel_mode: str = os.getenv("INFLATIONFORGE_OTEL_EXPORTER", "console")
    price_request_timeout_s: int = int(os.getenv("PRICE_REQUEST_TIMEOUT_S", "35"))
    price_sync_min_interval_s: int = int(os.getenv("PRICE_SYNC_MIN_INTERVAL_S", "300"))
    map_tile_url: str = os.getenv("MAP_TILE_URL", "https://tile.openstreetmap.org/{z}/{x}/{y}.png")
    map_attribution: str = os.getenv("MAP_ATTRIBUTION", "© OpenStreetMap contributors")
    map_max_zoom: int = int(os.getenv("MAP_MAX_ZOOM", "19"))
    signoz_ui_url: str = os.getenv("SIGNOZ_UI_URL", "http://localhost:8080")

    @property
    def artifacts_dir(self) -> Path:
        return self.root / "artifacts"


settings = Settings()
