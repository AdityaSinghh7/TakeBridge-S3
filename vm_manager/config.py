# vm_manager/config.py

from pydantic_settings import BaseSettings
from pydantic import field_validator


class Settings(BaseSettings):
    # Orchestrator configuration
    ORCHESTRATOR_BASE_URL: str = "https://127.0.0.1:8000"
    ORCHESTRATOR_TIMEOUT_SECONDS: int = 300

    # AWS + Agent VM config
    AWS_REGION: str = "us-west-2"
    AGENT_AMI_ID: str = "ami-xxxxxxxx"
    AGENT_INSTANCE_TYPE: str = "t3.large"
    AGENT_SECURITY_GROUP_IDS: str = ""  # comma-separated list, e.g. "sg-abc,sg-def"
    AGENT_SUBNET_ID: str = ""  # required if you use a specific VPC subnet
    AGENT_SSH_KEY_NAME: str | None = None  # optional, if you want SSH in

    # Where the Flask VM controller listens inside the VM
    AGENT_CONTROLLER_PORT: int = 5000
    AGENT_CONTROLLER_HEALTH_PATH: str = "/health"

    # VNC WebSocket configuration
    AGENT_VNC_SCHEME: str = "ws"  # ws or wss later
    AGENT_VNC_WS_PORT: int = 6080  # where websockify will listen
    AGENT_VNC_WS_PATH: str = ""

    # Supabase auth
    SUPABASE_JWT_SECRET: str = ""  # from Supabase project settings → API → JWT secret
    SUPABASE_JWT_ALG: str = "HS256"

    @field_validator("SUPABASE_JWT_SECRET")
    @classmethod
    def trim_jwt_secret(cls, v: str) -> str:
        """Trim whitespace from JWT secret (common issue when copying from Supabase dashboard)"""
        return v.strip() if v else v

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
