import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash, createHmac } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { presignPut, validateUpload } from '../src/uploads.js';
import worker from '../src/worker.js';
import { sendFile } from '../../ui/upload/upload.js';

const client = 'c-' + 'a'.repeat(32);
const uploadId = 'u_' + 'b'.repeat(24);
const objectPath = `clients/${client}/intake/${uploadId}.png`;
const account = 'c'.repeat(32);
const env = { R2_ACCOUNT_ID: account, R2_ACCESS_KEY_ID: 'fake-key', R2_SECRET_ACCESS_KEY: 'fake-secret' };
const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j5ioAAAAASUVORK5CYII=', 'base64');

test('default bucket and SigV4 match independent Node crypto derivation', async () => {
  const result = await presignPut(env, objectPath, 'image/png');
  assert.equal(result.ok, true);
  const url = new URL(result.upload.url);
  assert.equal(url.pathname, `/zhw-drama-studio/${objectPath}`);
  const signature = url.searchParams.get('X-Amz-Signature');
  const query = url.search.slice(1).replace(/&X-Amz-Signature=[^&]+/, '');
  const amzDate = url.searchParams.get('X-Amz-Date');
  const scope = `${amzDate.slice(0, 8)}/auto/s3/aws4_request`;
  const canonical = ['PUT', url.pathname, query, `host:${url.hostname}`, '', 'host', 'UNSIGNED-PAYLOAD'].join('\n');
  const toSign = ['AWS4-HMAC-SHA256', amzDate, scope, createHash('sha256').update(canonical).digest('hex')].join('\n');
  let key = Buffer.from('AWS4fake-secret');
  for (const value of [amzDate.slice(0, 8), 'auto', 's3', 'aws4_request']) key = createHmac('sha256', key).update(value).digest();
  assert.equal(signature, createHmac('sha256', key).update(toSign).digest('hex'));
});

test('real PNG bridge metadata passes the service validation unchanged', () => {
  const bridgeDir = fileURLToPath(new URL('../../../shared-bridge/', import.meta.url));
  const code = 'import sys,json,tempfile,pathlib,base64; sys.path.insert(0,sys.argv[1]); import studio_bridge as b\nwith tempfile.TemporaryDirectory() as d:\n p=pathlib.Path(d)/"photo.png"; p.write_bytes(base64.b64decode(sys.argv[2])); print(json.dumps(b.photo_request(p)))';
  const proc = spawnSync('python3', ['-c', code, bridgeDir, png.toString('base64')], { encoding: 'utf8' });
  assert.equal(proc.status, 0, proc.stderr);
  const body = JSON.parse(proc.stdout);
  assert.deepEqual(validateUpload({ channel: body.channel, filename: body.filename, sizeBytes: body.size_bytes, contentType: body.content_type, headerBytes: body.header_bytes }), { ok: true, ext: 'png' });
});

test('phone sends metadata with key, then file without key, and exposes only receipt', async () => {
  const file = new File([png], 'photo.png', { type: 'image/png' });
  const calls = [];
  const transport = async (url, opts) => {
    calls.push({ url, opts });
    if (calls.length === 1) return new Response(JSON.stringify({ ok: true, upload_id: uploadId, object_path: objectPath, upload: { url: `https://${account}.r2.cloudflarestorage.com/zhw-drama-studio/${objectPath}?signed=test`, content_type: 'image/png' } }), { status: 201 });
    return new Response('', { status: 200 });
  };
  const receipt = await sendFile(file, 'sentinel-client-key', 'image', transport);
  assert.equal(calls[0].opts.headers['x-ds-key'], 'sentinel-client-key');
  assert.deepEqual(JSON.parse(calls[0].opts.body).header_bytes, [...png.subarray(0, 16)]);
  assert.equal(calls[1].opts.body, file);
  assert.deepEqual(calls[1].opts.headers, { 'Content-Type': 'image/png' });
  assert.equal(calls[1].opts.redirect, 'error');
  assert.deepEqual(receipt, { upload_id: uploadId, object_path: objectPath });
});

test('phone refuses oversized images before requesting a link', async () => {
  let calls = 0;
  await assert.rejects(sendFile({ name: 'photo.png', size: 30 * 1024 * 1024 }, 'key', 'image', () => { calls++; }), /under 25 MB/);
  assert.equal(calls, 0);
});

test('phone refuses an unexpected storage host without sending bytes', async () => {
  let calls = 0;
  const transport = async () => {
    calls++;
    return new Response(JSON.stringify({ ok: true, upload_id: uploadId, object_path: objectPath, upload: { url: 'https://example.com/file', content_type: 'image/png' } }), { status: 201 });
  };
  await assert.rejects(sendFile(new File([png], 'photo.png'), 'key', 'image', transport), /invalid upload link/);
  assert.equal(calls, 1);
});

test('Worker serves phone page through the asset binding with no-store headers', async () => {
  const response = await worker.fetch(new Request('https://studio.zerohumanworkforce.com/uploads'), { DS_UPLOAD_ASSETS: { fetch: async (req) => {
    assert.equal(new URL(req.url).pathname, '/index.html');
    return new Response('upload form', { headers: { 'Content-Type': 'text/html' } });
  } } });
  assert.equal(response.status, 200);
  assert.equal(response.headers.get('Cache-Control'), 'no-store');
  assert.match(response.headers.get('Content-Security-Policy'), /frame-ancestors 'none'/);
});
