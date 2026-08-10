"use client";

import React from "react";

import { useDoorData } from "@/hooks/useDoorData";
import { useSmokeData } from "@/hooks/useSmokeData";
import { useDeviceCount } from "@/hooks/useSensorData";
import { useIntruderCount } from "@/hooks/useMistyData";
import { useMoistureData } from "@/hooks/useMoistureData";

import CloudCards from "@/components/CloudCards";
import EdgeCards from "@/components/EdgeCards";
import { useTHPData } from "@/hooks/useTHPData";
import { parseTHPContext } from "@/lib/utils";

// Soil moisture is reported as a percentage on the canonical `moisture_pct`
// field; turn the most recent reading into the label the cards colour on.
function soilConditionFrom(rows) {
    const latest = (rows || []).find(
        (row) => typeof row?.contextvalue?.moisture_pct === "number"
    );
    if (!latest) return "-";
    const pct = latest.contextvalue.moisture_pct;
    if (pct < 25) return "DRY";
    if (pct > 60) return "WET";
    return "OPTIMAL";
}

export default function CardsSection({ databaseLayer }) {
    // Moisture data
    const { data: moistureRows } = useMoistureData({
        hours: 1,
        databaseLayer: databaseLayer,
    });
    const soil_condition = soilConditionFrom(moistureRows);

    // Intruder Count
    // const intruderCount = -1; // Placeholder value
    const { intruderCount } = useIntruderCount({
        timeRange: 1,
        databaseLayer: databaseLayer,
    }); // Last 1 hour
    //const { intruderCount, loading, error, refresh } = useIntruderCount(1, 30000); Refresh every 30 seconds (30000 ms)
    // console.log("Intruder Count: ", intruderCount);

    // Sensor count
    //const sensorCount = -1; // Placeholder value
    // const { uniqueDevices: sensorCount } = useDeviceCount();

    // Smoke Sensor Data. The tile counts raised alarms, not every reading the
    // detector produced, so filter on the event rather than using row count.
    const { data: smokeRows } = useSmokeData({
        hours: 1,
        databaseLayer: databaseLayer,
    });
    const smokeEventCount = (smokeRows || []).filter(
        (row) => row?.contextvalue?.event === "smoke_alarm"
    ).length;

    // Door Sensor Data. As with smoke, the tile counts openings rather than
    // every contact reading — row count alone just reported the query's
    // server-side row cap.
    const { data: doorRows } = useDoorData({
        hours: 1,
        databaseLayer: databaseLayer,
    });
    const doorEventCount = (doorRows || []).filter(
        (row) => row?.contextvalue?.event === "opened"
    ).length;

    let thp_temp = -1;
    let thp_humidity = -1;
    let thp_pressure = -1;

    let thp_data = null;
    ({ data: thp_data } = useTHPData({
        hours: 1,
        databaseLayer: databaseLayer,
    }));

    // console.log("THP Data Fetched:", thp_data);
    const firstThp = thp_data?.[0];
    // console.log("THP Data (first record):", firstThp);
    thp_temp = firstThp?.contextvalue?.temperature;
    thp_humidity = firstThp?.contextvalue?.humidity;
    thp_pressure = firstThp?.contextvalue?.pressure;
    // console.log("Parsed THP:", { thp_temp, thp_humidity, thp_pressure });

    return (
        <div className="">
            {/* <div className="*:data-[slot=card]:from-primary/5 *:data-[slot=card]:to-card dark:*:data-[slot=card]:bg-card grid grid-cols-1 gap-4 px-4 *:data-[slot=card]:bg-gradient-to-t *:data-[slot=card]:shadow-xs lg:px-6 @xl/main:grid-cols-2 @5xl/main:grid-cols-4"> */}

            {databaseLayer === "edge" ? (
                <EdgeCards
                    soilCondition={soil_condition}
                    intruderCount={intruderCount}
                    doorEventCount={doorEventCount}
                    thpTemp={thp_temp}
                    thpHumidity={thp_humidity}
                    thpPressure={thp_pressure}
                />
            ) : (
                <CloudCards
                    soilCondition={soil_condition}
                    intruderCount={intruderCount}
                    smokeEventCount={smokeEventCount}
                    doorEventCount={doorEventCount}
                    thpTemp={thp_temp}
                    thpHumidity={thp_humidity}
                    thpPressure={thp_pressure}
                />
            )}
        </div>
    );
}
