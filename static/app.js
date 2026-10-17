'use strict';
const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const icon = name => `<svg aria-hidden="true"><use href="#i-${name}"/></svg>`;
const escapeHTML = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const text = escapeHTML;
const storage = {get(key, fallback) {try {return localStorage.getItem(key) || fallback;} catch {return fallback;}}, set(key, value) {try {localStorage.setItem(key, value);} catch {}}};
const state = {profileId:Number(storage.get('netflix-profile', '1')), profiles:[], titles:[], saved:[], progress:[], profile:null, feature:'dune', query:'', genre:'', searchOpen:false, managing:false};
const video = $('#videoPlayer');
let toastTimer, searchTimer, searchSequence = 0, playing = null, lastSaved = 0, closingPlayer = false;
let detailId = null, detailSeason = 1, previousFocus = null;

function toast(message) {
  clearTimeout(toastTimer); $('#toast').textContent = message; $('#toast').hidden = false;
  toastTimer = setTimeout(() => $('#toast').hidden = true, 3400);
}
async function api(path, options = {}) {
  const separator = path.includes('?') ? '&' : '?';
  const response = await fetch(`/api/${path}${separator}profile=${state.profileId}`, {...options, headers:{...(options.body instanceof FormData ? {} : {'Content-Type':'application/json'}), ...options.headers}});
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'Something went wrong. Please try again.');
  return data;
}
function report(error) {toast(error.message || 'Something went wrong. Please try again.');}
function titleById(id) {return state.titles.find(t => t.id === id);}
function saved(id) {return state.saved.find(s => s.title_id === id) || {};}
function episodeLabel(item,key) {const episode=item.uploaded?item.episodes.find(e=>e.key===key):null;return episode?`S${episode.season}:E${episode.episode}`:`Episode ${key}`;}
function latestProgress(id) {return state.progress.find(p => p.title_id === id);}
function openDialog(dialog) {previousFocus = document.activeElement; if (!dialog.open) dialog.showModal();}
function closeDialog(dialog) {dialog.close(); if (previousFocus?.isConnected) previousFocus.focus({preventScroll:true});}
function route() {return ['home','series','movies','new','list','uploads'].includes(location.hash.slice(1)) ? location.hash.slice(1) : 'home';}
function setRoute(value) {
  if (location.hash === `#${value}`) render();
  else location.hash = value;
}
async function refreshState() {
  const result = await api('state'); Object.assign(state, {saved:result.saved, progress:result.progress, profile:result.profile});
  updateProfileUI();
}
async function loadProfile() {
  const [catalog, result] = await Promise.all([api('catalog'), api('state')]);
  state.titles = catalog.titles; state.saved = result.saved; state.progress = result.progress; state.profile = result.profile;
  $('#genreSelect').innerHTML = '<option value="">All genres</option>' + catalog.genres.map(g => `<option>${text(g)}</option>`).join('');
  $('#genreSelect').value = state.genre;
  if (!titleById(state.feature)) state.feature = state.titles[0]?.id;
  updateProfileUI(); updateHero(); render();
}
function updateProfileUI() {
  if (!state.profile) return;
  $('#headerAvatar').className = `avatar ${state.profile.color}`;
  $('#profileButton').setAttribute('aria-label', `${state.profile.name}: switch or manage profiles`);
  $('#libraryLink').hidden = !!state.profile.kids;
  $('#kidsButton').textContent = state.profile.kids ? 'Kids mode' : 'Kids';
  const count = state.saved.filter(s => s.in_list).length;
  $('#listCount').textContent = count; $('#listCount').hidden = !count;
}
function updateHero() {
  const item = titleById(state.feature); if (!item) return;
  $('#heroArt').style.backgroundImage = `url("${item.backdrop}")`;
  $('#heroTitle').innerHTML = item.id === 'dune' ? '<span class="dune-lettering">DUNE</span><span class="dune-subtitle">PART TWO</span>' : `<span class="feature-name">${text(item.title)}</span>`;
  $('#heroMeta').innerHTML = meta(item);
  const lines = {'dune':'Beyond fear. Beyond destiny.', 'stranger-things':'Every ending has a beginning.', 'interstellar':'Love is the one thing that transcends time.'};
  $('#heroTagline').textContent = lines[item.id] || 'A new adventure starts here.';
  $('#heroDescription').textContent = item.description;
  $('.hero-trending > span:last-child').textContent = item.type === 'series' ? '#1 in TV Shows today' : '#1 in Movies today';
  $('#heroAge').textContent = item.rating === 'TV-MA' ? '18+' : item.rating === 'PG' ? '7+' : '13+';
  $('#heroSave').innerHTML = icon(saved(item.id).in_list ? 'check' : 'plus');
  $('#heroSave').setAttribute('aria-label', `${saved(item.id).in_list ? 'Remove' : 'Add'} ${item.title} ${saved(item.id).in_list ? 'from' : 'to'} My List`);
  $('#heroSave').setAttribute('aria-pressed', !!saved(item.id).in_list);
  $$('.hero-dot').forEach(d => {d.classList.toggle('active', d.dataset.feature === item.id); d.setAttribute('aria-pressed', d.dataset.feature === item.id); d.hidden = !titleById(d.dataset.feature);});
}
function meta(item) {
  return `<span class="match">${item.match}% match</span><span>${item.year}</span><span class="rating">${item.rating}</span><span>${item.duration}</span>${item.uploaded ? '<span class="quality">YOUR VIDEO</span>' : '<span class="quality">4K</span>'}`;
}
function addButton(item) {
  const inList = !!saved(item.id).in_list;
  return `<button class="mini-add ${inList ? 'selected' : ''}" data-save="${item.id}" aria-label="${inList ? 'Remove' : 'Add'} ${text(item.title)} ${inList ? 'from' : 'to'} My List" aria-pressed="${inList}">${icon(inList ? 'check' : 'plus')}</button>`;
}
function card(item, {rank, progress, grid = false} = {}) {
  const done = progress && progress.duration > 0 ? Math.min(100, progress.position / progress.duration * 100) : 0;
  let displayTitle = item.title;
  if (item.id === 'dune') displayTitle = 'Dune';
  return `<article class="title-card ${rank ? 'ranked-card' : ''}" data-title="${item.id}">
    ${rank ? `<span class="rank-number" aria-hidden="true">${rank}</span>` : ''}
    <button class="card-cover" ${progress ? `data-play="${item.id}" data-episode="${progress.episode}"` : `data-detail="${item.id}"`} aria-label="${progress ? 'Continue watching' : 'More about'} ${text(item.title)}${rank ? `, number ${rank} in the collection` : ''}">
      <img src="${progress ? item.backdrop : item.image}" alt="" loading="lazy" width="300" height="200">
      ${item.original ? '<span class="card-n" aria-hidden="true">N</span>' : ''}
      ${['dune','squid-game','wednesday'].includes(item.id) && !rank && !progress ? '<span class="card-badge">TOP 10</span>' : ''}
      ${progress ? `<span class="resume-label">${icon('play')}</span>` : ''}
      <span class="card-art-title">${text(displayTitle)}</span>
    </button>
    ${progress ? `<button class="remove-progress" data-remove-progress="${item.id}" aria-label="Remove ${text(item.title)} from Continue Watching">${icon('close')}</button><div class="progress-line"><span style="width:${done}%"></span></div>` : ''}
    ${grid ? `<button class="card-name" data-detail="${item.id}">${text(item.title)}</button>` : ''}
    <div class="card-bottom"><p>${progress ? `<b>${item.type === 'series' ? episodeLabel(item,progress.episode) : item.uploaded ? 'Video' : 'Preview'}</b><span>·</span>${Math.max(1, Math.ceil((progress.duration-progress.position)/60))}m left` : `<b>${text(item.genres[0])}</b><span>·</span>${item.type === 'series' ? item.duration : item.year}`}</p>${addButton(item)}</div>
  </article>`;
}
function collection(name, items, options = {}) {
  if (!items.length) return '';
  return `<section class="collection"><div class="collection-heading"><div class="collection-title"><h2>${text(name)}</h2>${options.tag ? `<span class="collection-tag">${text(options.tag)}</span>` : ''}</div><div class="collection-heading-right">${options.route ? `<a class="see-all" href="#${options.route}">Explore all ${icon('chevron')}</a>` : ''}<div class="row-arrows"><button class="row-arrow prev" data-scroll="-1" aria-label="Scroll ${text(name)} left">${icon('chevron')}</button><button class="row-arrow" data-scroll="1" aria-label="Scroll ${text(name)} right">${icon('chevron')}</button></div></div></div><div class="card-row ${options.ranked ? 'top-row' : ''} ${options.continue ? 'continue-row' : ''}">${items.map((item,i) => card(item, {rank:options.ranked ? i+1 : null, progress:options.continue ? latestProgress(item.id) : null})).join('')}</div></section>`;
}
function emptyState(title, description, symbol = 'search') {
  return `<div class="empty-state">${icon(symbol)}<h2>${text(title)}</h2><p>${text(description)}</p><button class="button button-white" data-reset>Explore the catalog</button></div>`;
}
function renderHome() {
  const all = state.titles;
  const pick = ids => ids.map(titleById).filter(Boolean);
  const continuing = [...new Set(state.progress.filter(p => p.position > .5 && p.position < p.duration - 1).map(p => p.title_id))].map(titleById).filter(Boolean);
  const preferredGenres = state.saved.filter(s => s.liked).map(s => titleById(s.title_id)?.genres[0]).filter(Boolean);
  const recommended = preferredGenres.length ? [...all].sort((a,b) => Number(preferredGenres.includes(b.genres[0])) - Number(preferredGenres.includes(a.genres[0]))) : pick(['stranger-things','wednesday','breaking-bad','dark','queens-gambit','arcane','one-piece','squid-game']);
  let html = collection(`Continue watching for ${state.profile.name}`, continuing, {continue:true});
  html += collection('From your library',all.filter(t=>t.uploaded),{tag:'YOUR UPLOADS',route:'uploads'});
  html += collection('Your next obsession', recommended.length ? recommended : all, {tag:'PICKED FOR YOU',route:'series'});
  html += collection('Trending now', pick(['dune','squid-game','interstellar','oppenheimer','batman','spiderverse','inception','knives-out']), {route:'new'});
  html += collection('Top 10 to lose yourself in', pick(['wednesday','stranger-things','dune','squid-game','dark','breaking-bad','arcane','queens-gambit','one-piece','peaky-blinders']), {ranked:true,tag:'THE MOST WATCHED',route:'new'});
  html += collection('Out of this world', all.filter(t => t.genres.includes('Sci-Fi') || t.genres.includes('Fantasy')), {route:'movies'});
  html += collection('Only on Netflix', all.filter(t => t.original), {tag:'UNFORGETTABLE ORIGINALS',route:'series'});
  if (state.profile.kids) html = collection('Big adventures for little explorers', all, {tag:'KIDS & FAMILY'});
  $('#collections').innerHTML = html;
}
async function render() {
  if (!state.profile) return;
  const seq = ++searchSequence;
  const page = state.searchOpen ? 'home' : route(), browse = page !== 'home' || state.searchOpen || state.genre;
  document.body.classList.toggle('browse-mode', !!browse);
  document.body.classList.toggle('search-open', state.searchOpen);
  $('#hero').hidden = !!browse;
  $('#uploadManager').hidden = page !== 'uploads';
  $('#collections').hidden = page === 'uploads';
  $('#discoveryBar').hidden = page === 'uploads';
  $('#browseHeading').hidden = !browse;
  $('#editorialBanner').hidden = !!browse || !!state.profile.kids;
  $$('.main-nav a').forEach(a => a.classList.toggle('active', a.dataset.nav === page));
  const titleMap = {home:'Discover your next favorite',series:'TV Shows',movies:'Movies',new:'New & Popular',list:'My List',uploads:'Your video library'};
  $('#browseTitle').textContent = state.searchOpen ? state.query ? `Results for “${state.query}”` : 'What are you in the mood for?' : state.genre || titleMap[page];
  $('#browseEyebrow').textContent = page === 'list' ? 'THE STORIES YOU’RE SAVING FOR LATER' : state.profile.kids ? 'LITTLE VIEWERS, BIG ADVENTURES' : 'FIND YOUR NEXT FAVORITE';
  if (page === 'uploads') {$('#browseEyebrow').textContent = 'A HOME FOR YOUR OWN STORIES';uploadManager.render();return;}
  if (!browse) {renderHome(); updateHero(); return;}
  let items = [...state.titles];
  const params = new URLSearchParams();
  if (state.query) params.set('q', state.query);
  if (state.genre) params.set('genre', state.genre);
  if (page === 'series') params.set('type', 'series');
  if (page === 'movies') params.set('type', 'movie');
  try {
    if (params.size) {
      const data = await api(`catalog?${params}`); if (seq !== searchSequence) return; items = data.titles;
    }
    if (page === 'list') items = items.filter(t => saved(t.id).in_list);
    if (page === 'new') items.sort((a,b) => b.year - a.year);
    $('#browseSubtitle').textContent = `${items.length} ${items.length === 1 ? 'title' : 'titles'}${state.genre ? ` in ${state.genre}` : ''}${page === 'list' ? ` saved for ${state.profile.name}` : ' · A new world is just a play away.'}`;
    $('#collections').innerHTML = items.length ? `<div class="catalog-grid">${items.map(item => card(item,{grid:true})).join('')}</div>` : page === 'list' && !state.query && !state.genre ? emptyState('Your next great watch belongs here.', 'Tap + on any title to save it. Your list is yours to curate.', 'plus') : emptyState('No plot twists here. No results, either.', 'Try a different title, actor, or genre. There’s a whole world of stories to explore.');
  } catch(error) {if (seq === searchSequence) report(error);}
}
async function toggleSave(id) {
  const item = titleById(id); if (!item) return;
  const value = !saved(id).in_list;
  try {
    await api(`saved/${id}`, {method:'PUT',body:JSON.stringify({in_list:value})});
    await refreshState(); render(); syncDetailActions();
    toast(value ? `Added ${item.title} to My List` : `Removed ${item.title} from My List`);
  } catch(error) {report(error);}
}
async function toggleLike(id) {
  try {
    const value = !saved(id).liked;
    await api(`saved/${id}`,{method:'PUT',body:JSON.stringify({liked:value})});
    await refreshState(); syncDetailActions(); render();
    toast(value ? 'Liked! We’ll move more stories like this into your picks.' : 'Rating removed');
  } catch(error) {report(error);}
}
function syncDetailActions() {
  if (!detailId) return;
  const save = $('[data-detail-save]', $('#detailDialog'));
  const like = $('[data-like]', $('#detailDialog'));
  if (save) {save.innerHTML = icon(saved(detailId).in_list ? 'check' : 'plus'); save.setAttribute('aria-pressed',!!saved(detailId).in_list); save.setAttribute('aria-label', saved(detailId).in_list ? 'Remove from My List' : 'Add to My List');}
  if (like) {like.classList.toggle('selected',!!saved(detailId).liked);like.setAttribute('aria-pressed',!!saved(detailId).liked);like.setAttribute('aria-label',saved(detailId).liked ? 'Remove like' : 'Like this title');}
}
function showDetails(id) {
  const item = titleById(id); if (!item) return;
  detailId = id; detailSeason = item.uploaded ? item.episodes[0].season : 1;
  const similar = state.titles.filter(t => t.id !== id && t.genres.some(g => item.genres.includes(g))).slice(0,3);
  $('#detailDialog').innerHTML = `<button class="circle-button dialog-close" data-close-detail aria-label="Close title details">${icon('close')}</button><div class="detail-visual"><img src="${item.backdrop}" alt=""><div class="detail-visual-content"><div class="eyebrow">${item.original ? 'N · A NETFLIX ORIGINAL' : 'YOUR NEXT GREAT WATCH'}</div><h2>${text(item.title)}</h2><div class="detail-actions"><button class="button button-white" data-play="${id}">${icon('play')}${latestProgress(id)?.position > .5 ? item.uploaded ? 'Resume' : 'Resume preview' : item.uploaded ? 'Play video' : 'Play preview'}</button><button class="circle-button" data-detail-save="${id}" aria-label="Add to My List"></button><button class="circle-button" data-like="${id}" aria-label="Like this title">${icon('heart')}</button></div></div></div><div class="detail-body"><div class="detail-overview"><div><div class="hero-meta">${meta(item)}</div><p class="detail-description">${text(item.description)}</p></div><div class="detail-facts"><p><span>Cast: </span>${text(item.cast)}</p><p><span>Genres: </span>${text(item.genres.join(', '))}</p><p><span>This story is: </span>${item.genres.includes('Thriller') ? 'Suspenseful, gripping, unforgettable' : 'Immersive, imaginative, unforgettable'}</p></div></div><p class="demo-note">${item.uploaded ? 'FROM YOUR LIBRARY · This title plays your uploaded video. Watchlists, likes, and viewing progress are saved for this profile.' : 'CLASSROOM PREVIEW · Every built-in title plays the openly licensed Sintel trailer. ' + (item.type === 'series' ? 'Episode navigation below is simulated; progress is saved separately for each preview chapter.' : 'Your list, likes, and viewing progress are saved for this profile.')}</p>${item.type === 'series' ? `<div class="episodes-heading"><h3>Episodes ${item.uploaded ? '' : '<small class="preview-label">DEMO CHAPTERS</small>'}</h3><select id="seasonSelect" aria-label="Season">${(item.uploaded ? [...new Set(item.episodes.map(e=>e.season))] : Array.from({length:item.seasons},(_,i)=>i+1)).map(season => `<option value="${season}">Season ${season}</option>`).join('')}</select></div><div id="episodes"></div>` : ''}${similar.length ? `<h3 class="related-heading">More like this</h3><div class="related-row">${similar.map(t => card(t)).join('')}</div>` : ''}</div>`;
  syncDetailActions(); if (item.type === 'series') renderEpisodes();
  $('#detailDialog').scrollTop = 0; openDialog($('#detailDialog'));
}
function renderEpisodes() {
  const item = titleById(detailId); if (!item) return;
  const names = ['The beginning','A world beyond','Into the unknown','The turning point','An unexpected alliance','A new horizon'];
  if(item.uploaded){
    $('#episodes').innerHTML=item.episodes.filter(e=>e.season===detailSeason).map(e=>`<button class="episode" data-play="${item.id}" data-episode="${e.key}"><span class="episode-number">${e.episode}</span><span class="episode-thumbnail"><img src="${item.image}" alt="">${icon('play')}</span><span class="episode-info"><b>${text(e.episode_title || 'Episode '+e.episode)}</b><p>Season ${e.season} · Your uploaded video</p></span><span class="episode-duration">${Math.ceil(e.duration/60)}m</span></button>`).join('');return;
  }
  $('#episodes').innerHTML = names.map((name,i) => {
    const number = (detailSeason-1)*6+i+1;
    const progress = state.progress.find(p => p.title_id === item.id && p.episode === number);
    return `<button class="episode" data-play="${item.id}" data-episode="${number}"><span class="episode-number">${i+1}</span><span class="episode-thumbnail"><img src="${item.backdrop}" alt="" loading="lazy">${icon('play')}</span><span class="episode-info"><b>${name}</b><p>Season ${detailSeason} · Open-film preview ${progress?.position > .5 ? '· Continue watching' : '· Start a new chapter'}</p></span><span class="episode-duration">Sintel preview</span></button>`;
  }).join('');
}
async function playTitle(id, episode) {
  const item = titleById(id); if (!item) return;
  if (playing) await persistProgress();
  const recent = latestProgress(id);
  const requested = Number(episode) || recent?.episode || 1;
  const uploadedEpisode = item.uploaded ? item.episodes.find(e=>e.key===requested) || item.episodes[0] : null;
  const ep = uploadedEpisode?.key || requested;
  video.pause();
  playing = null;
  video.removeAttribute('src'); video.load();
  playing = {id, episode:ep, profile:state.profileId, item};
  const progress = state.progress.find(p => p.title_id === id && p.episode === ep);
  if ($('#detailDialog').open) $('#detailDialog').close();
  $('#notificationPanel').hidden = true;
  $('#playerHeading').textContent = `${item.title}${item.type === 'series' ? ` · S${uploadedEpisode?.season || Math.ceil(ep/6)}:E${uploadedEpisode?.episode || (ep-1)%6+1}` : ''}`;
  $('#playingTitle').textContent = item.title;
  $('#nextEpisode').hidden = item.type !== 'series' || (item.uploaded ? item.episodes.findIndex(e=>e.key===ep) >= item.episodes.length-1 : ep >= item.seasons * 6);
  $('#playerBadge').textContent = item.uploaded ? 'YOUR LIBRARY' : 'DEMO SCREENING';
  $('#playerCredits').textContent = item.uploaded ? 'Playing your uploaded video · Progress is saved to this profile.' : 'Sintel trailer · Blender Foundation · CC BY 3.0. Commercial titles use this open-film preview.';
  if(item.uploaded) $('#demoCaptions').removeAttribute('src');else $('#demoCaptions').src='/static/video/credits.vtt';
  $('#playerError').hidden = true;
  $('#playerError').textContent = item.uploaded ? 'This browser could not play the uploaded video. Try an MP4 with H.264/AAC or a supported WebM codec.' : 'We couldn’t play this preview. Please try again or check your browser’s video support.';
  video.src = item.uploaded ? `${uploadedEpisode.video_url}?profile=${state.profileId}` : '/static/video/sintel-trailer.mp4'; video.load();
  video.playbackRate = Number($('#playbackSpeed').value);
  video.onloadedmetadata = () => {
    if (progress && progress.position < video.duration - 1) video.currentTime = progress.position;
    if (state.profile.autoplay) video.play().catch(() => {});
  };
  lastSaved = 0; openDialog($('#playerDialog'));
}
async function persistProgress() {
  if (!playing || !Number.isFinite(video.duration) || video.duration <= 0) return;
  const current = {...playing};
  const payload = {episode:current.episode,position:Math.min(video.currentTime,video.duration),duration:video.duration};
  try {
    const response = await fetch(`/api/progress/${current.id}?profile=${current.profile}`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload),keepalive:true});
    if (!response.ok) throw new Error('Your playback progress could not be saved.');
    const previous = state.progress.findIndex(p => p.title_id === current.id && p.episode === current.episode);
    if (previous >= 0) state.progress.splice(previous,1);
    state.progress.unshift({title_id:current.id, ...payload});
  } catch(error) {report(error);}
}
async function closePlayer() {
  if (closingPlayer) return; closingPlayer = true;
  video.pause(); await persistProgress(); playing = null;
  video.removeAttribute('src'); video.load();
  closeDialog($('#playerDialog')); render(); closingPlayer = false;
}
function showProfiles(managing = false) {
  state.managing = managing;
  $('#profilesDialog').innerHTML = `<button class="circle-button dialog-close" data-close-profiles aria-label="Close profiles">${icon('close')}</button><div class="eyebrow">YOUR WORLD. YOUR STORIES.</div><h2>${managing ? 'Make it your own.' : 'Who’s watching?'}</h2><p class="profile-subtitle">${managing ? 'Choose a profile to edit its name, avatar, or preferences.' : 'A little something for every version of you.'}</p><div class="profile-options">${state.profiles.map(p => `<button class="profile-tile" data-${managing ? 'edit' : 'choose'}-profile="${p.id}"><span class="avatar ${p.color}"><span class="avatar-face"></span></span>${managing ? `<span class="profile-edit-overlay">${icon('edit')}</span>` : ''}<span class="profile-name">${text(p.name)}${p.kids ? ' · Kids' : ''}</span></button>`).join('')}${state.profiles.length < 5 ? `<button class="profile-tile" data-add-profile><span class="profile-add">${icon('plus')}</span><span class="profile-name">Add profile</span></button>` : ''}</div><button class="profile-manage" data-manage-profiles>${icon(managing ? 'check' : 'edit')}${managing ? 'Done' : 'Manage profiles'}</button>`;
  openDialog($('#profilesDialog'));
}
function editProfile(id) {
  const profile = state.profiles.find(p => p.id === Number(id));
  $('#profilesDialog').innerHTML = `<button class="circle-button dialog-close" data-close-profiles aria-label="Close profiles">${icon('close')}</button><div class="eyebrow">A SPACE THAT’S ALL YOURS</div><h2>${profile ? 'Edit profile' : 'Add a profile'}</h2><p class="profile-subtitle">Keep your favorites and your next watch in one place.</p><form class="profile-form" id="profileForm" data-id="${profile?.id || ''}"><label for="profileName">Profile name</label><input id="profileName" name="name" type="text" placeholder="A fictional name" value="${text(profile?.name || '')}" maxlength="20" required autocomplete="off"><label style="margin-top:20px">Choose your avatar</label><div class="profile-colors">${['blue','purple','orange','green','red'].map(color => `<button type="button" class="color-choice ${(profile?.color || 'blue') === color ? 'selected' : ''}" data-color="${color}" aria-label="${color} avatar" aria-pressed="${(profile?.color || 'blue') === color}"><span class="avatar ${color}"><span class="avatar-face"></span></span></button>`).join('')}</div><label class="check-label"><input type="checkbox" name="kids" ${profile?.kids ? 'checked' : ''}>Kids profile — show family-friendly titles only</label><label class="check-label"><input type="checkbox" name="autoplay" ${!profile || profile.autoplay ? 'checked' : ''}>Start previews automatically when I press Play</label><p class="form-error" id="profileError" role="alert" hidden></p><div class="profile-form-actions"><button class="button button-white" type="submit">Save profile</button><button class="button button-glass" type="button" data-profile-cancel>Cancel</button>${profile && state.profiles.length > 1 ? `<button type="button" class="delete-profile" data-delete-profile="${profile.id}">Delete profile</button>` : ''}</div></form>`;
  $('#profileName').focus();
}
async function chooseProfile(id) {
  try {
    uploadManager.pause();
    state.profileId = Number(id); storage.set('netflix-profile',state.profileId);
    state.query = '';state.genre = '';state.feature = 'dune';state.searchOpen = false; $('#searchBar').hidden = true;$('#searchInput').value = '';
    await loadProfile();closeDialog($('#profilesDialog'));setRoute('home');window.scrollTo(0,0);
    toast(`Welcome, ${state.profile.name}`);
  } catch(error) {report(error);}
}
async function saveProfile(event) {
  event.preventDefault();
  const form = event.target;
  const button = $('button[type=submit]', form);button.disabled = true;
  try {
    const data = {name:form.elements.name.value.trim(), color:$('.color-choice.selected',form).dataset.color,kids:form.elements.kids.checked,autoplay:form.elements.autoplay.checked};
    const id = form.dataset.id;
    const result = await api(id ? `profiles/${id}` : 'profiles',{method:id ? 'PATCH' : 'POST',body:JSON.stringify(data)});
    if (!id && !data.autoplay) await api(`profiles/${result.id}`,{method:'PATCH',body:JSON.stringify({autoplay:false})});
    state.profiles = (await api('profiles')).profiles;
    if (id && Number(id) === state.profileId) await loadProfile();
    showProfiles();toast('Profile saved');
  } catch(error) {$('#profileError').textContent = error.message;$('#profileError').hidden = false;} finally {button.disabled = false;}
}
function toggleSearch(open) {
  state.searchOpen = open;$('#searchBar').hidden = !open;
  if (open) {$('#searchInput').focus();window.scrollTo(0,0);} else {state.query = '';$('#searchInput').value = '';}
  render();
}
function resetBrowse() {
  state.query = '';state.genre = '';$('#genreSelect').value = '';toggleSearch(false);setRoute('home');window.scrollTo(0,0);
}

