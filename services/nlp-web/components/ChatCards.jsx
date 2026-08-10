import React from "react";
import { Clock, Wifi, Camera, DoorOpen, User, Compass } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

// Helper: format timestamp (seconds or ms)
const formatTimestamp = (timestamp) => {
    if (!timestamp) return "N/A";
    const ts =
        String(timestamp).length > 10
            ? parseInt(timestamp)
            : parseInt(timestamp) * 1000;
    const date = new Date(ts);
    return date.toLocaleString();
};

// Helper: get device icon
const getDeviceIcon = (deviceName) => {
    if (deviceName?.toLowerCase().includes("door"))
        return <DoorOpen className="w-4 h-4" />;
    if (deviceName?.toLowerCase().includes("robot"))
        return <Camera className="w-4 h-4" />;
    return <Wifi className="w-4 h-4" />;
};

// Helper: get event badge variant
const getEventBadgeVariant = (event) => {
    if (event === "intruder_detected" || event === "intruder")
        return "destructive";
    if (event === "familiar_face") return "primary";
    if (event) return "default";
    return "secondary";
};

// Main component
const IoTDataVisualization = ({ sensorData, sensorDataHeader }) => {
    // console.log("Rendering IoTDataVisualization with data:", {
    //     sensorData,
    //     sensorDataHeader,
    // });
    // Handle sensorData as [[row1, row2, ...]]
    let rows = [];
    if (
        Array.isArray(sensorData) &&
        Array.isArray(sensorDataHeader) &&
        sensorData.length === 1 &&
        Array.isArray(sensorData[0]) &&
        Array.isArray(sensorData[0][0]) &&
        sensorData[0][0].length === sensorDataHeader.length
    ) {
        // sensorData = [ [ [row1], [row2], ... ] ]
        rows = sensorData[0].map((rowArr) => {
            const rowObj = {};
            for (let j = 0; j < sensorDataHeader.length; j++) {
                rowObj[sensorDataHeader[j]] = rowArr[j];
            }
            return rowObj;
        });
    } else if (
        Array.isArray(sensorData) &&
        Array.isArray(sensorDataHeader) &&
        sensorData.length > 0 &&
        Array.isArray(sensorData[0]) &&
        sensorData[0].length === sensorDataHeader.length
    ) {
        // sensorData = [ [row1], [row2], ... ]
        rows = sensorData.map((rowArr) => {
            const rowObj = {};
            for (let j = 0; j < sensorDataHeader.length; j++) {
                rowObj[sensorDataHeader[j]] = rowArr[j];
            }
            return rowObj;
        });
    } else if (
        Array.isArray(sensorData) &&
        Array.isArray(sensorDataHeader) &&
        sensorData.length % sensorDataHeader.length === 0
    ) {
        // fallback: flat array
        for (let i = 0; i < sensorData.length; i += sensorDataHeader.length) {
            const row = {};
            for (let j = 0; j < sensorDataHeader.length; j++) {
                row[sensorDataHeader[j]] = sensorData[i + j];
            }
            rows.push(row);
        }
    } else if (Array.isArray(sensorData)) {
        // fallback: try to parse as string objects (legacy)
        rows = sensorData
            .map((dataString) => {
                if (
                    typeof dataString === "string" &&
                    dataString.startsWith("{")
                ) {
                    try {
                        const content = dataString.slice(1, -1);
                        const pairs = content.split(", ");
                        const obj = {};
                        pairs.forEach((pair) => {
                            const [key, ...valueParts] = pair.split("=");
                            const value = valueParts.join("=");
                            obj[key] = value === "null" ? null : value;
                        });
                        return obj;
                    } catch {
                        return null;
                    }
                }
                return null;
            })
            .filter(Boolean);
    }

    if (!rows.length) {
        return (
            <div className="text-gray-400 text-sm">
                No sensor data available.
            </div>
        );
    }

    // Reverse rows so earliest event is 1, latest is last
    const orderedRows = [...rows].reverse();

    const [showMeta, setShowMeta] = React.useState({});

    const handleToggleMeta = (idx) => {
        setShowMeta((prev) => ({ ...prev, [idx]: !prev[idx] }));
    };

    return (
        <div className="p-2 rounded">
            <div className="flex flex-col items-center w-full">
                <div className="w-full grid grid-cols-1 sm:grid-cols-2 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
                    {orderedRows.map((data, index) => (
                        <div
                            key={index}
                            className="relative flex flex-col items-stretch"
                        >
                            {/* Sequence badge */}
                            <span className="absolute -top-3 left-2 z-10 bg-emerald-500 text-white text-xs font-bold rounded-full w-6 h-6 flex items-center justify-center shadow-md">
                                {index + 1}
                            </span>
                            <Card className="w-full p-2 shadow-none">
                                <CardHeader className=" pt-2 px-2">
                                    <div className="flex items-center justify-between">
                                        <CardTitle className="flex items-center gap-2 text-sm font-semibold">
                                            {getDeviceIcon(data.device_name)}
                                            {data.device_name ||
                                                "Unknown Device"}
                                        </CardTitle>
                                        <Badge
                                            className={`px-1 text-clip ${getEventBadgeVariant(data.event) === "primary" ? "bg-blue-500 text-white dark:bg-blue-600" : ""}`}
                                            variant={getEventBadgeVariant(
                                                data.event
                                            )}
                                        >
                                            {data.event || "Door opened"}
                                        </Badge>
                                    </div>
                                </CardHeader>
                                <CardContent className="space-y-1 px-2 pb-2">
                                    <div className="flex items-center gap-2 text-xs text-gray-600">
                                        <Clock className="w-3 h-3" />
                                        <span>
                                            {formatTimestamp(data.timestamp)}
                                        </span>
                                    </div>
                                    {/* <div className="flex flex-wrap gap-x-2 gap-y-1 text-xs mt-1">
                                        <span className="font-medium">ID:</span>
                                        <span className="font-mono bg-gray-100 px-1 rounded text-xs">
                                            {data.device_id || "N/A"}
                                        </span>
                                    </div> */}
                                    {/* Metadata toggle */}
                                    <button
                                        className="text-xs underline mt-1 focus:outline-none hover:cursor-pointer"
                                        onClick={() => handleToggleMeta(index)}
                                        type="button"
                                    >
                                        metadata
                                    </button>
                                    {(data.gateway_id ||
                                        data.person ||
                                        data.yaw ||
                                        data.pitch ||
                                        data.distance) && (
                                        <>
                                            {showMeta[index] && (
                                                <>
                                                    <div className="flex flex-wrap gap-x-2 gap-y-1 text-xs mt-1">
                                                        <span className="font-medium">
                                                            ID:
                                                        </span>
                                                        <span className="font-mono bg-gray-100 px-1 rounded text-xs">
                                                            {data.device_id ||
                                                                "N/A"}
                                                        </span>
                                                    </div>
                                                    {data.gateway_id && (
                                                        <p className="text-xs">
                                                            <span className="font-medium">
                                                                Gateway ID:
                                                            </span>{" "}
                                                            <span className="text-clip">
                                                                {
                                                                    data.gateway_id
                                                                }
                                                            </span>
                                                        </p>
                                                    )}

                                                    <div className="flex flex-wrap gap-x-1 gap-y-1 text-xs rounded">
                                                        {data.person && (
                                                            <>
                                                                <span className="font-medium">
                                                                    Person:
                                                                </span>{" "}
                                                                <span>
                                                                    {
                                                                        data.person
                                                                    }
                                                                </span>
                                                            </>
                                                        )}
                                                        {data.distance && (
                                                            <>
                                                                <span className="font-medium">
                                                                    Distance:
                                                                </span>{" "}
                                                                <span>
                                                                    {
                                                                        data.distance
                                                                    }
                                                                    cm
                                                                </span>
                                                            </>
                                                        )}
                                                        {data.yaw && (
                                                            <>
                                                                <span className="font-medium">
                                                                    Yaw:
                                                                </span>{" "}
                                                                <span>
                                                                    {data.yaw}°
                                                                </span>
                                                            </>
                                                        )}
                                                        {data.pitch && (
                                                            <>
                                                                <span className="font-medium">
                                                                    Pitch:
                                                                </span>{" "}
                                                                <span>
                                                                    {data.pitch}
                                                                    °
                                                                </span>
                                                            </>
                                                        )}
                                                    </div>
                                                </>
                                            )}
                                        </>
                                    )}
                                </CardContent>
                            </Card>
                        </div>
                    ))}
                </div>
                {/* If less than 4 cards, fill empty columns for grid alignment */}
                {orderedRows.length < 4 && (
                    <div
                        className={`hidden lg:grid grid-cols-${4 - orderedRows.length} gap-4`}
                    ></div>
                )}
            </div>
        </div>
    );
};

export default IoTDataVisualization;
