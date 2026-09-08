import { Stamp } from "./Stamp";
import type { Run, RunEvent } from "../types";

type GateState = "idle" | "busy" | "open" | "shut";

interface Props {
  run: Run | null;
  events: RunEvent[];
  busy: boolean;
  finished: boolean;
}

function gateStates(events: RunEvent[], busy: boolean, finished: boolean) {
  const codes = new Set(events.map((e) => e.code));
  const drift = codes.has("drift_detected");
  const contract = events.find((e) => e.code === "gate_contract");
  const continuity = events.find((e) => e.code === "gate_continuity");

  let one: GateState = "idle";
  let two: GateState = "idle";

  if (contract) one = "open";
  else if (drift && finished) one = "shut";
  else if (drift && busy) one = "busy";

  if (continuity) two = continuity.level === "ok" ? "open" : "shut";
  else if (contract && busy) two = "busy";
  else if (contract && finished) two = "shut";

  return { one, two, drift };
}

/** A connector shows what the stage *behind* it did, never what the stage
 *  ahead will do. Records that reach a gate have travelled that far even if
 *  the gate then holds them. */
function flowClass(behind: GateState | "source", read: number): string {
  if (behind === "source") return read > 0 ? "flow is-live" : "flow";
  if (behind === "open") return "flow is-live";
  if (behind === "shut") return "flow is-stopped";
  return "flow";
}

const GATE_COPY: Record<GateState, string> = {
  idle: "—",
  busy: "checking",
  open: "passed",
  shut: "held",
};

export function Bench({ run, events, busy, finished }: Props) {
  const { one, two, drift } = gateStates(events, busy, finished);
  const read = run?.records_read ?? 0;
  const published = finished ? run?.records_published ?? 0 : 0;

  const verdictKind = busy ? "running" : run?.status ?? "running";
  const verdictLabel = busy
    ? "running"
    : run?.status === "healed"
      ? "healed · published"
      : run?.status ?? "no run yet";

  return (
    <>
      <div className="track">
        <div className="station">
          <div className="station__label">Read from source</div>
          <div className="station__count">{read}</div>
          <div className="station__note">
            {run?.mapping_version ? `mapping v${run.mapping_version}` : "records"}
          </div>
        </div>

        <div className={flowClass("source", read)} aria-hidden="true" />

        <div className={`gate is-${one}`}>
          <div className="gate__ord">Gate one</div>
          <div className="gate__name">Contract</div>
          <div className="gate__state">{GATE_COPY[one]}</div>
        </div>

        <div className={flowClass(one, read)} aria-hidden="true" />

        <div className={`gate is-${two}`}>
          <div className="gate__ord">Gate two</div>
          <div className="gate__name">Continuity</div>
          <div className="gate__state">{GATE_COPY[two]}</div>
        </div>

        <div className={flowClass(two, read)} aria-hidden="true" />

        <div className={`station station--out${finished && published === 0 ? " is-empty" : ""}`}>
          <div className="station__label">Published</div>
          <div className="station__count">{published}</div>
          <div className="station__note">
            {finished && published === 0 ? "nothing shipped" : "records downstream"}
          </div>
        </div>
      </div>

      <div className="bench__verdict">
        <Stamp kind={verdictKind} label={verdictLabel} pressed={finished} />
        <span className="bench__verdict-note">
          {busy && "Reading the source and checking it against the contract."}
          {!busy && !run && "Run the pipeline while the source still matches its contract."}
          {!busy && run?.status === "published" &&
            "The source matched its contract. These records are now the baseline a repair has to recover."}
          {!busy && run?.status === "healed" &&
            "The mapping was repaired, and the repair cleared both gates before anything was published."}
          {!busy && run?.status === "blocked" && drift &&
            "The source no longer matches its contract and nothing passed the gates, so nothing was published."}
          {!busy && run?.status === "error" && run.error}
        </span>
        {run && Number(run.cost_usd) > 0 && (
          <span className="bench__cost">repair cost ${Number(run.cost_usd).toFixed(4)}</span>
        )}
        {run?.duration_ms != null && !busy && (
          <span className="bench__cost">{(run.duration_ms / 1000).toFixed(1)}s</span>
        )}
      </div>
    </>
  );
}
