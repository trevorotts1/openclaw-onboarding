#!/usr/bin/env python3
"""
AI Provider Interface
Handles connections to various AI video generation services.
"""

import os
import time
import json
import math
import subprocess
import sys
import tempfile
import importlib.util
import mimetypes
import requests
from pathlib import Path
from typing import Optional, Dict, Any


# KIE.ai live unified job API (Skill 74 kie-live-adapter will become the shared
# transport for all KIE skills; Skill 25 deliberately does NOT import it yet).
KIE_API_BASE = 'https://api.kie.ai/api/v1'
KIE_UPLOAD_URL = 'https://kieai.redpandaai.co/api/file-stream-upload'
KIE_UPLOAD_PATH = 'video-creator/inputs'  # no leading/trailing slash (KIE requirement)
KIE_AUTH_CODES = (401, 403)
KIE_POLL_DEADLINE = 900  # seconds; video jobs are slow
KIE_VIDEO_SKILL = '67-kie-video'
# Image-to-video input key per model, from each model's KIE docs page input schema (read 2026-10-05;
# page URL = https://docs.kie.ai/market/<path>.md, listed in docs.kie.ai/llms.txt) cross-checked with
# Skill 67 models.json / validate_payload.py. Value: (input key, 'str' single URL | 'list' array of URLs).
#   model id                              | key              | type | source (docs.kie.ai/market/...)
#   wan/3-0-video                         | first_frame_url  | str  | wan/3-0-video
#   wan/3-0-video-prime                   | first_frame_url  | str  | wan/3-0-video-prime
#   wan/2-7-image-to-video                | first_frame_url  | str  | wan/2-7-image-to-video
#   bytedance/seedance-2-5                | first_frame_url  | str  | bytedance/seedance-2-5
#   bytedance/seedance-2-mini             | first_frame_url  | str  | bytedance/seedance-2-mini
#   minimax-h3/image-to-video             | first_frame_url  | str  | minimax-h3/image-to-video
#   kling/v2-5-turbo-image-to-video-pro   | image_url        | str  | kling/v25-turbo-image-to-video-pro
#       (page text: "Must be kling/v2-5-turbo-image-to-video-pro"; its enum shows v2-1-master, a docs copy error)
#   kling-3.0-omni/image-to-video         | image_urls       | list | kling/v3-omni-image-to-video (both oneOf branches)
#   kling-3.0/video                       | image_urls       | list | kling/kling-3-0 (first and last frame)
#   pixverse-v6/image-to-video            | image_urls       | list | pixverse/image-to-video
#   happyhorse-1-1/image-to-video         | image_urls       | list | happyhorse-1-1/image-to-video
#   happyhorse/image-to-video             | image_urls       | list | happyhorse/image-to-video
#   gemini-omni-video                     | image_urls       | list | gemini-omni-video
# Required fields other than the image (for example mode/sound, quality, string durations) are the
# caller's to supply through input_extra; KIE answers a missing one with a body code, surfaced as an error.
KIE_I2V_IMAGE_FIELD = {
    'wan/3-0-video': ('first_frame_url', 'str'),
    'wan/3-0-video-prime': ('first_frame_url', 'str'),
    'wan/2-7-image-to-video': ('first_frame_url', 'str'),
    'bytedance/seedance-2-5': ('first_frame_url', 'str'),
    'bytedance/seedance-2-mini': ('first_frame_url', 'str'),
    'minimax-h3/image-to-video': ('first_frame_url', 'str'),
    'kling/v2-5-turbo-image-to-video-pro': ('image_url', 'str'),
    'kling-3.0-omni/image-to-video': ('image_urls', 'list'),
    'kling-3.0/video': ('image_urls', 'list'),
    'pixverse-v6/image-to-video': ('image_urls', 'list'),
    'happyhorse-1-1/image-to-video': ('image_urls', 'list'),
    'happyhorse/image-to-video': ('image_urls', 'list'),
    'gemini-omni-video': ('image_urls', 'list'),
}
# Dedicated KIE APIs (not createTask): unsupported by this client.
KIE_DEDICATED_MODELS = ('runway', 'veo3', 'veo3_fast', 'veo3_lite')


