/* The Sankey on a search page for one quarter (scripts/seo_history.py → c/<slug>/<quarter>/): the quarter's chart from the
   company's own data, drawn by sankey.js; the figure is removed when it cannot be drawn. */
(async () => {
  const f = document.getElementById('sankey');
  if (!f) return;
  try {
    const d = await (await fetch(f.dataset.src)).json();
    const q = (d.quarters || []).find((x) => x.label === f.dataset.label);
    if (!q || !q.nodes || !window.Sankey) { f.remove(); return; }
    if (document.fonts && document.fonts.ready) await document.fonts.ready;
    f.innerHTML = Sankey.toSVG(Sankey.layout(q, {}), Sankey.dec(q.title));
    f.querySelectorAll('.note-mark, .hit').forEach((x) => x.remove());
  } catch (err) { f.remove(); }
})();
