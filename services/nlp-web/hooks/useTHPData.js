"use client";

import { useState, useEffect, useCallback } from "react";

import { SQL_TABLE, timeWindowSql } from "@/lib/sql";

import { withBasePath } from "@/lib/basePath";

export const useTHPData = ({
    timeRange,
    hours,
    databaseLayer,
    autoRefreshInterval = 0,
}) => {
    const [data, setData] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);


    const fetchTHPStats = useCallback(async () => {
        try {
            setLoading(true);
            setError(null);

            // Select only dashboard-safe fields: canonical_json is not readable by Presto.
            const query = `SELECT timestamp, resource.device_name, contextattribute, contextvalue
                FROM ${SQL_TABLE}
                WHERE resource.device_name = 'LabTHPSensor'
                AND ${timeWindowSql(hours)}
                ORDER BY timestamp DESC;`;

            const response = await fetch(withBasePath("/api/dashboard/thp"), {
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
            // console.log("THP Data Fetched: ", result.data);
        } catch (err) {
            setError(err instanceof Error ? err.message : "An error occurred");
            console.error("Error fetching device stats:", err);
        } finally {
            setLoading(false);
        }
    }, [timeRange, hours, databaseLayer]);

    useEffect(() => {
        fetchTHPStats();
        // Set up auto refresh if interval is provided
        let intervalId;
        if (autoRefreshInterval > 0) {
            intervalId = setInterval(fetchTHPStats, autoRefreshInterval);
        }

        // Clean up interval on unmount
        return () => {
            if (intervalId) {
                clearInterval(intervalId);
            }
        };
    }, [fetchTHPStats, autoRefreshInterval]);

    return {
        data,
        loading,
        error,
        refresh: fetchTHPStats,
    };
};
