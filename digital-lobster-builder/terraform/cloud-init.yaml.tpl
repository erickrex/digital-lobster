#cloud-config
# ──────────────────────────────────────────────
# Cloud-init configuration for an owned Ubuntu 24.04 Strapi + Astro VPS.
# This avoids patching vendor-managed marketplace files and keeps the
# runtime topology under repository control.
# Domain: ${domain_name}
# ──────────────────────────────────────────────

write_files:
  - path: /etc/nginx/snippets/digital-lobster-strapi-proxy.conf
    permissions: "0644"
    content: |
      proxy_pass http://127.0.0.1:1337;
      proxy_http_version 1.1;
      proxy_set_header Host $$host;
      proxy_set_header X-Real-IP $$remote_addr;
      proxy_set_header X-Forwarded-For $$proxy_add_x_forwarded_for;
      proxy_set_header X-Forwarded-Proto $$scheme;
      proxy_set_header Upgrade $$http_upgrade;
      proxy_set_header Connection "upgrade";
      proxy_read_timeout 300;

  - path: /etc/nginx/sites-available/${domain_name}
    permissions: "0644"
    content: |
      server {
          listen 80;
          listen [::]:80;
          server_name ${domain_name};
          return 301 https://$$host$$request_uri;
      }

      server {
          listen 443 ssl http2;
          listen [::]:443 ssl http2;
          server_name ${domain_name};

          ssl_certificate     /etc/ssl/certs/ssl-cert-snakeoil.pem;
          ssl_certificate_key /etc/ssl/private/ssl-cert-snakeoil.key;

          add_header X-Frame-Options "SAMEORIGIN" always;
          add_header X-Content-Type-Options "nosniff" always;
          add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

          client_max_body_size 100m;

          gzip on;
          gzip_vary on;
          gzip_proxied any;
          gzip_comp_level 6;
          gzip_types text/plain text/css application/json application/javascript text/xml application/xml application/xml+rss text/javascript image/svg+xml;

          location = /_health {
              include /etc/nginx/snippets/digital-lobster-strapi-proxy.conf;
          }

          location ^~ /api/ {
              include /etc/nginx/snippets/digital-lobster-strapi-proxy.conf;
          }

          location = /admin {
              include /etc/nginx/snippets/digital-lobster-strapi-proxy.conf;
          }

          location ^~ /admin/ {
              include /etc/nginx/snippets/digital-lobster-strapi-proxy.conf;
          }

          location ^~ /uploads/ {
              include /etc/nginx/snippets/digital-lobster-strapi-proxy.conf;
          }

          location ^~ /content-manager/ {
              include /etc/nginx/snippets/digital-lobster-strapi-proxy.conf;
          }

          location ^~ /content-type-builder/ {
              include /etc/nginx/snippets/digital-lobster-strapi-proxy.conf;
          }

          location ^~ /i18n/ {
              include /etc/nginx/snippets/digital-lobster-strapi-proxy.conf;
          }

          location ^~ /documentation/ {
              include /etc/nginx/snippets/digital-lobster-strapi-proxy.conf;
          }

          location = /graphql {
              include /etc/nginx/snippets/digital-lobster-strapi-proxy.conf;
          }

          location ^~ /graphql/ {
              include /etc/nginx/snippets/digital-lobster-strapi-proxy.conf;
          }

          location ^~ /users-permissions/ {
              include /etc/nginx/snippets/digital-lobster-strapi-proxy.conf;
          }

          location ~* \.(jpg|jpeg|png|gif|ico|svg|webp|woff|woff2|ttf|eot|css|js)$$ {
              root /var/www/astro;
              expires 30d;
              add_header Cache-Control "public, immutable";
              try_files $$uri =404;
          }

          location / {
              root /var/www/astro;
              try_files $$uri $$uri/index.html $$uri.html =404;
          }
      }

  - path: /usr/local/bin/patch-strapi-server-config.py
    permissions: "0755"
    content: |
      #!/usr/bin/env python3
      from __future__ import annotations

      import re
      import sys
      from pathlib import Path


      def _ensure_setting(text: str, key: str, value: str) -> str:
          pattern = re.compile(rf"(?m)^(\s*{re.escape(key)}:\s*.+,\s*)$")
          if pattern.search(text):
              return text

          port_pattern = re.compile(r"(?m)^(\s*port:\s*.+,\s*)$")
          if port_pattern.search(text):
              return port_pattern.sub(rf"\1\n  {key}: {value},", text, count=1)

          app_pattern = re.compile(r"(?m)^(\s*app:\s*\{{\s*)$")
          if app_pattern.search(text):
              return app_pattern.sub(rf"  {key}: {value},\n\1", text, count=1)

          raise RuntimeError(f"Could not inject '{key}' into server config")


      def main() -> int:
          if len(sys.argv) != 3:
              raise SystemExit("usage: patch-strapi-server-config.py <app-root> <domain>")

          app_root = Path(sys.argv[1])
          domain_name = sys.argv[2]
          config_candidates = [
              app_root / "config" / "server.js",
              app_root / "config" / "server.ts",
          ]
          for path in config_candidates:
              if path.exists():
                  text = path.read_text()
                  text = _ensure_setting(text, "url", "env('PUBLIC_URL', '')")
                  text = _ensure_setting(text, "proxy", "true")
                  path.write_text(text)
                  print(f"Patched {path}")
                  return 0

          raise SystemExit("Strapi server config was not found")


      if __name__ == "__main__":
          raise SystemExit(main())

  - path: /usr/local/bin/bootstrap-owned-strapi.sh
    permissions: "0755"
    content: |
      #!/bin/bash
      set -euo pipefail

      DOMAIN_NAME="$1"
      APP_ROOT="/srv/strapi/app"
      APP_ENV_FILE="$$APP_ROOT/.env"
      STRAPI_USER="strapi"
      STRAPI_GROUP="strapi"
      STRAPI_HOME="/srv/strapi"

      install -d -m 0755 -o "$$STRAPI_USER" -g "$$STRAPI_GROUP" "$$STRAPI_HOME"
      install -d -m 0755 -o "$$STRAPI_USER" -g "$$STRAPI_GROUP" /var/www/astro /var/www/astro-src /opt/rebuild-service

      if [ ! -f "$$APP_ROOT/package.json" ]; then
        su - "$$STRAPI_USER" -s /bin/bash -c "CI=true npx create-strapi-app@latest $$APP_ROOT --quickstart --no-run --skip-cloud --use-npm"
      fi

      /usr/local/bin/patch-strapi-server-config.py "$$APP_ROOT" "$$DOMAIN_NAME"

      touch "$$APP_ENV_FILE"
      chown "$$STRAPI_USER":"$$STRAPI_GROUP" "$$APP_ENV_FILE"

      upsert_env() {
        local key="$1"
        local value="$2"
        if grep -q "^$${key}=" "$$APP_ENV_FILE"; then
          sed -i "s|^$${key}=.*|$${key}=$${value}|" "$$APP_ENV_FILE"
        else
          printf '%s=%s\n' "$$key" "$$value" >> "$$APP_ENV_FILE"
        fi
      }

      ensure_secret() {
        local key="$1"
        if ! grep -q "^$${key}=" "$$APP_ENV_FILE"; then
          printf '%s=%s\n' "$$key" "$$(openssl rand -hex 32)" >> "$$APP_ENV_FILE"
        fi
      }

      upsert_env "HOST" "127.0.0.1"
      upsert_env "PORT" "1337"
      upsert_env "PUBLIC_URL" "https://$$DOMAIN_NAME"
      if ! grep -q "^APP_KEYS=" "$$APP_ENV_FILE"; then
        printf 'APP_KEYS=%s,%s,%s,%s\n' \
          "$$(openssl rand -hex 16)" \
          "$$(openssl rand -hex 16)" \
          "$$(openssl rand -hex 16)" \
          "$$(openssl rand -hex 16)" >> "$$APP_ENV_FILE"
      fi
      ensure_secret "API_TOKEN_SALT"
      ensure_secret "ADMIN_JWT_SECRET"
      ensure_secret "TRANSFER_TOKEN_SALT"
      ensure_secret "JWT_SECRET"

      chown -R "$$STRAPI_USER":"$$STRAPI_GROUP" "$$STRAPI_HOME"
      su - "$$STRAPI_USER" -s /bin/bash -c "cd $$APP_ROOT && NODE_ENV=production npm run build"

  - path: /etc/systemd/system/strapi.service
    permissions: "0644"
    content: |
      [Unit]
      Description=Digital Lobster Strapi CMS
      After=network.target

      [Service]
      Type=simple
      User=strapi
      Group=strapi
      WorkingDirectory=/srv/strapi/app
      Environment=NODE_ENV=production
      ExecStart=/usr/bin/npm run start
      Restart=on-failure
      RestartSec=10

      [Install]
      WantedBy=multi-user.target

  - path: /opt/rebuild-service/server.js
    permissions: "0755"
    content: |
      const http = require('http');
      const { execSync } = require('child_process');
      const fs = require('fs');

      const DEBOUNCE_MS = 30000;
      const LOG_FILE = '/var/log/astro-rebuild.log';
      let debounceTimer = null;

      function log(msg) {
        const ts = new Date().toISOString();
        const line = `[${ts}] ${msg}\n`;
        fs.appendFileSync(LOG_FILE, line);
        process.stdout.write(line);
      }

      function runBuild() {
        log('Starting Astro rebuild...');
        try {
          execSync(
            'cd /var/www/astro-src && STRAPI_URL=http://127.0.0.1 npm run build && cp -r dist/* /var/www/astro/ && chown -R www-data:www-data /var/www/astro',
            { stdio: 'pipe', timeout: 300000 }
          );
          log('Astro rebuild completed successfully.');
        } catch (err) {
          log(`Astro rebuild FAILED: ${err.message}`);
        }
      }

      const server = http.createServer((req, res) => {
        if (req.method === 'POST' && req.url === '/rebuild') {
          log('Received rebuild webhook request; debouncing.');
          if (debounceTimer) clearTimeout(debounceTimer);
          debounceTimer = setTimeout(() => {
            debounceTimer = null;
            runBuild();
          }, DEBOUNCE_MS);
          res.writeHead(200, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ status: 'queued' }));
        } else {
          res.writeHead(404);
          res.end();
        }
      });

      server.listen(4000, '127.0.0.1', () => {
        log('Rebuild service listening on 127.0.0.1:4000');
      });

  - path: /etc/systemd/system/astro-rebuild.service
    permissions: "0644"
    content: |
      [Unit]
      Description=Astro Rebuild Service (webhook listener)
      After=network.target

      [Service]
      Type=simple
      User=root
      WorkingDirectory=/opt/rebuild-service
      ExecStart=/usr/bin/node /opt/rebuild-service/server.js
      Restart=on-failure
      RestartSec=10
      Environment=NODE_ENV=production

      [Install]
      WantedBy=multi-user.target

