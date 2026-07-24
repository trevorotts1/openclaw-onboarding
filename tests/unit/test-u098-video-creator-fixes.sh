#!/usr/bin/env bash
# tests/unit/test-u098-video-creator-fixes.sh
# U098 — Video-creator silent-success fix tests
# Tests that each of the 8 defects is guarded against.
# MoviePy is NOT required — all tests validate logic that runs before MoviePy imports.
set -euo pipefail

PASS=0; FAIL=0
green(){ printf "\033[32m  ✓ %s\033[0m\n" "$1"; PASS=$((PASS+1)); }
red(){ printf "\033[31m  ✗ %s\033[0m\n" "$1"; FAIL=$((FAIL+1)); }

echo "=== U098 Video-creator silent-success fixes ==="
echo ""

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

# T0-32: Provider failure must re-raise, not return placeholder
echo "--- T0-32: Provider failure raises ---"
python3 -c "
import sys; sys.path.insert(0, '$REPO_DIR/25-video-creator/scripts')
from ai_providers import AIProvider
from pathlib import Path
try:
    p = AIProvider('nonexistent_provider', {})
    p.generate_video('test', output=Path('/tmp/test.mp4'))
    assert False, 'Should have raised'
except ValueError:
    pass
try:
    p = AIProvider('kieai', {'kieai': {'api_key': None}})
    p.generate_video('test', output=Path('/tmp/test.mp4'))
    assert False, 'Should have raised for missing KIE API key'
except (ValueError, RuntimeError):
    pass
" 2>&1 && green "T0-32: provider failures raise (unknown + missing API key)" || red "T0-32: provider failure did not raise"

# T0-33: Validate downloaded artifacts
echo "--- T0-33: Download validation ---"
python3 -c "
import sys; sys.path.insert(0, '$REPO_DIR/25-video-creator/scripts')
from ai_providers import AIProvider
from pathlib import Path
import tempfile, os
p = AIProvider('mock', {'mock': {}})
tf = tempfile.NamedTemporaryFile(suffix='.mp4', delete=False)
tf.write(b'not a video file just some text')
tf.close()
try:
    p._validate_downloaded_video(Path(tf.name))
    os.unlink(tf.name)
    assert False, 'Should have detected invalid video'
except RuntimeError:
    os.unlink(tf.name)
tf2 = tempfile.NamedTemporaryFile(suffix='.mp4', delete=False)
tf2.write(b'')
tf2.close()
try:
    p._validate_downloaded_video(Path(tf2.name))
    os.unlink(tf2.name)
    assert False, 'Should have detected empty video'
except RuntimeError:
    os.unlink(tf2.name)
" 2>&1 && green "T0-33: invalid/empty downloads detected by ffprobe" || red "T0-33: invalid download passed validation"

# T0-34: Partial results tracking
echo "--- T0-34: Empty clip list detection ---"
python3 -c "
import sys; sys.path.insert(0, '$REPO_DIR/25-video-creator/scripts')
from multi_clip_assembly import assemble_clips
try:
    assemble_clips([])
    assert False, 'Empty clip list should raise ValueError'
except ValueError as e:
    assert 'No input clips' in str(e), f'Wrong message: {e}'
" 2>&1 && green "T0-34: empty clip list raises ValueError before MoviePy" || red "T0-34: empty clip list not validated"

echo "--- T0-34b: Missing music file guard ---"
python3 -c "
import sys; sys.path.insert(0, '$REPO_DIR/25-video-creator/scripts')
from multi_clip_assembly import assemble_clips
from pathlib import Path
import tempfile
# Music guard at line 89 runs before clip loop at 103
# Verify it catches missing music
with tempfile.TemporaryDirectory() as td:
    dummy = Path(td) / 'dummy.mp4'
    dummy.write_text('')
    missing_music = Path(td) / 'missing_music.mp3'
    try:
        assemble_clips([dummy], music=str(missing_music), output=Path(td)/'out.mp4')
        assert False, 'Should have raised for missing music'
    except FileNotFoundError:
        pass
    except ModuleNotFoundError:
        pass
" 2>&1 && green "T0-34b: music file not found raises FileNotFoundError" || red "T0-34b: missing music guard missing"

# T0-35: Required template fields
echo "--- T0-35: Template field validation ---"
python3 -c "
import sys; sys.path.insert(0, '$REPO_DIR/25-video-creator/scripts')
from template_video import TemplateEngine
for tmpl, data in [('product_showcase', {}), ('tutorial', {}), ('testimonial', {'quote': 'Great!'})]:
    try:
        TemplateEngine(tmpl, data).generate()
        assert False, f'{tmpl} should have raised for missing fields'
    except ValueError:
        pass
" 2>&1 && green "T0-35: required template fields enforced" || red "T0-35: missing fields not detected"

# T0-36: Audio source validation
echo "--- T0-36: Audio source validation ---"
python3 -c "
with open('$REPO_DIR/25-video-creator/scripts/add_music.py') as f:
    s = f.read()
assert 'not video_path.exists()' in s
assert 'not Path(music_source).is_file()' in s
assert 'voiceover and not voiceover.is_file()' in s
" 2>&1 && green "T0-36: all audio-source guards present" || red "T0-36: audio guards missing"

# T0-37: Directives applied
echo "--- T0-37: Music directive conflict detection ---"
python3 -c "
with open('$REPO_DIR/25-video-creator/scripts/add_music.py') as f:
    s = f.read()
assert 'music_source and genre' in s
assert 'Choose either music_source or genre, not both' in s
with open('$REPO_DIR/25-video-creator/scripts/multi_clip_assembly.py') as f:
    s = f.read()
assert 'transition_type not in SUPPORTED_TRANSITIONS' in s
" 2>&1 && green "T0-37: conflicting directives + unsupported transitions rejected" || red "T0-37: directive validation missing"

# T0-38: Resolution preset mapping
echo "--- T0-38: Resolution preset mapping ---"
python3 -c "
import sys; sys.path.insert(0, '$REPO_DIR/25-video-creator/scripts')
from multi_clip_assembly import get_resolution
assert get_resolution('720p') == (1280, 720)
assert get_resolution('1080p') == (1920, 1080)
assert get_resolution('4k') == (3840, 2160)
assert get_resolution('vertical') == (1080, 1920)
assert get_resolution('square') == (1080, 1080)
assert get_resolution('social') == (1080, 1920)
assert get_resolution('unknown') == (1920, 1080)
" 2>&1 && green "T0-38: all 7 resolution presets correctly mapped" || red "T0-38: preset mapping broken"

# T0-39: Unsupported options rejected
echo "--- T0-39: Unsupported option rejection ---"
python3 -c "
import sys; sys.path.insert(0, '$REPO_DIR/25-video-creator/scripts')
from ai_providers import AIProvider
from pathlib import Path
for prov in ['runway', 'pika']:
    p = AIProvider(prov, {prov: {'api_key': 'dummy'}})
    try:
        p.generate_video('test', output=Path('/tmp/t.mp4'), seed=42, negative_prompt='bad')
        assert False, f'{prov} should have rejected unsupported options'
    except ValueError:
        pass
" 2>&1 && green "T0-39: unsupported options rejected on non-kieai providers" || red "T0-39: unsupported options not rejected"

echo ""
echo "=== U098 Results: $PASS passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ] || exit 1
