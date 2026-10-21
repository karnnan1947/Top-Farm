// Playwright helpers for driving the Odoo 20 web client and saving screenshots with their captions.
const { chromium } = require('playwright-core');
const fs = require('fs');
const path = require('path');

const BASE = process.env.TF_BASE || 'http://localhost:8021';
const DB = process.env.TF_DB || 'topfarm20_flock';
const CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const ROOT = path.resolve(__dirname, '..', '..');
const SHOTS = path.join(ROOT, 'screenshots');
const RESULTS = path.join(ROOT, 'test_scripts', 'results');
const W = 1600, H = 1000;
fs.mkdirSync(SHOTS, { recursive: true });
fs.mkdirSync(RESULTS, { recursive: true });

const IDS = () => JSON.parse(fs.readFileSync(path.join(RESULTS, 'ids.json'), 'utf8'));

let CREDS = null;

async function login(page) {
  await page.goto(`${BASE}/web/login?db=${DB}`);
  if (page.url().includes('/web/login')) {
    await page.fill('input[name="login"]', CREDS.user);
    await page.fill('input[name="password"]', CREDS.pwd);
    await page.click('button[type="submit"]');
  }
  await page.waitForSelector('.o_main_navbar', { timeout: 120000 });
  await settle(page);
}

async function start(user = 'admin', pwd = 'admin') {
  CREDS = { user, pwd };
  const browser = await chromium.launch({ executablePath: CHROME, headless: true });
  const context = await browser.newContext({ viewport: { width: W, height: H }, timezoneId: 'Asia/Colombo', locale: 'en-US' });
  context.setDefaultNavigationTimeout(240000);
  context.setDefaultTimeout(60000);
  const page = await context.newPage();
  page.on('pageerror', (e) => console.log('PAGE ERROR:', e.message));
  page.on('console', (m) => { if (m.type() === 'error') console.log('CONSOLE ERROR:', m.text().slice(0, 300)); });
  await login(page);
  return { browser, context, page };
}

// Odoo 20 sometimes expires the session of a headless run: log in again and reopen the page we were on
let LAST_URL = null;

async function expired(page) {
  return (await page.locator('.modal:visible:has-text("Session Expired")').count()) > 0;
}

async function recoverSession(page) {
  if (!(await expired(page))) return false;
  console.log('session expired: logging in again');
  await login(page);
  if (LAST_URL) {
    await page.goto(LAST_URL);
    await page.waitForSelector('.o_action_manager .o_action, .o_action_manager > div', { timeout: 120000 });
    await settle(page, 900);
  }
  return true;
}

async function settle(page, extra = 500) {
  try { await page.waitForLoadState('networkidle', { timeout: 2500 }); } catch (e) {}
  for (let i = 0; i < 80; i++) {
    const busy = await page.locator('.o_loading_indicator, .o_blockUI, .o-loading').count();
    if (!busy) break;
    await page.waitForTimeout(250);
  }
  await page.waitForTimeout(extra);
}

async function go(page, url) {
  LAST_URL = url.startsWith('http') ? url : `${BASE}${url}`;
  for (let attempt = 0; attempt < 3; attempt++) {
    await page.goto(LAST_URL);
    await page.waitForSelector('.o_action_manager .o_action, .o_action_manager > div', { timeout: 120000 });
    await settle(page, 900);
    if (!(await recoverSession(page))) return;
  }
}

// screenshot + caption registry (results/shots.json) used by the report generator
async function shot(page, name, caption, opts = {}) {
  if (opts.height || opts.width) await page.setViewportSize({ width: opts.width || W, height: opts.height || H });
  await settle(page, opts.wait || 700);
  if (await page.locator('.modal:visible:has-text("Session Expired")').count()) {
    throw new Error(`session expired before screenshot ${name}`);
  }
  await page.addStyleTag({ content: '*{caret-color:transparent !important}.o-tooltip,.popover:has(.o-tooltip){display:none !important}' }).catch(() => {});
  if (!opts.keepScroll) {   // top of the page and newest chatter messages first
    await page.evaluate(() => document.querySelectorAll('.o_content, .o_list_renderer, .o_pivot, .o-mail-Chatter, .o-mail-Form-chatter, .o-mail-Chatter-content')
      .forEach((e) => { e.scrollTop = 0; })).catch(() => {});
    await page.waitForTimeout(200);
  }
  if (opts.scrollTo) {
    await page.locator(opts.scrollTo).first().scrollIntoViewIfNeeded().catch(() => {});
    await page.waitForTimeout(300);
  }
  const file = path.join(SHOTS, name);
  await page.screenshot({ path: file, fullPage: false });
  if (opts.height || opts.width) await page.setViewportSize({ width: W, height: H });
  const registry = path.join(RESULTS, 'shots.json');
  const all = fs.existsSync(registry) ? JSON.parse(fs.readFileSync(registry, 'utf8')) : {};
  all[name] = caption;
  fs.writeFileSync(registry, JSON.stringify(all, null, 2));
  console.log('SHOT', name);
  return file;
}

