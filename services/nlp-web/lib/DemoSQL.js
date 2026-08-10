export const sqlData = [
    {
        sql1: "SELECT * FROM iot_edge_x_sensors_data WHERE device_name IN ('Door Sensor', 'Misty Robot 1') AND FROM_UNIXTIME(timestamp) >= TIMESTAMP '2025-09-03 00:00:00' AND FROM_UNIXTIME(timestamp) < TIMESTAMP '2025-09-03 01:00:00';",
    },
    {
        sql2: "SELECT * FROM iot_edge_x_sensors_data WHERE device_name = 'Temperature Sensor 1' AND date_format(from_unixtime(timestamp), '%Y-%m-%d') = date_format(current_date, '%Y-%m-%d');",
    },
    {
        sql3: "SELECT * FROM iot_edge_x_sensors_data WHERE device_name = 'Temperature Sensor 1' AND FROM_UNIXTIME(timestamp) >= TIMESTAMP '2025-09-04 01:00:01' AND FROM_UNIXTIME(timestamp) < TIMESTAMP '2025-09-04 23:00:00';",
    },
];

const edgeSQL = [
    {
        edge1: "SELECT * FROM soil_streams WHERE sensor = 'soil moisturizer' AND to_timestamp(timestamp) >= NOW() - INTERVAL '2000' hour AND to_timestamp(timestamp) < NOW() ORDER BY timestamp DESC;",
    },
    {
        edge2: "SELECT COUNT(*) as intruders FROM misty_streams WHERE event = 'intruder_detected' AND to_timestamp(timestamp) >= NOW() - INTERVAL '24' hour AND to_timestamp(timestamp) < NOW();",
    },
    {
        edge3: "SELECT COUNT(*) FROM drone_streams WHERE to_timestamp(timestamp) >= NOW() - INTERVAL '1010 hour';",
    },
];
