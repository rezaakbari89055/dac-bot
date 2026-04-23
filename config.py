from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    BOT_TOKEN: str
    ADMIN_ID: int
    DB_NAME: str
    DB_USER: str
    DB_PASS: str
    PROXY_URL: str = ""
    DATABASE_URL: str = "" # ساخته میشود در پایین

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.DATABASE_URL = f"mysql+pymysql://{self.DB_USER}:{self.DB_PASS}@localhost/{self.DB_NAME}"

    class Config:
        env_file = ".env"

@lru_cache()
def get_settings():
    return Settings()
