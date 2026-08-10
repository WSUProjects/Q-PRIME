"use client";

import { useState, useEffect, useCallback } from "react";

import { SQL_TABLE, timeWindowSql } from "@/lib/sql";

import { withBasePath } from "@/lib/basePath";

export const useMoistureData = ({
    hours = 1,
    databaseLayer,
    autoRefreshInterval = 0,
}) => {
    const [data, setData] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);


    // Query for hourly moisture stats
    const query = `SELECT *
        FROM ${SQL_TABLE}
        WHERE resource.device_name IN ('Soil Moisture Sensor 1', 'SoilMoisture_1')
        AND ${timeWindowSql(hours)}
        ORDER BY timestamp DESC;`;

    const fetchMoistureStats = useCallback(async () => {
        //query

        try {
            setLoading(true);
            setError(null);

            const response = await fetch(withBasePath("/api/dashboard/moisture"), {
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
        fetchMoistureStats();
        // Set up auto refresh if interval is provided
        let intervalId;
        if (autoRefreshInterval > 0) {
            intervalId = setInterval(fetchMoistureStats, autoRefreshInterval);
        }

        // Clean up interval on unmount
        return () => {
            if (intervalId) {
                clearInterval(intervalId);
            }
        };
    }, [fetchMoistureStats, autoRefreshInterval]);

    return {
        data,
        loading,
        error,
        refresh: fetchMoistureStats,
    };
};
