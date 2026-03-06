# ──────────────────────────────────────────────
# Input Variables
# ──────────────────────────────────────────────

variable "do_token" {
  description = "DigitalOcean API token for provisioning resources"
  type        = string
  sensitive   = true
}

variable "domain_name" {
  description = "Domain name for the hosted site (e.g., example.com)"
  type        = string
}

variable "droplet_region" {
  description = "DigitalOcean region slug for the Droplet"
  type        = string
  default     = "nyc3"
}

variable "droplet_size" {
  description = "DigitalOcean Droplet size slug (minimum s-2vcpu-4gb for Strapi + Astro builds)"
  type        = string
  default     = "s-2vcpu-4gb"
}

variable "ssh_public_key" {
  description = "SSH public key for Droplet access"
  type        = string
  sensitive   = true
}

variable "strapi_admin_email" {
  description = "Email address for the initial Strapi admin user"
  type        = string
}

variable "strapi_admin_password" {
  description = "Password for the initial Strapi admin user"
  type        = string
  sensitive   = true
}
