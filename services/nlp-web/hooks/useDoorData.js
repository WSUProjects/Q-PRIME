"use client";

import { useState, useEffect, useCallback } from "react";

import { SQL_TABLE, timeWindowSql } from "@/lib/sql";

import { withBasePath } from "@/lib/basePath";

export const useDoorData = ({
    timeRange,
    hours = 1,
    databaseLayer,
    autoRefreshInterval = 0,
}) => {
    const [data, setData] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);


    const fetchDoorStats = useCallback(async () => {
        try {
            setLoading(true);
            setError(null);

            // Query for hourly door stats
            const query = `SELECT *
                FROM ${SQL_TABLE}
                WHERE resource.device_name IN ('LabDoorSensor_1', 'LabDoorSensor_2', 'Door Sensor', 'Main Door Sensor', 'Back Door Sensor')
                AND ${timeWindowSql(hours)};`;

            const response = await fetch(withBasePath("/api/dashboard/door"), {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({ query, scope: databaseLayer }),
            });

            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}));
                throw new Error(
                    errorData.error || errorData.message ||
                        `HTTP error! status: ${response.status}`
                );
            }

            const result = await response.json();
            setData(result.data || []);
        } catch (err) {
            setError(err instanceof Error ? err.message : "An error occurred");
            console.error("Error fetching device stats:", err);
        } finally {
            setLoading(false);
        }
    }, [timeRange, hours, databaseLayer]);

    useEffect(() => {
        fetchDoorStats();
        // Set up auto refresh if interval is provided
        let intervalId;
        if (autoRefreshInterval > 0) {
            intervalId = setInterval(fetchDoorStats, autoRefreshInterval);
        }

        // Clean up interval on unmount
        return () => {
            if (intervalId) {
                clearInterval(intervalId);
            }
        };
    }, [fetchDoorStats, autoRefreshInterval]);

    const doorEventCount = data.length;

    return {
        data,
        doorEventCount,
        loading,
        error,
        refresh: fetchDoorStats,
    };
};
