'use strict';
const $ = (id) => document.getElementById(id);
let active = null;
let user = localStorage.getItem('peoplepay-user') || crypto.randomUUID();
localStorage.setItem('peoplepay-user', user);
let token = sessionStorage.getItem('peoplepay-token') || '';
async function api(path, body) {
  const headers = { 'X-Beacon-User': user, 'Content-Type': 'application/json' };
  if (token) headers.Authorization = `Bearer ${token}`;
  const response = await fetch(path, { method: body === undefined ? 'GET' : 'POST', headers, ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
  const value = await response.json();
  if (!response.ok) throw new Error(value.error || 'Request failed');
  return value;
}
function text(tag, content, target) { const el = document.createElement(tag); el.textContent = content; target.append(el); return el; }
async function run(work) {
  document.querySelectorAll('button').forEach(b => { b.disabled = true; });
  $('notice').textContent = 'Checking…';
  try { await work(); $('notice').textContent = 'Updated'; } catch (e) { $('notice').textContent = e.message; }
  finally { document.querySelectorAll('button').forEach(b => { b.disabled = false; }); }
}
function render(value) {
  $('result').replaceChildren(); $('trace').textContent = '';
  $('answer').hidden = true; $('retry').hidden = true; $('history').hidden = true;
  if (value.status === 'UNSUPPORTED') {
    active = null; text('p', value.route.reason, $('result')); return;
  }
  if (value.status === 'ROUTED_TO_PROCUREMENT') {
    active = null;
    text('p', value.route.reason, $('result'));
    const link = text('a', 'Continue with GreenChain and InflationForge', $('result')); link.href = '/journey';
    return;
  }
  active = value; history.replaceState(null, '', `/assistance?workflow=${encodeURIComponent(active.id)}`);
  text('h2', value.phase.replaceAll('_', ' '), $('result'));
  text('p', `${value.route.reason} No payment has been made.`, $('result'));
  const d = value.decision;
  $('retry').hidden = !['ASSISTANCE_PROVIDER_UNAVAILABLE', 'EXTENSION_UNAVAILABLE', 'ECHO_UNAVAILABLE_OR_REJECTED'].includes(value.phase);
  $('history').hidden = !d; $('answer').hidden = !d;
  if (!d) { text('p', value.phase === 'UNSUPPORTED_JURISDICTION' ? 'No configured policy provider covers this country.' : 'Assistance provider unavailable. Your structured workflow is saved.', $('result')); return; }
  text('p', `CivicMesh · policy version ${d.policy_version} · checked for ${d.policy_date} · decision ${d.version}`, $('result'));
  text('p', d.explanation, $('result'));
  for (const option of d.options) {
    const card = document.createElement('article'); card.className = 'module-card'; $('result').append(card);
    text('h3', option.name, card);
    if (option.assessment) {
      text('p', `${option.assessment.tier.replaceAll('_', ' ')} · heuristic score ${option.estimate.value} (not a probability)`, card);
      for (const c of option.assessment.criteria) text('p', `${c.label}: ${c.status} — ${c.detail}`, card);
      const source = d.provider_receipt.evidence.find(item => option.evidence_ids.includes(item.id));
      if (source?.source_uri) { const link = text('a', 'Program source (bundled reference)', card); link.href = source.source_uri; link.target = '_blank'; link.rel = 'noopener noreferrer'; }
    } else text('p', `${option.terms.amount_minor / 100} ${option.terms.currency} · user supplied, unverified bill · separate approval required`, card);
  }
  text('h3', 'Suggested plan', $('result'));
  for (const s of d.plan.steps) text('p', `${s.step_number}. ${s.agency_name}: ${s.action_description}`, $('result'));
  if (d.paths?.length) { text('h3', 'Possible assistance routes', $('result')); for (const path of d.paths) text('p', `${path.start} → ${path.end} · estimated ${path.total_days} days · verify locally`, $('result')); }
  $('answer').elements.value.value = '';
  $('question').textContent = d.question?.text || 'Add or correct a fact';
  const field = {income: 'income_annual', household: 'household_size', location: 'state'}[d.question?.key] || d.question?.key;
  const supported = [...$('answer').elements.key.options].some(o => o.value === field);
  if (supported) $('answer').elements.key.value = field;
  else if (d.question?.key) {
    $('answer').hidden = true;
    text('p', `${d.question.text} This question requires a program representative or the native CivicMesh intake; this portal does not collect that additional fact.`, $('result'));
  }
  if (d.question?.key === 'income') $('question').textContent = `${d.question.text} Enter total annual household income in USD here (monthly income multiplied by 12).`;
}
$('need').addEventListener('submit', e => { e.preventDefault(); run(async () => {
  const f = new FormData(e.target); const facts = {};
  for (const key of ['age', 'income_annual', 'household_size']) if (f.get(key) !== '') facts[key] = Number(f.get(key));
  if (f.get('state')) facts.state = f.get('state').toUpperCase();
  const body = {message: f.get('message'), jurisdiction: f.get('jurisdiction'), language: f.get('language'), facts, consent: f.get('consent') === 'on'};
  if (f.get('bill') !== '') body.payment_option = {amount_minor: Math.round(Number(f.get('bill')) * 100), currency: 'USD'};
  render(await api('/api/v1/assistance', body));
}); });
$('answer').addEventListener('submit', e => { e.preventDefault(); run(async () => {
  const f = new FormData(e.target); const key = f.get('key'); const raw = f.get('value');
  const value = ['age', 'income_annual', 'household_size'].includes(key) ? Number(raw) : raw;
  if (typeof value === 'number' && !Number.isInteger(value)) throw new Error('Enter a whole number for this fact.');
  render(await api(`/api/v1/assistance/${active.id}/answer`, { facts: {[key]: value} }));
}); });
$('retry').addEventListener('click', () => run(async () => render(await api(`/api/v1/assistance/${active.id}/retry`, {}))));
$('history').addEventListener('click', () => run(async () => {
  const history = await api(`/api/v1/assistance/${active.id}/explain`); $('trace').replaceChildren();
  text('h2', 'Preserved decision history', $('trace'));
  for (const decision of history.historical_decisions) {
    text('h3', `Version ${decision.version} · ${new Date(decision.created_at).toLocaleString()}`, $('trace'));
    text('p', `Policy used: ${decision.policy_version}, evaluated for ${decision.policy_date}. ${decision.explanation}`, $('trace'));
    text('p', decision.options.map(option => option.name).join(' · '), $('trace'));
  }
  text('h3', 'What changed?', $('trace'));
  text('p', history.changes.length ? history.changes.map(change => ({policy_date:'Policy date',policy_version:'Policy version',options:'Option evidence or estimates',question:'Next question'}[change.field] || change.field)).join(' · ') : 'No changes between preserved evaluation versions.', $('trace'));
  text('p', history.note, $('trace'));
}));
$('account').elements.user.value = user;
$('account').addEventListener('submit', e => { e.preventDefault(); const f = new FormData(e.target); user = f.get('user').trim(); token = f.get('token').trim(); localStorage.setItem('peoplepay-user', user); sessionStorage.setItem('peoplepay-token', token); $('notice').textContent = 'Account connected'; });
const workflow = new URLSearchParams(location.search).get('workflow');
if (workflow) run(async () => render(await api(`/api/v1/assistance/${encodeURIComponent(workflow)}`)));
api('/api/v1/assistance/providers').then(value => { $('provider-status').textContent = value.providers.length ? value.providers.map(p => `${p.metadata.name} · ${p.metadata.version} · ${p.jurisdictions.join(', ')} · ${p.health.status.replaceAll('_', ' ')}`).join(' · ') : 'Assistance is not configured. The procurement workspace remains available.'; }).catch(() => { $('provider-status').textContent = 'Provider status is unavailable.'; });
