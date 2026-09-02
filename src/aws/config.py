from pydantic_settings import BaseSettings, SettingsConfigDict

class AWSSettings(BaseSettings):
    AWS_REGION: str = "us-east-1"
    AWS_ACCESS_KEY_ID: str
    AWS_SECRET_ACCESS_KEY: str
    SES_SOURCE_EMAIL: str  
    SES_CONFIGURATION_SET: str | None = None 
    S3_BUCKET: str

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore"
    )

aws_settings = AWSSettings()  # type: ignore[call-arg]