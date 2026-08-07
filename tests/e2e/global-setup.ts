/**
 * Playwright globalSetup — no-op.
 *
 * The fixture DB rebuild used to live here, but Playwright starts `webServer`
 * BEFORE globalSetup runs, which meant the rebuild replaced the DB file after
 * uvicorn's SQLAlchemy pool had already opened handles to the previous inode.
 * Those stale handles caused readonly-database 500s on POST /api/auth/login
 * and stale-inode `validate_session` misses that 401 post-login requests
 * (see #286).  The rebuild has moved into `webServer.command` so it runs
 * before uvicorn starts, keeping the pool aligned with the file.
 *
 * Kept as an exported no-op so the `globalSetup: './global-setup.ts'` line in
 * `playwright.config.ts` doesn't error.
 */
export default function globalSetup() {
  // no-op — see file header
}
