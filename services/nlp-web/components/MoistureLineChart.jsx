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

// Expects data: [{ timestamp, event }, ...]
export default function MoistureLineChart({ data, timeUnit = "minute" }) {
    // console.log("MoistureLineChart data:", data);

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

    // Custom tooltip to show WET/DRY instead of 1/0
    const CustomTooltip = ({ active, payload, label }) => {
        if (active && payload && payload.length) {
            const data = payload[0].payload;
            return (
                <div className="bg-white p-3 border border-gray-300 rounded shadow">
                    <p className="font-medium">{formatTime(label)}</p>
                    <p className="text-blue-600">
                        Status:{" "}
                        <span className="font-medium">{data.event}</span>
                    </p>
                </div>
            );
        }
        return null;
    };

    return (
        <div style={{ width: "100%", height: 320 }}>
            <h3 className="font-semibold mb-2">
                Moisture Sensor Status Over Time
            </h3>
            <ResponsiveContainer width="100%" height="100%">
                <LineChart data={data}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="timestamp" tickFormatter={formatTime} />
                    <YAxis
                        domain={[0, 1]}
                        ticks={[0, 1]}
                        tickFormatter={(value) => (value === 1 ? "WET" : "DRY")}
                        label={{
                            value: "Status",
                            angle: -90,
                            position: "insideLeft",
                        }}
                    />
                    <Tooltip content={<CustomTooltip />} />
                    <Line
                        type="stepAfter"
                        dataKey="moisture"
                        stroke="#2563eb"
                        strokeWidth={2}
                        dot={{ fill: "#2563eb", strokeWidth: 2, r: 4 }}
                    />
                </LineChart>
            </ResponsiveContainer>
        </div>
    );
}
