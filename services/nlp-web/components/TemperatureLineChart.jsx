import React from "react";
import {
    LineChart,
    Line,
    XAxis,
    YAxis,
    Tooltip,
    CartesianGrid,
    ResponsiveContainer,
} from "recharts";

// Expects data: [{ timestamp, temperature }, ...]
export default function TemperatureLineChart({ data, timeUnit = "minute" }) {
    // Check if data spans more than 24 hours
    const getTimeSpan = () => {
        if (!data || data.length < 2) return 0;
        const timestamps = data.map((d) =>
            parseInt(d.timestamp.length > 10 ? d.timestamp : d.timestamp * 1000)
        );
        const minTime = Math.min(...timestamps);
        const maxTime = Math.max(...timestamps);
        return (maxTime - minTime) / (1000 * 60 * 60); // hours
    };

    const timeSpanHours = getTimeSpan();
    const showDate = timeSpanHours > 24;

    // Format timestamp for axis label
    const formatTime = (ts) => {
        const date = new Date(parseInt(ts.length > 10 ? ts : ts * 1000));
        if (timeUnit === "day" || showDate) {
            return `${date.toLocaleDateString()} ${date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`;
        }
        if (timeUnit === "hour")
            return date.toLocaleTimeString([], {
                hour: "2-digit",
                minute: "2-digit",
            });
        return date.toLocaleTimeString([], {
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit",
        });
    };

    return (
        <div style={{ width: "100%", height: 320 }}>
            <h3 className="font-semibold mb-2">Temperature Over Time (°C)</h3>
            <ResponsiveContainer width="100%" height="100%">
                <LineChart data={data}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="timestamp" tickFormatter={formatTime} />
                    <YAxis
                        domain={["auto", "auto"]}
                        label={{
                            value: "°C",
                            angle: -90,
                            position: "insideLeft",
                        }}
                    />
                    <Tooltip labelFormatter={formatTime} />
                    <Line
                        type="monotone"
                        dataKey="temperature"
                        stroke="#f59e42"
                        dot={false}
                    />
                </LineChart>
            </ResponsiveContainer>
        </div>
    );
}
