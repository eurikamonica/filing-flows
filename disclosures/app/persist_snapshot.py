"""Commit collector output while preserving newer modules written by another run."""
import json
import subprocess
import time
from pathlib import Path
from core import publish, write_json


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
    git('commit', '-m', 'Update disclosure data and source status')
    for attempt in range(4):
        git('fetch', '-q', 'origin', 'main')
        result = git('rebase', '-X', 'theirs', 'origin/main', check=False)
        if result.returncode:
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
            result = git('push', '-q', 'origin', 'HEAD:main', check=False)
            if result.returncode == 0:
                print('Pushed on attempt', attempt + 1); return
        time.sleep(15 * (attempt + 1))
    raise RuntimeError('Could not push the data snapshot after four attempts')


if __name__ == '__main__':
    main()
