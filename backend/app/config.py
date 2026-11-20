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
    brevo_api_key:str=""
    outreach_enabled:bool=False
    outreach_sender_email:str=""
    outreach_sender_name:str=""
    outreach_sender_verified:bool=False
    outreach_postal_address:str=""
    outreach_public_api_url:str=""
    outreach_daily_cap:int=250
    whatsapp_app_secret:str=""
    whatsapp_webhook_verify_token:str=""
    whatsapp_enabled:bool=False
    whatsapp_access_token:str=""
    whatsapp_phone_number_id:str=""
    whatsapp_business_account_id:str=""
    whatsapp_template_name:str=""
    whatsapp_template_language:str="en_US"
    whatsapp_graph_version:str="v23.0"
    whatsapp_daily_cap:int=20
    whatsapp_cost_acknowledged:bool=False
    assistant_whatsapp_enabled:bool=False
    assistant_whatsapp_org_id:int=0
    model_config=SettingsConfigDict(env_file="../.env",extra="ignore")
    @property
    def cors_list(self): return [x.strip() for x in self.cors_origins.split(",") if x.strip()]
settings=Settings()
