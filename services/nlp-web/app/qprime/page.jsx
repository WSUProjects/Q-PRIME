"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
    Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart,
    Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { withBasePath } from "@/lib/basePath";
import styles from "./qprime.module.css";

const TABS = ["Overview", "QoC Factors", "Decisions", "Privacy", "Configuration", "Sensitivity", "Performance", "Data Sources"];
const COLOURS = { edge: "#32c57a", cloud: "#4f8df7", both: "#f5a623" };
const empty = { overview: {}, qoc: { timeline: [], mean_by_device: {} }, decisions: [], privacy: {}, performance: {} };
const PAPER_STREAMS = ["camera_vision", "door", "heart", "misty_vision", "smoke", "soil", "tello_vision", "thp", "zed_vision"];
const CRITERIA = [["temporal", "Temporal QoC"], ["spatial", "Content QoC"], ["privacy", "Privacy"]];
const DEFAULT_WEIGHTS = { temporal: 1 / 3, spatial: 1 / 3, privacy: 1 / 3 };
const DEFAULT_JUDGEMENTS = { temporal_vs_spatial: 1, temporal_vs_privacy: 1, spatial_vs_privacy: 1 };
const SAATY_OPTIONS = [
    [9, "9 — first criterion is extremely more important"], [7, "7 — first criterion is very strongly more important"],
    [5, "5 — first criterion is strongly more important"], [3, "3 — first criterion is moderately more important"],
    [1, "1 — equally important"], [1 / 3, "1/3 — second criterion is moderately more important"],
    [1 / 5, "1/5 — second criterion is strongly more important"], [1 / 7, "1/7 — second criterion is very strongly more important"],
    [1 / 9, "1/9 — second criterion is extremely more important"],
];

function normaliseWeights(weights) {
    const raw = Object.fromEntries(CRITERIA.map(([key]) => [key, Math.max(0, Number(weights?.[key]) || 0)]));
    const total = Object.values(raw).reduce((sum, value) => sum + value, 0);
    if (!total) return DEFAULT_WEIGHTS;
    return Object.fromEntries(Object.entries(raw).map(([key, value]) => [key, value / total]));
}

function matrixJudgements(matrix) {
    return {
        temporal_vs_spatial: Number(matrix?.[0]?.[1]) || 1,
        temporal_vs_privacy: Number(matrix?.[0]?.[2]) || 1,
        spatial_vs_privacy: Number(matrix?.[1]?.[2]) || 1,
    };
}

async function api(path, options) {
    const response = await fetch(withBasePath(`/api/qprime/${path}`), { cache: "no-store", ...options });
    const payload = await response.json();
    if (!response.ok || payload.error) throw new Error(payload.error || `HTTP ${response.status}`);
    return payload;
}

function StatusBadge({ label, status }) {
    const good = ["connected", "configured", "ok"].includes(status);
    const fallback = status === "local_fallback";
    return <span className={`${styles.badge} ${good ? styles.good : fallback ? styles.warn : styles.bad}`}>{label}: {status || "checking"}</span>;
}

function Metric({ label, value, tone = "default" }) {
    return <article className={styles.metric}><span>{label}</span><strong className={styles[tone]}>{value ?? 0}</strong></article>;
}

function Panel({ title, subtitle, children }) {
    return <section className={styles.panel}><div className={styles.panelTitle}><h2>{title}</h2>{subtitle && <span>{subtitle}</span>}</div>{children}</section>;
}

function Overview({ data }) {
    const split = Object.entries(data.placement_split || {}).map(([name, value]) => ({ name, value }));
    return <>
        <div className={styles.metrics}>
            <Metric label="Records processed" value={data.records_processed} />
            <Metric label="Stored at Edge" value={data.stored_at_edge} tone="edge" />
            <Metric label="Cloud decisions" value={data.sent_to_cloud} tone="cloud" />
            <Metric label="Both tiers" value={data.both_tiers} tone="both" />
            <Metric label="Cloud retained locally" value={data.cloud_fallback_records} tone="both" />
            <Metric label="PII records" value={data.pii_records} />
        </div>
        <div className={styles.grid2}>
            <Panel title="Storage placement per device">
                <ResponsiveContainer width="100%" height={330}><BarChart data={data.placement_by_device || []}><CartesianGrid stroke="#e2e8f0"/><XAxis dataKey="device" angle={-18} textAnchor="end" height={80}/><YAxis allowDecimals={false}/><Tooltip/><Legend/><Bar dataKey="edge" stackId="a" fill={COLOURS.edge}/><Bar dataKey="cloud" stackId="a" fill={COLOURS.cloud}/><Bar dataKey="both" stackId="a" fill={COLOURS.both}/></BarChart></ResponsiveContainer>
            </Panel>
            <Panel title="Overall placement split">
                <ResponsiveContainer width="100%" height={330}><PieChart><Pie data={split} dataKey="value" nameKey="name" innerRadius="48%" outerRadius="78%">{split.map((item) => <Cell key={item.name} fill={COLOURS[item.name] || "#8aa0c2"}/>)}</Pie><Tooltip/><Legend/></PieChart></ResponsiveContainer>
            </Panel>
        </div>
    </>;
}

