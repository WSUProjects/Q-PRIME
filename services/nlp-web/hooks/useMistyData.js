"use client";

import { useState, useEffect, useCallback } from "react";

import { SQL_TABLE, timeWindowSql } from "@/lib/sql";

import { withBasePath } from "@/lib/basePath";

export const useMistyData = ({
    databaseLayer,
    timeRange = 1,
    eventType = "intruder_detected",
    autoRefreshInterval = 0, // in milliseconds (0 = no auto refresh)
}) => {
    const [data, setData] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);


    const fetchMistyData = useCallback(async () => {
        try {
            setLoading(true);
            setError(null);

            const query = `SELECT COUNT(*) as intruders FROM ${SQL_TABLE} WHERE contextAttribute = 'misty_vision' AND contextValue.event = '${eventType}' AND ${timeWindowSql(timeRange)};`;

            // Q-PRIME core: continuum query API
            const response = await fetch(withBasePath("/api/dashboard/misty"), {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({
                    query,
                    scope: databaseLayer,
                    timeRange: timeRange * 60 * 60, // convert to seconds
                }),
            });

            // console.log(response);
            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}));
                throw new Error(
                    errorData.error ||
                        errorData.message ||
                        `HTTP error! status: ${response.status}`
                );
            }

            const result = await response.json();
            setData(result.data || []);
        } catch (err) {
            setError(err instanceof Error ? err.message : "An error occurred");
            console.error("Error fetching Misty data:", err);
        } finally {
            setLoading(false);
        }
    }, [timeRange, eventType, databaseLayer]);

    useEffect(() => {
        // Initial fetch
        fetchMistyData();

        // Set up auto refresh if interval is provided
        let intervalId;
        if (autoRefreshInterval > 0) {
            intervalId = setInterval(fetchMistyData, autoRefreshInterval);
        }

        // Clean up interval on unmount
        return () => {
            if (intervalId) {
                clearInterval(intervalId);
            }
        };
    }, [fetchMistyData, autoRefreshInterval]);

    return {
        data,
        loading,
        error,
        refresh: fetchMistyData,
    };
};

// Hook for specific intruder counting with auto refresh
export const useIntruderCount = ({
    databaseLayer,
    timeRange = 1,
    autoRefreshInterval = 0,
} = {}) => {
    const { data, loading, error, refresh } = useMistyData({
        databaseLayer,
        timeRange,
        eventType: "intruder_detected",
        autoRefreshInterval,
    });

    const intruderCount = data[0]?.["intruders"];
    return {
        intruderCount,
        loading,
        error,
        refresh,
    };
};
