// Export imprimeur : PDF vectoriel (texte et QR restent vectoriels, polices incorporées)
// + un aperçu PNG à 300 DPI par page. Usage : node print.js <url_html> <sortie_sans_ext> <largeur_mm> <hauteur_mm> [sélecteur_page]
const { chromium } = require('playwright');
(async () => {
  const [url, out, wmm, hmm, sel] = process.argv.slice(2);
  const pxPerMm = 96 / 25.4;                       // CSS px par mm
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: Math.round(wmm * pxPerMm), height: Math.round(hmm * pxPerMm) },
                              deviceScaleFactor: 300 / 96 });   // 300 DPI
  await p.goto(url, { waitUntil: 'networkidle' });
  await p.evaluate(() => document.fonts.ready);
  await p.waitForTimeout(400);
  await p.pdf({ path: out + '.pdf', width: wmm + 'mm', height: hmm + 'mm', preferCSSPageSize: true, printBackground: true });
  if (sel) {
    const pages = await p.$$(sel);
    for (let i = 0; i < pages.length; i++) await pages[i].screenshot({ path: `${out}-${i + 1}.png` });
    console.log('saved', out + '.pdf', '+', pages.length, 'PNG');
  } else {
    await p.screenshot({ path: out + '.png' });
    console.log('saved', out + '.pdf + .png');
  }
  await b.close();
})();
