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

/** The line a form leaves blank until someone fills it in. */
const GATE_ENTRY: Record<GateState, string> = {
  idle: "",
  busy: "checking",
  open: "passed",
  shut: "held",
};

export function Bench({ run, events, busy, finished }: Props) {
  const { one, two, drift } = gateStates(events, busy, finished);
  const read = run?.records_read ?? 0;
  const published = finished ? run?.records_published ?? 0 : 0;

  const verdictKind = busy ? "running" : run ? run.status : "idle";
  const verdictLabel = busy
    ? "under inspection"
    : !run
      ? "no ruling yet"
      : run.status === "healed"
        ? "repaired · published"
        : run.status;

  return (
    <>
      <div className="bench__stamp">
        <Stamp kind={verdictKind} label={verdictLabel} pressed={finished} />
      </div>

      <div className="track">
        <div className="box">
          <span className="box__ord">1</span>
          <div className="box__label">Presented</div>
          <div className="box__count">{read}</div>
          <div className="box__note">
            {run?.mapping_version ? `read with mapping v${run.mapping_version}` : "records read"}
          </div>
        </div>

        <div className={flowClass("source", read)} aria-hidden="true" />

        <div className={`box is-${one}`}>
          <span className="box__ord">2</span>
          <div className="box__label">Gate one</div>
          <div className="box__name">Contract</div>
          <div className="box__entry">{GATE_ENTRY[one]}</div>
          <div className="box__note">reads clean today</div>
        </div>

        <div className={flowClass(one, read)} aria-hidden="true" />

        <div className={`box is-${two}`}>
          <span className="box__ord">3</span>
          <div className="box__label">Gate two</div>
          <div className="box__name">Continuity</div>
          <div className="box__entry">{GATE_ENTRY[two]}</div>
          <div className="box__note">recovers what was already right</div>
        </div>

        <div className={flowClass(two, read)} aria-hidden="true" />

        <div className={`box box--out${finished && published === 0 ? " is-empty" : ""}`}>
          <span className="box__ord">4</span>
          <div className="box__label">Published</div>
          <div className="box__count">{published}</div>
          <div className="box__note">
            {finished && published === 0 ? "nothing shipped" : "records downstream"}
          </div>
        </div>
      </div>

      <div className="bench__verdict">
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
          <span className="bench__cost">repair ${Number(run.cost_usd).toFixed(4)}</span>
        )}
        {run?.duration_ms != null && !busy && (
          <span className="bench__cost">{(run.duration_ms / 1000).toFixed(1)}s</span>
        )}
      </div>
    </>
  );
}
