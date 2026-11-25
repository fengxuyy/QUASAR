import fs from 'node:fs';
import path from 'node:path';
/**
 * Lexical containment: target is base or a descendant after resolve().
 * Does not follow symlinks — pair with assertPathInsideWorkspace for I/O.
 */
export function isPathInside(baseDir, targetPath) {
    const base = path.resolve(baseDir);
    const target = path.resolve(targetPath);
    const relative = path.relative(base, target);
    return relative === '' || (!!relative && !relative.startsWith('..') && !path.isAbsolute(relative));
}
/** Optional extra roots that workspace symlinks may target (shared docs/RAG caches). */
export function allowedExternalRoots(env = process.env) {
    const roots = [];
    for (const key of ['QUASAR_RESOURCE_CACHE', 'QUASAR_BUNDLED_ENGINE_ROOT', 'QUASAR_RUNTIME_ROOT']) {
        const value = (env[key] || '').trim();
        if (!value)
            continue;
        const resolved = path.resolve(value);
        roots.push(resolved);
        // macOS often resolves /var → /private/var; compare against realpath too.
        try {
            roots.push(fs.realpathSync(resolved));
        }
        catch {
            // root may not exist yet
        }
    }
    return [...new Set(roots)];
}
export function isAllowedResolvedPath(realBase, realPath, extraRoots = allowedExternalRoots()) {
    if (isPathInside(realBase, realPath))
        return true;
    return extraRoots.some(root => isPathInside(root, realPath));
}
function lexicalResolve(baseDir, relativePath) {
    if (typeof relativePath !== 'string') {
        return { ok: false, error: 'Invalid path' };
    }
    // Reject NUL and absolute inputs disguised as relative segments.
    if (relativePath.includes('\0')) {
        return { ok: false, error: 'Invalid path' };
    }
    // Allow "" / "." for workspace root; still reject absolute paths.
    const cleaned = relativePath === '' || relativePath === '.' ? '.' : relativePath;
    if (cleaned !== '.' && path.isAbsolute(cleaned)) {
        return { ok: false, error: 'Absolute paths are not allowed' };
    }
    const absolute = cleaned === '.' ? path.resolve(baseDir) : path.resolve(baseDir, cleaned);
    if (!isPathInside(baseDir, absolute)) {
        return { ok: false, error: 'Access denied' };
    }
    let realBase;
    try {
        realBase = fs.realpathSync(path.resolve(baseDir));
    }
    catch {
        return { ok: false, error: 'Workspace is not accessible' };
    }
    return { ok: true, absolute, realBase };
}
/**
 * Resolve user-supplied relative path under baseDir and ensure it cannot escape.
 *
 * - Always enforces lexical containment (blocks `../sibling-prefix` startsWith bugs).
 * - For existing paths, resolves realpath and requires the real location stay inside
 *   the real workspace (blocks symlink escape to other tenants/host paths).
 * - For new paths (`mode: 'new'`), walks parents until an existing directory is found
 *   and checks that ancestor; refuses if any intermediate existing component is a
 *   symlink that points outside the workspace.
 * - For `lexical`, only containment of the path string (used to delete symlinks without
 *   following them to outside targets).
 */
export function resolveSafeWorkspacePath(baseDir, relativePath, mode = 'existing') {
    const lexical = lexicalResolve(baseDir, relativePath);
    if (!lexical.ok)
        return lexical;
    const { absolute, realBase } = lexical;
    if (mode === 'lexical') {
        return lexical;
    }
    if (mode === 'existing') {
        let realPath;
        try {
            // realpath fails on missing paths; follows symlinks when present.
            realPath = fs.realpathSync(absolute);
        }
        catch {
            return { ok: false, error: 'Path not found' };
        }
        if (!isAllowedResolvedPath(realBase, realPath)) {
            return { ok: false, error: 'Access denied' };
        }
        return { ok: true, absolute, realBase, realPath };
    }
    // mode === 'new': file/dir may not exist yet. Validate deepest existing ancestor.
    // Refuse writing through a symlink leaf or symlink parent that escapes.
    try {
        const realPath = fs.realpathSync(absolute);
        if (!isAllowedResolvedPath(realBase, realPath)) {
            return { ok: false, error: 'Access denied' };
        }
        // Overwrite only when real location stays inside workspace (not external caches).
        if (!isPathInside(realBase, realPath)) {
            return { ok: false, error: 'Access denied' };
        }
        return { ok: true, absolute, realBase, realPath };
    }
    catch {
        // does not exist — walk parents
    }
    let cursor = absolute;
    while (cursor !== realBase && cursor !== path.dirname(cursor)) {
        const parent = path.dirname(cursor);
        try {
            const realParent = fs.realpathSync(parent);
            // New files only under the real workspace, never under external cache roots.
            if (!isPathInside(realBase, realParent)) {
                return { ok: false, error: 'Access denied' };
            }
            const leaf = path.relative(parent, absolute);
            const projected = path.resolve(realParent, leaf);
            if (!isPathInside(realBase, projected)) {
                return { ok: false, error: 'Access denied' };
            }
            return { ok: true, absolute, realBase };
        }
        catch {
            cursor = parent;
        }
    }
    return { ok: true, absolute, realBase };
}
/** Convenience for API handlers: returns absolute path or null + sets nothing. */
export function safeExistingPath(baseDir, relativePath) {
    const result = resolveSafeWorkspacePath(baseDir, relativePath, 'existing');
    return result.ok ? (result.realPath || result.absolute) : null;
}
export function safeNewPath(baseDir, relativePath) {
    const result = resolveSafeWorkspacePath(baseDir, relativePath, 'new');
    return result.ok ? result.absolute : null;
}
export function safePathError(result) {
    return result.ok === false ? result.error : 'Access denied';
}
export function safePathHttpStatus(result) {
    return result.ok === false && result.error === 'Path not found' ? 404 : 403;
}
