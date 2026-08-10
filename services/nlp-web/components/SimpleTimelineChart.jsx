"use client";

import React, { useState, useEffect, useMemo } from "react";

import { useDoorData } from "@/hooks/useDoorData";
import { useSmokeData } from "@/hooks/useSmokeData";
import { useMoistureData } from "@/hooks/useMoistureData";
import { useAllSensorsData } from "@/hooks/useAllSensorsData";
import { useTemperatureData } from "@/hooks/useTemperatureData";

import { Card } from "@/components/ui/card";
import { QuickActions } from "@/components/QuickActions";
import MoistureLineChart from "@/components/MoistureLineChart";
import TemperatureLineChart from "@/components/TemperatureLineChart";
import PressureLineChart from "@/components/PressureLineChart";
import HumidityLineChart from "./HumidityLineChart";
import DeviceEventStackedBar from "@/components/DeviceEventStackedBar";
import DoorEventsTimeline from "@/components/DoorEventsTimeline";
import SmokeEventsTimeline from "@/components/SmokeEventsTimeline";
import { useTHPData } from "@/hooks/useTHPData";

const SimpleTimelineChart = ({ databaseLayer, timeRange, setTimeRange }) => {
    // Accept timeRange, setTimeRange
    const [selectedAction, setSelectedAction] = useState("all-sensors");
    const [currentSensorTag, setCurrentSensorTag] = useState(
        "All Sensors Timeline"
    );

    const [chartType, setChartType] = useState("all-sensors");
    const [heartRateData, setHeartRateData] = useState(null);

    // Fetch data
    const effectiveHours = timeRange?.hours ?? 24;
    // console.log("[STC] effectiveHours:", effectiveHours);
    const { data: thpSeries } = useTHPData({
        timeRange,
        hours: effectiveHours,
        databaseLayer,
    });

    const moistureSeries = [];
    // const { data: moistureSeries } = useMoistureData({
    //     hours: effectiveHours,
    //     databaseLayer,
    // });

    // all sensors data fetch
    const { data: allSensorsSeries } = useAllSensorsData({
        hours: effectiveHours,
        databaseLayer,
    });

    // Fetch Smoke Data
    const smokeData = [];
    // const { data: smokeData } = useSmokeData({
    //     hours: effectiveHours,
    //     databaseLayer,
    // });

    // Fetch Door Data
    const { data: doorData } = useDoorData({
        hours: effectiveHours,
        databaseLayer,
    });

    const { doorTimelineData, doorKeys } = useMemo(() => {
        if (!Array.isArray(doorData) || doorData.length === 0) {
            return { doorTimelineData: [], doorKeys: [] };
        }

        const bucketMap = new Map();
        const labels = new Set();

        for (const entry of doorData) {
            const rawTimestamp = Number(entry?.timestamp);
            if (!Number.isFinite(rawTimestamp)) continue;

            const bucketSeconds = Math.floor(rawTimestamp / 900) * 900; // 15-minute buckets
            const bucketTime = bucketSeconds * 1000; // milliseconds for chart
            const deviceName = entry?.device_name || "Door Sensor";

            labels.add(deviceName);

            if (!bucketMap.has(bucketTime)) {
                bucketMap.set(bucketTime, { time: bucketTime });
            }

            const bucket = bucketMap.get(bucketTime);
            bucket[deviceName] = (bucket[deviceName] || 0) + 1;
        }

        const timeline = Array.from(bucketMap.values()).sort(
            (a, b) => a.time - b.time
        );

        return {
            doorTimelineData: timeline,
            doorKeys: Array.from(labels).sort(),
        };
    }, [doorData]);

    const { smokeTimelineData, smokeKeys } = useMemo(() => {
        if (!Array.isArray(smokeData) || smokeData.length === 0) {
            return { smokeTimelineData: [], smokeKeys: [] };
        }

        const bucketMap = new Map();
        const labels = new Set();

        for (const entry of smokeData) {
            const rawTimestamp = Number(entry?.timestamp);
            if (!Number.isFinite(rawTimestamp)) continue;

            const bucketSeconds = Math.floor(rawTimestamp / 900) * 900;
            const bucketTime = bucketSeconds * 1000;
            const deviceName = entry?.device_name || "Smoke Sensor";

            labels.add(deviceName);

            if (!bucketMap.has(bucketTime)) {
                bucketMap.set(bucketTime, { time: bucketTime });
            }

            const bucket = bucketMap.get(bucketTime);
            bucket[deviceName] = (bucket[deviceName] || 0) + 1;
        }

        const timeline = Array.from(bucketMap.values()).sort(
            (a, b) => a.time - b.time
        );

        return {
            smokeTimelineData: timeline,
            smokeKeys: Array.from(labels).sort(),
        };
    }, [smokeData]);

    // Fetch heartrate data only when selected
    useEffect(() => {
        let cancelled = false;
        async function fetchData() {
            if (chartType === "heartrate") {
                const data = await fetchHeartRateData(
                    effectiveHours,
                    databaseLayer
                );
                if (!cancelled) {
                    setHeartRateData(data);
                }
            }
        }
        if (chartType === "heartrate") {
            fetchData();
        } else {
            setHeartRateData(null);
        }

        return () => {
            cancelled = true;
        };
    }, [chartType, effectiveHours, databaseLayer]);

    // Handler for QuickActions select
    // QuickActions now updates the PARENT timeRange so the whole app stays in sync
    async function handleQuickAction(action) {
        setSelectedAction(action.id);
        setCurrentSensorTag(action.tag || "");
        setChartType(action.sensorType || "all-sensors");

        // Update global timeRange
        if (
            typeof setTimeRange === "function" &&
            typeof action.timeRange === "number"
        ) {
            const end = new Date();
            const start = new Date(
                end.getTime() - action.timeRange * 60 * 60 * 1000
            );
            setTimeRange({
                hours: action.timeRange,
                label: action.tag || `Last ${action.timeRange} hours`,
                start,
                end,
            });
        }
    }

    async function fetchHeartRateData(hours, layer) {
        return {
            type: "heartrate",
            values: [70, 72, 75, 73, 74],
            hours,
            layer,
        };
    }

    // Transform chartData for temperature chart
    const filteredTemperatureData =
        chartType === "temperature" && Array.isArray(thpSeries)
            ? thpSeries
                  .filter(
                      (d) =>
                          d &&
                          typeof d.timestamp !== "undefined" &&
                          typeof d.contextvalue.temperature !== "undefined"
                  )
                  .map((d) => ({
                      timestamp: Number(d.timestamp),
                      temperature: Number(d.contextvalue.temperature),
                  }))
                  .sort((a, b) => a.timestamp - b.timestamp) // Sort by timestamp ascending
            : [];

    // Transform chartData for pressure chart
    const filteredPressureData =
        chartType === "pressure" && Array.isArray(thpSeries)
            ? thpSeries
                  .filter(
                      (d) =>
                          d &&
                          typeof d.timestamp !== "undefined" &&
                          typeof d.contextvalue.pressure !== "undefined"
                  )
                  .map((d) => ({
                      timestamp: Number(d.timestamp),
                      pressure: Number(d.contextvalue.pressure),
                  }))
                  .sort((a, b) => a.timestamp - b.timestamp) // Sort by timestamp ascending
            : [];

    // Transform chartData for humidity chart
    const filteredHumidityData =
        chartType === "humidity" && Array.isArray(thpSeries)
            ? thpSeries
                  .filter(
                      (d) =>
                          d &&
                          typeof d.timestamp !== "undefined" &&
                          typeof d.contextvalue.humidity !== "undefined"
                  )
                  .map((d) => ({
                      timestamp: Number(d.timestamp),
                      humidity: Number(d.contextvalue.humidity),
                  }))
                  .sort((a, b) => a.timestamp - b.timestamp) // Sort by timestamp ascending
            : [];

    const filteredMoistureData =
        chartType === "moisture" && Array.isArray(moistureSeries)
            ? moistureSeries
                  .filter(
                      (d) =>
                          d &&
                          typeof d.timestamp !== "undefined" &&
                          typeof d.event !== "undefined" &&
                          (d.event === "WET" || d.event === "DRY")
                  )
                  .map((d) => ({
                      timestamp: Number(d.timestamp),
                      moisture: d.event === "WET" ? 1 : 0, // Convert WET to 1, DRY to 0
                      event: d.event, // Keep original event for tooltip
                  }))
                  .sort((a, b) => a.timestamp - b.timestamp) // Sort by timestamp ascending
            : [];

    return (
        <div className="space-y-4">
            {/* Quick Action Tab */}
            <div className="flex items-center justify-between">
                <div>
                    <h3 className="font-medium">{currentSensorTag}</h3>
                    {/* Selected time range display */}
                    {timeRange && (
                        <p className="text-xs text-muted-foreground">
                            {(() => {
                                const hasStart = !!timeRange.start;
                                const hasEnd = !!timeRange.end;
                                const options = {
                                    year: "numeric",
                                    month: "short",
                                    day: "2-digit",
                                    hour: "2-digit",
                                    minute: "2-digit",
                                    second: "2-digit",
                                };
                                const rangeStr =
                                    hasStart && hasEnd
                                        ? `${new Date(timeRange.start).toLocaleString(undefined, options)} — ${new Date(timeRange.end).toLocaleString(undefined, options)}`
                                        : "";
                                const rawLabel = timeRange.label || "";
                                const sanitizedLabel = rawLabel.startsWith(
                                    "Custom:"
                                )
                                    ? "Custom"
                                    : rawLabel;
                                return sanitizedLabel
                                    ? `${sanitizedLabel}${rangeStr ? ` • ${rangeStr}` : ""}`
                                    : rangeStr;
                            })()}
                        </p>
                    )}
                </div>
                {/* Selected time range */}
                <QuickActions
                    onActionClick={handleQuickAction}
                    selectedAction={selectedAction}
                />
            </div>
            {/* Chart */}
            <Card className="p-6">
                <div className="h-80 flex items-center justify-center text-muted-foreground">
                    {chartType === "temperature" &&
                    filteredTemperatureData.length > 0 ? (
                        <TemperatureLineChart data={filteredTemperatureData} />
                    ) : chartType === "pressure" &&
                      filteredPressureData.length > 0 ? (
                        <PressureLineChart data={filteredPressureData} />
                    ) : chartType === "humidity" &&
                      filteredHumidityData.length > 0 ? (
                        <HumidityLineChart data={filteredHumidityData} />
                    ) : chartType === "moisture" &&
                      filteredMoistureData.length > 0 ? (
                        <MoistureLineChart data={filteredMoistureData} />
                    ) : chartType === "door" && doorTimelineData.length > 0 ? (
                        <DoorEventsTimeline
                            data={doorTimelineData}
                            doorKeys={doorKeys}
                        />
                    ) : chartType === "smoke" &&
                      smokeTimelineData.length > 0 ? (
                        <SmokeEventsTimeline
                            data={smokeTimelineData}
                            smokeKeys={smokeKeys}
                        />
                    ) : chartType === "all-sensors" &&
                      Array.isArray(allSensorsSeries) &&
                      allSensorsSeries.length > 0 ? (
                        <DeviceEventStackedBar rows={allSensorsSeries} />
                    ) : chartType === "heartrate" && heartRateData ? (
                        <div>
                            Heart Rate Chart (data:{" "}
                            {JSON.stringify(heartRateData)})
                        </div>
                    ) : (
                        <div>
                            No data, please try increasing the time range.
                        </div>
                    )}
                </div>
                {/* Debug output for datasets */}
                {/* <div className="mt-4 p-2 bg-gray-100 rounded text-xs text-gray-700">
                    <strong>Debug:</strong>
                     <div>
                        thpSeries: {JSON.stringify(thpSeries)}
                    </div>
                    <div>moistureSeries: {JSON.stringify(moistureSeries)}</div>
                    <div>
                        allSensorsSeries: {JSON.stringify(allSensorsSeries)}
                    </div>

                    <div>doorData: {JSON.stringify(doorData)}</div>
                    <div>smokeData: {JSON.stringify(smokeData)}</div>
                </div>*/}
            </Card>
        </div>
    );
};

export default SimpleTimelineChart;