function QoC({ data }) {
    const byDevice = Object.entries(data.mean_by_device || {}).map(([device, values]) => ({ device, ...values }));
    const keys = ["timeliness", "completeness", "correctness", "resolution", "significance"];
    const colours = ["#4f8df7", "#32c57a", "#f5a623", "#e84455", "#7b5cf5"];
    return <div className={styles.stack}>
        <Panel title="QoC factor scores over time" subtitle="Persistent evaluation results">
            <ResponsiveContainer width="100%" height={340}><LineChart data={data.timeline || []}><CartesianGrid stroke="#e2e8f0"/><XAxis dataKey="timestamp" tickFormatter={(v) => new Date(v).toLocaleTimeString()}/><YAxis domain={[0, 1]}/><Tooltip labelFormatter={(v) => new Date(v).toLocaleString()}/><Legend/>{keys.map((key, i) => <Line key={key} type="monotone" dataKey={key} stroke={colours[i]} dot={false}/>)}</LineChart></ResponsiveContainer>
        </Panel>
        <Panel title="Current mean QoC per device">
            <ResponsiveContainer width="100%" height={360}><BarChart data={byDevice}><CartesianGrid stroke="#e2e8f0"/><XAxis dataKey="device" angle={-16} textAnchor="end" height={75}/><YAxis domain={[0, 1]}/><Tooltip/><Legend/>{keys.map((key, i) => <Bar key={key} dataKey={key} fill={colours[i]}/>)}</BarChart></ResponsiveContainer>
        </Panel>
    </div>;
}

function Decisions({ rows }) {
    return <Panel title="Recent placement decisions" subtitle="Recommendation and actual backend are shown separately">
        <div className={styles.tableWrap}><table><thead><tr><th>Time</th><th>Device</th><th>Stream</th><th>Decision</th><th>S edge</th><th>S cloud</th><th>Profile</th><th>Actual backend</th><th>Reason</th><th>Source</th></tr></thead><tbody>{rows.map((row) => <tr key={row.record_id}><td>{new Date(row.created_at).toLocaleString()}</td><td>{row.device_name || "—"}</td><td>{row.contextattribute}</td><td className={styles[row.recommended_tier]}>{row.recommended_tier}</td><td>{row.analysis?.score_edge ?? "—"}</td><td>{row.analysis?.score_cloud ?? "—"}</td><td>{row.profile_scope}:{row.profile_version}</td><td>{(row.actual_backends || []).join(", ")}</td><td>{row.analysis?.reason}</td><td>{row.source}</td></tr>)}</tbody></table></div>
    </Panel>;
}

function Privacy({ data }) {
    return <><div className={styles.metrics}><Metric label="PII records" value={data.pii_records}/><Metric label="PII sent to configured AWS" value={data.pii_leaked_to_cloud} tone={data.pii_leaked_to_cloud ? "danger" : "edge"}/><Metric label="Leak rate" value={`${data.leak_rate || 0}%`}/><Metric label="Cloud fallback is local" value="MongoDB" tone="both"/></div><Panel title="PII placement per device"><ResponsiveContainer width="100%" height={350}><BarChart data={data.by_device || []}><CartesianGrid stroke="#e2e8f0"/><XAxis dataKey="device"/><YAxis allowDecimals={false}/><Tooltip/><Legend/><Bar dataKey="pii_records" fill="#f5a623"/><Bar dataKey="leaked_to_cloud" fill="#e84455"/></BarChart></ResponsiveContainer></Panel></>;
}

