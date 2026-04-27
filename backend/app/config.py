from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "TCGA KM Explorer"
    database_url: str = "postgresql+psycopg://tcga:tcga@postgres:5432/tcga_explorer"
    tcga_data_dir: Path = Path("/data/tcga")
    tcga_cdr_path: Path = Path("/app/clinical/TCGA-CDR-SupplementalTableS1.xlsx")
    tcga_sync_state_dir: Path = Path("/data/tcga/.sync")
    clinical_sync_state_dir: Path = Path("/app/clinical/.sync")
    gdc_api_base_url: str = "https://api.gdc.cancer.gov"
    artifact_dir: Path = Path("/app/artifacts")
    derived_expression_dir: Path = Path("/app/derived/rna_bulk")
    r_script_path: Path = Path("/app/scripts/km_analysis.R")
    maxstat_script_path: Path = Path("/app/scripts/maxstat_cutpoint.R")
    cors_origins: str = "http://localhost:3000,http://localhost:5173"
    bootstrap_on_startup: bool = True
    preload_cache_on_startup: bool = True
    preload_cache_strict: bool = True
    preload_gdc_expression_matrices_on_startup: bool = True
    analysis_batch_max_concurrency: int = 10

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
