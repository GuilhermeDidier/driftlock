import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError, api, storeUrl } from "./api";
import { Bench } from "./components/Bench";
import { Budget } from "./components/Budget";
import { RecordsTable } from "./components/RecordsTable";
import { RunLog } from "./components/RunLog";
import { SourcePanel } from "./components/SourcePanel";
import type { Budget as BudgetData, Run, RunEvent, Source } from "./types";

const SOURCE_KEY = "loja-exemplo";

const LAYOUTS = [
  { id: "v1", label: "Restore the original", hint: "Put the storefront back the way the mapping expects." },
  { id: "v2", label: "Redesign the source", hint: "Rebuild the markup so the rows stop matching at all." },
  { id: "v3", label: "Break it quietly", hint: "Leave the rows intact. Move the name, rename the price element. Nothing errors." },
] as const;

const prefersReducedMotion = () =>
  window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;

export default function App() {
  const [source, setSource] = useState<Source | null>(null);
  const [layout, setLayout] = useState<string>("v1");
  const [run, setRun] = useState<Run | null>(null);
  const [visible, setVisible] = useState<RunEvent[]>([]);
  const [budget, setBudget] = useState<BudgetData | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const timers = useRef<number[]>([]);

  const clearTimers = () => {
    timers.current.forEach(window.clearTimeout);
    timers.current = [];
  };

  const replay = useCallback((events: RunEvent[]) => {
    clearTimers();
    if (prefersReducedMotion()) {
      setVisible(events);
      return;
    }
    setVisible([]);
    events.forEach((event, i) => {
      const id = window.setTimeout(() => {
        setVisible((seen) => [...seen, event]);
      }, i * 170);
      timers.current.push(id);
    });
  }, []);

  const load = useCallback(async () => {
    try {
      const state = await api.state();
      setLayout(state.demo_layout);
      setBudget(state.budget);
      const detail = await api.source(SOURCE_KEY);
      setSource(detail);
      if (detail.latest_run) {
        const full = await api.run(detail.latest_run.id);
        setRun(full);
        setVisible(full.events ?? []);
      }
      setError(null);
    } catch (err) {
      setError(
        "The API is not answering. Start the Django server, then run `manage.py seed_demo`.",
      );
    }
  }, []);

  useEffect(() => {
    load();
    return clearTimers;
  }, [load]);

  async function startRun() {
    setBusy(true);
    setError(null);
    clearTimers();
    setVisible([]);
    setRun(null);
    try {
      const result = await api.triggerRun(SOURCE_KEY);
      setRun(result);
      setBudget(result.budget ?? null);
      replay(result.events ?? []);
      setSource(await api.source(SOURCE_KEY));
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 429
          ? "That is as many runs as one visitor gets in an hour. The limit rolls over shortly; the source and its history are unchanged."
          : "The run could not be started.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function changeLayout(next: string) {
    setBusy(true);
    try {
      await api.setLayout(next);
      setLayout(next);
    } finally {
      setBusy(false);
    }
  }

  const finished = !busy && run != null;
  const events = visible;

  return (
    <div className="shell">
      <header className="masthead">
        <div className="wordmark">
          drift<span>lock</span>
        </div>
        <div className="masthead__tag">proof before publication</div>
        <div className="masthead__spacer" />
        <div className="masthead__meta">
          {source ? `${source.key} · ${source.kind} · contract ${source.contract.key}` : "…"}
        </div>
      </header>

      <section className="hero">
        <h1 className="hero__lede">
          A broken pipeline rarely breaks. It <em>keeps running</em> and quietly ships
          the wrong numbers.
        </h1>
        <p className="hero__sub">
          Driftlock reads a source against a declared contract. When the source changes
          shape, it publishes nothing, repairs the mapping, and makes the repair prove
          itself twice before a single record moves downstream. Break the source below
          and watch it work.
        </p>

        <div className="bench">
          <Bench run={run} events={events} busy={busy} finished={finished} />

          <Budget budget={budget} />

          <div className="controls">
            <button className="btn btn--primary" onClick={startRun} disabled={busy}>
              {busy ? "Running…" : "Run the pipeline"}
            </button>
            <div className="controls__group">
              {LAYOUTS.filter((o) => o.id !== "v1").map((option) => (
                <button
                  key={option.id}
                  className={`btn btn--break${layout === option.id ? " is-active" : ""}`}
                  onClick={() => changeLayout(option.id)}
                  disabled={busy || layout === option.id}
                  title={option.hint}
                >
                  {option.label}
                </button>
              ))}
              <button
                className="btn btn--quiet"
                onClick={() => changeLayout("v1")}
                disabled={busy || layout === "v1"}
                title={LAYOUTS[0].hint}
              >
                Restore the original
              </button>
            </div>
            <span className="controls__hint">
              {LAYOUTS.find((l) => l.id === layout)?.hint}{" "}
              <a href={storeUrl} target="_blank" rel="noreferrer" style={{ color: "var(--paper-dim)" }}>
                See the page
              </a>
            </span>
          </div>
        </div>

        {error && (
          <p className="empty" style={{ color: "var(--refused)", paddingLeft: 0 }}>
            {error}
          </p>
        )}
      </section>

      <div className="grid">
        <section className="panel">
          <div className="panel__head">
            <span className="panel__title">Run log</span>
            <span className="panel__aside">
              {run ? `run #${run.id} · replayed in order` : "waiting"}
            </span>
          </div>
          <div className="panel__body panel__body--flush">
            <RunLog events={events} busy={busy} />
          </div>
        </section>

        <section className="panel">
          <div className="panel__head">
            <span className="panel__title">Source state</span>
            <span className="panel__aside">{source?.name ?? ""}</span>
          </div>
          {source && <SourcePanel source={source} />}
        </section>
      </div>

      <section className="panel" style={{ marginTop: "1.1rem" }}>
        <div className="panel__head">
          <span className="panel__title">Records</span>
          <span className="panel__aside">
            {run
              ? `${run.records_published} published · ${run.records_quarantined} quarantined · ${
                  run.records_read - run.records_published - run.records_quarantined
                } withheld`
              : ""}
          </span>
        </div>
        <div className="panel__body panel__body--flush">
          <RecordsTable records={run?.records ?? []} />
        </div>
      </section>

      <footer className="foot">
        <span>Contract engine and gates are covered by the test suite.</span>
        <span>Repairs are proposed by Claude and refused unless they prove out.</span>
      </footer>
    </div>
  );
}