document.addEventListener('click', async event => {
  const target = event.target.closest('button, a');if (!target) return;
  if (target.dataset.detail) {showDetails(target.dataset.detail);$('#notificationPanel').hidden = true;}
  if (target.dataset.play) await playTitle(target.dataset.play,target.dataset.episode);
  if (target.dataset.save || target.dataset.detailSave) {target.disabled = true;await toggleSave(target.dataset.save || target.dataset.detailSave);target.disabled = false;}
  if (target.dataset.like) {target.disabled = true;await toggleLike(target.dataset.like);target.disabled = false;}
  if (target.dataset.scroll) {const row = $('.card-row',target.closest('.collection'));row.scrollBy({left:Number(target.dataset.scroll)*row.clientWidth*.85,behavior:'smooth'});}
  if (target.hasAttribute('data-reset')) resetBrowse();
  if (target.hasAttribute('data-close-detail')) closeDialog($('#detailDialog'));
  if (target.hasAttribute('data-close-profiles')) closeDialog($('#profilesDialog'));
  if (target.hasAttribute('data-manage-profiles')) showProfiles(!state.managing);
  if (target.hasAttribute('data-profile-cancel')) showProfiles(state.managing);
  if (target.hasAttribute('data-add-profile')) editProfile();
  if (target.dataset.editProfile) editProfile(target.dataset.editProfile);
  if (target.dataset.chooseProfile) await chooseProfile(target.dataset.chooseProfile);
  if (target.dataset.color) {$$('.color-choice').forEach(el => {el.classList.toggle('selected',el === target);el.setAttribute('aria-pressed',el === target);});}
  if (target.dataset.feature) {state.feature = target.dataset.feature;updateHero();}
  if (target.dataset.removeProgress) {
    try {await api(`progress/${target.dataset.removeProgress}`,{method:'DELETE'});await refreshState();render();toast('Removed from Continue Watching');} catch(error) {report(error);}
  }
  if (target.dataset.deleteProfile) {
    // A second, explicit action makes removal reviewable without a browser prompt.
    if (!target.dataset.confirmed) {target.dataset.confirmed = 'true';target.textContent = 'Confirm delete';return;}
    try {
      const id = Number(target.dataset.deleteProfile);await api(`profiles/${id}`,{method:'DELETE'});
      state.profiles = (await api('profiles')).profiles;
      if (state.profileId === id) {state.profileId = state.profiles[0].id;storage.set('netflix-profile',state.profileId);await loadProfile();}
      showProfiles(true);toast('Profile deleted');
    } catch(error) {report(error);}
  }
  if (target.dataset.nav) {state.genre = '';$('#genreSelect').value = '';if(state.searchOpen) toggleSearch(false);window.scrollTo(0,0);}
});
document.addEventListener('submit', event => {if (event.target.id === 'profileForm') saveProfile(event);});
document.addEventListener('change', event => {if (event.target.id === 'seasonSelect') {detailSeason = Number(event.target.value);renderEpisodes();}});
$('#heroPlay').addEventListener('click', () => playTitle(state.feature));
$('#heroInfo').addEventListener('click', () => showDetails(state.feature));
$('#heroSave').addEventListener('click', async event => {const button = event.currentTarget;button.disabled = true;await toggleSave(state.feature);button.disabled = false;});
$('#profileButton').addEventListener('click', async () => {try {state.profiles = (await api('profiles')).profiles;showProfiles();}catch(error){report(error);}});
$('#kidsButton').addEventListener('click', async () => {
  if (state.profile?.kids) {showProfiles();return;}
  const kids = state.profiles.find(p => p.kids);if (kids) await chooseProfile(kids.id);else {showProfiles();toast('Add a profile and select Kids mode.');}
});
$('#searchButton').addEventListener('click', () => toggleSearch(!state.searchOpen));
$('#closeSearch').addEventListener('click', () => toggleSearch(false));
$('#searchInput').addEventListener('input', event => {state.query = event.target.value.trim();clearTimeout(searchTimer);searchTimer = setTimeout(render,220);});
$('#genreSelect').addEventListener('change', event => {state.genre = event.target.value;render();});
$('#surpriseButton').addEventListener('click', () => {if (state.titles.length) showDetails(state.titles[Math.floor(Math.random()*state.titles.length)].id);});
$('#notificationButton').addEventListener('click', event => {const panel = $('#notificationPanel');panel.hidden = !panel.hidden;event.currentTarget.setAttribute('aria-expanded',!panel.hidden);$('.notification-dot').hidden = true;});
document.addEventListener('click', event => {if (!event.target.closest('.notification-wrap')) {$('#notificationPanel').hidden = true;$('#notificationButton').setAttribute('aria-expanded',false);}});
$('#movieNight').addEventListener('click', () => {setRoute('movies');window.scrollTo(0,0);});
$('#aboutButton').addEventListener('click', () => openDialog($('#aboutDialog')));
$('#aboutClose').addEventListener('click', () => closeDialog($('#aboutDialog')));
$('#playerClose').addEventListener('click',closePlayer);
$('#playerDialog').addEventListener('cancel',event => {event.preventDefault();closePlayer();});
$('#playbackSpeed').addEventListener('change',event => video.playbackRate = Number(event.target.value));
$('#nextEpisode').addEventListener('click',async () => {if (playing) {const {id,episode,item} = playing;const next = item.uploaded ? item.episodes[item.episodes.findIndex(e=>e.key===episode)+1]?.key : episode+1;if(next) await playTitle(id,next);}});
video.addEventListener('timeupdate', () => {if (playing && video.currentTime-lastSaved >= 5) {lastSaved = video.currentTime;persistProgress();}});
video.addEventListener('pause', () => {if (!closingPlayer) persistProgress();});
video.addEventListener('ended', async () => {await persistProgress();toast(playing?.item.uploaded ? 'Video complete. Explore another story or play the next episode.' : 'Preview complete. Explore another story or choose the next demo chapter.');});
video.addEventListener('error', () => {if (video.hasAttribute('src')) $('#playerError').hidden = false;});
window.addEventListener('pagehide',persistProgress);
window.addEventListener('hashchange',render);
window.addEventListener('scroll', () => $('#header').classList.toggle('scrolled',window.scrollY > 40), {passive:true});
document.addEventListener('keydown',event => {if (event.key === 'Escape' && state.searchOpen && !document.querySelector('dialog[open]')) toggleSearch(false);if(event.key === '/' && !['INPUT','TEXTAREA','SELECT'].includes(document.activeElement.tagName) && !document.querySelector('dialog[open]')) {event.preventDefault();toggleSearch(true);}});
$$('dialog:not(#playerDialog)').forEach(dialog => dialog.addEventListener('click',event => {if(event.target === dialog) {const rect = dialog.getBoundingClientRect();if(event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) closeDialog(dialog);}}));
(async () => {
  try {
    state.profiles = (await api('profiles')).profiles;
    if (!state.profiles.some(p => p.id === state.profileId)) {state.profileId = state.profiles[0].id;storage.set('netflix-profile',state.profileId);}
    await loadProfile();
  } catch(error) {$('#collections').innerHTML = `<div class="empty-state"><h2>We couldn’t set the scene.</h2><p>${text(error.message)}</p><button class="button button-white" onclick="location.reload()">Try again</button></div>`;}
})();
