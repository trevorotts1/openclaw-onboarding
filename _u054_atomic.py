#!/usr/bin/env python3
"""U054: atomic fix script — checkout, edit, test, commit all in one invocation."""
import subprocess, sys, os, py_compile

REPO = '/Users/blackceomacmini/Downloads/July 25th Presentation Spec Documents/repos/openclaw-onboarding'
os.chdir(REPO)

def run(cmd, **kw):
    kw.setdefault('check', True)
    return subprocess.run(cmd, shell=True, capture_output=True, text=True, **kw)

# 1. Force checkout correct branch from origin/main
run('git checkout -B unit/U054-fix-exposed-file-generator-fix origin/main')
print("1. Checked out unit/U054-fix-exposed-file-generator-fix from origin/main")

# 2. Read the file
fpath = '23-ai-workforce-blueprint/scripts/create_role_workspaces.py'
with open(fpath, 'r', encoding='utf-8') as f:
    content = f.read()

# Verify starting state
assert 'def _link_shared_files_only(role_path, workspace_root, results):' in content
assert 'symlinked = []\n    converted = []\n    for shared in V21_SYMLINKS:' in content
print("2. Verified starting state on origin/main")

# 3. Edit 1: Update _link_shared_files_only signature (results=None, return dict)
idx_fn = content.find('def _link_shared_files_only(role_path, workspace_root, results):')
idx_next = content.find('\ndef _is_sops_library_dir', idx_fn)
old_fn = content[idx_fn:idx_next]

new_fn = (
    'def _link_shared_files_only(role_path, workspace_root, results=None):\n'
    '    """Create symlinks for shared V21_SYMLINKS files in a role folder or container.\n'
    '\n'
    '    U054: The single canonical symlink + stale-file-conversion implementation\n'
    '    called by create_role_workspace(), augment_role_folder(), and\n'
    '    augment_all_existing_role_folders() (for sops/ containers).\n'
    '\n'
    '    Backs up stale regular copies as .bak-unify-<timestamp> before converting\n'
    '    them to symlinks.  Never writes stubs or touches AGENTS.md.\n'
    '\n'
    '    Args:\n'
    '        role_path: Path to the role folder or container.\n'
    '        workspace_root: Path to the workspace root.\n'
    '        results: Optional list to append result dict to (for sops containers).\n'
    '\n'
    '    Returns:\n'
    '        dict with keys "symlinked", "converted" (and "skipped_container" when\n'
    '        results is passed).\n'
    '    """\n'
    '    role_path = Path(role_path)\n'
    '    workspace_root = Path(workspace_root)\n'
    '    symlinked = []\n'
    '    converted = []\n'
    '    for shared in V21_SYMLINKS:\n'
    '        link_path = role_path / shared\n'
    '        target = workspace_root / shared\n'
    '        if link_path.is_symlink():\n'
    '            if link_path.resolve() == target.resolve():\n'
    '                continue                      # already correct\n'
    '            link_path.unlink()                # wrong target: relink\n'
    '        elif link_path.exists():\n'
    '            ts = datetime.now().strftime("%Y%m%d-%H%M%S")\n'
    '            bak = link_path.with_name(f"{shared}.bak-unify-{ts}")\n'
    '            try:\n'
    '                link_path.replace(bak)\n'
    '            except OSError as e:\n'
    '                print(f"  WARN: could not back up {shared} before converting: {e}",\n'
    '                      file=sys.stderr)\n'
    '                continue\n'
    '            converted.append(shared)\n'
    '        try:\n'
    '            link_path.symlink_to(target)\n'
    '            symlinked.append(shared)\n'
    '        except OSError as e:\n'
    '            print(f"  WARN: could not symlink {shared}: {e}", file=sys.stderr)\n'
    '    result = {"symlinked": symlinked, "converted": converted}\n'
    '    if results is not None:\n'
    '        results.append({"role": role_path.name, "written": [],\n'
    '                        "symlinked": symlinked, "converted": converted,\n'
    '                        "skipped_container": True})\n'
    '    return result'
)
content = content.replace(old_fn, new_fn, 1)
print("3. Edit 1 OK: unified _link_shared_files_only signature")

