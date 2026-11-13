'use strict';
const $ = (s) => document.querySelector(s);
const icon = (name) => `<svg aria-hidden="true"><use href="#i-${name}"/></svg>`;
const esc = (v) => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const LOCAL = document.body.dataset.storage === 'local';
const CONTACT_KEY = 'folio.contacts.v1';
const EVENT_KEY = 'folio.event.v1';
let contacts = [], currentEvent = 'General networking', stream = null, cameraSide = 'user', cameraRequest = 0, busy = false, imageData = '', toastTimer, worker = null;
let loadFailed = false;
function toast(message) { $('#toast').textContent = message; $('#toast').classList.add('visible'); clearTimeout(toastTimer); toastTimer = setTimeout(() => $('#toast').classList.remove('visible'), 5000); }
function readLocal(key, fallback) { try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch { return fallback; } }
async function api(path, options = {}) { const r = await fetch(path, { ...options, headers: { 'Content-Type': 'application/json' } }); const data = await r.json(); if (!r.ok) throw Error(data.error || 'Unable to save. Please try again.'); return data; }
async function init() {
  currentEvent = readLocal(EVENT_KEY, 'General networking');
  if (typeof currentEvent !== 'string' || !currentEvent.trim()) currentEvent = 'General networking';
  $('#sidebar-event').textContent = currentEvent;
  $('#storage-label').textContent = LOCAL ? 'Saved on this device' : 'Saved to this workspace';
  try { if (LOCAL) { const raw = localStorage.getItem(CONTACT_KEY); contacts = raw ? JSON.parse(raw) : []; if (!Array.isArray(contacts) || contacts.some(c => !c || typeof c.name !== 'string' || !c.id)) throw Error('Invalid collection'); } else contacts = await api('/api/contacts'); }
  catch { loadFailed = true; contacts = []; toast('Could not load your collection. Reload before saving new contacts.'); }
  render();
}
function allEvents() { return [...new Set([currentEvent, ...contacts.map(c => c.event)].filter(Boolean))].sort(); }
function render() {
  $('#nav-count').textContent = contacts.length; $('#total-stat').textContent = contacts.length; $('#contacts-count').textContent = contacts.length;
  $('#events-stat').textContent = new Set(contacts.map(c => c.event).filter(Boolean)).size;
  const filter = $('#event-filter').value;
  $('#event-filter').innerHTML = '<option value="">All events</option>' + allEvents().map(e => `<option value="${esc(e)}">${esc(e)}</option>`).join('');
  if (allEvents().includes(filter)) $('#event-filter').value = filter;
  $('#event-options').innerHTML = allEvents().map(e => `<option value="${esc(e)}"></option>`).join('');
  $('#export-all').disabled = !contacts.length;
  renderList(); renderEvents();
}
function renderList() {
  const q = $('#search').value.toLowerCase().trim(), event = $('#event-filter').value;
  const list = contacts.filter(c => (!event || c.event === event) && ['name','company','email','title','notes','event','phone'].some(k => String(c[k] || '').toLowerCase().includes(q)));
  list.sort($('#sort').value === 'name' ? (a,b) => a.name.localeCompare(b.name) : (a,b) => b.created_at.localeCompare(a.created_at));
  if (!list.length) { $('#contacts-list').innerHTML = `<div class="empty-state">${icon('users')}<strong>${loadFailed ? 'Your collection couldn’t be loaded' : contacts.length ? 'No connections found' : 'Your collection starts with a hello.'}</strong><p>${loadFailed ? 'Reload this page to try again. Your saved data has not been changed.' : contacts.length ? 'Try a different search or event.' : 'Scan your first card or add a contact to get the conversation going.'}</p></div>`; return; }
  $('#contacts-list').innerHTML = `<table><thead><tr><th>Connection</th><th>Company / role</th><th>Event</th><th><span class="sr-only">Open contact</span></th></tr></thead><tbody>${list.map(c => `<tr class="contact-row" data-id="${esc(c.id)}"><td><div class="contact-name"><span class="avatar">${esc(c.name.split(/\s+/).slice(0,2).map(n => n[0]).join('').toUpperCase())}</span><div><strong>${esc(c.name)}</strong><small>${esc(c.email || c.phone || 'Details to come')}</small></div></div></td><td>${esc(c.company || '—')}<small>${esc(c.title)}</small></td><td><span class="event-pill">${esc(c.event || 'No event')}</span></td><td><button class="row-open" aria-label="Edit ${esc(c.name)}">↗</button></td></tr>`).join('')}</tbody></table>`;
}
function renderEvents() {
  $('#events-list').innerHTML = allEvents().map(e => { const n = contacts.filter(c => c.event === e).length; return `<button class="event-card" data-event="${esc(e)}">${icon('calendar')}<h3>${esc(e)}</h3><p>${n} connection${n === 1 ? '' : 's'}${e === currentEvent ? ' · Current event' : ''}</p><span>View connections ↗</span></button>`; }).join('');
}
function setView(view) {
  if (view !== 'scan') stopCamera();
  document.querySelectorAll('[data-view]').forEach(b => { b.classList.toggle('active', b.dataset.view === view); b.setAttribute('aria-current', b.dataset.view === view ? 'page' : 'false'); });
  $('#scan-view').hidden = view !== 'scan'; $('#contacts-section').hidden = view === 'events'; $('#events-section').hidden = view !== 'events';
  $('#breadcrumb-current').textContent = {scan:'Card scanner', contacts:'My contacts', events:'Events'}[view];
  $('#page-title').innerHTML = {scan:'Meet. Scan. <span>Connect.</span>', contacts:'People worth <span>remembering.</span>', events:'Be there. <span>Stay connected.</span>'}[view];
  $('#page-description').textContent = {scan:'Turn business cards into your next big opportunity.', contacts:'All your introductions, in one thoughtful place.', events:'Keep every connection close to where it started.'}[view];
}
document.querySelectorAll('[data-view]').forEach(b => b.addEventListener('click', () => setView(b.dataset.view)));
$('.brand').addEventListener('click', e => { e.preventDefault(); setView('scan'); });
for (const id of ['#search','#event-filter','#sort']) $(id).addEventListener(id === '#search' ? 'input' : 'change', renderList);
$('#contacts-list').addEventListener('click', e => { const row = e.target.closest('[data-id]'); if (row) openContact(contacts.find(c => c.id === row.dataset.id)); });
$('#events-list').addEventListener('click', e => { const card = e.target.closest('[data-event]'); if (!card) return; setView('contacts'); $('#event-filter').value = card.dataset.event; renderList(); });
function openEvent() { $('#event-name').value = currentEvent; $('#event-dialog').showModal(); }
$('#change-event').addEventListener('click', openEvent); $('#new-event').addEventListener('click', openEvent);
$('#event-form').addEventListener('submit', e => { e.preventDefault(); const value = $('#event-name').value.trim(); if (!value) return; try { localStorage.setItem(EVENT_KEY, JSON.stringify(value)); } catch { toast('Event could not be saved. Device storage is unavailable.'); return; } currentEvent = value; $('#sidebar-event').textContent = value; render(); $('#event-dialog').close(); toast(`New connections will be tagged “${value}”.`); });
document.querySelectorAll('.close-dialog').forEach(b => b.addEventListener('click', () => b.closest('dialog').close()));
document.querySelectorAll('dialog').forEach(d => d.addEventListener('click', e => { if (e.target !== d) return; const r = d.getBoundingClientRect(); if (e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom) d.close(); }));
function openContact(contact = {}, scanned = false) {
  const form = $('#contact-form'); form.reset(); $('#form-error').textContent = '';
  for (const key of ['id','name','company','title','email','phone','website','event','notes']) form.elements[key].value = contact[key] || (key === 'event' ? currentEvent : '');
  $('#dialog-title').textContent = contact.id ? 'A familiar connection.' : 'Make it a keeper.';
  $('#dialog-eyebrow').textContent = contact.id ? 'THE DETAILS THAT MATTER' : 'A NEW CONNECTION';
  $('#review-notice').textContent = scanned ? 'Check each detail — card layouts and text recognition can vary.' : 'Add the details you want to remember.';
  $('#review-image').hidden = !scanned || !imageData; if (scanned && imageData) $('#review-image').src = imageData;
  $('#delete-contact').hidden = !contact.id; $('#download-vcard').hidden = !contact.id;
  $('#contact-dialog').showModal();
}
$('#manual-add').addEventListener('click', () => openContact());
$('#contact-form').addEventListener('submit', async e => {
  e.preventDefault(); if (loadFailed) { $('#form-error').textContent = 'Reload your collection before saving.'; return; }
  const form = e.target, c = Object.fromEntries(new FormData(form)); Object.keys(c).forEach(k => c[k] = c[k].trim());
  if (!c.name) { $('#form-error').textContent = 'Please enter a name.'; return; }
  if (c.email && contacts.some(x => x.id !== c.id && x.email?.toLowerCase() === c.email.toLowerCase())) { $('#form-error').textContent = 'A connection with this email already exists. Find it in your collection to edit it.'; return; }
  $('#save-contact').disabled = true;
  try {
    if (LOCAL) { const existing = contacts.find(x => x.id === c.id); c.id ||= crypto.randomUUID(); c.created_at = existing?.created_at || new Date().toISOString(); const next = contacts.filter(x => x.id !== c.id).concat(c); localStorage.setItem(CONTACT_KEY, JSON.stringify(next)); contacts = next; }
    else { await api(c.id ? `/api/contacts/${encodeURIComponent(c.id)}` : '/api/contacts', {method:c.id ? 'PUT' : 'POST', body:JSON.stringify(c)}); contacts = await api('/api/contacts'); }
    render(); $('#contact-dialog').close(); toast('Connection saved. Here’s to what comes next.');
  } catch (error) { $('#form-error').textContent = LOCAL ? 'Could not save. Your device storage may be full or disabled. Export your collection and try again.' : error.message; }
  finally { $('#save-contact').disabled = false; }
});
$('#delete-contact').addEventListener('click', async () => {
  const id = $('#contact-form').elements.id.value;
  if (!confirm('Delete this connection? This cannot be undone.')) return;
  try { const next = contacts.filter(c => c.id !== id); if (LOCAL) localStorage.setItem(CONTACT_KEY, JSON.stringify(next)); else await api(`/api/contacts/${encodeURIComponent(id)}`, {method:'DELETE'}); contacts = next; render(); $('#contact-dialog').close(); toast('Connection deleted.'); } catch (e) { $('#form-error').textContent = e.message; }
});
function download(text, filename, type) { const url = URL.createObjectURL(new Blob([text], {type})); const a = document.createElement('a'); a.href = url; a.download = filename; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000); }
function csvCell(v) { let s = String(v ?? ''); if (/^[\s]*[=+@-]/.test(s)) s = "'" + s; return '"' + s.replace(/"/g, '""') + '"'; }
$('#export-all').addEventListener('click', () => { const keys = ['name','company','title','email','phone','website','event','notes']; download('\uFEFF' + [keys, ...contacts.map(c => keys.map(k => c[k]))].map(row => row.map(csvCell).join(',')).join('\r\n'), 'folio-connections.csv', 'text/csv;charset=utf-8'); toast('Your connections are ready to take with you.'); });
function vEscape(s) { return String(s || '').replace(/\\/g,'\\\\').replace(/\n/g,'\\n').replace(/;/g,'\\;').replace(/,/g,'\\,').replace(/\r/g,''); }
$('#download-vcard').addEventListener('click', () => { const c = contacts.find(x => x.id === $('#contact-form').elements.id.value); if (!c) return; const lines = ['BEGIN:VCARD','VERSION:3.0',`FN:${vEscape(c.name)}`,`N:;${vEscape(c.name)};;;`,`ORG:${vEscape(c.company)}`,`TITLE:${vEscape(c.title)}`,`EMAIL:${vEscape(c.email)}`,`TEL:${vEscape(c.phone)}`,`URL:${vEscape(c.website)}`,`NOTE:${vEscape([c.event,c.notes].filter(Boolean).join('\n'))}`,'END:VCARD']; download(lines.join('\r\n'), `${c.name.replace(/[^a-z0-9-]/gi,'_')}.vcf`, 'text/vcard'); });
function resetCameraUI() { $('#camera').hidden = true; $('#sample-card').hidden = false; $('#captured').hidden = true; $('#preview-label').hidden = false; $('#camera-button').innerHTML = `${icon('camera')}<span>Enable camera</span>${icon('arrow')}`; $('#switch-camera').hidden = true; $('#stop-camera').hidden = true; $('#scanner-status').textContent = 'READY WHEN YOU ARE'; }
function stopCamera(reset = true) { cameraRequest++; $('#camera-button').disabled = busy; if (stream) stream.getTracks().forEach(t => t.stop()); stream = null; $('#camera').srcObject = null; if (reset && !busy) resetCameraUI(); }
async function startCamera() {
  if (!navigator.mediaDevices?.getUserMedia) { toast('Camera access requires HTTPS or localhost. You can upload a photo instead.'); return; }
  stopCamera(); const requestId = ++cameraRequest; $('#camera-button').disabled = true; $('#stop-camera').hidden = false; $('#camera-hint').textContent = 'Allow camera access in your browser to start.';
  try {
    const next = await navigator.mediaDevices.getUserMedia({audio:false, video:{facingMode:{ideal:cameraSide}, width:{ideal:1920},height:{ideal:1080}}});
    if (requestId !== cameraRequest) { next.getTracks().forEach(t => t.stop()); return; }
    stream = next; const video = $('#camera'); video.srcObject = stream; await video.play();
    video.hidden = false; $('#sample-card').hidden = true; $('#captured').hidden = true; $('#preview-label').hidden = true; $('#switch-camera').hidden = false; $('#stop-camera').hidden = false;
    $('#camera-button').innerHTML = `${icon('scan')}<span>Capture card</span>${icon('arrow')}`; $('#scanner-status').textContent = 'CAMERA IS LIVE'; $('#camera-hint').textContent = 'Keep the card inside the corners, then capture.';
    stream.getVideoTracks()[0].addEventListener('ended', () => { if (stream === next) stopCamera(); });
  } catch (error) {
    if (requestId !== cameraRequest) return;
    stopCamera(); const messages = {NotAllowedError:'Camera access was declined. Allow it in browser settings or upload a photo.', NotFoundError:'No camera was found. Connect a camera or upload a photo.', NotReadableError:'The camera is busy. Close other camera apps and try again.'};
    $('#camera-hint').textContent = messages[error.name] || 'Could not start the camera. Try again or upload a photo.'; toast($('#camera-hint').textContent);
  } finally { $('#camera-button').disabled = busy; }
}
$('#switch-camera').addEventListener('click', () => { cameraSide = cameraSide === 'user' ? 'environment' : 'user'; startCamera(); });
$('#stop-camera').addEventListener('click', () => { stopCamera(); $('#camera-hint').textContent = 'Camera off. Enable it when you’re ready.'; });
$('#camera-button').addEventListener('click', () => {
  if (busy) return; if (!stream) { startCamera(); return; }
  const video = $('#camera'); if (!video.videoWidth) { toast('Your camera is still getting ready. Try again in a moment.'); return; }
  const vr = video.getBoundingClientRect(), fr = $('#scan-frame').getBoundingClientRect();
  const scale = Math.max(vr.width / video.videoWidth, vr.height / video.videoHeight);
  const ox = (video.videoWidth * scale - vr.width)/2, oy = (video.videoHeight * scale - vr.height)/2;
  const sx = (fr.left - vr.left + ox)/scale, sy = (fr.top - vr.top + oy)/scale, sw = fr.width/scale, sh = fr.height/scale;
  const canvas = document.createElement('canvas'); canvas.width = Math.round(sw); canvas.height = Math.round(sh); canvas.getContext('2d').drawImage(video,sx,sy,sw,sh,0,0,canvas.width,canvas.height);
  stopCamera(false); recognize(canvas.toDataURL('image/png'));
});
$('#upload-button').addEventListener('click', () => { if (!busy) $('#file-input').click(); });
$('#file-input').addEventListener('change', async e => {
  const file = e.target.files[0]; e.target.value = ''; if (!file || busy) return;
  if (!['image/jpeg','image/png','image/webp'].includes(file.type)) { toast('Choose a JPG, PNG or WebP image.'); return; }
  if (file.size > 12 * 1024 * 1024) { toast('Please choose an image smaller than 12 MB.'); return; }
  const url = URL.createObjectURL(file);
  try { const img = new Image(); img.src = url; await img.decode(); if (img.naturalWidth * img.naturalHeight > 60000000) throw Error(); const canvas = document.createElement('canvas'); const scale = Math.min(1,2200 / Math.max(img.naturalWidth,img.naturalHeight)); canvas.width = img.naturalWidth*scale; canvas.height = img.naturalHeight*scale; canvas.getContext('2d').drawImage(img,0,0,canvas.width,canvas.height); stopCamera(false); await recognize(canvas.toDataURL('image/png')); }
  catch { toast('That image couldn’t be opened. Please try another photo.'); }
  finally { URL.revokeObjectURL(url); }
});
function loadOCR() { if (window.Tesseract) return Promise.resolve(); return new Promise((resolve,reject) => { const script = document.createElement('script'); script.src = 'https://cdn.jsdelivr.net/npm/tesseract.js@5.1.1/dist/tesseract.min.js'; script.onload = resolve; script.onerror = () => { script.remove(); reject(Error('Recognition needs an internet connection to download its engine. Try again or add the details manually.')); }; document.head.append(script); }); }
function parseCard(text) {
  const lines = text.split('\n').map(l => l.trim()).filter(Boolean);
  const email = (text.match(/[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}/i) || [''])[0];
  const phone = (text.match(/(?:\+?\d[\d ().-]{7,}\d)/) || [''])[0].trim();
  const website = (text.replace(email,'').match(/(?:https?:\/\/|www\.)[^\s]+|\b[a-z0-9-]+\.(?:com|org|net|io|co|design|studio|example)\b(?:\/[^\s]*)?/i) || [''])[0];
  const titleLine = lines.find(l => /\b(director|manager|founder|engineer|designer|president|officer|consultant|partner|sales|marketing|developer|lead|architect|specialist|ceo|cto|cfo|owner)\b/i.test(l)) || '';
  const candidates = lines.filter(l => l !== titleLine && !/[\d@]|https?:|www\.|\.(com|net|org|example|io|co)\b/i.test(l) && l.length > 3 && l.length < 65);
  const name = candidates.find(l => l.split(/\s+/).length >= 2 && !/\b(studio|inc|llc|ltd|company|solutions|group|design|agency)\b/i.test(l)) || '';
  const company = candidates.find(l => l !== name && /\b(studio|inc|llc|ltd|company|solutions|group|design|agency)\b/i.test(l)) || candidates.find(l => l !== name) || '';
  return {name,company,title:titleLine,email,phone,website,event:currentEvent,notes:''};
}
async function recognize(data) {
  if (busy) return; busy = true; imageData = data;
  $('#camera-button').disabled = true; $('#upload-button').disabled = true; $('#try-sample').disabled = true; $('#switch-camera').hidden = true; $('#stop-camera').hidden = true;
  $('#camera').hidden = true; $('#sample-card').hidden = true; $('#preview-label').hidden = true; $('#captured').src = data; $('#captured').hidden = false; $('#scan-laser').hidden = false;
  $('#scanner-status').textContent = 'READING YOUR CARD'; $('#camera-hint').textContent = 'Preparing recognition. The first scan may take a little longer…';
  try {
    await loadOCR();
    worker = await Tesseract.createWorker('eng', 1, {logger:m => { if (m.status === 'recognizing text') $('#camera-hint').textContent = `Reading card details… ${Math.round(m.progress*100)}%`; }});
    const result = await worker.recognize(data);
    if (!result.data.text.trim()) { toast('No text found. Try a sharper photo, or enter the details below.'); openContact({},true); }
    else openContact(parseCard(result.data.text),true);
  } catch (error) { toast(error.message || 'We couldn’t read this card. You can enter the details manually.'); openContact({},true); }
  finally { if (worker) { await worker.terminate().catch(() => {}); worker = null; } busy = false; $('#camera-button').disabled = false; $('#upload-button').disabled = false; $('#try-sample').disabled = false; $('#scan-laser').hidden = true; resetCameraUI(); $('#camera-hint').textContent = 'Ready for your next connection.'; }
}
$('#try-sample').addEventListener('click', async () => {
  if (busy) return; stopCamera(false);
  const canvas = document.createElement('canvas'); canvas.width = 1200; canvas.height = 680; const c = canvas.getContext('2d'); c.fillStyle = '#ffffff'; c.fillRect(0,0,1200,680); c.fillStyle='#18392a'; c.font='bold 45px Arial'; c.fillText('ARC STUDIO',75,105); c.font='bold 68px Arial'; c.fillText('Alex Morgan',75,280); c.font='34px Arial'; c.fillText('Design Director',75,345); c.font='29px Arial'; c.fillText('alex@arcstudio.example',75,470); c.fillText('+1 (415) 555-0142',75,525); c.fillText('arcstudio.example',75,580); await recognize(canvas.toDataURL('image/png'));
});
window.addEventListener('pagehide', () => { stopCamera(false); if (worker) worker.terminate(); });
document.addEventListener('visibilitychange', () => { if (document.hidden) stopCamera(); });
init();
