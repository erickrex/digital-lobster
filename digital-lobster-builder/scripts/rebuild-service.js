#!/usr/bin/env node
/**
 * Astro Rebuild Service
 *
 * Lightweight HTTP server that listens for Strapi webhook POST requests
 * and triggers an Astro static site rebuild with debouncing.
 *
 * Environment variables:
 *   DEBOUNCE_MS  – debounce delay in milliseconds (default: 30000)
 *
 * Endpoints:
 *   POST /rebuild  → 200 {"status":"queued"}
 *   *              → 404
 *
 * Requirements: 12.3, 12.4, 12.5
 */

const http = require('http');
const { exec } = require('child_process');
const fs = require('fs');

// ── Configuration ──────────────────────────────────────────────
const PORT = 4000;
const HOST = '127.0.0.1';
const DEBOUNCE_MS = parseInt(process.env.DEBOUNCE_MS, 10) || 30000;
const LOG_FILE = '/var/log/astro-rebuild.log';
const SRC_DIR = '/var/www/astro-src';
const DEST_DIR = '/var/www/astro';
const BUILD_TIMEOUT = 300000; // 5 minutes

let debounceTimer = null;
let buildInProgress = false;

// ── Logging ────────────────────────────────────────────────────
function log(msg) {
  const line = `[${new Date().toISOString()}] ${msg}\n`;
  process.stdout.write(line);
  try {
    fs.appendFileSync(LOG_FILE, line);
  } catch (_) {
    // If log file is not writable, continue silently
  }
}

// ── Build ──────────────────────────────────────────────────────
function runBuild() {
  if (buildInProgress) {
    log('Build already in progress — skipping.');
    return;
  }
  buildInProgress = true;
  log('Starting Astro rebuild...');

  const buildCmd = `cd ${SRC_DIR} && STRAPI_URL=http://localhost:1337 npm run build`;

  exec(buildCmd, { timeout: BUILD_TIMEOUT }, (buildErr, buildStdout, buildStderr) => {
    if (buildErr) {
      log(`Astro rebuild FAILED: ${buildErr.message}`);
      if (buildStderr) log(`stderr: ${buildStderr}`);
      buildInProgress = false;
      return;
    }

    log('Build succeeded. Copying output to ' + DEST_DIR + '...');

    const copyCmd = `cp -r ${SRC_DIR}/dist/* ${DEST_DIR}/ && chown -R www-data:www-data ${DEST_DIR}`;

    exec(copyCmd, (copyErr, _copyStdout, copyStderr) => {
      if (copyErr) {
        log(`Copy FAILED: ${copyErr.message}`);
        if (copyStderr) log(`stderr: ${copyStderr}`);
        // Previous build is retained in DEST_DIR
      } else {
        log('Astro rebuild completed successfully.');
      }
      buildInProgress = false;
    });
  });
}

// ── HTTP Server ────────────────────────────────────────────────
const server = http.createServer((req, res) => {
  if (req.method === 'POST' && req.url === '/rebuild') {
    log('Received rebuild webhook request — debouncing (' + DEBOUNCE_MS + 'ms)...');

    if (debounceTimer) clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => {
      debounceTimer = null;
      runBuild();
    }, DEBOUNCE_MS);

    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ status: 'queued' }));
  } else {
    res.writeHead(404, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ error: 'Not found' }));
  }
});

server.listen(PORT, HOST, () => {
  log(`Rebuild service listening on ${HOST}:${PORT} (debounce: ${DEBOUNCE_MS}ms)`);
});
