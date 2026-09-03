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

    # Webex Calling Service App credentials used only for Detailed Call History.
    webex_calling_cdr_base_url: str = "https://analytics-calling.webexapis.com"
    webex_calling_access_token: str = ""
    webex_calling_client_id: str = ""
    webex_calling_client_secret: str = ""
    webex_calling_refresh_token: str = ""
    webex_calling_token_url: str = "https://webexapis.com/v1/access_token"
    webex_calling_collector_lookback_minutes: int = 30

    # BHS Service After Hours voicemail group (Knoxville TN).
    service_vm_group_uuid: str = "2c655ada-1784-4002-9266-2f2f66839967"
    service_vm_group_name: str = "Service After Hours Vmail"
    service_vm_extension: str = "6005"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
