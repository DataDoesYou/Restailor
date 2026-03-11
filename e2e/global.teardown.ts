import path from 'path';
import { spawn } from 'child_process';

const ROOT_DIR = path.resolve(__dirname, '..');

function run(cmd: string, args: string[], cwd: string): Promise<void> {
  return new Promise((resolve) => {
    const p = spawn(cmd, args, { cwd, stdio: 'inherit', shell: process.platform === 'win32' });
    p.on('close', () => resolve());
    p.on('error', () => resolve());
  });
}

async function teardown() {
  // Best-effort purge of is_test=true rows after E2E run
  // Uses Poetry environment to execute the existing cleanup script.
  await run('poetry', ['run', 'python', 'scripts/purge_test_data.py'], ROOT_DIR);
}

export default teardown;
