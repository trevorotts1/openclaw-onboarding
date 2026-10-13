// The personal link carries the key in the fragment (#k=<32 hex>, possibly followed by &p=<page>).
// Browsers never send the fragment to the server, so it is the only place a link key may live.
export function linkKey(hash = globalThis.location?.hash ?? '') {
  const value = new URLSearchParams(hash.replace(/^#/, '')).get('k');
  return /^[0-9a-f]{32}$/.test(value ?? '') ? value : null;
}

const LIMITS = { image: 25 * 1024 * 1024, audio: 25 * 1024 * 1024, video: 200 * 1024 * 1024 };
const TYPES = {
  image: { jpg: 'image/jpeg', jpeg: 'image/jpeg', png: 'image/png', heic: 'image/heic', webp: 'image/webp' },
  audio: { webm: 'audio/webm', mp3: 'audio/mpeg', m4a: 'audio/mp4', wav: 'audio/wav', ogg: 'audio/ogg' },
  video: { mp4: 'video/mp4', mov: 'video/quicktime', webm: 'video/webm' },
};

export async function sendFile(file, key, channel, transport = globalThis.fetch) {
  if (!key || !file) throw new Error('Enter your studio access key and choose a file.');
  const contentType = TYPES[channel]?.[file.name.toLowerCase().split('.').pop()];
  if (!contentType) throw new Error('Choose a supported file for this file type.');
  if (file.size <= 0 || file.size > LIMITS[channel]) throw new Error(`Choose a file under ${LIMITS[channel] / 1024 / 1024} MB.`);
  const headerBytes = [...new Uint8Array(await file.slice(0, 16).arrayBuffer())];
  let response;
  try {
    response = await transport('/api/studio/uploads', {
      method: 'POST', headers: { 'Content-Type': 'application/json', 'x-ds-key': key },
      body: JSON.stringify({ channel, filename: file.name, size_bytes: file.size, content_type: contentType, header_bytes: headerBytes }),
      redirect: 'error',
    });
  } catch { throw new Error('The studio could not be reached. Please try again.'); }
  const result = await response.json();
  if (response.status !== 201 || !result.ok) throw new Error(`The studio refused this upload (${result.code || response.status}).`);
  const upload = result.upload || {};
  let url;
  try { url = new URL(upload.url); } catch { throw new Error('The studio returned an invalid upload link.'); }
  if (url.protocol !== 'https:' || url.username || url.password || url.port
      || !/^[a-f0-9]{32}\.r2\.cloudflarestorage\.com$/.test(url.hostname)
      || !/^clients\/c-[a-f0-9]{32}\/intake\/u_[a-f0-9]{24}\.[a-z0-9]+$/.test(result.object_path || '')
      || url.pathname !== `/zhw-drama-studio/${result.object_path}`
      || result.upload_id !== result.object_path.split('/').pop().split('.')[0]
      || upload.content_type !== contentType) throw new Error('The studio returned an invalid upload link.');
  let sent;
  try {
    sent = await transport(upload.url, { method: 'PUT', headers: { 'Content-Type': contentType }, body: file, redirect: 'error', credentials: 'omit', referrerPolicy: 'no-referrer' });
  } catch { throw new Error('The file transfer was interrupted. Its outcome is unknown.'); }
  if (!sent.ok) throw new Error(`The file transfer was refused (HTTP ${sent.status}).`);
  return { upload_id: result.upload_id, object_path: result.object_path };
}

if (typeof document !== 'undefined') {
  const form = document.getElementById('upload-form');
  const channel = document.getElementById('channel');
  const file = document.getElementById('file');
  const button = document.getElementById('send');
  const status = document.getElementById('status');
  const keyField = document.getElementById('paste-key');
  const keyInput = document.getElementById('studio-key');
  const hashKey = linkKey();
  if (hashKey) {
    keyField.hidden = true;
    keyInput.required = false;
  }
  channel.addEventListener('change', () => {
    file.accept = Object.keys(TYPES[channel.value]).map((ext) => '.' + ext).join(',');
    file.value = '';
  });
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    button.disabled = true;
    status.textContent = 'Sending your file. Keep this page open.';
    try {
      const result = await sendFile(file.files[0], hashKey || keyInput.value.trim(), channel.value);
      status.textContent = `File received. Upload reference: ${result.upload_id}`;
      file.value = '';
    } catch (error) { status.textContent = error.message; }
    finally { button.disabled = false; }
  });
}