class KieAPIError(RuntimeError):
    """KIE returned a non-200 body `code` (HTTP 200 does not mean success)."""

    def __init__(self, message, code=None):
        super().__init__(message)
        self.code = code


# Per-model input TYPES and allowed values, read from each model's KIE docs page input schema (the same
# pages as the image-field table above, 2026-10-05; durations that the schema only describes in prose
# use the stated range). Values are coerced to the documented type before sending and invalid values
# fail BEFORE any HTTP call. Fields not listed here pass through unchanged. 'rename' maps Skill 25's
# option name to the model's own key (pixverse calls resolution "quality"). 'required' lists the
# documented required inputs other than prompt/duration/the image field; supply them with input_extra.
_DUR_30 = {'kind': 'int', 'min': 2, 'max': 30, 'also': (-1,)}
_SEED = {'kind': 'int', 'min': 0, 'max': 2147483647}
_ASPECT_SEEDANCE = ['1:1', '4:3', '3:4', '16:9', '9:16', '21:9', 'adaptive']
_WAN3 = {'duration': _DUR_30, 'resolution': {'kind': 'enum', 'values': ['480P', '720P', '1080P']},
         'aspect_ratio': {'kind': 'enum', 'values': ['adaptive', '16:9', '4:3', '1:1', '3:4', '9:16']},
         'seed': _SEED}
KIE_INPUT_SPECS = {
    'wan/3-0-video': {'fields': _WAN3},
    'wan/3-0-video-prime': {'fields': _WAN3},
    'wan/2-7-image-to-video': {'fields': {
        'duration': {'kind': 'int', 'min': 2, 'max': 15},
        'resolution': {'kind': 'enum', 'values': ['720p', '1080p']}, 'seed': _SEED}},
    'bytedance/seedance-2-5': {'fields': {
        'duration': {'kind': 'int', 'min': 4, 'max': 30, 'also': (-1,)},
        'resolution': {'kind': 'enum', 'values': ['480p', '720p', '1080p']},
        'aspect_ratio': {'kind': 'enum', 'values': _ASPECT_SEEDANCE}}},
    'bytedance/seedance-2-mini': {'fields': {
        'duration': {'kind': 'int', 'min': 4, 'max': 15, 'also': (-1,)},
        'resolution': {'kind': 'enum', 'values': ['480p', '720p']},
        'aspect_ratio': {'kind': 'enum', 'values': _ASPECT_SEEDANCE}}},
    'minimax-h3/image-to-video': {'fields': {
        'duration': {'kind': 'int', 'min': 4, 'max': 15},
        'resolution': {'kind': 'enum', 'values': ['768P', '2K']}}},
    'kling/v2-5-turbo-image-to-video-pro': {'fields': {
        'duration': {'kind': 'numstr', 'values': ['5', '10']}}},
    'kling-3.0-omni/image-to-video': {'fields': {
        'duration': {'kind': 'int', 'min': 3, 'max': 15},
        'resolution': {'kind': 'enum', 'values': ['720p', '1080p', '4k']},
        'aspect_ratio': {'kind': 'enum', 'values': ['16:9', '9:16', '1:1', 'auto']}}},
    'kling-3.0/video': {'fields': {
        'duration': {'kind': 'numstr', 'values': [str(n) for n in range(3, 16)]},
        'aspect_ratio': {'kind': 'enum', 'values': ['16:9', '9:16', '1:1']},
        'mode': {'kind': 'enum', 'values': ['std', 'pro', '4K']}},
        'required': ['sound', 'aspect_ratio', 'mode', 'multi_shots', 'multi_prompt']},
    'pixverse-v6/image-to-video': {'fields': {
        'duration': {'kind': 'int', 'min': 1, 'max': 15},
        'quality': {'kind': 'enum', 'values': ['360p', '540p', '720p', '1080p']}, 'seed': _SEED},
        'rename': {'resolution': 'quality'}, 'required': ['quality']},
    'happyhorse-1-1/image-to-video': {'fields': {
        'duration': {'kind': 'num', 'min': 3, 'max': 15},
        'resolution': {'kind': 'enum', 'values': ['720p', '1080p']}}},
    'happyhorse/image-to-video': {'fields': {
        'duration': {'kind': 'int', 'min': 3, 'max': 15},
        'resolution': {'kind': 'enum', 'values': ['720p', '1080p']}, 'seed': _SEED}},
    'gemini-omni-video': {'fields': {
        'duration': {'kind': 'numstr', 'values': ['4', '6', '8', '10']},
        'aspect_ratio': {'kind': 'enum', 'values': ['16:9', '9:16']},
        'resolution': {'kind': 'enum', 'values': ['720p', '1080p', '4k']}, 'seed': {'kind': 'int'}}},
}