function DataSources({ producer, catalog, onSaved, onModeChange }) {
    const current = producer?.current || { mode: "off", running: false };
    const saved = producer?.saved || { devices: [] };
    const [mode, setMode] = useState(saved.mode === "simulator" ? "simulator" : "sample_edgex");
    const [selected, setSelected] = useState(saved.devices || []);
    const [message, setMessage] = useState(""); const [working, setWorking] = useState(false);
    useEffect(() => { if (!current.running && saved.mode === "simulator") setSelected(saved.devices || []); }, [saved.updated_at, current.running]);
    const selectedByName = Object.fromEntries(selected.map((device) => [device.device_name, device]));
    function chooseMode(nextMode) { setMode(nextMode); onModeChange(nextMode); }
    function toggle(device) {
        setSelected((items) => items.some((item) => item.device_name === device.device_name)
            ? items.filter((item) => item.device_name !== device.device_name)
            : [...items, { device_name: device.device_name, interval_ms: 1000, refresh_rate_ms: device.refresh_rate, extra_latency_ms: 0, drop_field_pct: 0, corrupt_pct: 0, low_significance_pct: 0.1, privacy_filter: device.privacy_filter || false }]);
    }
    function update(name, key, value) { setSelected((items) => items.map((item) => item.device_name === name ? { ...item, [key]: value } : item)); }
    async function start() {
        if (mode === "simulator" && !selected.length) { setMessage("Select at least one sensor."); return; }
        setWorking(true); try { await api("producer/start", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ mode, devices: mode === "simulator" ? selected : [] }) }); setMessage(mode === "simulator" ? "Simulator started." : "Sample EdgeX feed started."); onSaved(); }
        catch (error) { setMessage(error.message); } finally { setWorking(false); }
    }
    async function stop() { setWorking(true); try { await api("producer/stop", { method: "POST" }); setMessage("Generated data source stopped."); onSaved(); } catch (error) { setMessage(error.message); } finally { setWorking(false); } }
    return <div className={styles.configStack}>
        <Panel title="Data generation" subtitle="Off by default; choose one generated source at a time">
            <div className={styles.modeCards}>
                <label className={`${styles.modeCard} ${mode === "simulator" ? styles.modeSelected : ""}`}><input type="radio" checked={mode === "simulator"} onChange={() => chooseMode("simulator")}/><strong>Simulator</strong><span>Configure paper sensors and send direct records into Q-PRIME.</span></label>
                <label className={`${styles.modeCard} ${mode === "sample_edgex" ? styles.modeSelected : ""}`}><input type="radio" checked={mode === "sample_edgex"} onChange={() => chooseMode("sample_edgex")}/><strong>Sample EdgeX feed</strong><span>Generate the paper testbed through EdgeX and the export pipeline.</span></label>
            </div>
            <div className={styles.actions}><button disabled={working} onClick={start}>{current.running ? "Switch to selected mode" : "Start selected mode"}</button>{current.running && <button className={styles.secondaryButton} disabled={working} onClick={stop}>Stop generation</button>}<span>{message || current.message || "Off"}</span></div>
            <p className={`${styles.helpText} ${styles.producerStatus}`}>Current mode: <strong>{current.running ? current.mode.replace("_", " ") : "Off"}</strong> · delivered {current.sent || 0} · failed {current.failed || 0}.</p>
        </Panel>
        {mode === "simulator" && <Panel title="Simulator sensor configuration" subtitle="These controls affect only newly generated records">
            <div className={styles.sensorControls}>{catalog.map((device) => { const settings = selectedByName[device.device_name]; return <article key={device.device_name} className={`${styles.sensorControl} ${settings ? styles.sensorEnabled : ""}`}><label className={styles.sensorHeading}><input type="checkbox" checked={!!settings} onChange={() => toggle(device)}/><span><strong>{device.device_name}</strong><small>{device.stream}</small></span></label>{settings && <div className={styles.sensorFields}>
                <label>Interval (ms)<input type="number" min="100" value={settings.interval_ms} onChange={(e) => update(device.device_name, "interval_ms", Number(e.target.value))}/></label>
                <label>Refresh rate (ms)<input type="number" min="1" value={settings.refresh_rate_ms} onChange={(e) => update(device.device_name, "refresh_rate_ms", Number(e.target.value))}/></label>
                <label>Extra latency (ms)<input type="number" min="0" value={settings.extra_latency_ms} onChange={(e) => update(device.device_name, "extra_latency_ms", Number(e.target.value))}/></label>
                <label>Drop fields (%)<input type="number" min="0" max="100" value={Math.round((settings.drop_field_pct || 0) * 100)} onChange={(e) => update(device.device_name, "drop_field_pct", Number(e.target.value) / 100)}/></label>
                <label>Corrupt values (%)<input type="number" min="0" max="100" value={Math.round((settings.corrupt_pct || 0) * 100)} onChange={(e) => update(device.device_name, "corrupt_pct", Number(e.target.value) / 100)}/></label>
                <label>Low significance (%)<input type="number" min="0" max="100" value={Math.round(settings.low_significance_pct * 100)} onChange={(e) => update(device.device_name, "low_significance_pct", Number(e.target.value) / 100)}/></label>
                <label>Privacy filter<select value={String(settings.privacy_filter)} onChange={(e) => update(device.device_name, "privacy_filter", e.target.value === "strict" ? "strict" : e.target.value === "true")}><option value="false">Off</option><option value="true">On</option><option value="strict">Strict edge-only</option></select></label>
            </div>}</article>; })}</div>
        </Panel>}
        {mode !== "simulator" && <Panel title="Real devices through EdgeX" subtitle="Manage registered device services separately from Q-PRIME">
            <p className={styles.helpText}>Open the EdgeX Console to inspect services, device profiles, devices, commands, events, and readings. A physical device requires its compatible EdgeX device-service driver before it can appear here.</p>
            <a className={styles.consoleButton} href="http://localhost:4000" target="_blank" rel="noreferrer">Open EdgeX Console ↗</a>
        </Panel>}
    </div>;
}

