import type { RunEvent } from "../types";

const SHOW_DATA: Record<string, (d: Record<string, any>) => string | null> = {
  validate: (d) => {
    const fills = d.fill_rates ?? {};
    const distincts = d.distinct_ratios ?? {};
    const lines = Object.keys(fills).map((f) => {
      const fill = `${Math.round((fills[f] ?? 0) * 100)}% present`;
      const distinct = `${Math.round((distincts[f] ?? 0) * 100)}% distinct`;
      return `${f.padEnd(8)} ${fill.padEnd(14)} ${distinct}`;
    });
    return lines.length ? lines.join("\n") : null;
  },
  drift_detected: (d) =>
    Array.isArray(d.violations) && d.violations.length
      ? d.violations.map((v: string) => `· ${v}`).join("\n")
      : null,
  candidate_proposed: (d) => {
    const diff = d.diff ?? {};
    const rows = Object.entries(diff).map(([field, change]: [string, any]) => {
      const before = JSON.stringify(change.before ?? null);
      const after = JSON.stringify(change.after ?? null);
      return `${field}\n  was  ${before}\n  now  ${after}`;
    });
    return rows.length ? rows.join("\n") : null;
  },
  gate_continuity: (d) =>
    d.baseline_size
      ? `${d.matched}/${d.baseline_size} trusted records recovered · threshold ${Math.round(
          (d.threshold ?? 0) * 100,
        )}%`
      : null,
};

export function RunLog({ events, busy }: { events: RunEvent[]; busy: boolean }) {
  if (!events.length) {
    return (
      <p className="empty">
        {busy ? "Reading the source…" : "No run yet. Start the pipeline to see what it decides."}
      </p>
    );
  }

  return (
    <ul className="log">
      {events.map((event) => {
        const detail = SHOW_DATA[event.code]?.(event.data ?? {});
        return (
          <li key={event.seq} className={`log__item log__item--${event.level}`}>
            <span className="log__seq">{String(event.seq).padStart(2, "0")}</span>
            <div>
              <div className="log__code">{event.code}</div>
              <div className="log__msg">{event.message}</div>
              {detail && <pre className="log__data">{detail}</pre>}
            </div>
          </li>
        );
      })}
    </ul>
  );
}
