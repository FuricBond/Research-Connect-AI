/**
 * Phase 6.2 — test environment setup.
 *
 * jsdom supplies a real localStorage, so the storage tests exercise the same code path
 * the browser does rather than a hand-written stub.
 */

import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, beforeEach } from "vitest";

// React only enables act() support when it knows it is under a test runner.
declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

beforeEach(() => {
  // Each test starts with no stored identity, so one test's session cannot leak
  // into the next and make a later assertion pass for the wrong reason.
  window.localStorage.clear();
  window.sessionStorage.clear();
});

afterEach(() => {
  cleanup();
});
