// WaterExpert V1.0 -- Take empty-state screenshots for software introduction
// Strategy: intercept all data APIs to return empty data, so every page
// renders its "first open / no data uploaded" state.
//
// Usage:
//   node docs/screenshots/take_empty_screenshots.js
//
// Prerequisites:
//   - Server running at http://127.0.0.1:8000
//   - npm install playwright

const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

const BASE = 'http://127.0.0.1:8000';
const OUT_DIR = path.resolve(__dirname, 'empty');
const VIEWPORT = { width: 1920, height: 1080 };

// ---------------------------------------------------------------------------
// Empty data payloads for every data API.
// Auth endpoints (/api/v1/auth/*) are NOT intercepted -- login must work.
// ---------------------------------------------------------------------------
const EMPTY = {
  stations: [],
  'data/imports': [],
  'prediction-jobs': [],
  meta: {},
  dashboard: {
    station_profile: {},
    test_models: {},
    guardrails: [],
    high_priority_days: [],
    scenario_counts: {},
    best_model_summary: {},
  },
  diagnostics: {
    factor_summary: {
      top_driver_domains: [],
      top_inhibitor_domains: [],
      top_driver_features: [],
    },
    process_decomposition: [],
  },
  'scenario-triage': {
    high_priority_days: [],
    scenario_counts: {},
  },
  boundary: {},
  'response-playbook': {
    scenario_response_playbook: {},
  },
  sensitivity: {
    sobol: { top_factors: [] },
  },
  predictions: {
    series: [],
    summary: {},
    available_models: ['cmfbe_stgcn', 'mscim', 'mscim_no_kg'],
  },
  thresholds: {
    risk_snapshot: {},
    summary: [],
    knowledge_graph: { threshold_nodes: [] },
  },
  'database/summary': {
    total_records: 0,
    total_stations: 0,
    date_start: null,
    date_end: null,
    key_indicators: [],
  },
  'database/stations': [],
  'database/query': {
    rows: [],
    matched_rows: 0,
    returned_rows: 0,
    pagination: {},
    summary: {
      station_count: 0,
      mean_turbidity: 0,
      mean_secchi_depth: 0,
    },
  },
  'preprocess/summary': {
    rows_analyzed: 0,
    date_start: null,
    date_end: null,
    total_missing_cells: 0,
    total_outlier_flags: 0,
    recommendations: [],
    feature_profiles: [],
    station: {},
  },
  'visualization/summary': {
    series: [],
    stats: {},
    correlations: [],
    station: {},
  },
};

// Build a map from path prefix -> empty payload
function buildEmptyMap() {
  const map = {};
  for (const [key, payload] of Object.entries(EMPTY)) {
    map[`/api/v1/${key}`] = payload;
  }
  return map;
}

const EMPTY_MAP = buildEmptyMap();

// Find the best-matching empty payload for a request URL
function matchEmptyPayload(url) {
  let bestKey = '';
  for (const key of Object.keys(EMPTY_MAP)) {
    if (url.startsWith(key) && key.length > bestKey.length) {
      bestKey = key;
    }
  }
  return bestKey ? EMPTY_MAP[bestKey] : null;
}

