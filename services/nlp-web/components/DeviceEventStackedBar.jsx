"use client";

import React, { useMemo } from "react";
import {
    ResponsiveContainer,
    BarChart,
    XAxis,
    YAxis,
    Tooltip,
    CartesianGrid,
    Legend,
    Bar,
} from "recharts";

const COLORS = [
    "#2563eb",
    "#f97316",
    "#22c55e",
    "#a855f7",
    "#ec4899",
    "#0ea5e9",
    "#facc15",
    "#14b8a6",
];

const EVENT_LABEL_MAP = {
    C: "Temperature (°C)",
    DRY: "Soil Dry",
    WET: "Soil Wet",
    intruder_detected: "Intruder Detected",
    familiar_face_detected: "Familiar Face",
};

const UNKNOWN_EVENT_KEY = "__unknown_event__";

function formatEventLabel(key, nullEventLabel) {
    if (key === UNKNOWN_EVENT_KEY) return nullEventLabel;
    const mapped = EVENT_LABEL_MAP[key];
    if (mapped) return mapped;
    if (!key) return nullEventLabel;
    return key
        .replace(/_/g, " ")
        .replace(/\b\w/g, (char) => char.toUpperCase());
}

export default function DeviceEventStackedBar({
    rows = [],
    nullEventLabel = "Unknown",
}) {
    // console.log("DeviceEventStackedBar rows:", rows);
    const { data, eventKeys } = useMemo(() => {
        const map = new Map();
        const eventsSet = new Set();

        for (const r of rows) {
            const device = r.device_name ?? "Unknown Device";
            const rawEvent =
                r.event === null || typeof r.event === "undefined"
                    ? UNKNOWN_EVENT_KEY
                    : r.event;
            const count = Number(r.event_count ?? 0) || 0;

            eventsSet.add(rawEvent);
            if (!map.has(device))
                map.set(device, { device_name: device, __total: 0 });
            const obj = map.get(device);
            obj[rawEvent] = (obj[rawEvent] || 0) + count;
            obj.__total += count;
        }

        const arr = Array.from(map.values()).sort(
            (a, b) => b.__total - a.__total
        );
        const keys = Array.from(eventsSet).filter(
            (key) => key && key !== "total" && key !== "__total"
        );
        return { data: arr, eventKeys: keys };
    }, [rows, nullEventLabel]);

    if (!data.length)
        return <div className="text-sm text-muted-foreground">No data</div>;

    return (
        <div style={{ width: "100%", height: 360 }}>
            <ResponsiveContainer>
                <BarChart
                    data={data}
                    margin={{ top: 16, right: 24, left: 12, bottom: 72 }}
                    barCategoryGap="20%"
                    barGap={4}
                >
                    <CartesianGrid strokeDasharray="3 3" vertical={false} />
                    <XAxis
                        dataKey="device_name"
                        angle={0}
                        textAnchor="middle"
                        interval={0}
                        height={1}
                        tickLine={false}
                        axisLine={false}
                        tick={{ fontSize: 12 }}
                        tickFormatter={(value) =>
                            typeof value === "string"
                                ? value.split(/\s+/).join("\n")
                                : value
                        }
                    />
                    <YAxis
                        width={64}
                        tickLine={false}
                        axisLine={false}
                        tick={{ fontSize: 12 }}
                    />
                    <Tooltip
                        formatter={(value, name, { dataKey }) => [
                            Number.isFinite(value)
                                ? value.toLocaleString()
                                : value,
                            formatEventLabel(
                                typeof dataKey !== "undefined" ? dataKey : name,
                                nullEventLabel
                            ),
                        ]}
                    />
                    {/* <Legend
                        verticalAlign="top"
                        align="center"
                        wrapperStyle={{ paddingBottom: 12 }}
                        iconType="circle"
                        formatter={(value) =>
                            formatEventLabel(value, nullEventLabel)
                        }
                    /> */}
                    {eventKeys.map((key, idx) => (
                        <Bar
                            key={key}
                            dataKey={key}
                            stackId="a"
                            fill={COLORS[idx % COLORS.length]}
                            isAnimationActive={false}
                            radius={[6, 6, 0, 0]}
                            maxBarSize={64}
                        />
                    ))}
                </BarChart>
            </ResponsiveContainer>
        </div>
    );
}
