"""CMS pipeline configuration model."""

from pydantic import BaseModel, SecretStr


class CMSConfig(BaseModel):
    """Configuration for CMS mode pipeline runs."""

    domain_name: str
    droplet_region: str = "nyc3"
    droplet_size: str = "s-2vcpu-4gb"
    ssh_public_key: str
    ssh_private_key_path: str
    do_token: SecretStr
    strapi_admin_email: str
    strapi_admin_password: SecretStr
    terraform_state_path: str = "./terraform.tfstate"