runcmd:
  - |
    export DEBIAN_FRONTEND=noninteractive
    STATUS_FILE="/var/run/cloud-init-complete"
    LOG="/var/log/cloud-init-output.log"
    echo "cloud-init started at $$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$$LOG"

  - |
    LOG="/var/log/cloud-init-output.log"
    echo "[Step 1] Installing OS packages..." >> "$$LOG"
    if apt-get update >> "$$LOG" 2>&1 && \
       apt-get install -y curl nginx certbot python3-certbot-nginx build-essential python3 pkg-config libvips-dev sqlite3 >> "$$LOG" 2>&1; then
      echo "[Step 1] Base packages installed" >> "$$LOG"
      STEP1="success"
    else
      echo "[Step 1] FAILED: package installation failed" >> "$$LOG"
      STEP1="failed"
    fi

  - |
    LOG="/var/log/cloud-init-output.log"
    echo "[Step 2] Installing Node.js 24 LTS..." >> "$$LOG"
    if curl -fsSL https://deb.nodesource.com/setup_24.x | bash - >> "$$LOG" 2>&1 && \
       apt-get install -y nodejs >> "$$LOG" 2>&1; then
      echo "[Step 2] Node.js installed: $$(node --version)" >> "$$LOG"
      STEP2="success"
    else
      echo "[Step 2] FAILED: Node.js installation failed" >> "$$LOG"
      STEP2="failed"
    fi

  - |
    LOG="/var/log/cloud-init-output.log"
    echo "[Step 3] Creating users and directories..." >> "$$LOG"
    if id -u strapi >/dev/null 2>&1 || useradd --system --create-home --home-dir /srv/strapi --shell /bin/bash strapi; then
      if mkdir -p /srv/strapi /var/www/astro /var/www/astro-src /opt/rebuild-service && \
         chown -R strapi:strapi /srv/strapi && \
         chown -R www-data:www-data /var/www/astro /var/www/astro-src && \
         touch /var/log/astro-rebuild.log; then
        echo "[Step 3] Users and directories created" >> "$$LOG"
        STEP3="success"
      else
        echo "[Step 3] FAILED: directory bootstrap failed" >> "$$LOG"
        STEP3="failed"
      fi
    else
      echo "[Step 3] FAILED: could not create strapi user" >> "$$LOG"
      STEP3="failed"
    fi

  - |
    LOG="/var/log/cloud-init-output.log"
    echo "[Step 4] Bootstrapping owned Strapi app..." >> "$$LOG"
    if /usr/local/bin/bootstrap-owned-strapi.sh ${domain_name} >> "$$LOG" 2>&1; then
      echo "[Step 4] Strapi app bootstrapped" >> "$$LOG"
      STEP4="success"
    else
      echo "[Step 4] FAILED: Strapi bootstrap failed" >> "$$LOG"
      STEP4="failed"
    fi

  - |
    LOG="/var/log/cloud-init-output.log"
    echo "[Step 5] Enabling Strapi service..." >> "$$LOG"
    READY="no"
    if systemctl daemon-reload >> "$$LOG" 2>&1 && \
       systemctl enable strapi.service >> "$$LOG" 2>&1 && \
       systemctl restart strapi.service >> "$$LOG" 2>&1; then
      for _ in $$(seq 1 60); do
        CODE=$$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:1337/admin || true)
        if [ "$$CODE" = "200" ] || [ "$$CODE" = "301" ] || [ "$$CODE" = "302" ] || \
           [ "$$CODE" = "307" ] || [ "$$CODE" = "308" ]; then
          READY="yes"
          break
        fi
        sleep 5
      done
    fi
    if [ "$$READY" = "yes" ]; then
      echo "[Step 5] Strapi service is ready on 127.0.0.1:1337" >> "$$LOG"
      STEP5="success"
    else
      echo "[Step 5] FAILED: Strapi service did not become ready" >> "$$LOG"
      STEP5="failed"
    fi

  - |
    LOG="/var/log/cloud-init-output.log"
    echo "[Step 6] Configuring Nginx..." >> "$$LOG"
    if ln -sf /etc/nginx/sites-available/${domain_name} /etc/nginx/sites-enabled/${domain_name} && \
       rm -f /etc/nginx/sites-enabled/default && \
       nginx -t >> "$$LOG" 2>&1 && \
       systemctl enable nginx >> "$$LOG" 2>&1 && \
       systemctl restart nginx >> "$$LOG" 2>&1; then
      echo "[Step 6] Nginx configured successfully" >> "$$LOG"
      STEP6="success"
    else
      echo "[Step 6] FAILED: Nginx configuration failed" >> "$$LOG"
      STEP6="failed"
    fi

  - |
    LOG="/var/log/cloud-init-output.log"
    echo "[Step 7] Installing TLS certificate with certbot..." >> "$$LOG"
    if certbot --nginx -d ${domain_name} --non-interactive --agree-tos -m ${strapi_admin_email} --redirect >> "$$LOG" 2>&1; then
      echo "[Step 7] SSL certificate obtained for ${domain_name}" >> "$$LOG"
      STEP7="success"
    else
      echo "[Step 7] FAILED: certbot/SSL setup failed" >> "$$LOG"
      STEP7="failed"
    fi

  - |
    LOG="/var/log/cloud-init-output.log"
    echo "[Step 8] Enabling the astro rebuild service..." >> "$$LOG"
    if systemctl daemon-reload >> "$$LOG" 2>&1 && \
       systemctl enable astro-rebuild.service >> "$$LOG" 2>&1 && \
       systemctl restart astro-rebuild.service >> "$$LOG" 2>&1; then
      echo "[Step 8] Astro rebuild service enabled and started" >> "$$LOG"
      STEP8="success"
    else
      echo "[Step 8] FAILED: astro rebuild service configuration failed" >> "$$LOG"
      STEP8="failed"
    fi

  - |
    LOG="/var/log/cloud-init-output.log"
    STATUS_FILE="/var/run/cloud-init-complete"
    TIMESTAMP=$$(date -u +%Y-%m-%dT%H:%M:%SZ)
    echo "[Step 9] Writing completion status..." >> "$$LOG"
    cat > "$$STATUS_FILE" <<EOF
    {
      "completed_at": "$$TIMESTAMP",
      "steps": {
        "package_install": "$${STEP1:-unknown}",
        "nodejs_install": "$${STEP2:-unknown}",
        "directory_bootstrap": "$${STEP3:-unknown}",
        "strapi_bootstrap": "$${STEP4:-unknown}",
        "strapi_service": "$${STEP5:-unknown}",
        "nginx_config": "$${STEP6:-unknown}",
        "certbot_ssl": "$${STEP7:-unknown}",
        "rebuild_service_systemd": "$${STEP8:-unknown}"
      }
    }
    EOF
    echo "[Step 9] Cloud-init complete at $$TIMESTAMP" >> "$$LOG"
