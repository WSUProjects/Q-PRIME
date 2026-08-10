"use client";

import { useState, useEffect, useCallback } from "react";

import { SQL_TABLE, todayWindowSql } from "@/lib/sql";

import { withBasePath } from "@/lib/basePath";

export const useDeviceStats = ({ databaseLayer, autoRefreshInterval = 0 }) => {
    const [data, setData] = useState([]);
    // const [uniqueDevices, setUniqueDevices] = useState(0);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);


    // Query for unique devices today
    const query = `SELECT COUNT(DISTINCT resource.device_name) as unique_devices_today
        FROM ${SQL_TABLE}
        WHERE ${todayWindowSql()};`;

    const fetchDeviceStats = useCallback(async () => {
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
    }, []);

    useEffect(() => {
        fetchDeviceStats();
        // Set up auto refresh if interval is provided
        let intervalId;
        if (autoRefreshInterval > 0) {
            intervalId = setInterval(fetchDeviceStats, autoRefreshInterval);
        }

        // Clean up interval on unmount
        return () => {
            if (intervalId) {
                clearInterval(intervalId);
            }
        };
    }, [fetchDeviceStats, autoRefreshInterval]);

    return {
        data,
        loading,
        error,
        refresh: fetchDeviceStats,
    };
};

// Hook for specific device counting with auto refresh
export const useDeviceCount = (autoRefreshInterval = 0) => {
    const { data, loading, error, refresh } = useDeviceStats({
        autoRefreshInterval,
    });

    let length = -1;

    if (data.length == 0) {
        // console.log("Data fetched successfully:", data.length);
        length = data.length;
    } else if (data.length > 0) {
        length = data[0].unique_devices_today;
    }

    return {
        uniqueDevices: length,
        loading,
        error,
        refresh,
    };
};
