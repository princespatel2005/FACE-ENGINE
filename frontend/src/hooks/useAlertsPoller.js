import { useEffect, useRef } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";

/** Poll /api/alerts for new events and surface them as sonner + browser notifications. */
export default function useAlertsPoller(enabled = true) {
  const seenRef = useRef(new Set());
  const sinceRef = useRef(new Date().toISOString());

  useEffect(() => {
    if (!enabled) return;
    // Ask permission once
    if ("Notification" in window && Notification.permission === "default") {
      Notification.requestPermission().catch(() => {});
    }

    let cancelled = false;
    const tick = async () => {
      try {
        const { data } = await api.get(`/alerts?limit=25&since=${encodeURIComponent(sinceRef.current)}`);
        if (data && data.length) sinceRef.current = data[0].timestamp;
        for (const a of data.reverse()) {
          if (seenRef.current.has(a.id)) continue;
          seenRef.current.add(a.id);
          const kind = a.kind;
          const title =
            kind === "blocked" ? "🚨 BLOCKED identity" :
            kind === "vip" ? "⭐ VIP arrival" :
            kind === "unknown" ? "❓ Unknown face" : "Sentinel FR";
          const msg = a.message || "";
          if (kind === "blocked") toast.error(title, { description: msg });
          else if (kind === "vip") toast(title, { description: msg });
          else toast.warning(title, { description: msg });

          try {
            if ("Notification" in window && Notification.permission === "granted") {
              new Notification(title, { body: msg, tag: a.id });
            }
          } catch (_) {}
        }
      } catch (_) {}
    };
    const iv = setInterval(tick, 4000);
    tick();
    return () => { cancelled = true; clearInterval(iv); };
  }, [enabled]);
}