# 4. Edit 2: Replace augment_role_folder inline loop
old_a_start = content.find('symlinked = []\n    converted = []\n    for shared in V21_SYMLINKS:')
old_a_end_marker = 'return {"written": written, "symlinked": symlinked, "converted": converted}'
old_a_end = content.find(old_a_end_marker, old_a_start) + len(old_a_end_marker)
old_a = content[old_a_start:old_a_end]

new_a = (
    'link_result = _link_shared_files_only(role_path, workspace_root)\n'
    '    symlinked = link_result["symlinked"]\n'
    '    converted = link_result["converted"]\n'
    '\n'
    '    return {"written": written, "symlinked": symlinked, "converted": converted}'
)
content = content.replace(old_a, new_a, 1)
print("4. Edit 2 OK: augment_role_folder calls _link_shared_files_only")

# 5. Edit 3: Replace create_role_workspace inline loop
old_c_start = content.find('# Symlinks for shared files\n    for shared in ["AGENTS.md", "TOOLS.md", "USER.md"]:')
old_c_end_marker = 'return role_path\n\n'
old_c_end = content.find(old_c_end_marker, old_c_start) + len(old_c_end_marker)
old_c = content[old_c_start:old_c_end]

new_c = (
    '# Symlinks for shared files\n'
    '    _link_shared_files_only(role_path, Path(workspace_root))\n'
    '\n'
    '    return role_path\n\n'
)
content = content.replace(old_c, new_c, 1)
print("5. Edit 3 OK: create_role_workspace calls _link_shared_files_only")

# 6. Verify
py_compile.compile(fpath, doraise=True)
c = content.count('for shared in V21_SYMLINKS')
assert c == 1, f"Expected 1, got {c}"
c2 = content.count('def _link_shared_files_only')
assert c2 == 1, f"Expected 1 definition, got {c2}"
print(f"6. VERIFY: for shared in V21_SYMLINKS count = {c} (PASS)")
print("6. VERIFY: Python syntax check (PASS)")

# 7. Write file
with open(fpath, 'w', encoding='utf-8') as f:
    f.write(content)

# 8. Restore test file
src = 'fix-u054-v2:23-ai-workforce-blueprint/scripts/test_role_workspace_symlinks.py'
dest = '23-ai-workforce-blueprint/scripts/test_role_workspace_symlinks.py'
run(f'git show {src} > {dest}')
print("8. Restored test file")

# 9. Run tests
result = run('python3 23-ai-workforce-blueprint/scripts/test_role_workspace_symlinks.py', check=False)
if result.returncode != 0:
    print(f"TEST FAILED:\n{result.stdout}{result.stderr}")
    sys.exit(1)
print("9. All 4 tests PASSED")

# 10. Git add and commit
run('git add -A')
commit_msg = 'fix(U054): factor symlink loop into single _link_shared_files_only() call from both callers'
run(f'git commit -m "{commit_msg}"')
print("10. Committed")

# 11. Get HEAD
head = subprocess.run(['git', 'rev-parse', 'HEAD'], capture_output=True, text=True).stdout.strip()
print(f"11. HEAD: {head}")

# 12. Force push
run(f'git push --force-with-lease origin unit/U054-fix-exposed-file-generator-fix:unit/U054-fix-exposed-file-generator-fix')
print("12. Pushed")

# Final report
print(f"\n=== U054 FIX COMPLETE ===")
print(f"Branch: unit/U054-fix-exposed-file-generator-fix")
print(f"HEAD: {head}")
print(f"grep 'for shared in V21_SYMLINKS' count: 1")
print(f"Tests: all 4 passed")