function CloudConfiguration({ cloud, onSaved }) {
    const [form, setForm] = useState({ enabled: false, mode: "firehose", region: "", kinesis_stream: "", firehose_stream: "", athena_database: "", athena_table: "", athena_workgroup: "primary", athena_output: "", access_key_id: "", secret_access_key: "" });
    const [message, setMessage] = useState("");
    const [saving, setSaving] = useState(false);

    useEffect(() => {
        setForm((current) => ({ ...current, ...Object.fromEntries(["enabled", "mode", "region", "kinesis_stream", "firehose_stream", "athena_database", "athena_table", "athena_workgroup", "athena_output"].map((key) => [key, cloud?.[key] ?? current[key]])), access_key_id: "", secret_access_key: "" }));
    }, [cloud?.updated_at, cloud?.source]);

    function update(key, value) { setForm((current) => ({ ...current, [key]: value })); }
    async function save(event) {
        event.preventDefault(); setSaving(true);
        try {
            const saved = await api("cloud/config", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(form) });
            setMessage(`Saved and applied. Credentials are ${saved.access_key_configured ? "encrypted and stored" : "not configured"}.`);
            setForm((current) => ({ ...current, access_key_id: "", secret_access_key: "" })); onSaved();
        } catch (error) { setMessage(error.message); } finally { setSaving(false); }
    }
    async function probe() {
        setSaving(true);
        try { const result = await api("cloud/config/probe", { method: "POST" }); setMessage(result.status === "connected" ? "AWS connection verified." : result.last_error || `AWS status: ${result.status}.`); }
        catch (error) { setMessage(error.message); } finally { setSaving(false); }
    }
    const usesKinesis = form.mode === "kinesis";
    return <Panel title="AWS Cloud storage" subtitle="Saved in MongoDB and applied to new placements immediately">
        <p className={styles.helpText}>Enter the static AWS credentials once. They are encrypted before storage and never returned to this page. Existing keys are retained when these fields are left blank.</p>
        <form className={styles.cloudForm} onSubmit={save}>
            <label className={styles.toggle}><input type="checkbox" checked={form.enabled} onChange={(e) => update("enabled", e.target.checked)}/><span>Enable AWS Cloud placement</span></label>
            <div className={styles.cloudGrid}>
                <label>AWS region<input required={form.enabled} value={form.region} onChange={(e) => update("region", e.target.value)} placeholder="ap-southeast-2"/></label>
                <label>Ingestion service<select value={form.mode} onChange={(e) => update("mode", e.target.value)}><option value="firehose">Amazon Data Firehose</option><option value="kinesis">Amazon Kinesis Data Streams</option></select></label>
                <label className={usesKinesis ? "" : styles.hiddenField}>Kinesis stream<input required={form.enabled && usesKinesis} value={form.kinesis_stream} onChange={(e) => update("kinesis_stream", e.target.value)} placeholder="qprime-records"/></label>
                <label className={usesKinesis ? styles.hiddenField : ""}>Firehose delivery stream<input required={form.enabled && !usesKinesis} value={form.firehose_stream} onChange={(e) => update("firehose_stream", e.target.value)} placeholder="qprime-records"/></label>
            </div>
            <fieldset><legend>Static AWS credentials</legend><div className={styles.cloudGrid}>
                <label>Access key ID<input autoComplete="off" value={form.access_key_id} onChange={(e) => update("access_key_id", e.target.value)} placeholder={cloud?.access_key_configured ? "Configured — enter to replace" : "AKIA..."}/></label>
                <label>Secret access key<input type="password" autoComplete="new-password" value={form.secret_access_key} onChange={(e) => update("secret_access_key", e.target.value)} placeholder={cloud?.access_key_configured ? "Configured — enter to replace" : "Paste secret key"}/></label>
            </div></fieldset>
            <details className={styles.athena}><summary>Athena query settings <span>Optional, needed for Cloud queries</span></summary><div className={styles.cloudGrid}>
                <label>Database<input value={form.athena_database} onChange={(e) => update("athena_database", e.target.value)} placeholder="qprime"/></label><label>Table<input value={form.athena_table} onChange={(e) => update("athena_table", e.target.value)} placeholder="continuum"/></label><label>Workgroup<input value={form.athena_workgroup} onChange={(e) => update("athena_workgroup", e.target.value)} placeholder="primary"/></label><label>Athena results S3 URI<input value={form.athena_output} onChange={(e) => update("athena_output", e.target.value)} placeholder="s3://bucket/athena-results/"/></label>
            </div></details>
            <div className={styles.actions}><button type="submit" disabled={saving}>{saving ? "Saving…" : "Save and apply AWS configuration"}</button><button type="button" className={styles.secondaryButton} disabled={saving || !cloud?.access_key_configured} onClick={probe}>Test AWS connection</button><span>{message}</span></div>
        </form>
    </Panel>;
}

