import { Fragment, useEffect, useState } from "react";
import { api } from "../api/client";
import { Card, ErrorLine, Field, PageHead, Spinner, StatusBadge } from "../components";
import type { ReportStatus } from "../api/types";

export function Reports({ initialId }: { initialId: string }) {
  const [testId, setTestId] = useState(initialId);
  const [report, setReport] = useState<ReportStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const load = async (id: string) => {
    if (!id) return;
    setLoading(true);
    setError(null);
    try {
      setReport(await api.report(id));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setReport(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (initialId) {
      setTestId(initialId);
      void load(initialId);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialId]);

  const metrics = report?.parsed_metrics || {};

  return (
    <div>
      <PageHead title="Reports" subtitle="Inspect the parsed result and decision for one stored run." />
      <Card>
        <Field label="Test ID" value={testId} onChange={setTestId} placeholder="US30-SMOKE-0001-FIXED" />
        <div className="row-actions">
          <button className="btn" onClick={() => load(testId)} disabled={loading || !testId}>
            Load report
          </button>
        </div>
        {error ? <div style={{ marginTop: 12 }}><ErrorLine message={error} /></div> : null}
      </Card>

      {loading ? <Spinner /> : null}

      {report && report.ok ? (
        <>
          <Card title="Decision">
            <div className="kv">
              <div className="k">Status</div>
              <div><StatusBadge status={report.latest_status || "-"} /></div>
              <div className="k">Reason</div>
              <div>{report.decision_reason || "-"}</div>
              {report.likely_diagnosis ? (
                <>
                  <div className="k">Diagnosis</div>
                  <div className="muted">{report.likely_diagnosis}</div>
                </>
              ) : null}
            </div>
          </Card>

          <Card title="Parsed metrics">
            <div className="kv">
              {Object.entries(metrics).map(([key, value]) => (
                <Fragment key={key}>
                  <div className="k">{key}</div>
                  <div>{value === null || value === undefined ? "-" : String(value)}</div>
                </Fragment>
              ))}
            </div>
          </Card>
        </>
      ) : null}

      {report && !report.ok ? <ErrorLine message={report.error || "Report not found."} /> : null}
    </div>
  );
}
