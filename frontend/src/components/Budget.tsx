import type { Budget as BudgetData } from "../types";

/** What the demo has spent, said plainly.
 *
 *  A tool whose whole argument is about declared limits would be a poor
 *  advertisement for itself if it hid its own. */
export function Budget({ budget }: { budget: BudgetData | null }) {
  if (!budget) return null;

  const cap = Number(budget.cap_usd);
  const spent = Number(budget.spent_usd);
  const share = cap > 0 ? Math.min(1, spent / cap) : 0;

  return (
    <div className={`budget${budget.exhausted ? " budget--spent" : ""}`}>
      <div className="budget__bar" aria-hidden="true">
        <span style={{ width: `${share * 100}%` }} />
      </div>
      <span className="budget__text">
        {budget.exhausted ? (
          <>
            The 24-hour repair budget is spent. The pipeline still reads the source,
            still catches drift, and still refuses to publish — it just stops paying
            for repairs until the window rolls over.
          </>
        ) : (
          <>
            Repair budget · ${spent.toFixed(4)} of ${cap.toFixed(2)} spent in the last
            24 hours
          </>
        )}
      </span>
    </div>
  );
}