// ---------------------------------------------------------------------------
async function run() {
  fs.mkdirSync(OUT_DIR, { recursive: true });

  const browser = await chromium.launch({
    channel: 'msedge',
    headless: true,
  });

  const context = await browser.newContext({
    viewport: VIEWPORT,
    deviceScaleFactor: 1,
  });

  const page = await context.newPage();

  // ---- Intercept ALL /api/v1/ calls -----------------------------------
  // Auth endpoints pass through to the real server; everything else
  // returns the empty payload.
  await page.route('**/api/v1/**', async (route) => {
    const url = route.request().url();
    // Strip the base so we only match the path
    const parsed = new URL(url);
    const pathname = parsed.pathname;

    // Let auth calls through untouched
    if (pathname.startsWith('/api/v1/auth/')) {
      await route.continue();
      return;
    }

    const payload = matchEmptyPayload(pathname);
    if (payload !== null) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(payload),
      });
    } else {
      // Unknown /api/v1/* endpoint -- return empty object rather than failing
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: '{}',
      });
    }
  });

  // ---- 1. Login -------------------------------------------------------
  console.log('[1/7] Login page...');
  await page.goto(`${BASE}/ui/login.html`, { waitUntil: 'networkidle' });
  await page.waitForSelector('#loginUsername', { state: 'visible' });

  // Fill demo credentials (they come from the hint API which passes through)
  await page.fill('#loginUsername', '2510709');
  await page.fill('#loginPassword', 'AI4S666');
  await page.click('#loginSubmitButton');

  // Wait for navigation to index
  await page.waitForURL('**/index.html', { timeout: 10000 });
  console.log('  -> Logged in, arrived at index.');

  // ---- 2. Index / Dashboard (empty state) -----------------------------
  console.log('[2/7] Dashboard (empty state)...');
  await page.waitForSelector('[data-page="dashboard"]', { state: 'visible' });
  // Give empty-state renders a moment to settle
  await page.waitForTimeout(800);
  await page.screenshot({
    path: path.join(OUT_DIR, '02-index.png'),
    fullPage: true,
  });
  console.log('  -> 02-index.png saved.');

  // ---- 3. Database ----------------------------------------------------
  console.log('[3/7] Database...');
  await page.goto(`${BASE}/ui/database.html`, { waitUntil: 'networkidle' });
  await page.waitForSelector('[data-page="database"]', { state: 'visible' });
  await page.waitForTimeout(600);
  await page.screenshot({
    path: path.join(OUT_DIR, '03-database.png'),
    fullPage: true,
  });
  console.log('  -> 03-database.png saved.');

  // ---- 4. Upload ------------------------------------------------------
  console.log('[4/7] Upload...');
  await page.goto(`${BASE}/ui/upload.html`, { waitUntil: 'networkidle' });
  await page.waitForSelector('[data-page="upload"]', { state: 'visible' });
  await page.waitForTimeout(600);
  await page.screenshot({
    path: path.join(OUT_DIR, '04-upload.png'),
    fullPage: true,
  });
  console.log('  -> 04-upload.png saved.');

  // ---- 5. Preprocess --------------------------------------------------
  console.log('[5/7] Preprocess...');
  await page.goto(`${BASE}/ui/preprocess.html`, { waitUntil: 'networkidle' });
  await page.waitForSelector('[data-page="preprocess"]', { state: 'visible' });
  await page.waitForTimeout(600);
  await page.screenshot({
    path: path.join(OUT_DIR, '05-preprocess.png'),
    fullPage: true,
  });
  console.log('  -> 05-preprocess.png saved.');

  // ---- 6. Visualization -----------------------------------------------
  console.log('[6/7] Visualization...');
  await page.goto(`${BASE}/ui/visualization.html`, { waitUntil: 'networkidle' });
  await page.waitForSelector('[data-page="visualization"]', { state: 'visible' });
  await page.waitForTimeout(600);
  await page.screenshot({
    path: path.join(OUT_DIR, '06-visualization.png'),
    fullPage: true,
  });
  console.log('  -> 06-visualization.png saved.');

  // ---- 7. Prediction & Diagnosis --------------------------------------
  console.log('[7/7] Prediction & Diagnosis...');
  await page.goto(`${BASE}/ui/prediction.html`, { waitUntil: 'networkidle' });
  await page.waitForSelector('[data-page="analysis"]', { state: 'visible' });
  await page.waitForTimeout(800);
  await page.screenshot({
    path: path.join(OUT_DIR, '07-prediction.png'),
    fullPage: true,
  });
  console.log('  -> 07-prediction.png saved.');

  // ---- Done -----------------------------------------------------------
  await browser.close();
  console.log('\nAll 7 screenshots saved to docs/screenshots/empty/');
}

run().catch((err) => {
  console.error('Screenshot script failed:', err);
  process.exit(1);
});
