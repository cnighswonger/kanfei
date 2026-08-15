/**
 * Persona persistence + selection.
 *
 * Persona is the coarse audience-shape control that drives the
 * dashboard tile set and the sidebar filter (order + hidden pages).
 *
 * Two-tier persistence, same shape as ``ThemeContext``:
 *   - Signed-in admin's change: localStorage + PUT ``/api/config``
 *     via ``writeUIPref``.
 *   - Anonymous visitor's change: localStorage only.  The PUT will
 *     401/403 and ``writeUIPref`` swallows those — a passer-by on a
 *     public droplet can't re-skin the installation for everyone.
 *
 * Precedence on load: localStorage → backend default → 'everyday'.
 */

import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from 'react';
import { readUIPref, writeUIPref, syncUIPrefs } from '../utils/uiPrefs';

export type Persona = 'everyday' | 'agriculture' | 'weather_nerd';

export const PERSONAS: readonly Persona[] = ['everyday', 'agriculture', 'weather_nerd'] as const;

export const DEFAULT_PERSONA: Persona = 'everyday';

const PREF_KEY = 'ui_persona';

interface PersonaContextValue {
  persona: Persona;
  setPersona: (p: Persona) => void;
}

const PersonaContext = createContext<PersonaContextValue | null>(null);

function isPersona(v: string): v is Persona {
  return (PERSONAS as readonly string[]).includes(v);
}

function getInitialPersona(): Persona {
  const stored = readUIPref(PREF_KEY, DEFAULT_PERSONA);
  return isPersona(stored) ? stored : DEFAULT_PERSONA;
}

export function PersonaProvider({ children }: { children: ReactNode }) {
  const [persona, setPersonaState] = useState<Persona>(getInitialPersona);

  const setPersona = useCallback((p: Persona) => {
    if (!isPersona(p)) return;
    setPersonaState(p);
    writeUIPref(PREF_KEY, p);
  }, []);

  // Reconcile with backend on mount — matches ThemeContext pattern.
  // Only the first ``syncUIPrefs()`` call in the app does real work;
  // subsequent callers share the same promise.
  useEffect(() => {
    syncUIPrefs().then((prefs) => {
      const synced = prefs[PREF_KEY];
      if (synced && isPersona(synced) && synced !== persona) {
        setPersonaState(synced);
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <PersonaContext.Provider value={{ persona, setPersona }}>
      {children}
    </PersonaContext.Provider>
  );
}

export function usePersona(): PersonaContextValue {
  const ctx = useContext(PersonaContext);
  if (!ctx) {
    throw new Error('usePersona must be used within a PersonaProvider');
  }
  return ctx;
}
