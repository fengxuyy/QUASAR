import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { isPathInside, resolveSafeWorkspacePath, } from './pathSecurity.js';
test('isPathInside blocks sibling prefix bypass', () => {
    assert.equal(isPathInside('/tmp/ws', '/tmp/ws'), true);
    assert.equal(isPathInside('/tmp/ws', '/tmp/ws/a'), true);
    assert.equal(isPathInside('/tmp/ws', '/tmp/ws-evil/x'), false);
    assert.equal(isPathInside('/tmp/ws', '/tmp/ws2'), false);
    assert.equal(isPathInside('/srv/quasar/workspaces/user-1/workspace', '/srv/quasar/workspaces/user-1/workspace_evil'), false);
    assert.equal(isPathInside('/srv/quasar/workspaces/user-1/workspace', path.resolve('/srv/quasar/workspaces/user-1/workspace', '../workspace_evil')), false);
});
test('resource-cache docs symlink is allowed for existing paths', () => {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), 'quasar-path-docs-'));
    const workspace = path.join(root, 'workspace');
    const cache = path.join(root, 'resource-cache', 'docs', 'lammps');
    fs.mkdirSync(workspace, { recursive: true });
    fs.mkdirSync(cache, { recursive: true });
    fs.writeFileSync(path.join(cache, 'README'), 'lammps docs\n', 'utf8');
    fs.symlinkSync(path.join(root, 'resource-cache', 'docs'), path.join(workspace, 'docs'));
    const prev = process.env.QUASAR_RESOURCE_CACHE;
    process.env.QUASAR_RESOURCE_CACHE = path.join(root, 'resource-cache');
    try {
        const listed = resolveSafeWorkspacePath(workspace, 'docs/lammps', 'existing');
        assert.equal(listed.ok, true);
        if (listed.ok) {
            assert.ok(listed.realPath?.includes('resource-cache'));
            assert.ok(listed.absolute.endsWith(path.join('docs', 'lammps')));
        }
    }
    finally {
        if (prev === undefined)
            delete process.env.QUASAR_RESOURCE_CACHE;
        else
            process.env.QUASAR_RESOURCE_CACHE = prev;
        fs.rmSync(root, { recursive: true, force: true });
    }
});
test('resolveSafeWorkspacePath blocks traversal and symlink escape', () => {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), 'quasar-path-sec-'));
    const workspace = path.join(root, 'workspace');
    const outsider = path.join(root, 'secret.txt');
    fs.mkdirSync(workspace, { recursive: true });
    fs.writeFileSync(outsider, 'top-secret\n', 'utf8');
    fs.writeFileSync(path.join(workspace, 'ok.txt'), 'safe\n', 'utf8');
    fs.symlinkSync(outsider, path.join(workspace, 'leak'));
    try {
        assert.equal(resolveSafeWorkspacePath(workspace, 'ok.txt').ok, true);
        assert.equal(resolveSafeWorkspacePath(workspace, '../secret.txt').ok, false);
        assert.equal(resolveSafeWorkspacePath(workspace, '../workspace_evil').ok, false);
        assert.equal(resolveSafeWorkspacePath(workspace, '/etc/passwd').ok, false);
        const leak = resolveSafeWorkspacePath(workspace, 'leak', 'existing');
        assert.equal(leak.ok, false);
        const nested = path.join(workspace, 'sub');
        fs.mkdirSync(nested);
        const created = resolveSafeWorkspacePath(workspace, 'sub/new.txt', 'new');
        assert.equal(created.ok, true);
        // Symlink directory pointing outside must not allow new writes under it.
        const outsideDir = path.join(root, 'outside-dir');
        fs.mkdirSync(outsideDir);
        fs.symlinkSync(outsideDir, path.join(workspace, 'out-link'));
        const viaLink = resolveSafeWorkspacePath(workspace, 'out-link/pwned.txt', 'new');
        assert.equal(viaLink.ok, false);
    }
    finally {
        fs.rmSync(root, { recursive: true, force: true });
    }
});
