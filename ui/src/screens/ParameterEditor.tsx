import { useState } from "react";
import { api } from "../api/client";
import { useAsync } from "../hooks";
import { Card, ErrorLine, Field, Notice, PageHead } from "../components";

interface Row {
  name: string;
  value: string;
}

// Parameter Editor: edit EA inputs in a grid and preview the generated .set
// before any run. (Editing happens in the UI; the backend stays the engine.)
export function ParameterEditor() {
  const eas = useAsync(() => api.eas().catch(() => ({ ok: false, eas: [] })), []);
  const [ea, setEa] = useState("");
  const [symbol, setSymbol] = useState("US30");
  const [timeframe, setTimeframe] = useState("M15");
  const [rows, setRows] = useState<Row[]>([
    { name: "TP_R", value: "2.0" },
    { name: "ATR_Mult", value: "2.0" },
  ]);
  const [preview, setPreview] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const eaList = eas.data?.eas || [];
  const effectiveEa = ea || eaList[0]?.name || "";

  const update = (i: number, key: keyof Row, val: string) => {
    setRows((prev) => prev.map((r, idx) => (idx === i ? { ...r, [key]: val } : r)));
  };
  const addRow = () => setRows((prev) => [...prev, { name: "", value: "" }]);
  const removeRow = (i: number) => setRows((prev) => prev.filter((_, idx) => idx !== i));

  const doPreview = async () => {
    setError(null);
    const inputs: Record<string, string> = {};
    for (const r of rows) {
      if (r.name.trim()) inputs[r.name.trim()] = r.value;
    }
    try {
      const res = await api.setPreview({ ea: effectiveEa, symbol, timeframe, inputs });
      setPreview(res.set_text);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  return (
    <div>
      <PageHead title="Parameter Editor" subtitle="Edit EA inputs and preview the generated .set before running." />
      <Notice>
        Manual overrides are honored. The research engine can suggest ranges; you always confirm before a run.
      </Notice>

      <Card title="Target">
        {eaList.length > 0 ? (
          <label className="field">
            <span>EA</span>
            <select value={effectiveEa} onChange={(e) => setEa(e.target.value)}>
              {eaList.map((item) => <option key={item.name} value={item.name}>{item.name}</option>)}
            </select>
          </label>
        ) : (
          <Field label="EA name" value={ea} onChange={setEa} placeholder="YourCompiledEA" />
        )}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
          <Field label="Symbol" value={symbol} onChange={setSymbol} />
          <Field label="Timeframe" value={timeframe} onChange={setTimeframe} />
        </div>
      </Card>

      <Card title="Inputs">
        <table>
          <thead>
            <tr><th>Name</th><th>Value</th><th></th></tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i}>
                <td><input type="text" value={r.name} onChange={(e) => update(i, "name", e.target.value)} /></td>
                <td><input type="text" value={r.value} onChange={(e) => update(i, "value", e.target.value)} /></td>
                <td><button className="btn ghost" onClick={() => removeRow(i)}>✕</button></td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="row-actions" style={{ marginTop: 10 }}>
          <button className="btn ghost" onClick={addRow}>Add input</button>
          <button className="btn" onClick={doPreview}>Preview .set</button>
        </div>
        {error ? <div style={{ marginTop: 10 }}><ErrorLine message={error} /></div> : null}
      </Card>

      {preview ? (
        <Card title="Generated .set preview">
          <pre className="pre">{preview}</pre>
        </Card>
      ) : null}
    </div>
  );
}
