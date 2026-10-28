import { useEffect, useState } from 'react';

export type ThemePref = 'light' | 'dark' | 'system';

const KEY = 'openprism-theme';
const listeners = new Set<(pref: ThemePref) => void>();

function readStored(): ThemePref {
  try {
    const v = window.localStorage.getItem(KEY);
    if (v === 'light' || v === 'dark' || v === 'system') return v;
  } catch {
    /* storage unavailable */
  }
  return 'light';
}

let current: ThemePref = typeof window === 'undefined' ? 'light' : readStored();

function resolve(pref: ThemePref): 'light' | 'dark' {
  if (pref !== 'system') return pref;
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

/** Apply the stored theme to <html>. Call once before the first render. */
export function initTheme() {
  document.documentElement.setAttribute('data-theme', resolve(current));
  window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
    if (current === 'system') document.documentElement.setAttribute('data-theme', resolve('system'));
  });
}

export function setTheme(pref: ThemePref) {
  current = pref;
  try {
    window.localStorage.setItem(KEY, pref);
  } catch {
    /* storage unavailable */
  }
  document.documentElement.setAttribute('data-theme', resolve(pref));
  listeners.forEach((fn) => fn(pref));
}

export function useTheme(): [ThemePref, (pref: ThemePref) => void] {
  const [pref, setPref] = useState<ThemePref>(current);
  useEffect(() => {
    listeners.add(setPref);
    return () => {
      listeners.delete(setPref);
    };
  }, []);
  return [pref, setTheme];
}
