import {
    Clock,
    Activity,
    Thermometer,
    Droplet,
    WindArrowDown,
    Heart,
    BarChart3,
} from "lucide-react";

export const timeRangeOptions = [
    { label: "Last 1 Hour", hours: 1 },
    { label: "Last 6 Hours", hours: 6 },
    { label: "Last 12 Hours", hours: 12 },
    { label: "Last 3 Days", hours: 72 },
    { label: "Last 5 Days", hours: 120 },
    { label: "Last 7 Days", hours: 168 },
];

export const refreshRates = [
    { label: "Every 5s", value: 5 },
    { label: "Every 30s", value: 30 },
    { label: "Every 1min", value: 60 },
    { label: "Every 5min", value: 300 },
    { label: "Every 15min", value: 900 },
    { label: "Hourly", value: 3600 },
];

export const quickActions = [
    {
        id: "temperature",
        label: "Temperature",
        timeRange: 24,
        sensorType: "temperature",
        tag: "Temperature Timeline",
        icon: Thermometer,
    },
    {
        id: "pressure",
        label: "Pressure",
        timeRange: 24,
        sensorType: "pressure",
        tag: "Pressure Timeline",
        icon: WindArrowDown,
    },
    {
        id: "humidity",
        label: "Humidity",
        timeRange: 24,
        sensorType: "humidity",
        tag: "Humidity Timeline",
        icon: Droplet,
    },
    {
        id: "moisture",
        label: "Soil Moisture",
        timeRange: 24,
        sensorType: "moisture",
        tag: "Soil Moisture Timeline",
        icon: Thermometer,
    },
    {
        id: "door",
        label: "Door Opens",
        timeRange: 24,
        sensorType: "door",
        tag: "Door Activity Timeline",
        icon: Activity,
    },
    {
        id: "smoke",
        label: "Smoke Detector",
        timeRange: 24,
        sensorType: "smoke",
        tag: "Smoke Detection Timeline",
        icon: Heart,
    },
    {
        id: "all-sensors",
        label: "All Sensors",
        timeRange: 24,
        sensorType: "all-sensors",
        tag: "All Sensors Timeline",
        icon: BarChart3,
    },
    // {
    //     id: "all-7d",
    //     label: "Weekly Overview",
    //     timeRange: 168,
    //     sensorType: "all",
    //     tag: "Weekly Overview",
    //     icon: Clock,
    // },
];

// SQL examples target the Q-PRIME continuum view: one table spanning the
// edge store and the cloud tier.
export const exampleQueryTypes = {
    sql_cloud: [
        "SELECT timestamp, resource.device_id, resource.device_name, contextvalue.temperature, contextvalue.humidity FROM qprime.continuum WHERE contextattribute = 'thp' ORDER BY timestamp DESC LIMIT 10;",
        "SELECT resource.device_name, COUNT(*) AS events FROM qprime.continuum WHERE FROM_UNIXTIME(timestamp) >= NOW() - INTERVAL '24' HOUR GROUP BY resource.device_name;",
    ],
    sql_edge: [
        "SELECT timestamp, resource.device_id, resource.device_name, contextattribute, contextvalue.event, storage_location FROM qprime.continuum ORDER BY timestamp DESC LIMIT 10;",
        "SELECT storage_location, COUNT(*) AS records FROM qprime.continuum GROUP BY storage_location;",
    ],
    natural: [
        "Show me the average temperature today",
        "How many door events today",
        "Show me the latest sensor activity",
    ],
};
