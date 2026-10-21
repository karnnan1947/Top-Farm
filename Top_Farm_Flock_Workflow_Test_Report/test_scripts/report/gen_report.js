// Builds the Top Farm flock workflow test report (.docx) from the screenshots and the results of the test run.
// usage: NODE_PATH=<folder with docx> node gen_report.js
const fs = require('fs');
const path = require('path');
const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType, Table, TableRow, TableCell, WidthType,
  ShadingType, BorderStyle, ImageRun, Header, Footer, PageNumber, TableOfContents, LevelFormat,
} = require('docx');

const ROOT = path.resolve(__dirname, '..', '..');
const SHOTS = path.join(ROOT, 'screenshots');
const RESULTS = path.join(ROOT, 'test_scripts', 'results');
const OUT = path.join(ROOT, 'Top_Farm_Flock_Workflow_Test_Report.docx');
const read = (f) => JSON.parse(fs.readFileSync(path.join(RESULTS, f), 'utf8'));
const S = read('summary.json');
const CHECKS = read('checks.json');
const CAPTIONS = read('shots.json');
const IDS = read('ids.json');
const REUSE = read('reuse.json');

const GREEN = '2E7D32', GREY = '6B6B6B', AMBER = 'B26A00', RED = 'C62828', BLUE = '1565C0';
const W = 9746;                      // content width (DXA): A4 11906 - 2 x 1080
const IMG_W = 650;                   // px at 96 dpi = the full content width
const money = (n) => Number(n || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const int = (n) => Number(n || 0).toLocaleString('en-US', { maximumFractionDigits: 0 });
const num = (n, d = 2) => Number(n || 0).toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });
const ok = (a, b) => (Math.abs((a || 0) - (b || 0)) <= 0.01 ? 'PASS' : 'FAIL');

