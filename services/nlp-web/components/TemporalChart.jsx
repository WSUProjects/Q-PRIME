"use client";

import { useMemo } from "react";
import {
    ResponsiveContainer,
    LineChart,
    Line,
    XAxis,
    YAxis,
    Tooltip,
    CartesianGrid,
    Brush,
} from "recharts";

function floorToBin(d, bin) {
    const t = d.getTime();
    if (bin === "minute") return new Date(Math.floor(t / 60000) * 60000);
    if (bin === "hour") return new Date(Math.floor(t / 3600000) * 3600000);
    if (bin === "day")
        return new Date(
            new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime()
        );
    return d;
}

function pad(num) {
    return String(num).padStart(2, "0");
}

function formatBinLabel(d, bin) {
    const y = d.getFullYear();
    const m = pad(d.getMonth() + 1);
    const day = pad(d.getDate());
    const base = `${y}-${m}-${day}`;

    if (bin === "day") return base;

    const hour = pad(d.getHours());
    if (bin === "hour") return `${base} ${hour}:00`;

    const minute = pad(d.getMinutes());
    return `${base} ${hour}:${minute}`;
}

export default function TemporalChart({
    rows = [],
    timeKey = "ts",
    bin = "minute",
    title = "Events over time",
}) {
    function parseTime(raw) {
        if (raw instanceof Date) return raw;
        if (raw === null || raw === undefined) return null;
        // numeric: could be seconds or milliseconds
        if (typeof raw === "number")
            return raw > 1e12 ? new Date(raw) : new Date(raw * 1000);
        const s = String(raw).trim();
        if (/^\d+$/.test(s)) {
            const n = Number(s);
            return n > 1e12 ? new Date(n) : new Date(n * 1000);
        }
        // common datetime like '2025-10-15 13:00:21.000' -> convert to ISO-like
        let t = s.replace(" ", "T");
        // if timezone absent, Date will parse as local; that's acceptable
        const d = new Date(t);
        if (!isNaN(d)) return d;
        // try removing fractional seconds
        const t2 = t.replace(/\.\d+$/, "");
        const d2 = new Date(t2);
        if (!isNaN(d2)) return d2;
        return null;
    }

    const { data, valueField, valueLabel } = useMemo(() => {
        if (!rows || rows.length === 0)
            return { data: [], valueField: "count", valueLabel: "Count" };

        const hasMisty = rows.some((r) => {
            const candidate =
                r?.device_name ||
                r?.deviceName ||
                r?.device ||
                r?.device_id ||
                r?.deviceId ||
                "";
            if (typeof candidate !== "string") return false;
            const normalized = candidate
                .toLowerCase()
                .replace(/[^a-z0-9]/g, "");
            return (
                normalized === "mistyrobot1" ||
                normalized === "mistyrobot" ||
                normalized === "misty03953"
            );
        });

        const allowNumericValues = !hasMisty;

        const map = new Map();
        let foundNumeric = false;
        let numericKey = null;

        for (const r of rows) {
            const raw = r[timeKey] ?? r.timestamp ?? r.time ?? r.ts ?? r.date;
            const dt = parseTime(raw);
            if (!dt) continue;
            const b = floorToBin(dt, bin);
            const key = b.getTime();

            const entry = map.get(key) || { count: 0, sum: 0 };
            entry.count += 1;

            let v = undefined;
            if (allowNumericValues) {
                const numericCandidates = [
                    "temperature",
                    "temp",
                    "value",
                    "reading",
                ];
                for (const candidateKey of numericCandidates) {
                    if (
                        r[candidateKey] !== undefined &&
                        r[candidateKey] !== null
                    ) {
                        const n = Number(r[candidateKey]);
                        if (!Number.isNaN(n) && Number.isFinite(n)) {
                            v = n;
                            numericKey = numericKey || candidateKey;
                            break;
                        }
                    }
                }
                if (v === undefined) {
                    for (const [k, val] of Object.entries(r)) {
                        if (
                            k === timeKey ||
                            ["timestamp", "time", "ts", "date"].includes(k)
                        )
                            continue;
                        const n = Number(val);
                        if (!Number.isNaN(n) && Number.isFinite(n)) {
                            v = n;
                            numericKey = numericKey || k;
                            break;
                        }
                    }
                }
            }

            if (v !== undefined) {
                foundNumeric = true;
                entry.sum = (entry.sum || 0) + v;
            }

            map.set(key, entry);
        }

        const labels = [...map.keys()].sort((a, b) => a - b);
        const toLabel = (key) => {
            if (!key) return "Value";
            const cleaned = key.replace(/_/g, " ");
            return cleaned.charAt(0).toUpperCase() + cleaned.slice(1);
        };

        const showNumericSeries = allowNumericValues && foundNumeric;
        const out = labels.map((k) => {
            const e = map.get(k);
            const date = new Date(k);
            const label = formatBinLabel(date, bin);

            if (showNumericSeries) {
                const avg = e.count > 0 ? e.sum / e.count : null;
                return {
                    time: label,
                    timestamp: date.getTime(),
                    value: avg,
                    count: e.count,
                };
            }
            return {
                time: label,
                timestamp: date.getTime(),
                count: e.count,
            };
        });

        const labelForSeries = showNumericSeries
            ? toLabel(numericKey)
            : "Count";

        return {
            data: out,
            valueField: showNumericSeries ? "value" : "count",
            valueLabel: labelForSeries,
        };
    }, [rows, timeKey, bin]);

    if (!data || data.length === 0) {
        return (
            <div
                style={{
                    border: "1px solid #e5e7eb",
                    borderRadius: 12,
                    padding: 12,
                }}
            >
                <h3 style={{ margin: "6px 0 12px 0" }}>{title}</h3>
                <div style={{ color: "#6b7280" }}>
                    No time-series data available.
                </div>
            </div>
        );
    }

    return (
        <div
            style={{
                border: "1px solid #e5e7eb",
                borderRadius: 12,
                padding: 12,
            }}
        >
            <h3 style={{ margin: "6px 0 12px 0" }}>{title}</h3>
            <div style={{ width: "100%", height: 320 }}>
                <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={data}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="time" tickFormatter={(t) => t} />
                        <YAxis
                            allowDecimals={valueField === "value"}
                            tickFormatter={(v) =>
                                valueField === "value" && typeof v === "number"
                                    ? v.toFixed(1)
                                    : v
                            }
                        />
                        <Tooltip
                            formatter={(val) => {
                                if (valueField === "count") {
                                    const num =
                                        typeof val === "number"
                                            ? Math.round(val)
                                            : val;
                                    return [num, "Count"];
                                }
                                const num =
                                    typeof val === "number"
                                        ? val.toFixed(2)
                                        : val;
                                return [num, valueLabel];
                            }}
                        />
                        <Line
                            type="monotone"
                            dataKey={valueField}
                            stroke={
                                valueField === "value" ? "#dc2626" : "#2563eb"
                            }
                            dot={false}
                            name={valueLabel}
                        />
                        <Brush dataKey="time" height={30} stroke="#8884d8" />
                    </LineChart>
                </ResponsiveContainer>
            </div>
        </div>
    );
}