function Configuration({ config, cloud, onSaved }) {
    const activeGlobal = (config.active_profiles || []).find((item) => item.scope === "global");
    const [scope, setScope] = useState("global");
    const [selector, setSelector] = useState("");
    const [weightMode, setWeightMode] = useState("per_sensor");
    const [stream, setStream] = useState(PAPER_STREAMS[0]);
    const [directWeights, setDirectWeights] = useState(DEFAULT_WEIGHTS);
    const [judgements, setJudgements] = useState(DEFAULT_JUDGEMENTS);
    const [ahpPreview, setAhpPreview] = useState(null);
    const [ahpError, setAhpError] = useState("");
    const [message, setMessage] = useState("");
    const activeConfig = activeGlobal?.config || {};

    useEffect(() => {
        if (!activeGlobal) return;
        const configuredMode = ["per_sensor", "global_direct", "global_ahp"].includes(activeGlobal.config.weight_mode)
            ? activeGlobal.config.weight_mode : "per_sensor";
        const initialStream = PAPER_STREAMS.find((key) => activeGlobal.config.criteria_weights?.[key]) || PAPER_STREAMS[0];
        setWeightMode(configuredMode);
        setStream(initialStream);
        setDirectWeights(activeGlobal.config.criteria_weights?.[initialStream] || activeGlobal.config.global_criteria_weights || DEFAULT_WEIGHTS);
        setJudgements(matrixJudgements(activeGlobal.config.ahp_matrix));
        setMessage("");
    }, [activeGlobal?.version]);

    useEffect(() => {
        if (weightMode !== "global_ahp") return undefined;
        let cancelled = false;
        setAhpError("");
        api("config/ahp", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ judgements }) })
            .then((result) => { if (!cancelled) setAhpPreview(result); })
            .catch((error) => { if (!cancelled) { setAhpPreview(null); setAhpError(error.message); } });
        return () => { cancelled = true; };
    }, [weightMode, judgements]);

    function selectStream(nextStream) {
        setStream(nextStream);
        setDirectWeights(activeConfig.criteria_weights?.[nextStream] || activeConfig.global_criteria_weights || DEFAULT_WEIGHTS);
    }

    function selectWeightMode(nextMode) {
        setWeightMode(nextMode);
        if (nextMode === "global_direct") setDirectWeights(activeConfig.global_criteria_weights || DEFAULT_WEIGHTS);
        if (nextMode === "per_sensor") setDirectWeights(activeConfig.criteria_weights?.[stream] || activeConfig.global_criteria_weights || DEFAULT_WEIGHTS);
    }

    function setWeight(key, value) {
        const next = Math.min(1, Math.max(0, Number(value) || 0));
        setDirectWeights((current) => ({ ...current, [key]: next }));
    }

    function setJudgement(key, value) {
        setJudgements((current) => ({ ...current, [key]: Number(value) }));
    }

    async function save() {
        try {
            const resolvedSelector = scope === "global" ? "" : scope === "stream" ? stream : selector.trim();
            if (scope === "device" && !resolvedSelector) throw new Error("Enter a device name or ID for a device-specific profile.");
            const normalised = normaliseWeights(directWeights);
            const patch = weightMode === "per_sensor"
                ? { weight_mode: "per_sensor", criteria_weights: { [stream]: normalised } }
                : weightMode === "global_direct"
                    ? { weight_mode: "global_direct", global_criteria_weights: normalised }
                    : { weight_mode: "global_ahp", ahp_matrix: ahpPreview?.matrix };
            if (weightMode === "global_ahp" && (!ahpPreview?.consistent || !ahpPreview?.matrix)) throw new Error("Use a consistent AHP matrix before saving.");
            await api("config/profiles", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ scope, selector: resolvedSelector, config: patch, label: `${scope} criteria weights` }) });
            setMessage("Criteria weights saved; the new immutable version is active for future records."); onSaved();
        } catch (error) { setMessage(error.message); }
    }

    const displayedWeights = normaliseWeights(directWeights);
    const ahpInvalid = weightMode === "global_ahp" && (!ahpPreview || !ahpPreview.consistent);
    return <div className={styles.configStack}>
      <div className={styles.gridConfig}>
        <Panel title="Criteria weights" subtitle="Controls the live placement score">
            <p className={styles.helpText}>Choose how Q-PRIME weights temporal QoC, content QoC, and privacy. This privacy criterion is separate from a record’s privacy sensitivity score.</p>
            <div className={styles.formRow}><label>Profile scope<select value={scope} onChange={(e) => setScope(e.target.value)}><option value="global">Global</option><option value="stream">One paper stream</option><option value="device">One device</option></select></label>{scope === "device" ? <label>Device selector<input value={selector} onChange={(e) => setSelector(e.target.value)} placeholder="device name or ID"/></label> : scope === "stream" ? <label>Profile stream<select value={stream} onChange={(e) => selectStream(e.target.value)}>{PAPER_STREAMS.map((key) => <option key={key} value={key}>{key.replace("_", " ")}</option>)}</select></label> : <label>Applies to<input value="All incoming records" disabled/></label>}</div>
            <div className={styles.modeGrid}>
                <label className={weightMode === "per_sensor" ? styles.modeActive : ""}><input type="radio" name="weight-mode" value="per_sensor" checked={weightMode === "per_sensor"} onChange={(e) => selectWeightMode(e.target.value)}/><strong>Per data stream</strong><span>Use a different direct weighting for each known stream.</span></label>
                <label className={weightMode === "global_direct" ? styles.modeActive : ""}><input type="radio" name="weight-mode" value="global_direct" checked={weightMode === "global_direct"} onChange={(e) => selectWeightMode(e.target.value)}/><strong>Global direct</strong><span>Use one direct weighting for all matching records.</span></label>
                <label className={weightMode === "global_ahp" ? styles.modeActive : ""}><input type="radio" name="weight-mode" value="global_ahp" checked={weightMode === "global_ahp"} onChange={(e) => selectWeightMode(e.target.value)}/><strong>AHP pairwise matrix</strong><span>Derive global weights from Saaty comparisons.</span></label>
            </div>
            {weightMode !== "global_ahp" && <div className={styles.weightTool}>
                {weightMode === "per_sensor" && <label className={styles.streamSelect}>Paper stream<select value={stream} onChange={(e) => selectStream(e.target.value)}>{PAPER_STREAMS.map((key) => <option key={key} value={key}>{key.replace("_", " ")}</option>)}</select></label>}
                <div className={styles.weightIntro}><strong>{weightMode === "per_sensor" ? `${stream.replace("_", " ")} criteria` : "Global criteria"}</strong><span>Saved values are normalised to 100%.</span></div>
                <div className={styles.weightControls}>{CRITERIA.map(([key, label]) => <label key={key}><span>{label}</span><input type="range" min="0" max="1" step="0.01" value={directWeights[key]} onChange={(e) => setWeight(key, e.target.value)}/><input type="number" min="0" max="1" step="0.01" value={directWeights[key]} onChange={(e) => setWeight(key, e.target.value)}/><strong>{Math.round(displayedWeights[key] * 100)}%</strong></label>)}</div>
            </div>}
            {weightMode === "global_ahp" && <div className={styles.ahpTool}>
                <p>For each comparison, choose how important the first criterion is relative to the second.</p>
                {[["temporal_vs_spatial", "Temporal QoC", "Content QoC"], ["temporal_vs_privacy", "Temporal QoC", "Privacy"], ["spatial_vs_privacy", "Content QoC", "Privacy"]].map(([key, first, second]) => <label key={key}><span>{first} compared with {second}</span><select value={judgements[key]} onChange={(e) => setJudgement(key, e.target.value)}>{SAATY_OPTIONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>)}
                {ahpPreview && <div className={`${styles.ahpResult} ${ahpPreview.consistent ? styles.consistent : styles.inconsistent}`}><strong>{ahpPreview.consistent ? "Consistent AHP matrix" : "Inconsistent AHP matrix"}</strong><span>Consistency ratio: {(ahpPreview.consistency_ratio * 100).toFixed(1)}% (must be 10% or less)</span><div>{CRITERIA.map(([key, label]) => <small key={key}>{label}: {Math.round(ahpPreview.weights[key] * 100)}%</small>)}</div></div>}
                {ahpError && <p className={styles.danger}>{ahpError}</p>}
            </div>}
            <div className={styles.actions}><button disabled={ahpInvalid} onClick={save}>Save new profile version</button><span>{message}</span></div>
        </Panel>
        <Panel title="Active profiles" subtitle="All changes persist in MongoDB">
            <p className={styles.helpText}>Resolution order: device → stream → global. New records resolve the active profile before Q-PRIME scores placement.</p><div className={styles.profileList}>{(config.active_profiles || []).map((profile) => <article key={profile.version}><strong>{profile.scope}{profile.selector ? ` · ${profile.selector}` : ""}</strong><span>{profile.label}</span><code>{profile.version}</code><small>{new Date(profile.created_at).toLocaleString()}</small></article>)}</div>
        </Panel>
      </div>
      <CloudConfiguration cloud={cloud} onSaved={onSaved}/>
    </div>;
}

