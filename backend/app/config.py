from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    database_url: str

    wxcc_base_url: str = "https://api.wxcc-us1.cisco.com"
    wxcc_access_token: str = ""
    wxcc_client_id: str = ""
    wxcc_client_secret: str = ""
    wxcc_refresh_token: str = ""
    wxcc_org_id: str = ""

    # OAuth token endpoint for Webex integrations/service auth.
    # Can be overridden in Render if Cisco's flow for this app uses a different host/path.
    wxcc_token_url: str = "https://webexapis.com/v1/access_token"

    collector_lookback_minutes: int = 30
    collector_max_window_hours: int = 24

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
