# ──────────────────────────────────────────────
# Terraform Outputs
# ──────────────────────────────────────────────

output "droplet_ip" {
  description = "Public IPv4 address of the Strapi Droplet"
  value       = digitalocean_droplet.strapi.ipv4_address
}

output "domain_name" {
  description = "Configured domain name for the site"
  value       = digitalocean_domain.site.name
}

output "strapi_admin_url" {
  description = "URL for the Strapi admin panel"
  value       = "https://${digitalocean_domain.site.name}/admin"
}

output "ssh_connection_string" {
  description = "SSH connection string for the Droplet"
  value       = "root@${digitalocean_droplet.strapi.ipv4_address}"
}
