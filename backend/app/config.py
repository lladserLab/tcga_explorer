from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "TCGA-TRACE"
    app_release_commit: str = "development"
    app_release_ref: str = "development"
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
    pancancer_script_path: Path = Path("/app/scripts/pancancer_cox_scan.R")
    publication_benchmark_dir: Path = Path("/app/publication/benchmark")
    cors_origins: str = "http://localhost:3000,http://localhost:5173"
    bootstrap_on_startup: bool = True
    preload_cache_on_startup: bool = True
    preload_cache_strict: bool = True
    preload_gdc_expression_matrices_on_startup: bool = True
    analysis_batch_max_concurrency: int = 10
    public_base_url: str = "https://apps.cienciavida.org/tcga_explorer"
    public_path_prefix: str = "/tcga_explorer"
    public_api_enabled: bool = True
    attestation_enabled: bool = True
    attestation_auto_generate: bool = True
    attestation_private_key_path: Path = Path(
        "/run/attestation/ed25519-private.pem"
    )
    attestation_public_key_dir: Path | None = None
    attestation_issuer: str | None = None
    compute_global_concurrency: int = 2
    compute_queue_max_size: int = 50
    compute_max_active_per_client: int = 5
    compute_single_hourly_limit: int = 10
    compute_batch_hourly_limit: int = 2
    compute_multiverse_hourly_limit: int = 1
    compute_pancancer_hourly_limit: int = 2
    compute_session_hourly_limit: int = 5
    public_batch_max_analyses: int = 25
    public_multiverse_max_analyses: int = 72
    artifact_retention_days: int = 90
    compute_stale_seconds: int = 1800
    compute_max_attempts: int = 2
    mcp_allowed_hosts: str = (
        "apps.cienciavida.org,apps.cienciavida.org:*,localhost,localhost:*,"
        "127.0.0.1,127.0.0.1:*,testserver"
    )
    mcp_allowed_origins: str = (
        "https://apps.cienciavida.org,https://chatgpt.com,https://chat.openai.com,"
        "https://claude.ai,http://localhost:3000,http://localhost:5173"
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def mcp_allowed_host_list(self) -> list[str]:
        return [host.strip() for host in self.mcp_allowed_hosts.split(",") if host.strip()]

    @property
    def mcp_allowed_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.mcp_allowed_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