// ------------------------------------------------------------------ building blocks
function runs(text, opts = {}) {
  // **bold** and `code` inline markup
  const out = [];
  const re = /(\*\*[^*]+\*\*|`[^`]+`)/g;
  let last = 0, m;
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(new TextRun({ text: text.slice(last, m.index), ...opts }));
    const t = m[0];
    if (t.startsWith('**')) out.push(new TextRun({ text: t.slice(2, -2), bold: true, ...opts }));
    else out.push(new TextRun({ text: t.slice(1, -1), font: 'Consolas', size: (opts.size || 21) - 2, ...opts }));
    last = m.index + t.length;
  }
  if (last < text.length) out.push(new TextRun({ text: text.slice(last), ...opts }));
  return out;
}
const P = (text, opts = {}) => new Paragraph({ children: runs(text, opts.run || {}), spacing: { after: 120, line: 276 }, ...opts.para });
const H1 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun(t)], pageBreakBefore: true });
const H2 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun(t)], keepNext: true });
const H3 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_3, children: [new TextRun(t)], keepNext: true, keepLines: true });
const bullets = (items) => items.map((t) => new Paragraph({ children: runs(t), numbering: { reference: 'bullets', level: 0 }, spacing: { after: 60, line: 264 } }));
let numInstance = 0;
const numbered = (items) => { numInstance += 1; return items.map((t) => new Paragraph({ children: runs(t), numbering: { reference: 'steps', level: 0, instance: numInstance }, spacing: { after: 60, line: 264 } })); };
const spacer = () => new Paragraph({ children: [], spacing: { after: 60 } });
const pretty = (v) => (typeof v === 'object' && v !== null ? JSON.stringify(v) : String(v))
  .replace(/["']/g, '').replace(/[{}]/g, '').replace(/^\[|\]$/g, '').replace(/\[/g, '(').replace(/\]/g, ')').replace(/,(?=\S)/g, ', ').slice(0, 160);

const STATUS_COLORS = { PASS: GREEN, FAIL: RED, Fixed: GREEN, Simulation: AMBER, Note: BLUE, Harness: GREY };
const border = { style: BorderStyle.SINGLE, size: 4, color: 'C8D3C8' };
const borders = { top: border, bottom: border, left: border, right: border };

function cell(text, width, opts = {}) {
  const color = opts.status && STATUS_COLORS[text] ? STATUS_COLORS[text] : undefined;
  return new TableCell({
    width: { size: width, type: WidthType.DXA },
    borders,
    shading: opts.fill ? { type: ShadingType.CLEAR, fill: opts.fill, color: 'auto' } : undefined,
    margins: { top: 50, bottom: 50, left: 90, right: 90 },
    children: String(text ?? '').split('\n').map((ln) => new Paragraph({
      alignment: opts.align || AlignmentType.LEFT,
      spacing: { after: 0, line: 252 },
      children: runs(ln, { size: opts.size || 18, bold: opts.bold || !!color, color: opts.header ? 'FFFFFF' : color }),
    })),
  });
}

function table(headers, rows, widths, opts = {}) {
  const total = widths.reduce((a, b) => a + b, 0);
  const statusCols = opts.statusCols || [];
  const rightCols = opts.rightCols || [];
  return new Table({
    width: { size: total, type: WidthType.DXA },
    columnWidths: widths,
    rows: [
      new TableRow({ tableHeader: true, children: headers.map((h, i) => cell(h, widths[i], { header: true, bold: true, fill: GREEN, size: opts.size })) }),
      ...rows.map((r, ri) => new TableRow({
        cantSplit: true,
        children: r.map((c, i) => cell(c, widths[i], {
          status: statusCols.includes(i), size: opts.size,
          align: rightCols.includes(i) ? AlignmentType.RIGHT : (statusCols.includes(i) ? AlignmentType.CENTER : AlignmentType.LEFT),
          fill: (opts.boldRows || []).includes(ri) ? 'E8F0E8' : (ri % 2 ? 'F3F7F3' : undefined),
          bold: (opts.boldRows || []).includes(ri),
        })),
      })),
    ],
  });
}

// ------------------------------------------------------------------ figures
let figNo = 0;
const used = new Set();
function pngSize(file) {
  const b = fs.readFileSync(file);
  return { w: b.readUInt32BE(16), h: b.readUInt32BE(20), data: b };
}
function shortTitle(caption) {
  // the caption up to its first colon or full stop; a long first clause is cut at a comma or a word
  const cut = caption.search(/[:.](\s|$)/);
  let t = cut > 0 ? caption.slice(0, cut) : caption;
  if (t.length <= 75) return t;
  const comma = t.lastIndexOf(',', 75);
  if (comma > 30) return t.slice(0, comma);
  return t.slice(0, t.lastIndexOf(' ', 72)) + ' ...';
}
function fig(file, extra = []) {
  const caption = CAPTIONS[file];
  if (!caption) throw new Error(`no caption for ${file}`);
  figNo += 1;
  used.add(file);
  const { w, h, data } = pngSize(path.join(SHOTS, file));
  const width = IMG_W, height = Math.round(h * IMG_W / w);
  return [
    H3(`Figure ${figNo}: ${shortTitle(caption)}`),
    new Paragraph({
      alignment: AlignmentType.CENTER, keepNext: true, spacing: { after: 40 },
      children: [new ImageRun({ type: 'png', data, transformation: { width, height },
        altText: { title: `Figure ${figNo}`, description: caption, name: file } })],
    }),
    new Paragraph({ alignment: AlignmentType.LEFT, spacing: { after: 120 }, keepNext: extra.length > 0,
      children: [new TextRun({ text: `Figure ${figNo}. ${caption}`, italics: true, size: 18, color: GREY })] }),
    ...extra.map((t) => P(t)),
    spacer(),
  ];
}
const figs = (prefix) => Object.keys(CAPTIONS).filter((f) => f.startsWith(prefix)).sort().flatMap((f) => fig(f));

// ------------------------------------------------------------------ results
const phaseOf = (tc) => tc.slice(3, 5);
const PHASES = [
  ['00', 'Configuration and master data'], ['01', 'Purchase into the main warehouse'],
  ['02', 'Dispatch to brooding, automated flock lot (Approach B)'], ['03', 'Dispatch with manual flock lot (Approach A)'],
  ['04', 'Brooding: feed, vaccines, heating, mortality'], ['06', 'Cage allocation and pre-laying rearing'],
  ['07', 'Point of lay: 50 % hen-day transition'], ['08', 'Laying: staged feed and graded egg MOs'],
  ['09', 'Sales: eggs and spent hens'], ['10', 'Independent verification (analytics, investment, P&L, ledger)'],
  ['11', 'Cage reuse by the next flock'],
];
const passCount = CHECKS.filter((c) => c.status === 'PASS').length;
const failCount = CHECKS.length - passCount;
const NSHOTS = Object.keys(CAPTIONS).length;
const inv = S.investment_total;
const pnl = Object.fromEntries(S.pnl.map((r) => [r.line, r]));

const children = [];
const add = (...items) => items.flat().forEach((i) => children.push(i));

// ------------------------------------------------------------------ cover
add(
  new Paragraph({ spacing: { before: 2400, after: 200 }, children: [new TextRun({ text: 'Top Farm ERP', size: 32, color: GREY })] }),
  new Paragraph({ spacing: { after: 200 }, children: [new TextRun({ text: 'Flock Lifecycle Workflow', size: 56, bold: true, color: GREEN })] }),
  new Paragraph({ spacing: { after: 600 }, children: [new TextRun({ text: 'Functional Test Report with Analytic Accounting Evidence', size: 32, color: '263238' })] }),
  table(['Item', 'Value'], [
    ['System', 'Odoo 20.0 Enterprise'],
    ['Modules', 'top_farm_core, top_farm_operations, top_farm_mortality, top_farm_dashboard 20.0.2.0.0 (revised flock-lot design)'],
    ['Test database', '`topfarm20_flock` (fresh database, company Top Farm, currency LKR)'],
    ['Test date', '20 October 2026'],
    ['Flock followed', 'IHL-20-10-2026 (Ihalapannawa Estate), from day-old chicks to spent hens'],
    ['Result', `${passCount} of ${CHECKS.length} checks passed, ${failCount} failed; ${NSHOTS} screenshots`],
  ], [2400, W - 2400], { size: 19 }),
);

add(H1('Contents'), new TableOfContents('Contents', { hyperlink: true, headingStyleRange: '1-2' }));

// ------------------------------------------------------------------ 1. summary
add(H1('1. Summary'),
  P('This report tests the complete life of a layer flock in the revised Top Farm design, where the farm infrastructure (estates, brooding nurseries, sheds, cages) is permanent and the **flock batch is a lot** that moves through it. Every step was performed in a fresh Odoo 20 database: master data and the daily records were entered by scripts, and the key actions (validating receipts and transfers, confirming feed logs, submitting and approving mortality, allocating the flock to the cages, producing eggs, starting the Laying Phase, confirming sales) were clicked in the browser, with a screenshot before and after.'),
  H2('1.1 Workflow tested'),
  ...numbered([
    'Products set up for the flock: the bird product (lot-tracked, Is Live Farm Bird), feed and vaccines with their Farm Input Type, graded egg products.',
    'Purchase of 10,000 day-old chicks, received into the main warehouse under the hatchery batch number **20_10_2026**; purchase of feed and medicine.',
    'Transfer of 5,000 chicks to the Ihalapannawa brooding nursery: a **new flock batch number IHL-20-10-2026** is created on validation (Approach B), with its own analytic account. The other 5,000 go to Baddegama with a batch number typed by the clerk (Approach A).',
    'Brooding (weeks 0-4): starter feed, vaccines, electrolytes and LPG heating given to the flock, brooding mortality with the 2 % manager approval, and the **brooding-stage expenses of the batch in analytic accounting**.',
    'Split of the flock into 5 cages with the Brooding-to-Cage wizard; the flock moves to Pre-Laying.',
    'Pre-laying rearing in the cages: grower feed and vitamins expensed directly, debeaking labour, cage mortality; analytic items carry the flock **and** the cage.',
    'First eggs and the 50 % rolling hen-day alert; the Farm Manager starts the Laying Phase and the pre-laying investment is locked.',
    'Laying: feed staged per cage, egg collections, graded manufacturing orders consuming the feed, egg lots linked to the flock, laying analytics.',
    'Sale of the eggs and of the spent hens, invoices tagged to the flock, flock marked Spent; lifetime P&L and ledger reconciled.',
    'Reuse of the permanent cages: the next chick purchase becomes a new flock in the same brooding nursery and the same 5 cages; the cage analytic accounts keep both flocks apart.',
  ]),
  H2('1.2 Results by step'),
  table(['Step', 'Checks', 'Passed', 'Result'],
    PHASES.map(([p, label]) => {
      const cs = CHECKS.filter((c) => phaseOf(c.tc) === p);
      const pass = cs.filter((c) => c.status === 'PASS').length;
      return [label, String(cs.length), String(pass), pass === cs.length ? 'PASS' : 'FAIL'];
    }), [5600, 1300, 1300, W - 8200], { statusCols: [3], rightCols: [1, 2] }),
  P(`All ${CHECKS.length} checks are listed in section 14. Section 15 records the defects found and fixed during this test.`),
  H2('1.3 Key figures of flock IHL-20-10-2026'),
  table(['Figure', 'Value'], [
    ['Birds placed / at point of lay / sold as spent hens', `5,000 / ${int(inv.birds)} / ${int(IDS.hens_sold)}`],
    ['Pre-laying investment (locked at point of lay)', `LKR ${money(inv.total)} = LKR ${money(inv.per_bird)} per bird (target LKR ${money(inv.target)} - ${money(inv.target_max)})`],
    ['Brooding-stage expenses (weeks 0-4)', `LKR ${money(S.brooding.reduce((a, r) => a + r.actual, 0))}`],
    ['Egg revenue / spent hen revenue', `LKR ${money(pnl['Egg revenue'].actual)} / LKR ${money(pnl['Spent hen revenue'].actual)}`],
    ['Total direct cost / gross operating profit', `LKR ${money(pnl['Total direct cost'].actual)} / LKR ${money(pnl['Gross operating profit'].actual)}`],
  ], [4200, W - 4200]),
  H2('1.4 Simulations (read before the figures)'),
  ...bullets([
    '**Time:** all transactions are posted on the test day (20 October 2026). To reach the Laying Phase, the flock\'s chick arrival date was moved back 18 weeks (16 June 2026) and its cage allocation 14 weeks, and the first egg collections were dated 13-19 October. The flock ages, the 17-week minimum and the rolling hen-day therefore behave as in real life; the brooding and rearing records themselves carry the test date.',
    '**End of cycle:** the spent hens are sold right after the first laying day instead of after 70-75 weeks, so that the flock\'s lifetime P&L can be closed within the test.',
    '**Quantities** are reduced to one or two feed logs per stage; the amounts are realistic per bird (LKR 150 chick, LKR 120-140 per kg feed).',
  ]),
);

// ------------------------------------------------------------------ 2. environment
add(H1('2. Test environment and method'),
  table(['Item', 'Value'], [
    ['Odoo', '20.0 Enterprise, Python 3.12, PostgreSQL 16, Windows 11'],
    ['Apps installed', 'Top Farm (4 modules), Inventory, Purchase, Sales, Manufacturing, Accounting'],
    ['Company', 'Top Farm, currency LKR, time zone Asia/Colombo'],
    ['Users', 'Farm Manager (Admin): Farm Manager and Mortality Manager roles; Farm Operator: Farm Operator and Mortality Operator roles. The operator records the daily feed, mortality and egg logs and submits the brooding mortality in the browser; the manager allocates, approves and starts the Laying Phase.'],
    ['Valuation', 'All farm product categories in automated (perpetual) valuation; consumption, mortality and production locations carry their expense / clearing accounts'],
    ['Analytic plans', 'Flock Batches (one account per flock, created automatically) and Farm Cages (one account per cage)'],
  ], [2400, W - 2400]),
  H2('2.1 How the evidence was produced'),
  ...bullets([
    'Data phases (`test_scripts/data/p*.py`) run in `odoo-bin shell` as the Farm Operator or the Farm Manager and record their checks in `results/checks.json`.',
    'Browser phases (`test_scripts/browser/s*.js`, Playwright + Chrome, 1600 px) click the business buttons and save every screenshot with its caption in `results/shots.json`.',
    'Phase p10 recomputes every expected amount from the source documents (quantity x purchase price, birds x standard cost) and compares it with the analytic items, the reports and the general ledger.',
    'The whole run (`run_all.sh`) was executed once, in order, on a freshly installed database; the screenshots of this report all come from that run.',
  ]),
);

// ------------------------------------------------------------------ 3. configuration
add(H1('3. Configuration and products for the flock'),
  P('The Top Farm settings choose the flock lot generation (Approach B, automated, from the chick arrival date), create one analytic account per flock, and set the laying benchmark (50 % rolling 7-day hen-day from 17 weeks, manager confirmation). The infrastructure is permanent: two estates with their estate codes, a brooding nursery each, a laying shed with 5 cages (each with its own cage analytic account) at Ihalapannawa, and a battery row at Baddegama.'),
  table(['Product', 'Type', 'Tracking', 'Cost (LKR)', 'Used for'], [
    ['Layer Bird - Brown (Hy-Line)', 'Live Farm Bird', 'Lots (hatchery, then flock)', '150.00', 'Chicks to spent hens'],
    ['Starter Crumbs (Weeks 0-4)', 'Feed', '-', '140.00 / kg', 'Brooding'],
    ['Grower Mash (Weeks 5-18)', 'Feed', '-', '130.00 / kg', 'Rearing in cages'],
    ['Layer Mash (Week 19+)', 'Feed', '-', '120.00 / kg', 'Laying (egg MO component)'],
    ["Marek's Vaccine (dose)", 'Medication / Vaccine', '-', '58.00', 'Brooding'],
    ['Newcastle ND-IB Vaccine (dose)', 'Medication / Vaccine', '-', '12.00', 'Brooding'],
    ['Electrolyte & Vitamin Mix (L)', 'Medication / Vaccine', '-', '900.00 / L', 'Brooding and rearing'],
    ['Egg - Large / Medium / Jumbo / Damaged', 'Graded eggs', 'Lots (daily flock egg lot)', 'from production', 'Sold at 45 / 40 / 50 / 20'],
  ], [2900, 1500, 1900, 1300, W - 7600], { size: 17 }),
  ...figs('01'),
);

// ------------------------------------------------------------------ 4. purchase
add(H1('4. Purchase into the main warehouse with the hatchery batch number'),
  P('The chicks are bought from the hatchery and received into the main warehouse (WH/Stock). The hatchery batch number **20_10_2026** is entered on the receipt line, so the chicks are stored under that lot; validating the receipt stamps the lot with the Chick Arrival Date. The hatchery lot is **not** a flock: the flock batch number is created when the chicks leave for an estate.'),
  table(['PO', 'Vendor', 'Product', 'Qty', 'Unit', 'Price', 'Subtotal'],
    S.purchases.map((r) => [r.po, r.vendor, r.product, int(r.qty), r.uom, money(r.price), money(r.subtotal)]),
    [900, 2000, 2700, 900, 700, 1100, W - 8300], { rightCols: [3, 5, 6], size: 16 }),
  ...figs('02'),
);

// ------------------------------------------------------------------ 5. dispatch
add(H1('5. Transfer to the brooding nursery: a new flock batch number'),
  P('The 5,000 chicks for Ihalapannawa are transferred from WH/Stock to **Brooding-01**. Odoo moves a lot unchanged, so on validation the chicks arrive under the hatchery lot and are immediately re-labelled under the flock lot through the virtual location *Flock Lot Conversion*: out under 20_10_2026, back in under the new flock lot, at the same value. The flock lot is named **[Estate Code]-[Chick Arrival Date] = IHL-20-10-2026**, gets the Brooding stage and its own analytic account in the Flock Batches plan.'),
  table(['Flock lot', 'Estate', 'Lot creation', 'From hatchery lot', 'Birds placed', 'Chick cost (LKR)', 'Analytic account', 'Stage at end of test'],
    S.flocks.map((f) => [f.flock, f.estate, f.mode, f.source, int(f.placed), money(f.chick_cost), f.account, f.stage]),
    [1300, 1300, 1500, 1050, 900, 1150, 1450, W - 8650], { rightCols: [4, 5], size: 16 }),
  P('The re-labelling posts no journal entry and leaves the stock value of the birds unchanged (checks TC-10-02 and TC-10-03).'),
  ...figs('03'),
  H2('5.1 Approach A: the clerk types the flock batch number'),
  P('With the Flock Lot Generation Mode set to manual entry, a dispatch to a brooding nursery cannot be validated until the clerk enters the flock lot in the Flock Lot column of the transfer line. The Baddegama chicks were dispatched this way as **BDG-20-10-2026**; the lot was completed on validation (Flock Batch, estate, arrival date, analytic account) exactly like a generated one.'),
  ...figs('04'),
);

// ------------------------------------------------------------------ 6. brooding
const broodTotal = S.brooding.reduce((a, r) => a + r.actual, 0);
add(H1('6. Brooding stage: feed, vaccines, heating and mortality'),
  P('During weeks 0-4 the chicks stay under heat in Brooding-01. The Farm Operator logs the feed and medication **on the brooding nursery** (no cage); the flock is filled in automatically. Brooding feed and medication are a direct expense of the flock and are consumed at once. The LPG heating bill is charged to the flock analytic account. Two brooding logs were recorded: FEED/2026/00001 (shown being confirmed) and FEED/2026/00002 (confirmed by the Farm Operator). Brooding mortality is checked against the 2 % cumulative daily threshold of the flock in the nursery: the operator submits, the manager approves above the threshold.'),
  H2('6.1 Brooding-stage expenses of the batch (analytic accounting)'),
  P('Every brooding cost is an analytic item on the flock account **IHL-20-10-2026** only (Farm Cages column empty). Expected amounts are recomputed from the logs and bills:'),
  table(['Expense', 'Quantity', 'Unit cost', 'Expected (LKR)', 'Analytic actual (LKR)', 'Accounts', 'Result'],
    [...S.brooding.map((r) => [r.item, int(r.qty), money(r.unit_cost), money(r.expected), money(r.actual), r.accounts, ok(r.expected, r.actual)]),
      ['Total brooding stage', '', '', money(S.brooding.reduce((a, r) => a + r.expected, 0)), money(broodTotal), '', ok(S.brooding.reduce((a, r) => a + r.expected, 0), broodTotal)]],
    [2700, 900, 1000, 1300, 1500, 1200, W - 8600], { rightCols: [1, 2, 3, 4], statusCols: [6], boldRows: [S.brooding.length], size: 16 }),
  ...figs('05'),
);

// ------------------------------------------------------------------ 7. allocation
add(H1('7. Splitting the flock into cages (pre-laying)'),
  P('At the end of brooding (about week 4 in production; on the test day here) the Farm Manager opens the **Brooding-to-Cage Allocation** wizard from the nursery: it detects the flock and its 4,890 surviving birds and lists the cages of the estate with their occupancy. Split Equally gives 978 birds to each of the 5 cages. One validated transfer moves the birds, **keeping the flock lot IHL-20-10-2026**, and the flock advances to Rearing / Pre-Laying.'),
  ...figs('06'),
);

// ------------------------------------------------------------------ 8. rearing
add(H1('8. Pre-laying rearing in the cages'),
  P('From now on the daily logs are per cage. Rearing feed and medication are still a **direct expense** of the flock (they build the pre-laying investment), but each cost lands on **one analytic line holding both the flock account and the cage account**, so the cost is reported per flock and per cage without being counted twice.'),
  H2('8.1 Rearing costs per cage (analytic accounting)'),
  table(['Cage', 'Grower Mash 100 kg', 'Vitamins 1 L', 'Mortality', 'Expected (LKR)', 'Analytic actual (LKR)', 'Result'],
    S.rearing.map((r) => [r.cage, money(r.grower), money(r.vitamins), money(r.mortality), money(r.expected), money(r.actual), ok(r.expected, r.actual)]),
    [1300, 1500, 1200, 1100, 1500, 1700, W - 8300], { rightCols: [1, 2, 3, 4, 5], statusCols: [6], size: 17 }),
  P('The debeaking labour bill (LKR 75,000) is charged to the flock account only, like the LPG bill.'),
  H2('8.2 Pre-Laying Flock Investment'),
  P(`The investment report accumulates, per flock, the chicks placed and every feed, medication and direct cost tagged to the flock until the Laying Phase starts; laying feed and mortality scraps are excluded (the chick cost already counts every bird placed). Locked on ${inv.locked_on} over ${int(inv.birds)} birds at point of lay:`),
  table(['Cost component', 'Expected (LKR)', 'Report (LKR)', 'Per bird (LKR)', 'Result'],
    [...S.investment.map((r) => [r.component, money(r.expected), money(r.actual), money(r.per_bird), ok(r.expected, r.actual)]),
      ['TOTAL ACCUMULATED INVESTMENT', money(inv.total), money(S.investment.reduce((a, r) => a + r.actual, 0)), money(inv.per_bird), ok(inv.total, S.investment.reduce((a, r) => a + r.actual, 0))]],
    [3400, 1600, 1600, 1600, W - 8200], { rightCols: [1, 2, 3], statusCols: [4], boldRows: [S.investment.length], size: 17 }),
  P(`Target benchmark LKR ${money(inv.target)} - ${money(inv.target_max)} per bird; remaining pre-laying budget at lock: LKR ${money(inv.remaining)} per bird (the test flock only received a few sample feed logs: two brooding logs and one rearing log per cage).`),
  ...figs('07'),
);

// ------------------------------------------------------------------ 9. point of lay
add(H1('9. Point of lay: the 50 % hen-day transition'),
  P('The Laying Phase is never forced by the calendar. Each egg collection of a rearing flock older than 17 weeks recomputes its **rolling 7-day hen-day rate** (eggs over live bird days of its cages; a cage-day without a harvest counts its birds with no eggs). When the rate reaches 50 % the Farm Managers get a chatter alert and a To-Do; in manual mode a manager confirms with Start Laying Phase, which locks the pre-laying investment.'),
  table(['Date', 'Eggs', 'Bird snapshot', 'Daily hen-day %', 'Feed in MOs (kg)', 'Rolling 7-day %'],
    S.hen_day.map((r) => [r.date, int(r.eggs), int(r.birds), num(r.hen_day), num(r.feed_kg), num(r.rolling)]),
    [1600, 1300, 1600, 1700, 1700, W - 7900], { rightCols: [1, 2, 3, 4, 5], size: 17 }),
  P('13-19 October: pre-laying harvests (no staged feed, no feed component in the MOs). The rolling column is the rate at the end of each day, all cages harvested. On 19 October the alert was raised as soon as the Cage A-01 harvest was produced, at 50.6 % (the other four cages counted with no eggs yet); with all five cages the day ends at 59.99 %. 20 October: first laying day, the feed is consumed by the egg MOs.'),
  ...figs('08'),
);

// ------------------------------------------------------------------ 10. laying
add(H1('10. Laying: staged feed, egg collection and manufacturing orders'),
  P('Once the flock is Laying, the day\'s cage feed is **staged** (no stock move) until the egg collection of that cage and day. Producing the collection creates one manufacturing order per egg grade; the staged feed becomes their component in proportion to the eggs of each grade, and the eggs are received into the Egg Cold Store under the daily flock egg lot **LOT-EGG-IHL-20-10-2026-<date>**, linked to its parent flock.'),
  H2('10.1 Laying feed per cage (analytic accounting)'),
  table(['Cage', 'Layer Mash (kg)', 'Expected (LKR)', 'Analytic actual (LKR)', 'Accounts', 'Result'],
    S.laying.map((r) => [r.cage, num(r.kg), money(r.expected), money(r.actual), 'Flock + cage', ok(r.expected, r.actual)]),
    [1500, 1500, 1700, 1900, 1700, W - 8300], { rightCols: [1, 2, 3], statusCols: [5], size: 17 }),
  H2('10.2 Egg balance'),
  table(['Grade', 'Collected', 'Produced by MOs', 'Sold', 'On hand', 'Result'],
    S.eggs.map((r) => [r.grade, int(r.collected), int(r.mo_produced), int(r.sold), int(r.on_hand),
      r.collected === r.mo_produced && r.mo_produced === r.sold + r.on_hand ? 'PASS' : 'FAIL']),
    [1600, 1500, 1800, 1400, 1400, W - 7700], { rightCols: [1, 2, 3, 4], statusCols: [5], size: 17 }),
  ...figs('09'),
);

// ------------------------------------------------------------------ 11. sales
add(H1('11. Sales: eggs and spent hens'),
  P('The eggs are sold from the Egg Cold Store; the delivery takes the oldest flock egg lots first. When the delivery is validated, each sale line receives the analytic distribution of the flock(s) of the delivered lots (here 100 % IHL-20-10-2026), and the invoice lines inherit it. At the end of the cycle (simulated) the spent hens are sold from the cages under the flock lot, the flock is marked Spent / Depleted and the permanent cages are free for the next flock.'),
  ...figs('10'),
);

// ------------------------------------------------------------------ 12. reports
add(H1('12. Flock reports and financial reconciliation'),
  H2('12.1 Flock lifetime P&L'),
  table(['Line', 'Expected (LKR)', 'Flock Lifetime Profitability (LKR)', 'Result'],
    S.pnl.map((r) => [r.line, money(r.expected), money(r.actual), ok(r.expected, r.actual)]),
    [3600, 2000, 2800, W - 8400], { rightCols: [1, 2], statusCols: [3], boldRows: [S.pnl.length - 2, S.pnl.length - 1] }),
  P('Bird cost of sales is the standard cost of the spent hens delivered; with the mortality loss it adds up to the cost of every chick that left the flock.'),
  H2('12.2 General ledger'),
  table(['Account', 'What it holds', 'Expected (LKR)', 'Balance (LKR)', 'Result'],
    S.gl.map((r) => [r.account, r.what, money(r.expected), money(r.actual), ok(r.expected, r.actual)]),
    [2600, 3200, 1500, 1500, W - 8800], { rightCols: [2, 3], statusCols: [4], size: 17 }),
  P('Feed and medication expenses include the Baddegama flock (150 kg starter, 5,000 Marek\'s doses). The laying feed is not an expense: it passes through the production clearing account into the egg stock.'),
  H2('12.3 Dashboard figures (13-20 October, flock IHL-20-10-2026)'),
  table(['KPI', 'Value'], [
    ['Eggs harvested', int(S.dashboard.eggs)], ['Hen-day rate', `${num(S.dashboard.hen_day)} %`],
    ['FCR (kg feed per dozen eggs)', num(S.dashboard.fcr, 3)], ['Feed consumed by egg MOs (kg)', num(S.dashboard.feed_kg)],
    ['Dead birds / mortality', `${int(S.dashboard.dead)} / ${num(S.dashboard.mortality, 3)} %`],
  ], [4200, W - 4200]),
  ...figs('11'),
);

// ------------------------------------------------------------------ 13. cage reuse
add(H1('13. Reusing the cages for the next flock'),
  P('Cages and brooding nurseries are permanent: after a flock is depleted and the cages are cleaned, the next flock moves into the same cages. Each cage keeps its **cage analytic account for ever** (Farm Cages plan), while every flock gets a **new flock analytic account** (Flock Batches plan). Every cost line carries both, so a cage account accumulates the history of all its flocks, and the flock account on each line keeps them apart.'),
  ...bullets([
    '**Per flock:** filter on the flock account: only that flock, whatever cages it used.',
    '**Per cage, all flocks:** filter on the cage account: the lifetime history of the cage.',
    '**One cage for one flock:** both accounts are on the same line; a pivot with the cages in rows and the flocks in columns splits them exactly.',
    'The allocation wizard only lets a flock into a cage that holds no other flock, so a cage never mixes two flocks at the same time.',
  ]),
  P(`In this test a second purchase of 4,000 chicks was dispatched to Ihalapannawa Brooding-01 and allocated into Cages A-01 to A-05 after the spent hens of ${REUSE.first} had left. Analytic items per cage, by flock (LKR, negative = net cost):`),
  table(['Cage', 'Cage account', `${REUSE.first} (before)`, `${REUSE.first} (after)`, `${REUSE.second}`, 'Expected', 'Result'],
    REUSE.rows.map((r) => [r.cage, r.cage_account, money(r.first_flock_before), money(r.first_flock), money(r.second_flock),
      money(r.second_expected), ok(r.first_flock, r.first_flock_before) === 'PASS' && ok(r.second_flock, r.second_expected) === 'PASS' ? 'PASS' : 'FAIL']),
    [1100, 1700, 1500, 1500, 1500, 1300, W - 8600], { rightCols: [2, 3, 4, 5], statusCols: [6], size: 16 }),
  P(`The first flock's figures per cage (its rearing and laying costs, mortality and the spent hens it sold) did not change; the next flock's grower feed, vitamins and mortality land on the same cage accounts under its own account ${REUSE.second_account}. In this same-day test the next flock is named ${REUSE.second}, because ${REUSE.first} already holds the estate-date name; in production the next flock arrives weeks later and carries its own date.`),
  ...figs('12'),
);

// ------------------------------------------------------------------ 14. checks
add(H1('14. All checks'),
  P(`${passCount} passed, ${failCount} failed. Negative cases (refused validations) ran in savepoints or in the browser and left no data.`),
  table(['Test case', 'Check', 'Expected', 'Actual', 'Result'],
    CHECKS.map((c) => [c.tc, c.label, pretty(c.expected), pretty(c.actual), c.status]),
    [1050, 3500, 2300, 2300, W - 9150], { statusCols: [4], size: 15 }),
);

// ------------------------------------------------------------------ 15. findings
add(H1('15. Findings, fixes and notes'),
  table(['ID', 'Type', 'Finding', 'Resolution'], [
    ['F-1', 'Fixed', 'The analytic cost of birds leaving in one move from several cages (spent hen delivery) was not charged to the flock: the hook only looked at the move\'s source location (WH/Stock).', 'The hook now weighs each delivered line on its flock and cage accounts (5 analytic lines for the 5 cages). Checked by TC-10-09.'],
    ['F-2', 'Fixed', 'The flock lifetime P&L counted egg revenue only, while the cost of the spent hens sold was a flock cost.', 'Spent hen sales are now flock revenue (Spent Hen Revenue) and the bird cost of sales has its own column. TC-10-15.'],
    ['F-3', 'Fixed', 'In Approach B the dispatch transfer did not show which flock lot was generated.', 'The generated flock lot is written on the transfer line (Flock Lot column, figure of section 5).'],
    ['F-4', 'Fixed', 'Unharvested laying feed expensed on the day of the transition counted in the locked pre-laying investment.', 'Laying-phase feed is excluded from the investment whatever its date. TC-10-12.'],
    ['F-5', 'Fixed', 'The Top Farm smart buttons used Font Awesome icon names, which Odoo 20 renders as a stray "-" next to the values.', 'Replaced by Odoo 20 icons (heart for Live Birds, grid for Cages, payments for Invested / Bird, ...).'],
    ['F-6', 'Fixed', 'The Approach A refusal message showed a fixed example lot (IHL-19-10-2026), also for other estates.', 'The example is built from the destination estate code and the arrival date (e.g. BDG-20-10-2026). TC-03-03.'],
    ['F-7', 'Fixed', 'A generated flock lot name already used by a flock that had left brooding would have put new chicks into that old flock.', 'Only a flock still in Brooding is topped up; otherwise the new flock gets a suffix (IHL-20-10-2026-2). TC-11-02.'],
    ['F-8', 'Fixed', 'Spent hen revenue was reported on the flock but not on the cages, while the cost of the hens was split per cage.', 'Spent hen revenue is attributed to the cage the hens were delivered from (P&L by cage, revenue allocation).'],
    ['N-1', 'Simulation', 'Flock age and first egg days simulated; spent hens sold right after the first laying day.', 'See section 1.4.'],
    ['N-2', 'Note', 'Approach A in the plan ("standard Odoo, use_create_lots") cannot re-label a lot during an internal transfer: Odoo moves a lot unchanged.', 'The clerk types the flock lot in the Flock Lot column; the system re-labels the chicks on validation (section 5.1).'],
    ['N-3', 'Note', 'The plan\'s GL codes 600000 / 610000 / 630000 collide with the generic chart; this test used 5101xx-5105xx.', 'Agree the final chart of accounts with Top Farm before go-live.'],
    ['N-4', 'Harness', 'Odoo 20 occasionally answered the headless browser with "Session Expired".', 'The browser scripts log in again and repeat the step; no business data is affected.'],
    ['N-5', 'Note', 'Totals of feed logs and quantity columns that mix vaccine doses and litres of electrolytes add different units.', 'Read them per product; the costs are always correct.'],
    ['N-6', 'Note', 'The report was reviewed by independent reviewers (screenshots against captions, figures against the database by read-only SQL, text against the request) before release.', 'Their findings were corrected in this version.'],
  ], [600, 1100, 4300, W - 6000], { statusCols: [1], size: 16 }),
);

// ------------------------------------------------------------------ appendix
add(H1('Appendix A: How to reproduce'),
  ...numbered([
    'Create a database on Odoo 20.0 Enterprise with `Top-Farm/top_farm_addons` in the addons path and install top_farm_dashboard, purchase_stock, sale_management and accountant (database `topfarm20_flock`).',
    'Serve it on port 8021: `test_scripts/run.sh serve`.',
    'Point `TF_NODE_MODULES` to a folder holding the npm packages docx and playwright-core (Chrome must be installed), then run `test_scripts/run_all.sh`: it runs the data phases (p00-p10) and the browser phases (s00-s10) in order.',
    'Build this document: `node test_scripts/report/gen_report.js`, then `python test_scripts/report/word_export.py Top_Farm_Flock_Workflow_Test_Report.docx` to refresh the table of contents and export the PDF.',
  ]),
  P(`Files: \`screenshots/\` (${NSHOTS} PNG files, numbered by section), \`test_scripts/\` (data, browser and report scripts, \`results/\` with the checks, captions and verification tables) and the PDF version of this document.`),
);

