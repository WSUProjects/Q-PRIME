"use client";

import React from "react";
import {
    ResponsiveContainer,
    LineChart,
    Line,
    XAxis,
    YAxis,
    Tooltip,
    CartesianGrid,
    Legend,
} from "recharts";

const COLORS = [
    "#2563eb",
    "#f97316",
    "#22c55e",
    "#a855f7",
    "#ec4899",
    "#0ea5e9",
];

function formatTimestamp(value) {
    if (!Number.isFinite(value)) return "";
    return new Date(value).toLocaleString(undefined, {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
    });
}

export default function DoorEventsTimeline({ data = [], doorKeys = [] }) {
    if (!Array.isArray(data) || data.length === 0) {
        return (
            <div className="text-sm text-muted-foreground">
                No door activity in this range
            </div>
        );
    }

    const keysToRender = doorKeys.length > 0 ? doorKeys : Object.keys(data[0]).filter((k) => k !== "time");

    return (
        <div className="w-full h-full">
            <ResponsiveContainer>
                <LineChart
                    data={data}
                    margin={{ top: 16, right: 24, left: 12, bottom: 8 }}
                >
                    <CartesianGrid strokeDasharray="3 3" vertical={false} />
                    <XAxis
                        dataKey="time"
                        type="number"
                        domain={["auto", "auto"]}
                        tickFormatter={formatTimestamp}
                        tickLine={false}
                        axisLine={false}
                        tick={{ fontSize: 12 }}
                    />
                    <YAxis
                        allowDecimals={false}
                        width={48}
                        tickLine={false}
                        axisLine={false}
                        tick={{ fontSize: 12 }}
                        label={{
                            value: "Events",
                            angle: -90,
                            position: "insideLeft",
                            offset: 10,
                        }}
                    />
                    <Tooltip
                        labelFormatter={(value) => formatTimestamp(value)}
                        formatter={(val, name) => [
                            Number.isFinite(val) ? val.toLocaleString() : val,
                            name,
                        ]}
                    />
                    <Legend
                        verticalAlign="top"
                        align="center"
                        wrapperStyle={{ paddingBottom: 12 }}
                        iconType="circle"
                    />
                    {keysToRender.map((doorName, idx) => (
                        <Line
                            key={doorName}
                            type="monotone"
                            dataKey={doorName}
                            stroke={COLORS[idx % COLORS.length]}
                            strokeWidth={2}
                            dot={{ r: 3 }}
                            activeDot={{ r: 5 }}
                        />
                    ))}
                </LineChart>
            </ResponsiveContainer>
        </div>
    );
}