function Sensitivity() {
    const [weights, setWeights] = useState({ temporal: .33, spatial: .33, privacy: .34 });
    const [floor, setFloor] = useState(0);
    const [force, setForce] = useState(false);
    const [result, setResult] = useState(null);
    const [error, setError] = useState("");
    async function replay() { try { setResult(await api("results/sensitivity", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ weights, privacy_floor: floor, force_pii_edge: force }) })); setError(""); } catch (e) { setError(e.message); } }
    const chart = useMemo(() => ["edge", "cloud", "both"].map((tier) => ({ tier, original: result?.original?.[tier] || 0, replayed: result?.replayed?.[tier] || 0 })), [result]);
    return <Panel title="What if the criteria weights were different?" subtitle="Replays logged decisions only; it does not re-ingest or move data">
        <div className={styles.sliders}>{Object.keys(weights).map((key) => <label key={key}>{key}<input type="range" min="0" max="1" step="0.01" value={weights[key]} onChange={(e) => setWeights({ ...weights, [key]: Number(e.target.value) })}/><strong>{weights[key].toFixed(2)}</strong></label>)}<label>Privacy floor<input type="number" min="0" max="1" step="0.05" value={floor} onChange={(e) => setFloor(Number(e.target.value))}/></label><label className={styles.check}><input type="checkbox" checked={force} onChange={(e) => setForce(e.target.checked)}/> Force Edge for all PII</label><button onClick={replay}>Replay placements</button>{error && <span className={styles.danger}>{error}</span>}</div>
        {result && <><div className={styles.metrics}><Metric label="Replayed records" value={result.replayed_records}/><Metric label="Placements changed" value={result.placements_changed} tone="both"/><Metric label="PII cloud placements" value={result.pii_cloud_placements} tone={result.pii_cloud_placements ? "danger" : "edge"}/></div><ResponsiveContainer width="100%" height={330}><BarChart data={chart}><CartesianGrid stroke="#e2e8f0"/><XAxis dataKey="tier"/><YAxis allowDecimals={false}/><Tooltip/><Legend/><Bar dataKey="original" fill="#94a3b8"/><Bar dataKey="replayed" fill="#990033"/></BarChart></ResponsiveContainer></>}
    </Panel>;
}

