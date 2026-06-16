import { api } from "../api/client";
import { useAsync } from "../hooks";
import { Card, Empty, ErrorLine, PageHead, PassFail, Spinner, StatusBadge } from "../components";

export function Leaderboard({ onOpenReport }: { onOpenReport: (testId: string) => void }) {
  const board = useAsync(() => api.leaderboard(), []);

  return (
    <div>
      <PageHead
        title="Leaderboard"
        subtitle="Ranked stored runs. Robustness (split validation) is required before any candidate is called best — raw return never wins alone."
      />
      <div className="row-actions" style={{ marginBottom: 14 }}>
        <button className="btn ghost" onClick={board.reload}>Refresh</button>
      </div>
      {board.loading ? <Spinner /> : null}
      {board.error ? <ErrorLine message={board.error} /> : null}
      {board.data ? (
        <Card>
          <div className="muted" style={{ marginBottom: 10, fontSize: 12 }}>
            CSV: <span className="mono">{board.data.leaderboard_csv}</span>
          </div>
          {board.data.runs.length === 0 ? (
            <Empty>No ranked runs yet.</Empty>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>#</th>
                  <th>Test ID</th>
                  <th>Status</th>
                  <th>Pass/Fail</th>
                  <th>EA</th>
                  <th>Symbol</th>
                </tr>
              </thead>
              <tbody>
                {board.data.runs.map((run, index) => (
                  <tr key={run.test_id} className="row-click" onClick={() => onOpenReport(run.test_id)}>
                    <td className="muted">{index + 1}</td>
                    <td className="mono">{run.test_id}</td>
                    <td><StatusBadge status={run.run_status} /></td>
                    <td><PassFail value={run.pass_fail} /></td>
                    <td>{run.ea}</td>
                    <td>{run.symbol}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
      ) : null}
    </div>
  );
}
