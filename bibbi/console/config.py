from dataclasses import dataclass
from pathlib import Path


@dataclass
class Config:
    dest_dir: Path
    ingest_apikey: str
