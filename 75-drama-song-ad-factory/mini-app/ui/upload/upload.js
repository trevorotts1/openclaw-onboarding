// The personal link carries the key in the fragment (#k=<hex>, possibly followed by &p=<page>).
// Browsers never send the fragment to the server, so it is the only place a link key may live.
// U-Z08 — 64 hex is what the service mints today; 32 hex is a legacy link and
// still accepted here, exactly as service-client.js accepts both.
export function linkKey(hash = globalThis.location?.hash ?? '') {
  const value = new URLSearchParams(hash.replace(/^#/, '')).get('k');
  return /^(?:[0-9a-f]{32}|[0-9a-f]{64})$/.test(value ?? '') ? value : null;
}

const LIMITS = { image: 25 * 1024 * 1024, audio: 25 * 1024 * 1024, video: 200 * 1024 * 1024 };
const TYPES = {
  image: { jpg: 'image/jpeg', jpeg: 'image/jpeg', png: 'image/png', heic: 'image/heic', webp: 'image/webp' },
  audio: { webm: 'audio/webm', mp3: 'audio/mpeg', m4a: 'audio/mp4', wav: 'audio/wav', ogg: 'audio/ogg' },
  video: { mp4: 'video/mp4', mov: 'video/quicktime', webm: 'video/webm' },
};

const UNSUPPORTED = 'That kind of file is not supported. Use JPG, PNG, HEIC or WEBP for photos, MP3, M4A or WAV for audio, MP4 or MOV for video.';
const NOT_TAKEN = 'The studio could not take that file. Please try again.';

/** The channel a file belongs to, read off its own extension — never a guess
 *  from a menu the client may not have touched. */
function channelFor(name) {
  const ext = String(name || '').toLowerCase().split('.').pop();
  return Object.keys(TYPES).find((c) => Object.prototype.hasOwnProperty.call(TYPES[c], ext)) || null;
}

/**
 * Send one file to the studio.
 *
 * `channel` is optional (U-Z08): the extension decides it. The third argument
 * may also be the transport, so a caller that only knows the file and the key
 * passes `sendFile(file, key, transport)`; the older `(file, key, channel,
 * transport)` shape still works.
 */
export async function sendFile(file, key, channel = null, transport = globalThis.fetch) {
  if (typeof channel === 'function') { transport = channel; channel = null; }
  if (!key || !file) throw new Error('Enter your studio access key and choose a file.');
  const picked = TYPES[channel] ? channel : channelFor(file.name);
  if (!picked) throw new Error(UNSUPPORTED);
  const contentType = TYPES[picked][file.name.toLowerCase().split('.').pop()];
  if (file.size <= 0 || file.size > LIMITS[picked]) throw new Error(`Choose a file under ${LIMITS[picked] / 1024 / 1024} MB.`);
  const headerBytes = [...new Uint8Array(await file.slice(0, 16).arrayBuffer())];
  let response;
  try {
    response = await transport('/api/studio/uploads', {
      method: 'POST', headers: { 'Content-Type': 'application/json', 'x-ds-key': key },
      body: JSON.stringify({ channel: picked, filename: file.name, size_bytes: file.size, content_type: contentType, header_bytes: headerBytes }),
      redirect: 'error',
    });
  } catch { throw new Error('The studio could not be reached. Please try again.'); }
  // A refusal may carry the service's own words; an answer that is not JSON at
  // all (a proxy error page, a plain-text 502) gets the one plain sentence.
  let result = null;
  try { result = await response.json(); } catch { result = null; }
  if (response.status !== 201 || !result || result.ok !== true) {
    throw new Error(result && typeof result.message === 'string' && result.message ? result.message : NOT_TAKEN);
  }
  const upload = result.upload || {};
  let url;
  try { url = new URL(upload.url); } catch { throw new Error('The studio returned an invalid upload link.'); }
  // The bucket is whatever the returned address names in its first path part —
  // the service owns that name, and the page never holds its own copy.
  const bucket = url.pathname.split('/').filter(Boolean)[0] || '';
  if (url.protocol !== 'https:' || url.username || url.password || url.port
      || !/^[a-f0-9]{32}\.r2\.cloudflarestorage\.com$/.test(url.hostname)
      || !/^clients\/c-[a-f0-9]{32}\/intake\/u_[a-f0-9]{24}\.[a-z0-9]+$/.test(result.object_path || '')
      || !bucket || url.pathname !== `/${bucket}/${result.object_path}`
      || result.upload_id !== result.object_path.split('/').pop().split('.')[0]
      || upload.content_type !== contentType) throw new Error('The studio returned an invalid upload link.');
  let sent;
  try {
    sent = await transport(upload.url, { method: 'PUT', headers: { 'Content-Type': contentType }, body: file, redirect: 'error', credentials: 'omit', referrerPolicy: 'no-referrer' });
  } catch { throw new Error('The file transfer was interrupted. Its outcome is unknown.'); }
  if (!sent.ok) throw new Error(`The file transfer was refused (HTTP ${sent.status}).`);
  return { upload_id: result.upload_id, object_path: result.object_path };
}

// The upload page's own wiring. The studio page imports sendFile() from this
// module too, and it has no upload form, so nothing here runs there.
if (typeof document !== 'undefined' && document.getElementById('upload-form')) {
  const form = document.getElementById('upload-form');
  const file = document.getElementById('file');
  const button = document.getElementById('send');
  const status = document.getElementById('status');
  const keyLine = document.getElementById('key-line');
  const hashKey = linkKey();
  if (hashKey) {
    if (keyLine) keyLine.hidden = true;
  } else {
    // U-Z08 — this page is opened from the client's own link, so there is no
    // key box at all. Without the key in the fragment there is nothing to open
    // and the page says so, with the form out of the way.
    if (form) form.hidden = true;
    if (keyLine) { keyLine.hidden = false; keyLine.textContent = 'Open this page from your personal studio link.'; }
  }
  if (form) form.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (button) button.disabled = true;
    if (status) status.textContent = 'Sending your file. Keep this page open.';
    const chosen = file && file.files && file.files[0];
    try {
      // The extension picks the channel (see sendFile); there is no menu to
      // disagree with the file the client chose.
      await sendFile(chosen, hashKey);
      if (status) status.textContent = `Got it - ${chosen.name} is with your studio.`;
      if (file) file.value = '';
    } catch (error) { if (status) status.textContent = error.message; }
    finally { if (button) button.disabled = false; }
  });
}
