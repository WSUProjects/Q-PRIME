"use client";

import { useState, useEffect, useCallback } from "react";

import { SQL_TABLE, timeWindowSql } from "@/lib/sql";

import { withBasePath } from "@/lib/basePath";

export const useAllSensorsData = ({
    hours = 1,
    databaseLayer,
    autoRefreshInterval = 0,
}) => {
    const [data, setData] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);


    // Event counts per device, which is what the stacked bar renders. Grouping
    // by the whole `contextValue` row instead produced one group per record —
    // thousands of single-count rows carrying no `event` column at all, so the
    // chart stacked everything into a single "Unknown" band.
    const query = `SELECT resource.device_name, contextValue.event AS event, COUNT(*) AS event_count
        FROM ${SQL_TABLE}
        WHERE ${timeWindowSql(hours)}
        GROUP BY resource.device_name, contextValue.event;`;

    const fetchAllSensorStats = useCallback(async () => {
        //query

        try {
            setLoading(true);
            setError(null);

            const response = await fetch(withBasePath("/api/dashboard/all"), {
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
    }, [hours, databaseLayer]);

    useEffect(() => {
        fetchAllSensorStats();
        // Set up auto refresh if interval is provided
        let intervalId;
        if (autoRefreshInterval > 0) {
            intervalId = setInterval(fetchAllSensorStats, autoRefreshInterval);
        }

        // Clean up interval on unmount
        return () => {
            if (intervalId) {
                clearInterval(intervalId);
            }
        };
    }, [fetchAllSensorStats, autoRefreshInterval]);

    return {
        data,
        loading,
        error,
        refresh: fetchAllSensorStats,
    };
};
export default useAllSensorsData;
