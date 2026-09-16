import type { Source } from "../types";

function ruleText(rule: Record<string, unknown>): string {
  if (rule.column) return `column "${rule.column}"`;
  const attr = rule.attr && rule.attr !== "text" ? ` @${rule.attr}` : "";
  return `${rule.selector}${attr}`;
}

export function SourcePanel({ source }: { source: Source }) {
  const mapping = source.active_mapping;
  const contract = source.contract;
  // A hand-written mapping has nothing to have changed *from*: the API reports
  // every field as new, which is true and is not a repair. Only a healed
  // mapping's diff marks what was actually rewritten.
  const changed = new Set(
    mapping?.origin === "heal" ? Object.keys(mapping.diff ?? {}) : [],
  );

  return (
    <div className="panel__body">
      <div className="section-label">Active mapping</div>
      {mapping ? (
        <>
          <dl className="kv">
            <dt>version</dt>
            <dd>
              v{mapping.version} · {mapping.origin === "heal" ? "repaired" : "hand-written"}
            </dd>
            <dt>of</dt>
            <dd>{source.mapping_count} total</dd>
          </dl>
          <div className="divider" />
          <div className="rules">
            {Object.entries(mapping.rules).map(([field, rule]) => {
              const label = field === "__row__" ? "row" : field;
              const isChanged = changed.has(field);
              const before = mapping.diff[field]?.before as Record<string, unknown> | undefined;
              return (
                <div key={field} className={`rule${isChanged ? " rule--changed" : ""}`}>
                  <span className="rule__field">{label}</span>
                  <span className="rule__val">
                    {before && <span className="rule__was">{ruleText(before)}</span>}
                    {ruleText(rule as Record<string, unknown>)}
                  </span>
                </div>
              );
            })}
          </div>
          {mapping.note && (
            <>
              <div className="divider" />
              <div className="section-label">Why it changed</div>
              <p className="note">{mapping.note}</p>
            </>
          )}
        </>
      ) : (
        <p className="note">No mapping yet.</p>
      )}

      <div className="divider" />
      <div className="section-label">Trusted records</div>
      {source.baseline.records.length ? (
        <dl className="kv">
          <dt>count</dt>
          <dd>{source.baseline.records.length}</dd>
          <dt>from</dt>
          <dd>{source.baseline.pinned ? "pinned by a person" : source.baseline.name}</dd>
          <dt>matched on</dt>
          <dd>{contract.unique_by.join(", ") || "—"}</dd>
          <dt>compared on</dt>
          <dd>{contract.fields.filter((f) => f.stable).map((f) => f.name).join(", ")}</dd>
          <dt>threshold</dt>
          <dd>{Math.round(contract.continuity_threshold * 100)}%</dd>
        </dl>
      ) : (
        <p className="note">
          None yet. A repair cannot be promoted until one clean run establishes what
          the right answer looks like.
        </p>
      )}

      <div className="divider" />
      <div className="section-label">Contract · {contract.key}</div>
      <div className="rules">
        {contract.fields.map((f) => (
          <div key={f.name} className="rule">
            <span className="rule__field">{f.name}</span>
            <span className="rule__val">
              {f.type}
              {f.stable ? " · stable" : ""}
              {f.min_fill_rate != null ? ` · ≥${Math.round(f.min_fill_rate * 100)}% present` : ""}
              {f.min_distinct_ratio != null
                ? ` · ≥${Math.round(f.min_distinct_ratio * 100)}% distinct`
                : ""}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
