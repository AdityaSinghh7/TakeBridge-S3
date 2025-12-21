# vm_manager/config.py

from pydantic_settings import BaseSettings
from pydantic import field_validator


class Settings(BaseSettings):
    # Orchestrator configuration
    ORCHESTRATOR_BASE_URL: str = "https://127.0.0.1:8000"
    ORCHESTRATOR_TIMEOUT_SECONDS: int = 300

    # AWS + Agent VM config
    VM_PROVIDER: str = "aws"  # aws | gcp
    AWS_REGION: str = "us-west-2"
    AGENT_AMI_ID: str = "ami-xxxxxxxx"
    AGENT_INSTANCE_TYPE: str = "t3.large"
    AGENT_SECURITY_GROUP_IDS: str = ""  # comma-separated list, e.g. "sg-abc,sg-def"
    AGENT_SUBNET_ID: str = ""  # required if you use a specific VPC subnet
    AGENT_SSH_KEY_NAME: str | None = None  # optional, if you want SSH in

    # GCP + Agent VM config
    GCP_PROJECT_ID: str = ""
    GCP_ZONE: str = "us-central1-a"
    GCP_MACHINE_TYPE: str = "n2-standard-4"
    GCP_IMAGE: str = ""  # full image self-link or image name
    GCP_IMAGE_PROJECT: str = ""  # optional if GCP_IMAGE is a name
    GCP_MACHINE_IMAGE: str = ""  # full machine image self-link or name
    GCP_MACHINE_IMAGE_PROJECT: str = ""  # optional if GCP_MACHINE_IMAGE is a name
    GCP_NETWORK: str = "global/networks/default"
    GCP_SUBNETWORK: str = ""  # optional subnetwork self-link
    GCP_ASSIGN_PUBLIC_IP: bool = True
    GCP_SERVICE_ACCOUNT: str = ""  # optional service account email
    GCP_TAGS: str = ""  # comma-separated network tags
    GCP_DISK_SIZE_GB: int = 50
    GCP_INSTANCE_NAME_PREFIX: str = "tb-agent"
    GCP_STARTUP_SCRIPT: str = ""  # optional metadata startup script
    GCP_LOCAL_SSD_COUNT: int = 1  # 0 to disable local SSD; each is 375GB
    GCP_LOCAL_SSD_INTERFACE: str = "NVME"  # NVME or SCSI

    # Where the Flask VM controller listens inside the VM
    AGENT_CONTROLLER_PORT: int = 5000
    AGENT_CONTROLLER_HEALTH_PATH: str = "/health"
    VM_SKIP_CONTROLLER_HEALTHCHECK: bool = False

    # VNC WebSocket configuration
    AGENT_VNC_SCHEME: str = "ws"  # ws or wss later
    AGENT_VNC_WS_PORT: int = 6080  # where websockify will listen
    AGENT_VNC_WS_PATH: str = ""
    AGENT_GUACAMOLE_PORT: int = 8080
    AGENT_GUACAMOLE_PATH: str = "/guacamole"

    # Supabase auth
    SUPABASE_JWT_SECRET: str = ""  # from Supabase project settings → API → JWT secret
    SUPABASE_JWT_ALG: str = "HS256"
    GUAC_ADMIN_USER: str = ""
    GUAC_ADMIN_PASS: str = ""

    @field_validator("SUPABASE_JWT_SECRET")
    @classmethod
    def trim_jwt_secret(cls, v: str) -> str:
        """Trim whitespace from JWT secret (common issue when copying from Supabase dashboard)"""
        return v.strip() if v else v

    @property
    def startup_script_content(self) -> str:
        try:
            with open("scripts/startup.sh", "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            return self.GCP_STARTUP_SCRIPT

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