function Performance({ data }) {
    return <><div className={styles.metrics}><Metric label="Placements measured" value={data.placement_count}/><Metric label="Mean placement latency" value={`${data.placement_latency_mean_ms || 0} ms`} tone="edge"/><Metric label="Queries measured" value={data.query_count}/><Metric label="Mean query latency" value={`${data.query_latency_mean_ms || 0} ms`} tone="cloud"/></div><div className={styles.grid2}><Panel title="Placement latency"><ResponsiveContainer width="100%" height={320}><AreaChart data={data.placement_timeline || []}><CartesianGrid stroke="#e2e8f0"/><XAxis dataKey="created_at" tickFormatter={(v) => new Date(v).toLocaleTimeString()}/><YAxis/><Tooltip/><Area dataKey="placement_latency_ms" stroke={COLOURS.edge} fill="#32c57a44"/></AreaChart></ResponsiveContainer></Panel><Panel title="Query latency"><ResponsiveContainer width="100%" height={320}><AreaChart data={data.query_timeline || []}><CartesianGrid stroke="#e2e8f0"/><XAxis dataKey="created_at" tickFormatter={(v) => new Date(v).toLocaleTimeString()}/><YAxis/><Tooltip/><Area dataKey="latency_ms" stroke={COLOURS.cloud} fill="#4f8df744"/></AreaChart></ResponsiveContainer></Panel></div></>;
}