function scope(page) {
  return page.locator('.modal:visible').count().then((n) => (n ? page.locator('.modal:visible').last() : page.locator('.o_action_manager')));
}

// click a visible button by its text, in the open dialog if any, else in the action. A click answered by
// "Session Expired" did not reach the server: log in again, reopen the page and click again.
async function click(page, text, opts = {}) {
  for (let attempt = 0; attempt < 3; attempt++) {
    const s = opts.scope ? page.locator(opts.scope) : await scope(page);
    let btn = s.locator('button:visible', { hasText: new RegExp(`^\\s*${text}\\s*$`) }).first();
    if (!(await btn.count())) btn = s.locator('button:visible', { hasText: text }).first();
    await btn.click();
    await settle(page, opts.wait || 1000);
    if (!(await recoverSession(page))) return;
  }
}

async function confirmDialog(page, text = 'Ok') {
  const modal = page.locator('.modal:visible').last();
  await modal.locator('button:visible', { hasText: new RegExp(`^\\s*${text}\\s*$`) }).first().click();
  await settle(page, 1200);
}

async function closeDialog(page) {
  const modal = page.locator('.modal:visible').last();
  await modal.locator('button.btn-close, button:has-text("Close"), button:has-text("Discard")').first().click();
  await settle(page);
}

async function save(page) {
  const b = page.locator('.o_form_button_save:visible');
  if (await b.count()) { await b.first().click(); await settle(page, 900); }
}

async function rpc(page, model, method, args = [], kwargs = {}) {
  return await page.evaluate(async ({ model, method, args, kwargs }) => {
    const r = await fetch('/web/dataset/call_kw', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ jsonrpc: '2.0', method: 'call', params: { model, method, args, kwargs } }),
    });
    const j = await r.json();
    if (j.error) throw new Error(JSON.stringify(j.error.data && j.error.data.message || j.error));
    return j.result;
  }, { model, method, args, kwargs });
}

// open any window action (list with a domain, pivot, grouped, ...) through the web client's action service
async function doAction(page, action, options = {}) {
  for (let attempt = 0; attempt < 3; attempt++) {
    await page.evaluate(async ({ action, options }) => {
      const env = odoo.__WOWL_DEBUG__.root.env;
      await env.services.action.doAction(action, options);
    }, { action, options });
    await settle(page, 1500);
    if (!(await recoverSession(page))) return;
  }
}

// open a record form inside an app (the navbar shows that app): load the app action, then the record
async function openForm(page, appUrl, model, id) {
  await go(page, appUrl);
  await doAction(page, { type: 'ir.actions.act_window', res_model: model, res_id: id, views: [[false, 'form']] });
}

// open every group of a grouped list view
async function expandGroups(page) {
  const headers = page.locator('.o_group_header');
  const count = await headers.count();
  for (let i = 0; i < count; i++) {
    const header = headers.nth(i);
    if (!((await header.getAttribute('class')) || '').includes('o_group_open')) {
      await header.click();
      await settle(page, 400);
    }
  }
}

// open a record through the action of its own app, so the navbar shows the right menu
const ACTIONS = {
  'stock.location': 'top_farm_core.action_top_farm_locations',
  'stock.lot': 'top_farm_core.action_farm_flock_lots',
  'farm.feed.log': 'top_farm_operations.action_farm_feed_log',
  'farm.egg.collection': 'top_farm_operations.action_farm_egg_collection',
  'farm.mortality.log': 'top_farm_mortality.action_farm_mortality_log',
  'stock.picking': 'stock.action_picking_tree_all',
  'purchase.order': 'purchase.purchase_form_action',
  'sale.order': 'sale.action_orders',
  'mrp.production': 'mrp.mrp_production_action',
  'account.move': 'account.action_move_journal_line',
  'product.template': 'stock.product_template_action_product',
  'product.category': 'product.product_category_action_form',
};
async function rec(page, model, id) {
  const act = ACTIONS[model];
  await go(page, act ? `/odoo/action-${act}/${id}` : `/odoo/${model}/${id}`);
}

module.exports = { BASE, SHOTS, RESULTS, IDS, start, settle, go, shot, click, confirmDialog, closeDialog, save, rpc, doAction, rec, expandGroups, openForm };
