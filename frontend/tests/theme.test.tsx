/**
 * P1.15 — the colour theme is one deliberate decision: light, dark or "match system", stored,
 * applied before first paint, and followed live while "system" is chosen.
 */

import React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { ThemeSwitcher } from "../components/ui/ThemeSwitcher/ThemeSwitcher";
import { THEME_INIT_SCRIPT, THEME_STORAGE_KEY, applyThemePreference, readThemePreference, resolveTheme } from "../utils/theme";

let systemDark = false;
let listeners: Array<() => void> = [];

beforeEach(() => {
  systemDark = false;
  listeners = [];
  vi.stubGlobal(
    "matchMedia",
    vi.fn(() => ({
      get matches() {
        return systemDark;
      },
      addEventListener: (_: string, listener: () => void) => listeners.push(listener),
      removeEventListener: (_: string, listener: () => void) => (listeners = listeners.filter((l) => l !== listener)),
    }))
  );
  document.documentElement.removeAttribute("data-theme");
  document.documentElement.removeAttribute("data-theme-preference");
});

afterEach(() => {
  vi.unstubAllGlobals();
});

const theme = () => document.documentElement.getAttribute("data-theme");

describe("theme resolution", () => {
  it("resolves system to the OS preference and keeps explicit choices", () => {
    expect(resolveTheme("system", true)).toBe("dark");
    expect(resolveTheme("system", false)).toBe("light");
    expect(resolveTheme("light", true)).toBe("light");
    expect(resolveTheme("dark", false)).toBe("dark");
  });

  it("stores and applies a choice", () => {
    applyThemePreference("dark");
    expect(theme()).toBe("dark");
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe("dark");
    expect(readThemePreference()).toBe("dark");
  });

  it("ignores a corrupt stored value", () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, "sepia");
    expect(readThemePreference()).toBe("system");
  });
});

describe("the script that runs before first paint", () => {
  it("applies the stored choice", () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, "dark");
    new Function(THEME_INIT_SCRIPT)();
    expect(theme()).toBe("dark");
  });

  it("follows the OS when nothing is stored", () => {
    systemDark = true;
    new Function(THEME_INIT_SCRIPT)();
    expect(theme()).toBe("dark");
    expect(document.documentElement.getAttribute("data-theme-preference")).toBe("system");
  });
});

describe("ThemeSwitcher", () => {
  it("offers three named choices and applies the one picked", () => {
    render(<ThemeSwitcher />);
    expect(screen.getByRole("group", { name: "Colour theme" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("radio", { name: "Dark theme" }));
    expect(theme()).toBe("dark");
    expect(screen.getByRole("radio", { name: "Dark theme" })).toBeChecked();
    fireEvent.click(screen.getByRole("radio", { name: "Light theme" }));
    expect(theme()).toBe("light");
  });

  it("follows an OS change live while 'match system' is chosen", () => {
    render(<ThemeSwitcher />);
    fireEvent.click(screen.getByRole("radio", { name: "Dark theme" }));
    fireEvent.click(screen.getByRole("radio", { name: "Match system theme" }));
    expect(theme()).toBe("light");
    systemDark = true;
    listeners.forEach((listener) => listener());
    expect(theme()).toBe("dark");
  });
});
