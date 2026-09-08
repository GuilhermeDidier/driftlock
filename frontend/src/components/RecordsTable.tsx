import type { RecordRow } from "../types";

export function RecordsTable({ records }: { records: RecordRow[] }) {
  if (!records.length) {
    return <p className="empty">No records read yet.</p>;
  }

  const columns = Object.keys(records[0].value);
  const withheld = records.filter((r) => r.status === "withheld").length;

  return (
    <>
      {withheld > 0 && (
        <p className="empty" style={{ paddingBottom: "0.6rem" }}>
          These {withheld} records were read but not published. They are kept as the
          evidence for whether blocking the batch was the right call.
        </p>
      )}
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>#</th>
              <th>Status</th>
              {columns.map((c) => (
                <th key={c}>{c}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {records.map((record) => (
              <tr key={record.index}>
                <td>{record.index}</td>
                <td>
                  <span className={`tag tag--${record.status}`}>{record.status}</span>
                </td>
                {columns.map((c) => (
                  <td key={c}>{String(record.value[c] ?? "—")}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
