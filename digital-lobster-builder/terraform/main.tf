# ──────────────────────────────────────────────
# DigitalOcean Strapi CMS Infrastructure
# ──────────────────────────────────────────────

# Configure the DigitalOcean provider
provider "digitalocean" {
  token = var.do_token
}

# ──────────────────────────────────────────────
# SSH Key
# ──────────────────────────────────────────────

resource "digitalocean_ssh_key" "strapi" {
  name       = "strapi-${replace(var.domain_name, ".", "-")}"
  public_key = var.ssh_public_key
}

# ──────────────────────────────────────────────
# Droplet — Strapi 1-Click Marketplace Image
# ──────────────────────────────────────────────

resource "digitalocean_droplet" "strapi" {
  name     = "strapi-${replace(var.domain_name, ".", "-")}"
  image    = "strapi-20-04"
  region   = var.droplet_region
  size     = var.droplet_size
  ssh_keys = [digitalocean_ssh_key.strapi.fingerprint]

  user_data = templatefile("${path.module}/cloud-init.yaml.tpl", {
    domain_name          = var.domain_name
    strapi_admin_email    = var.strapi_admin_email
    strapi_admin_password = var.strapi_admin_password
  })
}

# ──────────────────────────────────────────────
# Domain & DNS
# ──────────────────────────────────────────────

resource "digitalocean_domain" "site" {
  name = var.domain_name
}

resource "digitalocean_record" "site_a" {
  domain = digitalocean_domain.site.id
  type   = "A"
  name   = "@"
  value  = digitalocean_droplet.strapi.ipv4_address
  ttl    = 300
}

# ──────────────────────────────────────────────
# Firewall — Allow 22, 80, 443; Block 1337
# ──────────────────────────────────────────────

resource "digitalocean_firewall" "strapi" {
  name        = "strapi-${replace(var.domain_name, ".", "-")}"
  droplet_ids = [digitalocean_droplet.strapi.id]

  # Inbound: SSH
  inbound_rule {
    protocol         = "tcp"
    port_range       = "22"
    source_addresses = ["0.0.0.0/0", "::/0"]
  }

  # Inbound: HTTP
  inbound_rule {
    protocol         = "tcp"
    port_range       = "80"
    source_addresses = ["0.0.0.0/0", "::/0"]
  }

  # Inbound: HTTPS
  inbound_rule {
    protocol         = "tcp"
    port_range       = "443"
    source_addresses = ["0.0.0.0/0", "::/0"]
  }

  # Outbound: Allow all (needed for apt, npm, certbot, etc.)
  outbound_rule {
    protocol              = "tcp"
    port_range            = "1-65535"
    destination_addresses = ["0.0.0.0/0", "::/0"]
  }

  outbound_rule {
    protocol              = "udp"
    port_range            = "1-65535"
    destination_addresses = ["0.0.0.0/0", "::/0"]
  }

  outbound_rule {
    protocol              = "icmp"
    destination_addresses = ["0.0.0.0/0", "::/0"]
  }
}
