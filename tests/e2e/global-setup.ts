import { execSync } from 'child_process';
import path from 'path';
import fs from 'fs';

/**
 * Playwright globalSetup — runs before all tests.
 * Rebuilds the fixture database so timestamps are always "today".
 */
export default function globalSetup() {
  const scriptPath = path.resolve(__dirname, 'build-test-db.py');
  const fixturesDir = path.resolve(__dirname, 'fixtures');
  const projectRoot = path.resolve(__dirname, '../..');

  // Try the backend venv Python first, fall back to system python3
  const venvPython = path.join(projectRoot, 'backend', '.venv', 'bin', 'python');
  const python = fs.existsSync(venvPython) ? venvPython : 'python3';

  console.log(`Building test database with ${python}...`);
  execSync(`${python} ${scriptPath} ${fixturesDir}`, {
    stdio: 'inherit',
    cwd: projectRoot,
  });
}
