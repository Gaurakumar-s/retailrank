const $ = id => document.getElementById(id);
const pct = value => `${(value * 100).toFixed(2)}%`;
const names = {popular: 'Popularity', als: 'ALS retrieval', similarity: 'Item similarity', ranker: 'Two-stage ranker'};
const methodDescriptions = {
  ranker: 'Finds candidates from several sources, then learns which ones to show first.',
  als: 'Looks for products that match patterns in shoppers’ past interactions.',
  similarity: 'Finds products with shopping patterns similar to your recent items.',
  popular: 'Shows frequently explored products, regardless of your interests.'
};
let replay = null, offset = 0, catalogQuery = '', metricsReady = false;
let loadingAction = false, requestSequence = 0, catalogSequence = 0, toastTimer;
let selectedItem = null, currentRecommendations = [], ready = false;

function el(tag, text, cls) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (cls) node.className = cls;
  return node;
}
function toast(message) {
  $('status').textContent = message;
  $('status').hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => $('status').hidden = true, 6500);
}
async function api(path, body) {
  const response = await fetch(path, {
    ...(body === undefined ? {} : {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)
    }), signal: AbortSignal.timeout(20000)
  });
  if (!response.ok) {
    let message = 'Could not complete the request. Please try again.';
    try {
      const data = await response.json();
      if (typeof data.detail === 'string') message = data.detail;
    } catch {}
    throw Error(message);
  }
  return response.json();
}
function lockActions(locked) {
  loadingAction = locked;
  document.querySelectorAll('[data-mutation], .item-actions button').forEach(button => button.disabled = locked || !ready);
  $('method').disabled = locked;
}
function art(item, label) {
  const node = el('div', undefined, 'item-art');
  const hues = [['#e4ecdf','#7f9c75'],['#e5e8f0','#8795b4'],['#e0eceb','#76a19d'],['#f0e5df','#b79580'],['#eae4ef','#a08db4']];
  const palette = hues[item.item_id % hues.length];
  node.style.setProperty('--tint', palette[0]);
  node.style.setProperty('--shape', palette[1]);
  node.style.setProperty('--angle', `${item.item_id % 25 - 12}deg`);
  node.style.setProperty('--radius', item.item_id % 2 ? '8px' : '26px 26px 8px 8px');
  node.setAttribute('aria-hidden', 'true');
  if (label) node.append(el('span', label, 'rank-label'));
  return node;
}
function card(item, isRecommendation) {
  const product = el('article', undefined, 'product');
  const body = el('div', undefined, 'item-body');
  const description = isRecommendation
    ? (item.reason.startsWith('Popular') ? 'Popular with other shoppers' : 'Related to your recent activity')
    : 'Anonymous catalog product';
  body.append(el('h3', `Item #${item.item_id}`), el('p', description, 'item-sub'));
  const actions = el('div', undefined, 'item-actions');
  const view = el('button', 'Explore item');
  view.setAttribute('aria-label', `Explore item ${item.item_id}`);
  view.addEventListener('click', () => openItem(item));
  const cart = el('button', 'Add to demo cart');
  cart.setAttribute('aria-label', `Add item ${item.item_id} to demo cart`);
  cart.addEventListener('click', () => record(item.item_id, 'addtocart'));
  view.disabled = cart.disabled = loadingAction || !ready;
  actions.append(view, cart);
  body.append(actions);
  product.append(art(item, isRecommendation ? `Pick ${item.rank}` : ''), body);
  return product;
}
async function state() {
  const data = await api('/api/state');
  $('views').textContent = data.counts.view || 0;
  $('carts').textContent = data.counts.addtocart || 0;
  $('purchases').textContent = data.counts.transaction || 0;
  $('reset').disabled = loadingAction || !data.history.length;
  $('profile-note').textContent = data.history.length
    ? `${data.history.length} recent ${data.history.length === 1 ? 'action is' : 'actions are'} helping shape your suggestions.`
    : 'Your session is empty. Explore an item or try an example shopper.';
  $('history').replaceChildren(...data.history.slice(-5).reverse().map(item => {
    const row = el('div', undefined, 'history-item');
    const mark = item.event === 'view' ? '◎' : item.event === 'addtocart' ? '+' : '✓';
    const detail = el('div');
    detail.append(el('strong', `Item #${item.item_id}`), el('span', {
      view: 'Explored', addtocart: 'Added to demo cart', transaction: 'Simulated purchase'
    }[item.event]));
    row.append(el('div', mark, 'history-mark'), detail);
    return row;
  }));
  if (!data.history.length) $('history').append(el('p', 'Your recent items will appear here.', 'empty-state'));
  return data;
}
async function recommend() {
  const seq = ++requestSequence;
  const method = $('method').value;
  $('recommended').setAttribute('aria-busy', 'true');
  try {
    const data = await api(`/api/recommendations?method=${encodeURIComponent(method)}&k=8`);
    if (seq !== requestSequence) return;
    currentRecommendations = data.items;
    $('recommended').replaceChildren(...data.items.map(item => card(item, true)));
    const popular = data.cold_start || data.method === 'popular';
    $('recommendation-eyebrow').textContent = popular ? 'A PLACE TO START' : 'SHAPED BY YOUR ACTIVITY';
    $('recommendation-title').textContent = popular ? 'Popular with other shoppers' : 'Picked for you';
    $('serving-mode').textContent = data.cold_start
      ? 'Start with popular items. Explore one to make these suggestions more personal.'
      : data.method === 'popular'
        ? 'You’re comparing the popularity method. Switch back to personalized to use your activity.'
        : 'Updated using your recent activity. Items you just explored are left out so you can discover something new.';
    $('method-help').textContent = methodDescriptions[method];
    $('timing').textContent = `${names[data.method]} · ${data.candidate_count} candidates · ${data.latency_ms.toFixed(1)} ms server processing`;
    if (replay && !$('actual-item').hidden) showActual();
    return data;
  } finally {
    if (seq === requestSequence) $('recommended').setAttribute('aria-busy', 'false');
  }
}
async function refresh() { await state(); await recommend(); }
async function record(item, event) {
  if (loadingAction || !ready) return;
  lockActions(true);
  let saved = false;
  try {
    await api('/api/actions', {item_id: item, event});
    saved = true;
    replay = null;
    $('replay-result').hidden = true;
    $('scenario').value = '';
    await refresh();
    const message = event === 'transaction'
      ? `Demo purchase recorded for item #${item}. No payment was made.`
      : event === 'addtocart'
        ? `Item #${item} added to your demo cart. Your suggestions have updated.`
        : `Item #${item} explored. Your suggestions have updated.`;
    if ($('item-dialog').open) $('detail-feedback').textContent = message;
    else toast(message);
    return true;
  } catch (error) {
    const message = saved ? 'Your action was saved, but suggestions could not refresh. Reload the page to see them.' : error.message;
    if ($('item-dialog').open) $('detail-feedback').textContent = message;
    else toast(message);
    return false;
  } finally { lockActions(false); }
}
async function openItem(item) {
  if (loadingAction || !ready) return;
  selectedItem = item;
  $('detail-title').textContent = `Item #${item.item_id}`;
  $('detail-art').replaceChildren(art(item));
  $('detail-reason').textContent = item.reason || 'Explore this item to add it to your recent activity.';
  $('detail-popularity').textContent = `${item.training_events.toLocaleString()} interactions recorded during the earlier training period.`;
  $('detail-feedback').textContent = 'Updating your suggestions…';
  $('item-dialog').showModal();
  document.body.classList.add('dialog-open');
  await record(item.item_id, 'view');
}
$('close-dialog').addEventListener('click', () => $('item-dialog').close());
$('item-dialog').addEventListener('close', () => document.body.classList.remove('dialog-open'));
$('detail-cart').addEventListener('click', () => selectedItem && record(selectedItem.item_id, 'addtocart'));
$('detail-buy').addEventListener('click', () => selectedItem && record(selectedItem.item_id, 'transaction'));
async function catalog(append = false) {
  const seq = ++catalogSequence;
  $('catalog').setAttribute('aria-busy', 'true');
  try {
    const data = await api(`/api/catalog?q=${encodeURIComponent(catalogQuery)}&offset=${offset}&limit=12`);
    if (seq !== catalogSequence) return;
    if (!append) $('catalog').replaceChildren();
    $('catalog').append(...data.items.map(item => card(item, false)));
    if (!data.items.length && !append) $('catalog').append(el('p', 'No items match that number. Clear the search to browse all products.', 'empty-state'));
    offset += data.items.length;
    $('more').hidden = offset >= data.total;
  } finally { if (seq === catalogSequence) $('catalog').setAttribute('aria-busy', 'false'); }
}
$('search-form').addEventListener('submit', event => {
  event.preventDefault(); catalogQuery = $('search').value.trim(); offset = 0;
  catalog().catch(error => toast(error.message));
});
$('search').addEventListener('search', () => {
  if (!$('search').value) { catalogQuery = ''; offset = 0; catalog().catch(error => toast(error.message)); }
});
$('more').addEventListener('click', async () => {
  $('more').disabled = true;
  try { await catalog(true); } catch (error) { toast(error.message); }
  finally { $('more').disabled = false; }
});
$('method').addEventListener('change', () => recommend().catch(error => toast(error.message)));
$('reset').addEventListener('click', async () => {
  if (loadingAction || !ready) return;
  lockActions(true);
  try {
    await api('/api/reset', {});
    replay = null; $('replay-result').hidden = true; $('scenario').value = ''; $('method').value = 'ranker';
    await refresh(); toast('A fresh start. Your demo activity has been cleared.');
  } catch (error) { toast(error.message); } finally { lockActions(false); }
});
async function loadReplay(index) {
  if (loadingAction || !ready) return;
  lockActions(true);
  try {
    replay = await api(`/api/scenarios/${index}`, {});
    $('scenario').value = index;
    $('replay-result').hidden = false; $('actual-item').hidden = true; $('reveal').hidden = false;
    await refresh();
    toast('Example shopper loaded. Your suggestions now use their past activity.');
    $('recommendation-title').scrollIntoView({behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth', block: 'start'});
  } catch (error) { toast(error.message); } finally { lockActions(false); }
}
$('try-example').addEventListener('click', () => loadReplay(0));
$('load-replay').addEventListener('click', () => {
  if ($('scenario').value === '') { toast('Choose an example shopper first.'); return; }
  loadReplay($('scenario').value);
});
function showActual() {
  if (!replay) return;
  const match = currentRecommendations.find(item => item.item_id === replay.actual_next_item);
  $('actual-item').textContent = `Their next item was #${replay.actual_next_item}. ${match ? `It appears as suggestion ${match.rank} above.` : 'It is not in the eight suggestions above. Recommendations won’t always predict the next choice.'}`;
}
$('reveal').addEventListener('click', () => {
  if (!replay) return;
  $('actual-item').hidden = false; $('reveal').hidden = true; showActual();
});
function makeTable(headers,rows){const t=el('table');const head=el('thead'),tr=el('tr');headers.forEach(h=>tr.append(el('th',h)));head.append(tr);t.append(head);const body=el('tbody');rows.forEach(row=>{const tr=el('tr');row.forEach(value=>tr.append(el('td',value)));body.append(tr)});t.append(body);return t}
async function evaluation(){if(metricsReady)return;const m=await api('/api/metrics');const r=m.test.methods.ranker;const items=[[pct(r.hit_rate_at_10),'Next item found in top 10'],[r.ndcg_at_10.toFixed(4),'NDCG @10'],[m.retrieval.catalog_size.toLocaleString(),'Products in trained catalog'],[m.original_events.toLocaleString(),'Original behavior events']];$('metric-cards').replaceChildren(...items.map(([value,label])=>{const box=el('div',undefined,'metric');box.append(el('strong',value),el('span',label));return box}));const order=['popular','als','similarity','ranker'];const max=Math.max(...order.map(k=>m.test.methods[k].hit_rate_at_10));$('comparison-bars').replaceChildren(...order.map(key=>{const row=el('div',undefined,'bar-row'),track=el('div',undefined,'bar-track'),fill=el('div',undefined,'bar-fill');fill.style.width=`${m.test.methods[key].hit_rate_at_10/max*100}%`;track.append(fill);row.append(el('span',names[key]),track,el('strong',pct(m.test.methods[key].hit_rate_at_10)));return row}));$('comparison-table').replaceChildren(makeTable(['Method','Hit rate @10','NDCG @10','MRR @10','Hit rate @20'],order.map(key=>{const x=m.test.methods[key];return[names[key],pct(x.hit_rate_at_10),x.ndcg_at_10.toFixed(4),x.mrr_at_10.toFixed(4),pct(x.hit_rate_at_20)]})));$('coverage-stats').replaceChildren(...[['True next item in candidate pool',pct(m.test.candidate_recall)],['Test targets inside trained catalog',pct(m.test.target_catalog_coverage)],['Queries with a known profile item',pct(m.test.known_profile_fraction)],['Ranker catalog coverage @20',pct(r.catalog_coverage_at_20)]].map(([key,value])=>{const row=el('div',undefined,'stat-row');row.append(el('span',key),el('strong',value));return row}));const date=s=>s.slice(0,10);$('timeline').replaceChildren(...[['Fit ALS and item statistics',`${date(m.data_start)} to ${date(m.cutoffs.retrieval_end)}`],['Train the second-stage ranker',`${date(m.cutoffs.retrieval_end)} to ${date(m.cutoffs.ranker_train_end)}`],['Validate and stop training',`${date(m.cutoffs.ranker_train_end)} to ${date(m.cutoffs.validation_end)}`],['Evaluate on later sessions',`${date(m.cutoffs.validation_end)} to ${date(m.data_end)}`]].map(([label,range])=>{const row=el('div',undefined,'time-step');row.append(el('strong',label),el('span',range));return row}));$('limitations').replaceChildren(...m.limitations.map(text=>el('li',text)));$('uncertainty').textContent=`The ranker's NDCG difference versus ALS has a query-bootstrap 95% interval of ${m.test.ndcg_delta_vs_als_95pct_interval.map(x=>x.toFixed(4)).join(' to ')}. Item similarity remains slightly stronger on test NDCG, although the ranker was selected using validation data.`;$('latency-note').textContent=`Local model inference: median ${m.test.local_latency_ms.p50.toFixed(2)} ms and p95 ${m.test.local_latency_ms.p95.toFixed(2)} ms over ${m.test.local_latency_ms.samples} queries. This excludes network time and is not a hosted performance guarantee.`;metricsReady=true}
function setView(view) {
  ['studio', 'evaluation', 'system'].forEach(key => $(key + '-view').hidden = key !== view);
  document.querySelectorAll('[data-view]').forEach(button => {
    const active = button.dataset.view === view;
    button.classList.toggle('active', active);
    if (active) button.setAttribute('aria-current', 'page'); else button.removeAttribute('aria-current');
  });
  document.title = `${{studio:'Explore',evaluation:'Model results',system:'How it works'}[view]} · RetailRank`;
  if (view === 'evaluation') evaluation().catch(error => toast(error.message));
  window.scrollTo({top: 0, behavior: 'instant'});
}
document.querySelectorAll('[data-view]').forEach(button => button.addEventListener('click', () => setView(button.dataset.view)));
async function start() {
  lockActions(true);
  try {
    // Establish the session cookie before concurrent requests can create separate sessions.
    await state();
    await Promise.all([recommend(), catalog(), api('/api/scenarios').then(data => {
      data.scenarios.forEach((row, i) => {
        const option = el('option', `Shopper ${i + 1} · ${row.history_length} past actions`);
        option.value = row.id; $('scenario').append(option);
      });
    })]);
    ready = true;
  } catch (error) {
    toast('The demo could not load. Check that the server is running, then reload this page.');
    $('serving-mode').textContent = 'Could not load recommendations. Please reload to try again.';
    console.error(error);
  } finally { lockActions(false); }
}
start();
