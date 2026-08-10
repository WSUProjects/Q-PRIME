"use client";

import { useState, useEffect, useCallback } from "react";

import { SQL_TABLE, timeWindowSql } from "@/lib/sql";

import { withBasePath } from "@/lib/basePath";

export const useSmokeData = ({
    timeRange,
    hours = 1,
    databaseLayer,
    autoRefreshInterval = 0,
}) => {
    const [data, setData] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);


    const fetchSmokeStats = useCallback(async () => {
        try {
            setLoading(true);
            setError(null);

            // Query for hourly smoke stats
            const query = `SELECT *
                FROM ${SQL_TABLE}
                WHERE resource.device_name IN ('Smoke Sensor 1', 'Lab Smoke Sensor', 'SmokeDetector_1')
                AND ${timeWindowSql(hours)};`;

            const response = await fetch(withBasePath("/api/dashboard/smoke"), {
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
        fetchSmokeStats();
        // Set up auto refresh if interval is provided
        let intervalId;
        if (autoRefreshInterval > 0) {
            intervalId = setInterval(fetchSmokeStats, autoRefreshInterval);
        }

        // Clean up interval on unmount
        return () => {
            if (intervalId) {
                clearInterval(intervalId);
            }
        };
    }, [fetchSmokeStats, autoRefreshInterval]);

    const smokeEventCount = data.length;

    return {
        data,
        smokeEventCount,
        loading,
        error,
        refresh: fetchSmokeStats,
    };
};
