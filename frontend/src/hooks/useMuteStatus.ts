// Polls /api/mute/status for the list of channels the operator has
// muted.  The AppShell uses this to drive a persistent reminder banner
// whenever any sensor is being suppressed from outbound uploads
// (CWOP/APRS, Weather Underground, future destinations).
//
// Settings dispatches a `channel-mute-changed` window event after a
// successful save so the banner reflects mute toggles inside a frame,
// without waiting for the next 30s poll.

import { useEffect, useState } from "react";
import { fetchMuteStatus } from "../api/client.ts";

const POLL_MS = 30_000;
const EVENT_NAME = "channel-mute-changed";

export function useMuteStatus(): string[] {
  const [muted, setMuted] = useState<string[]>([]);

  useEffect(() => {
    let cancelled = false;

    const refresh = () => {
      fetchMuteStatus()
        .then((res) => {
          if (cancelled) return;
          // Preserve array identity when the muted set is unchanged so
          // consumers (AppShell) don't re-render every poll cycle.
          setMuted((prev) => {
            const next = res.muted;
            if (
              prev.length === next.length &&
              prev.every((c, i) => c === next[i])
            ) {
              return prev;
            }
            return next;
          });
        })
        .catch(() => {
          // Ignore — banner just stays at its previous state.
        });
    };

    refresh();
    const timer = window.setInterval(refresh, POLL_MS);
    window.addEventListener(EVENT_NAME, refresh);

    return () => {
      cancelled = true;
      window.clearInterval(timer);
      window.removeEventListener(EVENT_NAME, refresh);
    };
  }, []);

  return muted;
}

export function notifyMuteChanged(): void {
  window.dispatchEvent(new Event(EVENT_NAME));
}
