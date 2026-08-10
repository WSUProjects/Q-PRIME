"use client";

import React from "react";
import { useEffect, useState } from "react";

import TimelineActivityStream from "./TimelineActivityStream";

export default function TimelineDemo() {
    const [events, setEvents] = useState([]);
    // const SQL = `SELECT *
    //     FROM iot_edge_x_sensor_data
    //     WHERE FROM_UNIXTIME(timestamp) >= TIMESTAMP '2025-09-03 00:00:01'
    //     AND FROM_UNIXTIME(timestamp) < TIMESTAMP '2025-09-03 23:59:59';`;

    const SQL = `SELECT *
        FROM iot_edge_x_sensors_data
        WHERE date_format(from_unixtime(timestamp), '%Y-%m-%d') = date_format(current_date, '%Y-%m-%d');`;

    useEffect(() => {
        async function fetchData() {
            const res = await fetch("/api/query", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ input: SQL }),
            });
            const data = await res.json();
            // data.headers: array of headers
            // data.data: [ [row1], [row2], ... ]
            if (
                data &&
                Array.isArray(data.headers) &&
                Array.isArray(data.data)
            ) {
                const eventsArr = data.data.map((rowArr) => {
                    const obj = {};
                    data.headers.forEach((header, idx) => {
                        obj[header] = rowArr[idx];
                    });
                    return obj;
                });
                // Sort by timestamp descending (parseInt)
                setEvents(
                    eventsArr.sort(
                        (a, b) => parseInt(b.timestamp) - parseInt(a.timestamp)
                    )
                );
            } else {
                setEvents([]);
            }
        }
        fetchData();
    }, []);

    return (
        <div>
            <h2 className="text-xl font-bold mb-4 text-gray-700">
                Daily Activity Timeline
            </h2>
            <TimelineActivityStream events={events} />
        </div>
    );
}
