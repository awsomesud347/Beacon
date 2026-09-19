from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    narrator: Literal["cloud", "local", "template"] = "cloud"
    nvidia_api_key: str = ""
    nemotron_base_url: str = "https://integrate.api.nvidia.com/v1"
    nemotron_model: str = "nvidia/nemotron-3-nano-30b-a3b"
    local_llm_base_url: str = "http://localhost:11434/v1"
    local_llm_model: str = ""
    local_llm_api_key: str = "local"

    elevenlabs_api_key: str = ""
    elevenlabs_agent_id: str = ""
    elevenlabs_voice_id: str = ""
    llm_proxy_secret: str = ""

    dataset_path: str = "data/fixtures/demo_persona.csv"
    stub_mode: bool = False
    demo_mode: bool = False
    cors_origins: str = "http://localhost:5173"
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
