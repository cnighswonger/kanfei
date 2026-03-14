// ============================================================
// Feature flags context — controls visibility of optional
// features (sidebar nav items, routes, settings tabs).
// Fetches config once at mount; exposes refresh() for
// Settings to call after save so changes take effect immediately.
// ============================================================

import {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
} from "react";
import type { ReactNode } from "react";
import { fetchConfig } from "../api/client.ts";

export interface FeatureFlags {
  nowcastEnabled: boolean;
  sprayEnabled: boolean;
}

interface FeatureFlagsContextValue {
  flags: FeatureFlags;
  loading: boolean;
  refresh: () => Promise<void>;
}

const FeatureFlagsContext = createContext<FeatureFlagsContextValue | null>(null);

const DEFAULTS: FeatureFlags = { nowcastEnabled: false, sprayEnabled: false };

const FLAG_KEYS: Record<string, keyof FeatureFlags> = {
  nowcast_enabled: "nowcastEnabled",
  spray_enabled: "sprayEnabled",
};

function extractFlags(
  configItems: Array<{ key: string; value: unknown }>,
): FeatureFlags {
  const flags = { ...DEFAULTS };
  for (const item of configItems) {
    const mapped = FLAG_KEYS[item.key];
    if (mapped) {
      flags[mapped] = item.value === true || item.value === "true";
    }
  }
  return flags;
}

export function FeatureFlagsProvider({ children }: { children: ReactNode }) {
  const [flags, setFlags] = useState<FeatureFlags>(DEFAULTS);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const items = await fetchConfig();
      setFlags(extractFlags(items));
    } catch {
      // fail-open: keep current flags
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return (
    <FeatureFlagsContext.Provider value={{ flags, loading, refresh }}>
      {children}
    </FeatureFlagsContext.Provider>
  );
}

export function useFeatureFlags(): FeatureFlagsContextValue {
  const ctx = useContext(FeatureFlagsContext);
  if (!ctx) {
    throw new Error(
      "useFeatureFlags must be used within a FeatureFlagsProvider",
    );
  }
  return ctx;
}
