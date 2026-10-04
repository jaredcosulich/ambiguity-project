import { afterEach, describe, expect, it, vi } from 'vitest';
import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';
import { resolveContentRoot, resolveDataRoot } from './contentRoot';

/**
 * Create a throwaway project root holding a real `.codeyam/tmp/<name>` sidecar.
 * The sidecar tests write an actual file rather than mocking `fs`: it is the
 * behaviour that matters (a file on disk must not redirect anything), and an
 * ESM namespace import cannot be spied on anyway.
 */
function projectRootWithSidecar(name: string, contents: string): string {
  const projectRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'codeyam-contentroot-'));
  const tmpDir = path.join(projectRoot, '.codeyam', 'tmp');
  fs.mkdirSync(tmpDir, { recursive: true });
  fs.writeFileSync(path.join(tmpDir, name), contents);
  return projectRoot;
}

describe('resolveContentRoot', () => {
  afterEach(() => {
    delete process.env.CODEYAM_CONTENT_ROOT;
    vi.unstubAllEnvs();
  });

  // The env override wins outright — this is the only redirect channel, and it
  // reaches the app through the environment of the dev server the editor spawns.
  it('prefers the CODEYAM_CONTENT_ROOT env override', () => {
    process.env.CODEYAM_CONTENT_ROOT = '/tmp/sandbox/content';
    expect(resolveContentRoot('/proj')).toBe('/tmp/sandbox/content');
  });

  // The regression guard for the whole change: a real `.codeyam/tmp/content-root`
  // file on disk must be IGNORED. Reading it redirected every process whose cwd
  // was the project — including the developer's own `npm run dev` — and nothing
  // ever deleted it, so one editor session made a checkout render scenario data
  // forever. Red if the sidecar branch is reintroduced.
  it('ignores a real .codeyam/tmp/content-root sidecar on disk', () => {
    const projectRoot = projectRootWithSidecar('content-root', '/tmp/sandbox/content\n');
    expect(resolveContentRoot(projectRoot)).toBe(path.join(projectRoot, 'src/content'));
  });

  // A production build resolves committed source even with the override set.
  // This is what makes the deploy guarantee structural rather than dependent on
  // `.codeyam/tmp/` being gitignored and CI building from a clean checkout.
  it('ignores the env override during a production build', () => {
    vi.stubEnv('PROD', true);
    process.env.CODEYAM_CONTENT_ROOT = '/tmp/sandbox/content';
    expect(resolveContentRoot('/proj')).toBe(path.join('/proj', 'src/content'));
  });

  // With no override present (a real production build, or any process outside
  // an editor session), the site reads its committed `src/content`.
  it('defaults to _projectRoot_/src/content when no override is present', () => {
    expect(resolveContentRoot('/proj')).toBe(path.join('/proj', 'src/content'));
  });
});

describe('resolveDataRoot', () => {
  afterEach(() => {
    delete process.env.CODEYAM_DATA_ROOT;
    vi.unstubAllEnvs();
  });

  // The data root honors its own env override — the singleton half of the
  // sandbox redirect, proving the two roots are wired independently.
  it('prefers the CODEYAM_DATA_ROOT env override', () => {
    process.env.CODEYAM_DATA_ROOT = '/tmp/sandbox/data';
    expect(resolveDataRoot('/proj')).toBe('/tmp/sandbox/data');
  });

  // The sidecar refusal covers the data root too — both ambient files the editor
  // used to write are inert now, not just the content one.
  it('ignores a real .codeyam/tmp/data-root sidecar on disk', () => {
    const projectRoot = projectRootWithSidecar('data-root', '/tmp/sandbox/data\n');
    expect(resolveDataRoot(projectRoot)).toBe(path.join(projectRoot, 'src/data'));
  });

  // The production-build refusal covers the data root too, so a deploy cannot
  // be redirected at scenario singletons any more than at scenario content.
  it('ignores the env override during a production build', () => {
    vi.stubEnv('PROD', true);
    process.env.CODEYAM_DATA_ROOT = '/tmp/sandbox/data';
    expect(resolveDataRoot('/proj')).toBe(path.join('/proj', 'src/data'));
  });

  // With no override present the site reads its committed `src/data`.
  it('defaults to _projectRoot_/src/data when no override is present', () => {
    expect(resolveDataRoot('/proj')).toBe(path.join('/proj', 'src/data'));
  });
});