const missing = Object.keys(CAPTIONS).filter((f) => !used.has(f));
if (missing.length) console.log('WARNING screenshots not in the report:', missing.join(', '));

const doc = new Document({
  creator: 'Top Farm ERP Team', title: 'Top Farm Flock Lifecycle Workflow Test Report',
  description: 'Purchase to spent hens of a layer flock in the revised flock-lot design, with analytic accounting evidence',
  styles: {
    default: { document: { run: { font: 'Calibri', size: 21 } } },
    paragraphStyles: [
      { id: 'Heading1', name: 'Heading 1', basedOn: 'Normal', next: 'Normal', quickFormat: true,
        run: { size: 34, bold: true, color: GREEN }, paragraph: { spacing: { before: 120, after: 160 }, outlineLevel: 0 } },
      { id: 'Heading2', name: 'Heading 2', basedOn: 'Normal', next: 'Normal', quickFormat: true,
        run: { size: 26, bold: true, color: GREEN }, paragraph: { spacing: { before: 240, after: 100 }, outlineLevel: 1 } },
      { id: 'TOC1', name: 'toc 1', basedOn: 'Normal', next: 'Normal', run: { bold: true, size: 20 }, paragraph: { spacing: { before: 60, after: 20 } } },
      { id: 'TOC2', name: 'toc 2', basedOn: 'Normal', next: 'Normal', run: { size: 19 }, paragraph: { spacing: { after: 10 }, indent: { left: 300 } } },
      { id: 'Heading3', name: 'Heading 3', basedOn: 'Normal', next: 'Normal', quickFormat: true,
        run: { size: 21, bold: true, color: '263238' }, paragraph: { spacing: { before: 200, after: 80 }, outlineLevel: 2 } },
    ],
  },
  numbering: { config: [
    { reference: 'bullets', levels: [{ level: 0, format: LevelFormat.BULLET, text: '•', alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 400, hanging: 260 } } } }] },
    { reference: 'steps', levels: [{ level: 0, format: LevelFormat.DECIMAL, text: '%1.', alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 400, hanging: 300 } } } }] },
  ] },
  sections: [{
    properties: { titlePage: true, page: { size: { width: 11906, height: 16838 }, margin: { top: 1100, bottom: 1000, left: 1080, right: 1080, header: 500, footer: 500 } } },
    headers: {
      first: new Header({ children: [new Paragraph({ children: [] })] }),
      default: new Header({ children: [new Paragraph({
        border: { bottom: { style: BorderStyle.SINGLE, size: 4, color: 'C8D3C8', space: 4 } },
        children: [new TextRun({ text: 'Top Farm ERP  |  Flock Lifecycle Workflow  |  Functional Test Report', size: 16, color: GREY })] })] }),
    },
    footers: {
      first: new Footer({ children: [new Paragraph({ children: [] })] }),
      default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.RIGHT, children: [
        new TextRun({ text: 'Page ', size: 16, color: GREY }), new TextRun({ children: [PageNumber.CURRENT], size: 16, color: GREY }),
        new TextRun({ text: ' of ', size: 16, color: GREY }), new TextRun({ children: [PageNumber.TOTAL_PAGES], size: 16, color: GREY })] })] }),
    },
    children,
  }],
});

Packer.toBuffer(doc).then((buf) => {
  fs.writeFileSync(OUT, buf);
  console.log('written', OUT, (buf.length / 1048576).toFixed(1), 'MB; figures:', figNo, '; checks:', CHECKS.length, passCount, 'pass');
});
