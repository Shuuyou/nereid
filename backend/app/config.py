"""SecAgent 全局配置"""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file="../.env", env_file_encoding="utf-8", extra="ignore")

    # ---- LLM ----
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_chat_model: str = "deepseek-chat"
    deepseek_reasoner_model: str = "deepseek-reasoner"
    dashscope_api_key: str = ""
    dashscope_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    openai_api_key: str = ""
    openai_base_url: str = ""

    # ---- 资产测绘 ----
    hunter_api_key: str = ""
    fofa_email: str = ""
    fofa_key: str = ""
    shodan_api_key: str = ""

    # ---- 数据源凭据 ----
    nvd_api_key: str = ""
    github_token: str = ""

    # ---- 基础设施 ----
    postgres_host: str = "localhost"
    postgres_port: int = 5433
    postgres_user: str = "secagent"
    postgres_password: str = "secagent_dev_pwd"
    postgres_db: str = "secagent"
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "secagent_neo4j_pwd"
    redis_host: str = "localhost"
    redis_port: int = 6380

    # ---- 模型与运行参数 ----
    embedding_model: str = "Qwen/Qwen3-Embedding-0.6B"
    embedding_dim: int = 1024
    reranker_model: str = "BAAI/bge-reranker-v2-m3"
    poll_interval_seconds: int = 3600
    log_level: str = "INFO"
    data_dir: str = "../data"
    request_timeout: float = 30.0
    user_agent: str = "SecAgent/0.1 (AI Security Intelligence; HDU-EI-Lab)"

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/0"


@lru_cache
def get_settings() -> Settings:
    return Settings()
