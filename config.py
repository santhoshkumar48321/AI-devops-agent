"""
Configuration settings loaded from environment variables / .env file.
"""

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # LLM
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"

    # API server
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # Memory
    memory_dir: str = "./data/memory"
    max_memory_results: int = 5

    # Kubernetes
    kubeconfig: str = ""

    # Ansible
    ansible_private_data_dir: str = "./data/ansible"

    # Audit
    audit_log_path: str = "./data/audit.log"

    # Documentation
    docs_output_dir: str = "./docs/incidents"

    # Safety
    require_confirmation: bool = True

    # RBAC
    allowed_roles: str = "admin,operator"

    @property
    def allowed_roles_list(self) -> list[str]:
        return [r.strip() for r in self.allowed_roles.split(",")]


@lru_cache()
def get_settings() -> Settings:
    return Settings()
