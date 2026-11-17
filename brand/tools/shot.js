// Rendu d'une page HTML en PNG (Playwright). Usage : node shot.js <html> <out.png> [w] [h] [full]
const { chromium } = require('playwright');
(async () => {
  const [html, out, w, h, full] = [process.argv[2], process.argv[3], +process.argv[4] || 1080, +process.argv[5] || 1080, process.argv[6] === 'full'];
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: w, height: h }, deviceScaleFactor: +process.env.DSF || 2, javaScriptEnabled: !process.env.NOJS });
  await p.goto(html.startsWith('http') ? html : 'file://' + require('path').resolve(html), { waitUntil: 'networkidle' });
  try { await p.evaluate(() => document.fonts.ready); } catch (e) {}
  await p.waitForTimeout(400);
  await p.screenshot({ path: out, fullPage: full });
  const ow = await p.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  if (ow > 0) console.log('OVERFLOW horizontal:', ow, 'px');
  await b.close();
  console.log('saved', out);
})();