export default function QPrimePage() {
    const [tab, setTab] = useState("Overview"); const [data, setData] = useState(empty);
    const [health, setHealth] = useState({}); const [config, setConfig] = useState({ active_profiles: [] }); const [cloud, setCloud] = useState({}); const [producer, setProducer] = useState({}); const [catalog, setCatalog] = useState([]); const [sourceMode, setSourceMode] = useState("sample_edgex");
    const [error, setError] = useState(""); const [loading, setLoading] = useState(true);
    const refresh = useCallback(async () => {
        try {
            const [h, o, q, d, p, perf, cfg, cloudConfig, producerStatus, producerCatalog] = await Promise.all([api("health"), api("results/overview"), api("results/qoc"), api("results/decisions?limit=250"), api("results/privacy"), api("results/performance"), api("config"), api("cloud/config"), api("producer/status"), api("producer/catalog")]);
            setHealth(h); setData({ overview: o, qoc: q, decisions: d.decisions || [], privacy: p, performance: perf }); setConfig(cfg); setCloud(cloudConfig); setProducer(producerStatus); setCatalog(producerCatalog.devices || []); setSourceMode(producerStatus.saved?.mode === "simulator" ? "simulator" : "sample_edgex"); setError("");
        } catch (e) { setError(e.message); } finally { setLoading(false); }
    }, []);
    useEffect(() => { refresh(); const timer = setInterval(refresh, 10000); return () => clearInterval(timer); }, [refresh]);
    return <main className={styles.shell}>
        <header className={styles.header}><div className={styles.brand}><div className={styles.brandMark}>Q</div><div><strong>Q-PRIME</strong><span>Live QoC and placement analytics</span></div></div><div className={styles.status}><StatusBadge label="Core" status={health.status}/><StatusBadge label="EdgeX" status={health.edgex?.status}/><StatusBadge label="MongoDB" status={health.mongodb?.status}/><StatusBadge label="Cloud" status={health.cloud?.status}/>{sourceMode !== "simulator" && <a href="http://localhost:4000" target="_blank" rel="noreferrer">Open EdgeX Console ↗</a>}<Link href={withBasePath("/")}>Sensor Dashboard</Link></div></header>
        <div className={styles.content}><nav>{TABS.map((name) => <button key={name} className={`${tab === name ? styles.active : ""} ${name === "Data Sources" ? styles.dataSourcesTab : ""}`} onClick={() => setTab(name)}>{name}</button>)}</nav>{error && <div className={styles.error}>{error}</div>}{loading ? <div className={styles.loading}>Loading Q-PRIME results…</div> : <>{tab === "Overview" && <Overview data={data.overview}/>} {tab === "QoC Factors" && <QoC data={data.qoc}/>} {tab === "Decisions" && <Decisions rows={data.decisions}/>} {tab === "Privacy" && <Privacy data={data.privacy}/>} {tab === "Data Sources" && <DataSources producer={producer} catalog={catalog} onSaved={refresh} onModeChange={setSourceMode}/>} {tab === "Configuration" && <Configuration config={config} cloud={cloud} onSaved={refresh}/>} {tab === "Sensitivity" && <Sensitivity/>} {tab === "Performance" && <Performance data={data.performance}/>}</>}</div>
        <footer>Q-PRIME · A Quality- and Privacy-Aware Edge–Cloud Continuum Framework for IoT Applications</footer>
    </main>;
}
