import { api } from "../api/client";
import { useAsync } from "../hooks";
import { AsyncBoundary, Card, EmptyState, PageHead } from "../components";
import { VerdictBadge, fmt } from "../report_ui";
import type { CandidateCard } from "../api/types";

const SECTION_HELP: Record<string, string> = {
  Champion: "Best robust candidate — passed split validation, not simply the highest profit.",
  Challengers: "Promising candidates that might beat the champion once validated.",
  Survivors: "Passed the acceptance filters but aren't (yet) robust enough to lead.",
  Rejected: "Failed with a clear reason — kept visible, never hidden.",
};

export function StrategyBoard({ onOpenReport }: { onOpenReport: (testId: string) => void }) {
  const board = useAsync(() => api.strategyBoard(), []);

  return (
    <div>
      <PageHead
        title="Strategy Board"
        subtitle="Candidates ranked by robustness, not raw profit. A candidate is only champion after split validation passes."
      />
      <div className="row-actions" style={{ marginBottom: 14 }}>
        <button className="btn ghost" onClick={board.reload}>Refresh</button>
      </div>

      <AsyncBoundary
        state={board}
        isEmpty={(d) =>
          !d.champion && !d.challengers.length && !d.survivors.length && !d.rejected.length
        }
        empty={
          <EmptyState
            icon="leaderboard"
            title="No candidates yet"
            description="Run research from the Agent tab. Candidates appear here grouped by champion, challenger, survivor, and rejected."
          />
        }
      >
        {(d) => (
          <>
            <Section title="Champion" help={SECTION_HELP.Champion}>
              {d.champion ? (
                <CandidateTable rows={[d.champion]} onOpen={onOpenReport} highlight />
              ) : (
                <div className="muted" style={{ fontSize: 13 }}>
                  No robust champion yet — promote a challenger after it passes split validation.
                </div>
              )}
            </Section>
            <Section title="Challengers" help={SECTION_HELP.Challengers} count={d.challengers.length}>
              <CandidateTable rows={d.challengers} onOpen={onOpenReport} empty="No challengers right now." />
            </Section>
            <Section title="Survivors" help={SECTION_HELP.Survivors} count={d.survivors.length}>
              <CandidateTable rows={d.survivors} onOpen={onOpenReport} empty="No survivors yet." />
            </Section>
            <Section title="Rejected" help={SECTION_HELP.Rejected} count={d.rejected.length}>
              <CandidateTable rows={d.rejected} onOpen={onOpenReport} empty="Nothing rejected yet." showReason />
            </Section>
          </>
        )}
      </AsyncBoundary>
    </div>
  );
}

function Section({
  title,
  help,
  count,
  children,
}: {
  title: string;
  help: string;
  count?: number;
  children: React.ReactNode;
}) {
  return (
    <Card title={count === undefined ? title : `${title} (${count})`}>
      <div className="muted" style={{ fontSize: 12, marginTop: -6, marginBottom: 12 }}>{help}</div>
      {children}
    </Card>
  );
}

function CandidateTable({
  rows,
  onOpen,
  empty,
  highlight,
  showReason,
}: {
  rows: CandidateCard[];
  onOpen: (testId: string) => void;
  empty?: string;
  highlight?: boolean;
  showReason?: boolean;
}) {
  if (rows.length === 0) {
    return <div className="muted" style={{ fontSize: 13 }}>{empty}</div>;
  }
  return (
    <table>
      <thead>
        <tr>
          <th>Score</th>
          <th>Verdict</th>
          <th>Symbol / TF</th>
          <th>PF</th>
          <th>DD %</th>
          <th>Trades</th>
          <th>Return %</th>
          <th>Validation</th>
          {showReason ? <th>Reason</th> : null}
        </tr>
      </thead>
      <tbody>
        {rows.map((c) => (
          <tr
            key={c.test_id}
            className={`row-click ${highlight ? "champion-row" : ""}`}
            onClick={() => onOpen(c.test_id)}
          >
            <td><strong>{c.score}</strong></td>
            <td><VerdictBadge verdict={c.verdict} /></td>
            <td>{c.symbol} {c.timeframe}</td>
            <td>{fmt(c.profit_factor)}</td>
            <td>{c.drawdown_pct === null ? "—" : `${fmt(c.drawdown_pct)}%`}</td>
            <td>{c.total_trades ?? "—"}</td>
            <td>{c.return_pct === null ? "—" : `${fmt(c.return_pct)}%`}</td>
            <td><span className={`val-pill ${c.validation_status}`}>{c.validation_status}</span></td>
            {showReason ? <td className="muted">{c.reason || "—"}</td> : null}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
