import { defineConfig, type PluginOption } from 'vite';
import react from '@vitejs/plugin-react';
import { spawn, type ChildProcess } from 'node:child_process';
import { existsSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));

/**
 * Auto-start the OAK UVC bridge (scripts/oak_uvc.py) when the dev server
 * boots, so the user's live-capture flow "just works" without opening a
 * second terminal. The plugin:
 *
 *   - only runs on `vite` (dev), never on `vite build`
 *   - forwards the script's stdout/stderr with a [oak-uvc] prefix
 *   - is fail-soft: if python / depthai / an OAK aren't available, we log
 *     and continue — the rest of the app still works against any webcam
 *   - kills the child on server close + process exit signals
 *
 * Controls:
 *   VITE_NO_OAK_UVC=1      — disable the plugin entirely
 *   OAK_UVC_PYTHON=<path>  — override the python binary (defaults to
 *                            `python3` → `python` in that order)
 */
function oakUvcBridge(): PluginOption {
  const enabled = process.env.VITE_NO_OAK_UVC !== '1';
  let child: ChildProcess | null = null;

  const scriptPath = resolve(__dirname, 'scripts/oak_uvc.py');

  const killChild = () => {
    if (child && !child.killed) {
      try { child.kill('SIGTERM'); } catch { /* noop */ }
      child = null;
    }
  };

  return {
    name: 'oak-uvc-bridge',
    apply: 'serve',
    configureServer(server) {
      if (!enabled) {
        server.config.logger.info('[oak-uvc] disabled via VITE_NO_OAK_UVC=1');
        return;
      }
      if (!existsSync(scriptPath)) {
        server.config.logger.warn(`[oak-uvc] script missing at ${scriptPath}`);
        return;
      }

      // Prefer an adjacent .venv so the user doesn't have to activate one
      // before `npm run dev`. The repo-root venv at ../.venv is the common
      // layout for this project.
      const venvCandidates = [
        resolve(__dirname, '.venv/bin/python'),
        resolve(__dirname, '../.venv/bin/python'),
        resolve(__dirname, '../venv/bin/python'),
      ].filter((p) => existsSync(p));

      const pythonCandidates = [
        process.env.OAK_UVC_PYTHON,
        ...venvCandidates,
        'python3',
        'python',
      ].filter((x): x is string => !!x);

      const tryNext = (idx: number): void => {
        if (idx >= pythonCandidates.length) {
          server.config.logger.warn(
            '[oak-uvc] no usable python interpreter found. install Python 3 and depthai, ' +
              'or set OAK_UVC_PYTHON=/path/to/venv/python, then restart `npm run dev`. ' +
              'live capture will fall back to the built-in webcam.',
          );
          return;
        }
        const py = pythonCandidates[idx];
        server.config.logger.info(`[oak-uvc] starting: ${py} scripts/oak_uvc.py`);
        const proc = spawn(py, [scriptPath], {
          stdio: ['ignore', 'pipe', 'pipe'],
          env: process.env,
          cwd: __dirname,
        });
        child = proc;

        proc.stdout?.on('data', (d: Buffer) => {
          process.stdout.write(`[oak-uvc] ${d.toString()}`);
        });
        proc.stderr?.on('data', (d: Buffer) => {
          process.stderr.write(`[oak-uvc] ${d.toString()}`);
        });
        proc.on('error', (err) => {
          // spawn itself failed (binary not found, EACCES, …) — try next candidate.
          if ((err as NodeJS.ErrnoException).code === 'ENOENT') {
            server.config.logger.info(`[oak-uvc] ${py} not on PATH, trying next candidate`);
            child = null;
            tryNext(idx + 1);
          } else {
            server.config.logger.warn(`[oak-uvc] spawn error: ${err.message}`);
          }
        });
        proc.on('exit', (code, signal) => {
          if (child === proc) child = null;
          if (signal === 'SIGTERM' || signal === 'SIGINT') return; // we killed it
          if (code !== 0) {
            server.config.logger.warn(
              `[oak-uvc] exited with code=${code}. See messages above. ` +
                'Live capture will use whatever webcam is available.',
            );
          }
        });
      };

      tryNext(0);

      server.httpServer?.once('close', killChild);
    },
    closeBundle() { killChild(); },
    buildEnd()    { killChild(); },
  };
}

// Ensure the child is reaped even on uncaught process termination.
process.on('SIGINT', () => { process.exit(0); });
process.on('SIGTERM', () => { process.exit(0); });

export default defineConfig({
  plugins: [react(), oakUvcBridge()],
});
