'use strict';
/* Uploads use persistent server offsets. A page reload only requires reselecting the file. */
const uploadManager = (() => {
  let library = [], pending = [], limits = null, job = null, selectedFile = null, selectedDuration = 0;
  const files = new Map();
  let requestSequence = 0, starting = false, selectionSequence = 0;
  const bytes = value => {if (value < 1024) return `${value} B`; const unit = value >= 1024**3 ? 1024**3 : 1024**2; return `${(value/unit).toFixed(1)} ${unit === 1024**3 ? 'GiB' : 'MiB'}`;};
  const sha256 = async blob => {if(!window.crypto?.subtle) throw new Error('Uploads require HTTPS or localhost. Open the secure site URL and try again.');return [...new Uint8Array(await crypto.subtle.digest('SHA-256',await blob.arrayBuffer()))].map(n=>n.toString(16).padStart(2,'0')).join('');};
  const fingerprint = file => sha256(file.slice(0,65536));
  const mediaURL = url => `${url}${url.includes('?') ? '&' : '?'}profile=${state.profileId}`;
  const dialog = () => $('#uploadDialog');

  async function refresh() {
    const result = await api('library'); library = result.titles; pending = result.uploads; limits = result.storage;
    return result;
  }
  async function render() {
    const sequence = ++requestSequence;
    if (state.profile.kids) {$('#uploadManager').innerHTML = emptyState('A space for the grown-ups.', 'Switch to an adult profile to upload and manage videos.', 'info');return;}
    try {
      await refresh();if (sequence !== requestSequence || route() !== 'uploads') return;
      $('#browseSubtitle').textContent = `${library.length} ${library.length === 1 ? 'title' : 'titles'} · Upload, organize, and watch your own videos.`;
      $('#uploadManager').innerHTML = `<div class="library-toolbar"><div class="library-storage"><span>${icon('grid')} <b>${bytes(limits.used_bytes)}</b> stored${limits.reserved_bytes ? ` · ${bytes(limits.reserved_bytes)} reserved` : ''}</span><small>${bytes(limits.available_bytes)} available · Up to ${bytes(limits.max_video_bytes)} per video</small></div><button class="button button-white" data-new-upload>${icon('plus')}Upload video</button></div><p class="library-sharing">This is a shared classroom library. Upload only videos you have permission to share. All adult profiles can manage this library.</p><div id="uploadActivity"></div>${pending.length ? `<section class="pending-section"><h2>Unfinished uploads</h2><p>Progress is saved on the server. Reselect the same file to pick up where you left off.</p>${pending.map(session => `<div class="pending-upload"><div><b>${text(session.title)}</b><small>${text(session.original_name)} · ${bytes(session.offset)} of ${bytes(session.size)}</small></div><div class="pending-actions"><button class="button button-glass" data-resume-upload="${session.id}">${session.offset === session.size ? 'Finish publishing' : 'Resume'}</button><button class="library-text-button" data-cancel-upload="${session.id}">Cancel upload</button></div></div>`).join('')}</section>` : ''}${library.length ? `<div class="library-titles">${library.map(item => `<article class="library-title"><img src="${item.image}" alt=""><div class="library-title-content"><div class="library-title-heading"><div><span class="eyebrow">${item.type === 'series' ? 'SERIES' : 'MOVIE'} · ${item.rating}${item.family ? ' · FAMILY' : ''}</span><h2>${text(item.title)}</h2></div><button class="button button-white" data-play="${item.id}">${icon('play')}Play</button></div><p>${item.year} · ${text(item.genres.join(' · '))} · ${text(item.duration)} · ${bytes(item.total_bytes)}</p><div class="library-title-actions"><button data-edit-title="${item.id}">${icon('edit')}Edit details</button><button data-upload-target="${item.id}">${icon('plus')}${item.type === 'series' ? 'Add episode' : 'Replace video'}</button><button data-delete-title="${item.id}" class="danger-text">${icon('close')}Delete title</button></div>${item.type === 'series' ? `<details class="library-episodes"><summary>Manage ${item.episodes.length} episodes</summary>${item.episodes.map(e => `<div class="library-episode"><button data-play="${item.id}" data-episode="${e.key}">${icon('play')}<span><b>S${e.season}:E${e.episode} · ${text(e.episode_title || 'Episode '+e.episode)}</b><small>${text(e.original_name)} · ${bytes(e.size)}</small></span></button><div><a href="${mediaURL(e.download_url)}" download>Download</a><button data-replace-title="${item.id}" data-video-id="${e.id}">Replace</button><button class="danger-text" data-delete-video="${e.id}" data-video-title="${item.id}">Remove</button></div></div>`).join('')}</details>` : `<a class="library-download" href="${mediaURL(item.episodes[0].download_url)}" download>Download original video ${icon('down')}</a>`}</div></article>`).join('')}</div>` : `<div class="library-empty"><span class="library-empty-icon">${icon('play')}</span><p class="eyebrow">YOUR LIBRARY STARTS HERE</p><h2>Bring your own stories.</h2><p>Upload a movie, a short film, or episodes of a series. Add a cover and make it part of your collection.</p><button class="button button-white" data-new-upload>${icon('plus')}Upload your first video</button><small>MP4 · M4V · WebM · Resumable uploads</small></div>`}`;
      renderActivity();
    } catch(error) {if(sequence === requestSequence) {$('#uploadManager').innerHTML = `<div class="empty-state"><h2>We couldn’t load your library.</h2><p>${text(error.message)}</p><button class="button button-white" data-retry-library>Try again</button></div>`;}}
  }
  function renderActivity(progressOnly = false) {
    const element = $('#uploadActivity');if(!element) return;
    if (!job) {element.innerHTML='';return;}
    const percent = Math.min(100,Math.floor(job.loaded/job.session.size*100));
    if(progressOnly && $('progress',element)) {
      $('progress',element).value=job.loaded;$('.upload-activity-top>b',element).textContent=percent+'%';$('.upload-activity-bottom>span',element).textContent=bytes(job.loaded)+' / '+bytes(job.session.size);return;
    }
    element.innerHTML = `<section class="upload-activity ${job.error ? 'upload-has-error' : ''}" aria-label="Upload progress"><div class="upload-activity-top"><div><span class="eyebrow">${job.active ? job.loaded >= job.session.size ? 'VALIDATING & PUBLISHING' : 'UPLOADING' : 'UPLOAD PAUSED'}</span><h3>${text(job.session.title)}</h3></div><b>${percent}%</b></div><progress value="${job.loaded}" max="${job.session.size}" aria-label="Video upload progress"></progress><div class="upload-activity-bottom"><span>${bytes(job.loaded)} / ${bytes(job.session.size)}${job.error ? ` · ${text(job.error)}` : ''}</span><button class="button button-glass" ${job.active ? 'data-pause-upload' : `data-resume-upload="${job.session.id}"`}>${job.active ? 'Pause upload' : 'Resume upload'}</button></div><p role="status">${job.active ? 'Each completed chunk is saved. You can pause and return later.' : 'Your uploaded chunks are safe. Resume here or reselect this file after reopening the page.'}</p></section>`;
  }
  function pause() {
    if (job) {job.active=false;job.xhr?.abort();renderActivity();}
  }
  function metadataFields(item = {}) {
    return `<div class="upload-form-grid"><label>Title<input name="title" maxlength="120" required value="${text(item.title || '')}" placeholder="Give your story a name"></label><label>Year<input name="year" type="number" min="1888" max="2100" required value="${item.year || new Date().getFullYear()}"></label><label>Genres<input name="genres" maxlength="180" required value="${text(item.genres?.join(', ') || 'Independent')}" placeholder="Drama, Adventure"></label><label>Rating<select name="rating">${['NR','G','PG','PG-13','R','TV-Y','TV-Y7','TV-G','TV-14','TV-MA'].map(r=>`<option ${item.rating===r?'selected':''}>${r}</option>`).join('')}</select></label><label class="upload-wide">Description<textarea name="description" rows="3" maxlength="3000" placeholder="What is this story about?">${text(item.description || '')}</textarea></label><label class="upload-wide">Cast or creator<input name="cast" maxlength="500" value="${text(item.cast || '')}" placeholder="Optional"></label></div><label class="check-label"><input type="checkbox" name="family" ${item.family?'checked':''}>Show in Kids profiles (requires a family-friendly rating)</label><label class="upload-file-label">Cover image <span>Optional · JPEG, PNG, or WebP · Up to 5 MiB</span><input type="file" name="poster" accept="image/jpeg,image/png,image/webp"></label>`;
  }
  async function showForm(targetId, replacementId) {
    if (job?.active) {toast('Pause the current upload before starting another.');setRoute('uploads');return;}
    try {await refresh();} catch(error) {report(error);return;}
    const item = library.find(t=>t.id === targetId);
    const replacement = item?.episodes.find(e=>e.id === replacementId);
    selectedFile=null;selectedDuration=0;
    const season = replacement?.season || 1;
    const episode = replacement?.episode || (item?.type === 'series' ? Math.max(0,...item.episodes.filter(e=>e.season===season).map(e=>e.episode))+1 : 1);
    dialog().innerHTML = `<button class="circle-button dialog-close" data-close-upload aria-label="Close upload form">${icon('close')}</button><p class="eyebrow">YOUR VIDEO. YOUR STORY.</p><h2>${item ? item.type === 'movie' || replacement ? 'Replace video' : 'Add an episode' : 'Add to your library'}</h2><p class="upload-form-intro">${item ? text(item.title) : 'Upload a playable video, add the details, and make it yours.'}</p><form id="uploadForm" data-target="${item?.id || ''}"><label class="video-drop-zone" id="videoDropZone"><span class="library-empty-icon">${icon('plus')}</span><b>Select or drop a video</b><span>MP4, M4V, or WebM · Up to ${bytes(limits.max_video_bytes)}</span><input type="file" id="uploadVideoFile" name="video" accept=".mp4,.m4v,.webm,video/mp4,video/webm" required></label><p id="selectedVideoInfo" class="selected-video-info" role="status"></p>${item ? '' : `<label class="upload-kind">Content type<select name="type" id="uploadKind"><option value="movie">Movie / standalone video</option><option value="series">Series / episodes</option></select></label>${metadataFields()}`}<div class="upload-form-grid" id="episodeFields" ${(!item || item.type === 'movie')?'hidden':''}><label>Season<input name="season" type="number" min="1" max="100" value="${season}"></label><label>Episode<input name="episode" type="number" min="1" max="999" value="${episode}"></label><label class="upload-wide">Episode title<input name="episode_title" maxlength="160" value="${text(replacement?.episode_title || '')}" placeholder="Optional"></label></div>${item ? `<label class="check-label"><input type="checkbox" name="replace" ${replacement || item.type === 'movie' ? 'checked' : ''}>Replace an existing video at this movie or episode position. Its viewing progress will reset.</label>` : ''}<p class="form-error" id="uploadFormError" role="alert" hidden></p><div class="upload-form-footer"><span>Uploads are shared with everyone using this demo.</span><button class="button button-white" type="submit">${icon('plus')}Start upload</button></div></form>`;
    openDialog(dialog());
  }
  async function readSelection(file) {
    const sequence=++selectionSequence;
    selectedFile=null;selectedDuration=0;
    const info = $('#selectedVideoInfo');if(!file || !info) return;
    info.textContent='Checking video…';
    try {
      if (!/\.(mp4|m4v|webm)$/i.test(file.name)) throw new Error('Choose an MP4, M4V, or WebM video.');
      if (file.size < 64 || file.size > limits.max_video_bytes) throw new Error(`Choose a video up to ${bytes(limits.max_video_bytes)}.`);
      if (file.size > limits.available_bytes) throw new Error('There is not enough available storage for this video.');
      const duration = await new Promise((resolve,reject)=>{
        const preview=document.createElement('video'),url=URL.createObjectURL(file);
        let timer;
        const cleanup=()=>{clearTimeout(timer);preview.removeAttribute('src');preview.load();URL.revokeObjectURL(url);};
        preview.preload='metadata';preview.onloadedmetadata=()=>{const seconds=preview.duration;cleanup();Number.isFinite(seconds)&&seconds>0&&seconds<=86400?resolve(seconds):reject(new Error('Choose a playable video up to 24 hours long.'));};
        preview.onerror=()=>{cleanup();reject(new Error('This browser cannot read the video. Try MP4 with H.264/AAC or a WebM file.'));};
        timer=setTimeout(()=>{cleanup();reject(new Error('Reading the video took too long. Please select it again.'));},20000);preview.src=url;
      });
      if(sequence!==selectionSequence) return;
      selectedFile=file;selectedDuration=duration;
      info.textContent=`${file.name} · ${bytes(file.size)} · ${Math.ceil(duration)} seconds · Ready to upload`;
      $('#videoDropZone b').textContent=file.name;
    } catch(error) {if(sequence===selectionSequence) info.textContent=error.message;}
  }
  function readMetadata(form) {
    return {title:form.elements.title.value.trim(),year:Number(form.elements.year.value),genres:form.elements.genres.value.split(',').map(v=>v.trim()).filter(Boolean),rating:form.elements.rating.value,description:form.elements.description.value.trim(),cast:form.elements.cast.value.trim(),family:form.elements.family.checked};
  }
  async function savePoster(id,file) {
    if(!file) return;
    const data=new FormData();data.append('file',file);
    await api(`library/${id}/poster`,{method:'POST',body:data});
  }
  async function submitUpload(form) {
    const button=$('button[type=submit]',form);button.disabled=true;
    try {
      if (!selectedFile) throw new Error('Select a playable video and wait for the file check to finish.');
      const file=selectedFile, poster=form.elements.poster?.files[0];
      if(poster && poster.size>limits.max_poster_bytes) throw new Error('Cover images must be 5 MiB or smaller.');
      const metadata=form.dataset.target ? {title_id:form.dataset.target} : {...readMetadata(form),type:form.elements.type.value};
      const isSeries = metadata.type === 'series' || library.find(t=>t.id===metadata.title_id)?.type==='series';
      Object.assign(metadata,{filename:file.name,size:file.size,duration:selectedDuration,fingerprint:await fingerprint(file),season:isSeries?Number(form.elements.season.value):1,episode:isSeries?Number(form.elements.episode.value):1,episode_title:form.elements.episode_title.value.trim(),replace:form.elements.replace?.checked || false});
      const response=await api('uploads',{method:'POST',body:JSON.stringify(metadata)});
      files.set(response.upload.id,{file,poster});
      closeDialog(dialog());setRoute('uploads');
      await run(response.upload.id);
    } catch(error) {if(dialog().open) {$('#uploadFormError').textContent=error.message;$('#uploadFormError').hidden=false;} else report(error);} finally {button.disabled=false;}
  }
  function sendChunk(id, offset, chunk, checksum, transfer) {
    return new Promise((resolve,reject)=>{
      const xhr=new XMLHttpRequest();transfer.xhr=xhr;
      xhr.open('PATCH',`/api/uploads/${id}?profile=${transfer.profile}`);
      xhr.setRequestHeader('Content-Type','application/octet-stream');xhr.setRequestHeader('Upload-Offset',String(offset));xhr.setRequestHeader('X-Chunk-SHA256',checksum);xhr.timeout=120000;
      xhr.upload.onprogress=event=>{if(job===transfer){job.loaded=offset+event.loaded;renderActivity(true);}};
      xhr.onload=()=>{let response;try{response=JSON.parse(xhr.responseText);}catch{reject(new Error('The server could not accept this chunk. Resume to retry.'));return;}if(xhr.status>=200 && xhr.status<300) resolve(response.offset);else reject(new Error(response.error || 'Upload failed. Resume to retry.'));};
      xhr.onerror=()=>reject(new Error('The connection was interrupted. Resume when you’re online.'));
      xhr.ontimeout=()=>reject(new Error('The connection timed out. Resume to retry this chunk.'));
      xhr.onabort=()=>reject(new Error('Upload paused.'));
      xhr.send(chunk);
    });
  }
  async function run(id) {
    if(job?.active || starting) return;
    const known=pending.find(s=>s.id===id);
    if(known && known.offset<known.size && !files.has(id)) {$('#resumeVideoFile').dataset.session=id;$('#resumeVideoFile').click();return;}
    starting=true;
    let session;
    try {session=(await api(`uploads/${id}`)).upload;} catch(error) {report(error);return;}finally{starting=false;}
    const selection=files.get(id);
    if(session.status==='completed'){await loadProfile();await render();toast('This video is already in your library.');return;}
    if(session.offset<session.size && !selection?.file){$('#resumeVideoFile').dataset.session=id;$('#resumeVideoFile').click();return;}
    job={session,loaded:session.offset,active:true,error:null,profile:state.profileId};
    const transfer=job;
    renderActivity();
    try {
      let offset=session.offset;
      const chunkSize=Math.min(limits?.chunk_bytes || 8*1024*1024,2*1024*1024);
      while(offset<session.size && job===transfer && transfer.active) {
        const chunk=selection.file.slice(offset,Math.min(offset+chunkSize,session.size));
        const checksum=await sha256(chunk);if(job!==transfer || !transfer.active) break;
        offset=await sendChunk(id,offset,chunk,checksum,transfer);transfer.loaded=offset;if(job===transfer) renderActivity(true);
      }
      if(job!==transfer || !transfer.active) return;
      const result=await api(`uploads/${id}/complete`,{method:'POST',body:'{}'});
      if(job!==transfer) return;
      let posterError=null;
      try{await savePoster(result.title_id,selection?.poster);}catch(error){posterError=error.message;}
      files.delete(id);job=null;await loadProfile();if(route()==='uploads') await render();
      toast(posterError ? `Video saved. Cover upload failed: ${posterError}` : 'Your video is ready to watch.');
    } catch(error) {
      if(job===transfer){job.active=false;job.error=error.message;renderActivity();}
      // A status fetch is authoritative if a chunk reached the server before the connection dropped.
      try {const status=(await api(`uploads/${id}`)).upload;if(job===transfer){job.loaded=status.offset;job.session=status;renderActivity();}}catch{}
      if(route()==='uploads') await render();
    }
  }
  async function resumeFile(file,id) {
    if(!file) return;
    try {
      const session=(await api(`uploads/${id}`)).upload;
      if(file.size!==session.size || await fingerprint(file)!==session.fingerprint) throw new Error('This is a different file. Reselect the original video to resume.');
      files.set(id,{file});await run(id);
    }catch(error){report(error);}
  }
  function editTitle(id) {
    const item=library.find(t=>t.id===id);if(!item) return;
    dialog().innerHTML=`<button class="circle-button dialog-close" data-close-upload aria-label="Close video details">${icon('close')}</button><p class="eyebrow">MAKE IT YOURS</p><h2>Edit video details</h2><form id="editVideoForm" data-id="${id}">${metadataFields(item)}${item.image.startsWith('/media/')?'<button type="button" class="library-text-button danger-text" data-remove-poster="'+id+'">Remove current cover</button>':''}<p class="form-error" id="uploadFormError" role="alert" hidden></p><div class="upload-form-footer"><span>Your changes appear throughout the catalog.</span><button class="button button-white" type="submit">Save changes</button></div></form>`;openDialog(dialog());
  }
  async function saveTitle(form) {
    const button=$('button[type=submit]',form);button.disabled=true;
    try {await api(`library/${form.dataset.id}`,{method:'PATCH',body:JSON.stringify(readMetadata(form))});await savePoster(form.dataset.id,form.elements.poster.files[0]);closeDialog(dialog());await loadProfile();await render();toast('Video details saved.');}
    catch(error){$('#uploadFormError').textContent=error.message;$('#uploadFormError').hidden=false;}finally{button.disabled=false;}
  }
  document.addEventListener('submit',event=>{if(event.target.id==='uploadForm'){event.preventDefault();submitUpload(event.target);}if(event.target.id==='editVideoForm'){event.preventDefault();saveTitle(event.target);}});
  document.addEventListener('change',event=>{if(event.target.id==='uploadVideoFile')readSelection(event.target.files[0]);if(event.target.id==='uploadKind')$('#episodeFields').hidden=event.target.value!=='series';if(event.target.id==='resumeVideoFile'){resumeFile(event.target.files[0],event.target.dataset.session);event.target.value='';}});
  document.addEventListener('dragover',event=>{if(event.target.closest('#videoDropZone')){event.preventDefault();$('#videoDropZone').classList.add('drag-active');}});
  document.addEventListener('dragleave',event=>{if(event.target.closest('#videoDropZone'))$('#videoDropZone').classList.remove('drag-active');});
  document.addEventListener('drop',event=>{if(event.target.closest('#videoDropZone')){event.preventDefault();$('#videoDropZone').classList.remove('drag-active');const file=event.dataTransfer.files[0];if(file){$('#uploadVideoFile').files=event.dataTransfer.files;readSelection(file);}}});
  document.addEventListener('click',async event=>{
    const button=event.target.closest('button');if(!button)return;
    try {
      if(button.hasAttribute('data-new-upload')) await showForm();
      if(button.hasAttribute('data-close-upload')) closeDialog(dialog());
      if(button.hasAttribute('data-pause-upload')) pause();
      if(button.hasAttribute('data-retry-library')) await render();
      if(button.dataset.resumeUpload) await run(button.dataset.resumeUpload);
      if(button.dataset.uploadTarget) await showForm(button.dataset.uploadTarget);
      if(button.dataset.replaceTitle) await showForm(button.dataset.replaceTitle,button.dataset.videoId);
      if(button.dataset.editTitle) editTitle(button.dataset.editTitle);
      if(button.dataset.cancelUpload){if(job?.session.id===button.dataset.cancelUpload){pause();job=null;}await api(`uploads/${button.dataset.cancelUpload}`,{method:'DELETE'});files.delete(button.dataset.cancelUpload);await render();toast('Upload canceled. Storage released.');}
      if(button.dataset.removePoster){await api(`library/${button.dataset.removePoster}/poster`,{method:'DELETE'});await loadProfile();await render();toast('Cover removed.');button.remove();}
      if(button.dataset.deleteTitle || button.dataset.deleteVideo){
        if(!button.dataset.confirmed){button.dataset.confirmed='true';button.textContent=button.dataset.deleteTitle?'Confirm: delete title & files':'Confirm: remove episode';return;}
        const path=button.dataset.deleteTitle?`library/${button.dataset.deleteTitle}`:`library/${button.dataset.videoTitle}/videos/${button.dataset.deleteVideo}`;
        await api(path,{method:'DELETE'});await loadProfile();await render();toast('Video removed. Storage released.');
      }
    }catch(error){report(error);}
  });
  window.addEventListener('offline',()=>{if(job?.active){pause();job.error='You’re offline. Resume when the connection returns.';renderActivity();}});
  return {render,pause};
})();
