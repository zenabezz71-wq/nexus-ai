from pydantic_settings import BaseSettings, SettingsConfigDict
class Settings(BaseSettings):
    database_url:str="sqlite:///./nexus.db"
    redis_url:str="redis://localhost:6379/0"
    jwt_secret:str="development-secret-change-this-please"
    jwt_access_minutes:int=60
    bootstrap_email:str="admin@example.com"
    bootstrap_password:str="ChangeMe-Immediately-123!"
    cors_origins:str="http://localhost:3000"
    openai_api_key:str=""
    openai_model:str="gpt-4.1-mini"
    model_config=SettingsConfigDict(env_file="../.env",extra="ignore")
    @property
    def cors_list(self): return [x.strip() for x in self.cors_origins.split(",") if x.strip()]
settings=Settings()
