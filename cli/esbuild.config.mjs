import { build } from 'esbuild';
import { createRequire } from 'module';
import fs from 'fs';

const require = createRequire(import.meta.url);
const pkg = require('./package.json');

// Plugin to stub out optional dependencies that aren't needed at runtime
const stubPlugin = {
  name: 'stub-optional-deps',
  setup(build) {
    // react-devtools-core is an optional peer dep of ink, never needed in production
    build.onResolve({ filter: /^react-devtools-core$/ }, () => ({
      path: 'react-devtools-core',
      namespace: 'stub',
    }));
    build.onLoad({ filter: /.*/, namespace: 'stub' }, () => ({
      contents: 'export default undefined;',
      loader: 'js',
    }));
  },
};

await build({
  entryPoints: ['dist/cli.js'],
  bundle: true,
  platform: 'node',
  target: 'node20',
  format: 'esm',
  outfile: 'dist/cli.bundle.mjs',
  banner: {
    js: [
      // Provide require() and __dirname/__filename for CJS compatibility in ESM bundle
      'import { createRequire as __bundled_createRequire } from "module";',
      'import { fileURLToPath as __bundled_fileURLToPath } from "url";',
      'import { dirname as __bundled_dirname } from "path";',
      'const require = __bundled_createRequire(import.meta.url);',
      'const __filename = __bundled_fileURLToPath(import.meta.url);',
      'const __dirname = __bundled_dirname(__filename);',
    ].join('\n'),
  },
  plugins: [stubPlugin],
  // Inline source maps for error stack traces
  sourcemap: 'inline',
  // Minify to reduce bundle size
  minify: true,
  // Embed the version so package.json is not needed at runtime
  define: {
    'QUASAR_CLI_VERSION': JSON.stringify(pkg.version),
  },
  logLevel: 'info',
});

// Make the bundle executable
fs.chmodSync('dist/cli.bundle.mjs', 0o755);

console.log('✓ CLI bundle created: dist/cli.bundle.mjs');
