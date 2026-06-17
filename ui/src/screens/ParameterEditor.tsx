import { useMemo, useState } from "react";
import { api } from "../api/client";
import { useAsync } from "../hooks";
import { Card, ErrorLine, Field, Notice, PageHead } from "../components";
import { Icon } from "../icons";

type Group = "Strategy" | "Risk Management" | "Filters" | "Session / Time" | "Execution" | "Advanced";

const GROUPS: Group[] = ["Strategy", "Risk Management", "Filters", "Session / Time", "Execution", "Advanced"];

interface Row {
  name: string;
  value: string;
  min: string;
  max: string;
  step: string;
  group: Group;
  enabled: boolean;
  locked: boolean;
  initial: string;
}

const SEED: Row[] = [
  { name: "TP_R", value: "2.0", min: "1.0", max: "4.0", step: "0.5", group: "Strategy", enabled: true, locked: false, initial: "2.0" },
  { name: "ATR_Mult", value: "2.0", min: "1.0", max: "3.5", step: "0.5", group: "Risk Management", enabled: true, locked: false, initial: "2.0" },
  { name: "MaxSpread", value: "30", min: "10", max: "60", step: "5", group: "Filters", enabled: true, locked: false, initial: "30" },
  { name: "SessionStart", value: "8", min: "0", max: "23", step: "1", group: "Session / Time", enabled: true, locked: false, initial: "8" },
];

// Parameter Editor: grouped EA inputs with range/step/enable/lock controls and a
// .set preview. Editing happens in the UI; the backend stays the research engine.
export function ParameterEditor() {
  const eas = useAsync(() => api.eas().catch(() => ({ ok: false, eas: [] })), []);
  const [ea, setEa] = useState("");
  const [symbol, setSymbol] = useState("US30");
  const [timeframe, setTimeframe] = useState("M15");
  const [rows, setRows] = useState<Row[]>(SEED);
  const [preview, setPreview] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const eaList = eas.data?.eas || [];
  const effectiveEa = ea || eaList[0]?.name || "";

  const update = (idx: number, patch: Partial<Row>) =>
    setRows((prev) => prev.map((r, i) => (i === idx ? { ...r, ...patch } : r)));
  const addRow = (group: Group) =>
    setRows((prev) => [...prev, { name: "", value: "", min: "", max: "", step: "", group, enabled: true, locked: false, initial: "" }]);
  const removeRow = (idx: number) => setRows((prev) => prev.filter((_, i) => i !== idx));

  const grouped = useMemo(() => {
    const map = new Map<Group, { row: Row; idx: number }[]>();
    rows.forEach((row, idx) => {
      const list = map.get(row.group) ?? [];
      list.push({ row, idx });
      map.set(row.group, list);
    });
    return map;
  }, [rows]);

  const doPreview = async () => {
    setError(null);
    const inputs: Record<string, string> = {};
    for (const r of rows) {
      if (r.enabled && r.name.trim()) inputs[r.name.trim()] = r.value;
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
      <PageHead title="Parameters" subtitle="Edit EA inputs by group, set optimization ranges, and preview the .set before running." />
      <Notice>
        Manual overrides are honored. The research engine can suggest ranges; you always confirm before a run. Disabled
        rows are omitted from the .set; locked rows are kept fixed during optimization.
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

      {GROUPS.map((group) => {
        const list = grouped.get(group) ?? [];
        return (
          <Card key={group} title={group}>
            <div className="param-row head">
              <div>Name</div><div>Value</div><div>Min</div><div>Max</div><div>Step</div><div></div>
            </div>
            {list.length === 0 ? (
              <div className="muted" style={{ fontSize: 12.5, padding: "8px 0" }}>No parameters in this group.</div>
            ) : (
              list.map(({ row, idx }) => (
                <div className={`param-row ${row.enabled ? "" : "disabled"}`} key={idx}>
                  <div className="param-name">
                    <input type="text" value={row.name} placeholder="Input" onChange={(e) => update(idx, { name: e.target.value })} />
                  </div>
                  <input type="text" value={row.value} disabled={row.locked} onChange={(e) => update(idx, { value: e.target.value })} />
                  <input type="text" value={row.min} placeholder="—" onChange={(e) => update(idx, { min: e.target.value })} />
                  <input type="text" value={row.max} placeholder="—" onChange={(e) => update(idx, { max: e.target.value })} />
                  <input type="text" value={row.step} placeholder="—" onChange={(e) => update(idx, { step: e.target.value })} />
                  <div className="row-actions" style={{ margin: 0, gap: 4 }}>
                    <button className="icon-btn small" title={row.enabled ? "Disable" : "Enable"} onClick={() => update(idx, { enabled: !row.enabled })}>
                      {row.enabled ? "On" : "Off"}
                    </button>
                    <button className="icon-btn small" title={row.locked ? "Unlock" : "Lock (fixed in optimization)"} onClick={() => update(idx, { locked: !row.locked })}>
                      {row.locked ? "🔒" : "🔓"}
                    </button>
                    <button className="icon-btn small" title="Reset to initial" onClick={() => update(idx, { value: row.initial })}>
                      <Icon name="refresh" size={13} />
                    </button>
                    <button className="icon-btn small" title="Remove" onClick={() => removeRow(idx)}>
                      <Icon name="x" size={13} />
                    </button>
                  </div>
                </div>
              ))
            )}
            <div className="row-actions" style={{ marginTop: 10 }}>
              <button className="btn ghost" onClick={() => addRow(group)}>Add parameter</button>
            </div>
          </Card>
        );
      })}

      <div className="row-actions">
        <button className="btn" onClick={doPreview}>Preview .set</button>
        <span className="param-tag">Agent-suggested ranges: coming soon</span>
      </div>
      {error ? <div style={{ marginTop: 10 }}><ErrorLine message={error} /></div> : null}

      {preview ? (
        <Card title="Generated .set preview">
          <pre className="pre">{preview}</pre>
        </Card>
      ) : null}
    </div>
  );
}
