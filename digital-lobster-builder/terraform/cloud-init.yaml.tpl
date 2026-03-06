#cloud-config
# ──────────────────────────────────────────────
# Cloud-init configuration for Strapi + Astro VPS
# Domain: ${domain_name}
# ──────────────────────────────────────────────

write_files:
  # ── Nginx site configuration ──
  - path: /etc/nginx/sites-available/${domain_name}
    permissions: "0644"
    content: |
      # Redirect HTTP → HTTPS
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

          # SSL certificates (placeholder until certbot runs)
          ssl_certificate     /etc/ssl/certs/ssl-cert-snakeoil.pem;
          ssl_certificate_key /etc/ssl/private/ssl-cert-snakeoil.key;

          # ── Security headers ──
          add_header X-Frame-Options "SAMEORIGIN" always;
          add_header X-Content-Type-Options "nosniff" always;
          add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

          # ── Gzip compression ──
          gzip on;
          gzip_vary on;
          gzip_proxied any;
          gzip_comp_level 6;
          gzip_types text/plain text/css application/json application/javascript text/xml application/xml application/xml+rss text/javascript image/svg+xml;

          # ── Static asset cache (30 days) ──
          location ~* \.(jpg|jpeg|png|gif|ico|svg|webp|woff|woff2|ttf|eot|css|js)$$ {
              root /var/www/astro;
              expires 30d;
              add_header Cache-Control "public, immutable";
              try_files $$uri =404;
          }

          # ── Strapi API proxy ──
          location /api/ {
              proxy_pass http://127.0.0.1:1337;
              proxy_http_version 1.1;
              proxy_set_header Host $$host;
              proxy_set_header X-Real-IP $$remote_addr;
              proxy_set_header X-Forwarded-For $$proxy_add_x_forwarded_for;
              proxy_set_header X-Forwarded-Proto $$scheme;
              proxy_set_header Upgrade $$http_upgrade;
              proxy_set_header Connection "upgrade";
          }

          # ── Strapi admin proxy ──
          location /admin/ {
              proxy_pass http://127.0.0.1:1337;
              proxy_http_version 1.1;
              proxy_set_header Host $$host;
              proxy_set_header X-Real-IP $$remote_addr;
              proxy_set_header X-Forwarded-For $$proxy_add_x_forwarded_for;
              proxy_set_header X-Forwarded-Proto $$scheme;
              proxy_set_header Upgrade $$http_upgrade;
              proxy_set_header Connection "upgrade";
          }

          # ── Astro static files (catch-all) ──
          location / {
              root /var/www/astro;
              try_files $$uri $$uri/index.html $$uri.html =404;
          }
      }

  # ── Strapi systemd service ──
  - path: /etc/systemd/system/strapi.service
    permissions: "0644"
    content: |
      [Unit]
      Description=Strapi CMS
      After=network.target

      [Service]
      Type=simple
      User=root
      WorkingDirectory=/srv/strapi
      ExecStart=/usr/bin/node /srv/strapi/node_modules/.bin/strapi start
      Restart=on-failure
      RestartSec=10
      Environment=NODE_ENV=production
      Environment=STRAPI_ADMIN_EMAIL=${strapi_admin_email}
      Environment=STRAPI_ADMIN_PASSWORD=${strapi_admin_password}

      [Install]
      WantedBy=multi-user.target

  # ── Astro rebuild service script ──
  - path: /opt/rebuild-service/server.js
    permissions: "0755"
    content: |
      const http = require('http');
      const { execSync } = require('child_process');
      const fs = require('fs');

      const DEBOUNCE_MS = 30000; // 30 seconds
      const LOG_FILE = '/var/log/astro-rebuild.log';
      let debounceTimer = null;

      function log(msg) {
        const ts = new Date().toISOString();
        const line = `[$${ts}] $${msg}\n`;
        fs.appendFileSync(LOG_FILE, line);
        process.stdout.write(line);
      }

      function runBuild() {
        log('Starting Astro rebuild...');
        try {
          execSync(
            'cd /var/www/astro-src && STRAPI_URL=http://localhost:1337 npm run build && cp -r dist/* /var/www/astro/ && chown -R www-data:www-data /var/www/astro',
            { stdio: 'pipe', timeout: 300000 }
          );
          log('Astro rebuild completed successfully.');
        } catch (err) {
          log(`Astro rebuild FAILED: $${err.message}`);
          // Retain previous build — do not clear /var/www/astro
        }
      }

      const server = http.createServer((req, res) => {
        if (req.method === 'POST' && req.url === '/rebuild') {
          log('Received rebuild webhook request — debouncing...');
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

  # ── Astro rebuild systemd service ──
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
  # ── Step tracking ──
  - |
    STATUS_FILE="/var/run/cloud-init-complete"
    LOG="/var/log/cloud-init-output.log"
    echo "cloud-init started at $$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$$LOG"

  # ── Step 1: Install Node.js LTS via NodeSource ──
  - |
    LOG="/var/log/cloud-init-output.log"
    echo "[Step 1] Installing Node.js LTS via NodeSource..." >> "$$LOG"
    if curl -fsSL https://deb.nodesource.com/setup_lts.x | bash - >> "$$LOG" 2>&1 && \
       apt-get install -y nodejs >> "$$LOG" 2>&1; then
      echo "[Step 1] Node.js installed: $$(node --version)" >> "$$LOG"
      STEP1="success"
    else
      echo "[Step 1] FAILED: Node.js installation failed" >> "$$LOG"
      STEP1="failed"
    fi

  # ── Step 2: Configure Nginx reverse proxy ──
  - |
    LOG="/var/log/cloud-init-output.log"
    echo "[Step 2] Configuring Nginx..." >> "$$LOG"
    if ln -sf /etc/nginx/sites-available/${domain_name} /etc/nginx/sites-enabled/${domain_name} && \
       rm -f /etc/nginx/sites-enabled/default && \
       nginx -t >> "$$LOG" 2>&1 && \
       systemctl reload nginx >> "$$LOG" 2>&1; then
      echo "[Step 2] Nginx configured successfully" >> "$$LOG"
      STEP2="success"
    else
      echo "[Step 2] FAILED: Nginx configuration failed" >> "$$LOG"
      STEP2="failed"
    fi

  # ── Step 3: Install certbot and obtain Let's Encrypt certificate ──
  - |
    LOG="/var/log/cloud-init-output.log"
    echo "[Step 3] Installing certbot and obtaining SSL certificate..." >> "$$LOG"
    if apt-get install -y certbot python3-certbot-nginx >> "$$LOG" 2>&1 && \
       certbot --nginx -d ${domain_name} --non-interactive --agree-tos -m ${strapi_admin_email} --redirect >> "$$LOG" 2>&1; then
      echo "[Step 3] SSL certificate obtained for ${domain_name}" >> "$$LOG"
      STEP3="success"
    else
      echo "[Step 3] FAILED: certbot/SSL setup failed" >> "$$LOG"
      STEP3="failed"
    fi

  # ── Step 4: Create /var/www/astro directory ──
  - |
    LOG="/var/log/cloud-init-output.log"
    echo "[Step 4] Creating /var/www/astro directory..." >> "$$LOG"
    if mkdir -p /var/www/astro && \
       chown -R www-data:www-data /var/www/astro; then
      echo "[Step 4] /var/www/astro created with www-data ownership" >> "$$LOG"
      STEP4="success"
    else
      echo "[Step 4] FAILED: directory creation failed" >> "$$LOG"
      STEP4="failed"
    fi

  # ── Step 5: Configure Strapi systemd service ──
  - |
    LOG="/var/log/cloud-init-output.log"
    echo "[Step 5] Configuring Strapi systemd service..." >> "$$LOG"
    if systemctl daemon-reload && \
       systemctl enable strapi.service >> "$$LOG" 2>&1 && \
       systemctl start strapi.service >> "$$LOG" 2>&1; then
      echo "[Step 5] Strapi service enabled and started" >> "$$LOG"
      STEP5="success"
    else
      echo "[Step 5] FAILED: Strapi service configuration failed" >> "$$LOG"
      STEP5="failed"
    fi

  # ── Step 6: Create rebuild service directory ──
  - |
    LOG="/var/log/cloud-init-output.log"
    echo "[Step 6] Setting up rebuild service..." >> "$$LOG"
    if mkdir -p /opt/rebuild-service && \
       touch /var/log/astro-rebuild.log; then
      echo "[Step 6] Rebuild service directory created" >> "$$LOG"
      STEP6="success"
    else
      echo "[Step 6] FAILED: rebuild service setup failed" >> "$$LOG"
      STEP6="failed"
    fi

  # ── Step 7: Configure astro-rebuild systemd service ──
  - |
    LOG="/var/log/cloud-init-output.log"
    echo "[Step 7] Configuring astro-rebuild systemd service..." >> "$$LOG"
    if systemctl daemon-reload && \
       systemctl enable astro-rebuild.service >> "$$LOG" 2>&1 && \
       systemctl start astro-rebuild.service >> "$$LOG" 2>&1; then
      echo "[Step 7] Astro rebuild service enabled and started" >> "$$LOG"
      STEP7="success"
    else
      echo "[Step 7] FAILED: astro-rebuild service configuration failed" >> "$$LOG"
      STEP7="failed"
    fi

  # ── Step 8: Write completion status ──
  - |
    LOG="/var/log/cloud-init-output.log"
    STATUS_FILE="/var/run/cloud-init-complete"
    TIMESTAMP=$$(date -u +%Y-%m-%dT%H:%M:%SZ)
    echo "[Step 8] Writing completion status..." >> "$$LOG"
    cat > "$$STATUS_FILE" <<EOF
    {
      "completed_at": "$$TIMESTAMP",
      "steps": {
        "nodejs_install": "$${STEP1:-unknown}",
        "nginx_config": "$${STEP2:-unknown}",
        "certbot_ssl": "$${STEP3:-unknown}",
        "astro_directory": "$${STEP4:-unknown}",
        "strapi_service": "$${STEP5:-unknown}",
        "rebuild_service_setup": "$${STEP6:-unknown}",
        "rebuild_service_systemd": "$${STEP7:-unknown}"
      }
    }
    EOF
    echo "[Step 8] Cloud-init complete at $$TIMESTAMP" >> "$$LOG"