def _kie_number(value):
    """Parse int/float/numeric string to a number, rejecting bool and junk. Returns None if not numeric."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            try:
                return float(value.strip())
            except ValueError:
                return None
    return None


def _kie_coerce(model, key, value, spec):
    """Coerce one value to the documented type, or raise ValueError naming the allowed values."""
    kind = spec['kind']
    lo, hi = spec.get('min'), spec.get('max')
    also = tuple(spec.get('also', ()))

    def bad(allowed):
        return ValueError(f"KIE model {model}: {key}={value!r} is not valid; allowed: {allowed}")

    if kind == 'enum':
        for allowed in spec['values']:
            if isinstance(value, str) and value.strip().lower() == allowed.lower():
                return allowed
        raise bad('one of ' + ', '.join(spec['values']))
    num = _kie_number(value)
    if kind == 'numstr':  # documented as a string enum of numbers, for example "5"
        if num is not None and float(num) == int(num) and str(int(num)) in spec['values']:
            return str(int(num))
        raise bad('one of ' + ', '.join(spec['values']) + ' (sent as a string)')
    rng = ('' if lo is None else f"{'integer ' if kind == 'int' else ''}{lo} to {hi}") + \
          (' or ' + ', '.join(str(a) for a in also) if also else '')
    if num is None or (kind == 'int' and float(num) != int(num)):
        raise bad(rng or 'an integer')
    num = int(num) if kind == 'int' else num
    if num in also:
        return num
    if (lo is not None and num < lo) or (hi is not None and num > hi):
        raise bad(rng)
    return num


def kie_validate_input(model, payload, provided_by_caller=()):
    """Rename, coerce, and check the createTask input for a mapped model, in place. No-op for other models.

    `provided_by_caller` names inputs that will be added later (the image field)."""
    spec = KIE_INPUT_SPECS.get(model)
    if not spec:
        return payload
    for old, new in spec.get('rename', {}).items():
        if old in payload and new not in payload:
            payload[new] = payload.pop(old)
    for key, value in list(payload.items()):
        field_spec = spec['fields'].get(key)
        if field_spec is not None and value is not None:
            payload[key] = _kie_coerce(model, key, value, field_spec)
    missing = [r for r in spec.get('required', []) if r not in payload and r not in provided_by_caller]
    if missing:
        hints = {k: v for k, v in spec['fields'].items() if k in missing}
        allowed = '; '.join(f"{k}: {v.get('values')}" for k, v in hints.items() if v.get('values'))
        raise ValueError(
            f"KIE model {model} requires {', '.join(missing)} (documented required inputs). Supply them with "
            "input_extra (CLI --input-extra '{\"key\": value}')" + (f"; allowed values: {allowed}" if allowed else ''))
    return payload


def _skills_dirs():
    """Skill roots to search for sibling skills / shared-utils.

    The directory two levels above this file is the skills dir for both the
    numbered source (<skills>/25-video-creator/scripts) and the runtime copy
    (<skills>/video-creator/scripts). Well-known box paths are the fallback.
    """
    dirs = [Path(__file__).resolve().parents[2],
            Path.home() / '.openclaw' / 'skills',
            Path('/data/.openclaw/skills')]
    return [d for i, d in enumerate(dirs) if d not in dirs[:i]]


def _resolve_kie_key() -> Optional[str]:
    """KIE key via the shared canon (shared-utils/key_resolver.py), else env."""
    for skills in _skills_dirs():
        shared = skills / 'shared-utils'
        if (shared / 'key_resolver.py').is_file():
            if str(shared) not in sys.path:
                sys.path.append(str(shared))
            try:
                from key_resolver import resolve_key
                key = resolve_key('kie')
                if key:
                    return key
            except Exception:
                pass
            break
    return os.getenv('KIE_API_KEY') or os.getenv('KIEAI_API_KEY')


def _find_kie_video_skill() -> Optional[Path]:
    for skills in _skills_dirs():
        root = skills / KIE_VIDEO_SKILL
        if (root / 'scripts' / 'select_video_model.py').is_file() and (root / 'models.json').is_file():
            return root
    return None


def select_kie_video_model(task: str, duration=None) -> str:
    """Ask Skill 67's selector for the model id. Never guesses a model."""
    root = _find_kie_video_skill()
    if root is None:
        raise RuntimeError(
            f"Skill {KIE_VIDEO_SKILL} (KIE Video) is not installed, so no KIE video model can be "
            "chosen. Install/update it (run update-skills.sh), or pass an explicit KIE model id "
            "(--model <id>, e.g. one listed by https://api.kie.ai/api/v1/models)."
        )
    spec = importlib.util.spec_from_file_location('kie67_select_video_model',
                                                  root / 'scripts' / 'select_video_model.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    request = f"{task} {int(duration)} seconds" if duration else task
    choice = module.select(request)
    if not choice.get('valid') or not choice.get('selected_model_id'):
        raise RuntimeError(f"Skill {KIE_VIDEO_SKILL} could not select a model for '{request}': "
                           f"{choice.get('reason')}")
    return choice['selected_model_id']


def _kie_resolution(model: str, resolution: Optional[str]) -> Optional[str]:
    """Use Skill 67's registry spelling for the model (e.g. 1080p -> 1080P)."""
    if not resolution:
        return None
    root = _find_kie_video_skill()
    if root is None:
        return resolution
    with open(root / 'models.json', encoding='utf-8') as fh:
        entry = next((m for m in json.load(fh)['models'] if m['canonical_model_id'] == model), None)
    if entry is None or not entry.get('resolutions'):
        return resolution
    for allowed in entry['resolutions']:
        if allowed.lower() == resolution.lower():
            return allowed
    raise ValueError(f"Resolution '{resolution}' is not supported by KIE model {model} "
                     f"(supported: {', '.join(entry['resolutions'])})")


class AIProvider:
    """Unified interface for AI video generation providers."""
    
    def __init__(self, provider_name: str, config: Dict[str, Any]):
        """
        Initialize AI provider.
        
        Args:
            provider_name: Name of provider (kieai, runway, pika, etc.)
            config: Configuration dict with API keys and endpoints
        """
        self.provider = provider_name.lower()
        self.config = config.get(provider_name, {})

        # API key policy:
        # - KIE.ai uses KIE_API_KEY (preferred). KIEAI_API_KEY is accepted as a fallback.
        # - Other providers use {PROVIDER}_API_KEY (for example RUNWAY_API_KEY).
        self.api_key = self.config.get('api_key')
        if not self.api_key:
            if self.provider == 'kieai':
                self.api_key = _resolve_kie_key()
            else:
                self.api_key = os.getenv(f'{provider_name.upper()}_API_KEY')

        self.endpoint = self.config.get('endpoint', self._default_endpoint())
        if self.provider == 'kieai' and self.endpoint.rstrip('/') == 'https://api.kie.ai/v1':
            # Legacy endpoint from old configs: dead (HTTP 404). Use the live unified job API.
            self.endpoint = KIE_API_BASE
        
    def _default_endpoint(self) -> str:
        """Get default endpoint for provider."""
        endpoints = {
            'kieai': KIE_API_BASE,
            'runway': 'https://api.runwayml.com/v1',
            'pika': 'https://api.pika.art/v1',
            'stability': 'https://api.stability.ai/v2beta',
            'mock': None
        }
        return endpoints.get(self.provider, 'https://api.kie.ai/v1')
    
    def generate_video(self, prompt: str, duration: int = 5, 
                       resolution: str = "1080p", style: str = "cinematic",
                       output: Optional[Path] = None, **kwargs) -> Path:
        """
        Generate video from text prompt.
        
        Args:
            prompt: Text description
            duration: Video length in seconds
            resolution: Output resolution
            style: Visual style
            output: Output file path
            **kwargs: Additional provider-specific options
            
        Returns:
            Path to generated video
        """
        if self.provider != 'kieai':
            unsupported_options = [
                option for option in ('seed', 'negative_prompt', 'model', 'input_extra')
                if kwargs.get(option) is not None
            ]
            if unsupported_options:
                option_list = ', '.join(f"--{option.replace('_', '-')}" for option in unsupported_options)
                raise ValueError(
                    f"Provider '{self.provider}' does not support: {option_list}"
                )

        if self.provider == 'kieai':
            return self._generate_kieai(prompt, duration, resolution, style, output, **kwargs)
        elif self.provider == 'runway':
            return self._generate_runway(prompt, duration, resolution, style, output, **kwargs)
        elif self.provider == 'pika':
            return self._generate_pika(prompt, duration, resolution, style, output, **kwargs)
        elif self.provider == 'mock':
            return self._generate_mock(prompt, duration, resolution, style, output, **kwargs)
        else:
            raise ValueError(f"Unknown provider: {self.provider}")
    
    def _generate_kieai(self, prompt, duration, resolution, style, output, **kwargs):
        """Text-to-video on KIE's live unified job API (createTask + recordInfo)."""
        self._require_kie_key()
        model = kwargs.get('model') or select_kie_video_model('text to video', duration)
        payload = {'prompt': prompt, 'duration': duration}
        self._kie_common_input(payload, model, resolution, kwargs)
        return self._kie_run(model, payload, output, kwargs)

    def _image_to_video_kieai(self, image_path, prompt, duration, **kwargs):
        """Image-to-video: upload the local image, then createTask with its URL."""
        self._require_kie_key()
        image_path = Path(image_path)
        model = kwargs.get('model') or select_kie_video_model('image to video', duration)
        override = kwargs.get('image_field')
        if override:
            kind = {'string': 'str', 'array': 'list'}.get(kwargs.get('image_field_type'))
            field = override
            if kind is None:
                if model in KIE_I2V_IMAGE_FIELD and KIE_I2V_IMAGE_FIELD[model][0] == override:
                    kind = KIE_I2V_IMAGE_FIELD[model][1]
                else:
                    raise ValueError(
                        f"image_field '{override}' needs an explicit type: pass --image-field-type string|array "
                        "(image_field_type='string'|'array' in code); the type is never guessed from the name.")
        elif model in KIE_DEDICATED_MODELS:
            raise RuntimeError(
                f"KIE model '{model}' uses a dedicated KIE API (not createTask), which this client does "
                "not support. Choose a createTask model with --model, one of: "
                + ", ".join(sorted(KIE_I2V_IMAGE_FIELD)))
        elif model in KIE_I2V_IMAGE_FIELD:
            field, kind = KIE_I2V_IMAGE_FIELD[model]
        else:
            raise RuntimeError(
                f"Image field for KIE model '{model}' is not established (Skill 67 and the KIE docs "
                "do not pin it here), so no guess is sent. Pass --image-field <input key> with "
                "--image-field-type string|array (image_field=..., image_field_type=... in code; see "
                "https://docs.kie.ai/llms.txt for the model's page) or choose a supported model: "
                + ", ".join(sorted(KIE_I2V_IMAGE_FIELD)))
        payload = {'prompt': prompt or '', 'duration': duration}
        self._kie_common_input(payload, model, kwargs.get('resolution'), kwargs, image_field=field)  # validates before any HTTP
        image_url = self._kie_upload(image_path)
        payload[field] = [image_url] if kind == 'list' else image_url
        output = kwargs.get('output') or image_path.with_suffix('.mp4')
        return self._kie_run(model, payload, output, kwargs)

    def _require_kie_key(self):
        if not self.api_key:
            raise ValueError("KIE_API_KEY not configured (set it in your environment to use provider=kieai)")

    def _kie_common_input(self, payload, model, resolution, kwargs, image_field=None):
        if resolution:
            # mapped models: the docs enum is applied below; others: Skill 67's registry spelling
            payload['resolution'] = resolution if model in KIE_INPUT_SPECS else _kie_resolution(model, resolution)
        for key in ('aspect_ratio', 'seed', 'negative_prompt'):
            if kwargs.get(key) is not None:
                payload[key] = kwargs[key]
        payload.update(kwargs.get('input_extra') or {})  # model-specific fields (validated if the model is mapped)
        kie_validate_input(model, payload, provided_by_caller=(image_field,) if image_field else ())

    def _kie_call(self, method, url, **request_kwargs):
        """One KIE request. Checks the body `code`, not just the HTTP status."""
        request_kwargs.setdefault('headers', {})['Authorization'] = f'Bearer {self.api_key}'
        try:
            response = getattr(requests, method)(url, **request_kwargs)
        except requests.RequestException as exc:
            raise RuntimeError(f"KIE.AI network error: {exc}") from exc
        try:
            body = response.json()
        except ValueError:
            body = {}
        code = body.get('code', getattr(response, 'status_code', None))
        if getattr(response, 'status_code', 200) in KIE_AUTH_CODES:
            code = response.status_code
        if code in KIE_AUTH_CODES:
            # Fail closed (AGENTS.md N40): never loop on an unauthorized/forbidden key.
            raise KieAPIError(f"KIE.AI rejected the API key (code {code}): {body.get('msg', '')}. "
                              "Stopping; do not retry. Check KIE_API_KEY.", code)
        if code != 200:
            raise KieAPIError(f"KIE.AI error code {code}: {body.get('msg') or 'no message'}", code)
        return body.get('data')

    def _kie_upload(self, image_path: Path) -> str:
        """Upload a local file to KIE's temp file service; return its download URL."""
        if not image_path.is_file():
            raise FileNotFoundError(f"Image not found: {image_path}")
        mime = mimetypes.guess_type(image_path.name)[0] or 'application/octet-stream'
        with open(image_path, 'rb') as fh:
            data = self._kie_call(
                'post', KIE_UPLOAD_URL,
                files={'file': (image_path.name, fh, mime)},
                data={'uploadPath': KIE_UPLOAD_PATH, 'fileName': image_path.name},
                timeout=120)
        url = (data or {}).get('downloadUrl')
        if not url:
            raise RuntimeError("KIE.AI upload returned no downloadUrl")
        return url

    def _kie_run(self, model, payload, output, kwargs) -> Path:
        """createTask -> poll recordInfo -> download the result immediately."""
        body = {'model': model, 'input': payload}
        if kwargs.get('callback_url'):
            body['callBackUrl'] = kwargs['callback_url']
        data = self._kie_call('post', f"{self.endpoint}/jobs/createTask", json=body, timeout=30)
        task_id = (data or {}).get('taskId')
        if not task_id:
            raise RuntimeError("KIE.AI createTask returned no taskId")
        print(f"   KIE task submitted: {task_id} (model {model})")
        deadline = time.monotonic() + kwargs.get('timeout', KIE_POLL_DEADLINE)
        delay = 3.0
        while True:
            time.sleep(delay)
            delay = min(delay * 1.5, 15.0)
            try:
                info = self._kie_call('get', f"{self.endpoint}/jobs/recordInfo",
                                      params={'taskId': task_id}, timeout=30) or {}
            except KieAPIError as exc:
                if exc.code != 429:  # rate-limited polls are retried; auth/other codes stop here
                    raise
                info = {}
            except RuntimeError as exc:  # transient network error: keep polling until the deadline
                print(f"   Poll error: {exc}")
                info = {}
            state = info.get('state')
            if state:
                print(f"   KIE state: {state}")
            if state == 'success':
                urls = (info.get('response') or {}).get('resultUrls')
                if not urls and info.get('resultJson'):
                    urls = json.loads(info['resultJson']).get('resultUrls')
                if not urls:
                    raise RuntimeError(f"KIE task {task_id} succeeded but returned no resultUrls")
                return self._download_video(urls[0], output or Path(f"kie_{task_id}.mp4"))
            if state == 'fail':
                raise RuntimeError(f"KIE task {task_id} failed: {info.get('failCode')} {info.get('failMsg')}")
            if time.monotonic() >= deadline:
                raise RuntimeError(f"KIE task {task_id} timed out after "
                                   f"{kwargs.get('timeout', KIE_POLL_DEADLINE)}s (last state: {state})")

    def _generate_runway(self, prompt, duration, resolution, style, output, **kwargs):
        """Generate video using Runway ML API."""
        if not self.api_key:
            raise ValueError("Runway API key not configured")
        
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }
        
        res_map = {"720p": "720p", "1080p": "1080p", "4k": "4k"}
        
        payload = {
            'prompt': prompt,
            'duration': duration,
            'resolution': res_map.get(resolution, "1080p"),
            'style': style
        }
        
        try:
            response = requests.post(
                f"{self.endpoint}/video",
                headers=headers,
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            result = response.json()
            
            job_id = result.get('id')
            return self._poll_job(job_id, headers, output)
            
        except requests.RequestException as e:
            raise RuntimeError(f"Runway API error: {e}")
    
    def _generate_pika(self, prompt, duration, resolution, style, output, **kwargs):
        """Generate video using Pika Labs API."""
        if not self.api_key:
            raise ValueError("Pika API key not configured")
        
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }
        
        payload = {
            'prompt': prompt,
            'video_length': duration,
            'aspect_ratio': '16:9' if resolution != 'vertical' else '9:16',
            'style': style
        }
        
        try:
            response = requests.post(
                f"{self.endpoint}/videos",
                headers=headers,
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            result = response.json()
            
            job_id = result.get('id')
            return self._poll_job(job_id, headers, output)
            
        except requests.RequestException as e:
            raise RuntimeError(f"Pika API error: {e}")
    
    def _generate_mock(self, prompt, duration, resolution, style, output, **kwargs):
        """Generate a mock video for testing without API calls."""
        print("   Using mock provider (no API call)")
        
        # Create a simple colored video with text using MoviePy
        try:
            from moviepy.editor import ColorClip, TextClip, CompositeVideoClip
            
            res_map = {"720p": (1280, 720), "1080p": (1920, 1080), "4k": (3840, 2160)}
            width, height = res_map.get(resolution, (1920, 1080))
            
            # Create gradient background
            bg = ColorClip(size=(width, height), color=(30, 30, 60)).set_duration(duration)
            
            # Add animated text
            text_content = f"MOCK VIDEO\n\nPrompt:\n{prompt[:150]}"
            text = TextClip(
                text_content,
                fontsize=36,
                color='white',
                size=(width - 100, None),
                method='caption',
                align='center',
                font='Arial-Bold'
            ).set_duration(duration).set_position('center')
            
            # Add style label
            style_text = TextClip(
                f"Style: {style} | Duration: {duration}s",
                fontsize=24,
                color='yellow'
            ).set_duration(duration).set_position(('center', height - 100))
            
            video = CompositeVideoClip([bg, text, style_text])
            video.write_videofile(str(output), fps=30, codec='libx264', audio=False, verbose=False)
            video.close()
            
            return output
            
        except ImportError:
            raise RuntimeError("MoviePy required for mock generation")
    
    def _poll_job(self, job_id: str, headers: dict, output: Path, 
                  max_attempts: int = 60, delay: int = 5) -> Path:
        """
        Poll for job completion and download result.
        
        Args:
            job_id: Job identifier
            headers: Request headers
            output: Output file path
            max_attempts: Maximum poll attempts
            delay: Seconds between polls
            
        Returns:
            Path to downloaded video
        """
        for attempt in range(max_attempts):
            time.sleep(delay)
            
            try:
                status_resp = requests.get(
                    f"{self.endpoint}/jobs/{job_id}",
                    headers=headers,
                    timeout=30
                )
                status_resp.raise_for_status()
                status = status_resp.json()
                
                state = status.get('status') or status.get('state')
                print(f"   Status: {state} (attempt {attempt + 1}/{max_attempts})")
                
                if state in ('completed', 'done', 'success'):
                    video_url = status.get('video_url') or status.get('output_url')
                    if video_url:
                        return self._download_video(video_url, output)
                    raise RuntimeError("No video URL in completed job")
                    
                elif state in ('failed', 'error'):
                    error_msg = status.get('error', 'Unknown error')
                    raise RuntimeError(f"Generation failed: {error_msg}")
                    
            except requests.RequestException as e:
                print(f"   Poll error: {e}")
                continue
        
        raise RuntimeError(f"Job polling timeout after {max_attempts} attempts")
    
    def _download_video(self, url: str, output: Path) -> Path:
        """Download and validate a provider video before publishing it."""
        print(f"   Downloading video...")

        output = Path(output)
        output.parent.mkdir(parents=True, exist_ok=True)
        response = requests.get(url, stream=True, timeout=120)
        response.raise_for_status()

        content_type = response.headers.get('Content-Type', '').split(';', 1)[0].strip().lower()
        if not content_type.startswith('video/'):
            raise RuntimeError(
                f"Invalid downloaded video: expected video Content-Type, got "
                f"{content_type or 'missing'}"
            )

        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode='wb',
                dir=output.parent,
                prefix=f".{output.name}.",
                suffix='.part',
                delete=False,
            ) as temp_file:
                temp_path = Path(temp_file.name)
                byte_count = 0
                for chunk in response.iter_content(chunk_size=8192):
                    if not chunk:
                        continue
                    temp_file.write(chunk)
                    byte_count += len(chunk)

            if byte_count < 1024:
                raise RuntimeError(
                    f"Invalid downloaded video: payload is too small ({byte_count} bytes)"
                )

            self._validate_downloaded_video(temp_path)
            os.replace(temp_path, output)
            temp_path = None
        except Exception as exc:
            if isinstance(exc, RuntimeError) and str(exc).startswith('Invalid downloaded video:'):
                raise
            raise RuntimeError(f"Invalid downloaded video: {exc}") from exc
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)

        print(f"   Downloaded and verified: {output}")
        return output

    @staticmethod
    def _validate_downloaded_video(video_path: Path) -> None:
        """Require ffprobe to find a video stream with positive duration."""
        command = [
            'ffprobe',
            '-v', 'error',
            '-show_entries', 'stream=codec_type,duration:format=duration',
            '-of', 'json',
            str(video_path),
        ]
        try:
            probe = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            raise RuntimeError(f"ffprobe validation unavailable: {exc}") from exc

        if probe.returncode != 0:
            detail = probe.stderr.strip() or f"ffprobe exited {probe.returncode}"
            raise RuntimeError(f"ffprobe could not decode video: {detail}")

        try:
            metadata = json.loads(probe.stdout)
            video_streams = [
                stream for stream in metadata.get('streams', [])
                if stream.get('codec_type') == 'video'
            ]
            if not video_streams:
                raise ValueError("no video stream")

            duration_value = metadata.get('format', {}).get('duration')
            if duration_value is None:
                duration_value = next(
                    (stream.get('duration') for stream in video_streams if stream.get('duration')),
                    None,
                )
            duration = float(duration_value)
            if not math.isfinite(duration) or duration <= 0:
                raise ValueError("duration is not positive")
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"ffprobe returned invalid video metadata: {exc}") from exc
    
    def image_to_video(self, image_path: Path, prompt: str = None,
                       duration: int = 5, **kwargs) -> Path:
        """
        Animate an image into video.
        
        Args:
            image_path: Path to input image
            prompt: Optional motion description
            duration: Video length
            **kwargs: Additional options
            
        Returns:
            Path to generated video
        """
        if self.provider == 'kieai':
            generator = getattr(self, '_image_to_video_kieai', None)
        elif self.provider == 'runway':
            generator = getattr(self, '_image_to_video_runway', None)
        elif self.provider == 'pika':
            generator = getattr(self, '_image_to_video_pika', None)
        elif self.provider == 'local':
            return self._image_to_video_local(image_path, prompt, duration, **kwargs)
        else:
            raise ValueError(f"Unknown image-to-video provider: {self.provider}")

        if generator is None:
            raise NotImplementedError(
                f"Image-to-video provider '{self.provider}' is not implemented"
            )
        return generator(image_path, prompt, duration, **kwargs)
    
    def _image_to_video_local(self, image_path, prompt, duration, **kwargs):
        """Create video from image using MoviePy effects."""
        from moviepy.editor import ImageClip
        
        motion = kwargs.get('motion', 'ken_burns')
        
        clip = ImageClip(str(image_path))
        
        if motion == 'zoom':
            # Zoom in effect
            clip = clip.resize(lambda t: 1 + 0.2 * t / duration).set_duration(duration)
        elif motion == 'ken_burns':
            # Pan and zoom
            from moviepy.editor import vfx
            clip = clip.resize(1.2).set_duration(duration)
            clip = vfx.scroll(clip, w=clip.w*0.1, h=clip.h*0.05, x_speed=10, y_speed=5)
        else:
            clip = clip.set_duration(duration)
        
        output = kwargs.get('output', image_path.stem + '_video.mp4')
        clip.write_videofile(str(output), fps=30, codec='libx264')
        clip.close()
        
        return Path(output)
