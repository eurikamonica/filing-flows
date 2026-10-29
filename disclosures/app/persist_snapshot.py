"""Commit collector output while preserving newer modules written by another run."""
import json
import subprocess
import time
from pathlib import Path
from core import publish, write_json

# GitHub refuses a push that adds any file over 100 MiB (and warns from 50 MiB); the push then fails on every
# retry. Checked before pushing so the run says which file, instead of four silent retries.
GITHUB_FILE_LIMIT = 100 << 20
WARN_BYTES = 90 << 20


def freshness(value):
    return max((value.get(k) or '' for k in ('last_attempt', 'updated_at', 'last_success')), default='')


def merge_live(local, remote):
    out = {**remote, **local, 'modules': dict(remote.get('modules', {}))}
    for key, value in local.get('modules', {}).items():
        if freshness(value) >= freshness(out['modules'].get(key, {})):
            out['modules'][key] = value
    out['generated_at'] = max(local.get('generated_at') or '', remote.get('generated_at') or '')
    return out


def git(*args, check=True):
    return subprocess.run(['git', *args], check=check, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def too_large(names):
    """Staged files near or over GitHub's per-file limit: (errors, warnings) as readable lines."""
    errors, warnings = [], []
    for name in names:
        path = Path(name).relative_to('disclosures') if name.startswith('disclosures/') else Path(name)
        if not path.exists():
            continue
        size = path.stat().st_size
        line = f'{name}: {size / (1 << 20):.1f} MiB'
        if size > GITHUB_FILE_LIMIT:
            errors.append(line)
        elif size > WARN_BYTES:
            warnings.append(line)
    return errors, warnings


def tell(result):
    """The end of git's own message, so a failed rebase or push says why in the log."""
    text = ((result.stderr or '') + (result.stdout or '')).strip()
    return text[-1500:] if text else f'exit {result.returncode}'


def remote_json(path):
    result = git('show', 'origin/main:disclosures/' + str(path), check=False)
    return json.loads(result.stdout) if result.returncode == 0 else {}


def main():
    git('config', 'user.name', 'Filing Flows')
    git('config', 'user.email', 'filingflows@gmail.com')
    git('add', '-A', '--sparse', 'docs/data/')
    if git('diff', '--cached', '--quiet', check=False).returncode == 0:
        print('No data changes'); return
    # Keep our complete snapshot in memory: a text rebase cannot safely merge large JSON.
    live_path = Path('docs/data/live.json')
    local = json.loads(live_path.read_text()) if live_path.exists() else None
    changed = git('diff', '--cached', '--name-only').stdout.splitlines()
    statuses = {}
    for name in changed:
        relative = Path(name).relative_to('disclosures')
        if str(relative).startswith('docs/data/') and name.endswith('-status.json') and relative.exists():
            statuses[relative] = json.loads(relative.read_text())
    errors, warnings = too_large(changed)
    for line in warnings:
        print(f'::warning::{line} is close to GitHub\'s 100 MiB file limit; move more of it into shards', flush=True)
    if errors:
        for line in errors:
            print(f'::error::{line} is over GitHub\'s 100 MiB file limit, so the push would be refused', flush=True)
        raise RuntimeError('A data file is over GitHub\'s 100 MiB limit: ' + '; '.join(errors))
    git('commit', '-m', 'Update disclosure data and source status')
    for attempt in range(4):
        git('fetch', '-q', 'origin', 'main')
        result = git('rebase', '-X', 'theirs', 'origin/main', check=False)
        if result.returncode:
            print(f'::warning::rebase on the newest main failed (attempt {attempt + 1}): {tell(result)}', flush=True)
            git('rebase', '--abort', check=False)
        else:
            if local is not None:
                remote = remote_json(live_path)
                # Price enrichment may have hydrated and rewritten old holdings caches.
                # Keep the newer writer's dependent payloads together with its module header.
                for key in ('holdings', 'congress', 'cot', 'banks', 'npx'):
                    if freshness(remote.get('modules', {}).get(key, {})) > freshness(local.get('modules', {}).get(key, {})):
                        prefixes = (f'disclosures/docs/data/cache/{key}/', f'disclosures/docs/data/shards/{key}/')
                        for name in changed:
                            if name.startswith(prefixes) or name == f'disclosures/docs/data/catalogs/{key}.json':
                                relative = str(Path(name).relative_to('disclosures'))
                                if git('cat-file', '-e', 'origin/main:' + name, check=False).returncode == 0:
                                    git('restore', '--source=origin/main', '--worktree', '--', relative)
                publish(live_path.parent, merge_live(local, remote))
            for path, value in statuses.items():
                remote = remote_json(path)
                write_json(path, remote if freshness(remote) > freshness(value) else value)
            git('add', '-A', '--sparse', 'docs/data/')
            if git('diff', '--cached', '--quiet', check=False).returncode:
                git('commit', '-m', 'Preserve newest source snapshots after concurrent collection')
            merged, _ = too_large(['disclosures/docs/data/live.json', 'disclosures/docs/data/live.js'])
            if merged:
                raise RuntimeError('The merged snapshot is over GitHub\'s 100 MiB limit: ' + '; '.join(merged))
            result = git('push', '-q', 'origin', 'HEAD:main', check=False)
            if result.returncode == 0:
                print('Pushed on attempt', attempt + 1); return
            print(f'::warning::push refused (attempt {attempt + 1}): {tell(result)}', flush=True)
        time.sleep(15 * (attempt + 1))
    raise RuntimeError('Could not push the data snapshot after four attempts')


if __name__ == '__main__':
    main()
