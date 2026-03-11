// Kill any stray processes on our test ports before Playwright starts web servers.
// This avoids flaky port-in-use errors and ensures servers inherit test env.

const killPort = require('kill-port');
const { execSync } = require('child_process');
const path = require('path');

/** @type {import('@playwright/test').GlobalSetup} */
module.exports = async () => {
  const REUSE_UI = (process.env.REUSE_UI ?? '1').toString().trim() === '1';
  // Ensure frontend dependencies are installed (idempotent). On Windows, avoid
  // touching node_modules if it already exists to prevent EPERM unlink issues.
  try {
    const FRONTEND_DIR = path.resolve(__dirname, '..', '..', 'frontend');
    const fs = require('fs');
    const nm = path.join(FRONTEND_DIR, 'node_modules');
    if (!fs.existsSync(nm)) {
      try {
        execSync(`npm --prefix "${FRONTEND_DIR}" ci`, { stdio: 'inherit' });
      } catch {
        execSync(`npm --prefix "${FRONTEND_DIR}" install`, { stdio: 'inherit' });
      }
    }
  } catch {}
  // Ensure Next.js port 3000 is free before starting UI unless reusing
  if (!REUSE_UI) {
    try {
      await killPort(3000, 'tcp');
    } catch {}
    // Tiny delay to allow OS to release the port fully
    await new Promise(r => setTimeout(r, 250));
  }
};
