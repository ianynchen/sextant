"""The service's settings, as a service reads its peers' addresses: a pydantic-settings class
whose fields come from `ORDERS_`-prefixed environment variables, then the `.env` file it names,
then the defaults written here. Sextant publishes a field read as its key (`${ORDERS_RATES_URL}`
with this default) and fills it per environment from the file (plan 3 Task 5)."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="orders_", env_file=".env")

    rates_url: str = "https://rates.example/v1"
    # An alias replaces the name and takes no prefix: read from `CARRIER_TOKEN`.
    carrier_token: str = Field("none", alias="CARRIER_TOKEN")


settings = Settings()
