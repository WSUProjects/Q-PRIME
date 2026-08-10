/**
 * The logical table exposed by the Q-PRIME query API.
 * `NEXT_PUBLIC_SQL_TABLE_NAME` can override the default name.
 */
export const SQL_TABLE =
    process.env.NEXT_PUBLIC_SQL_TABLE_NAME || "qprime.continuum";

/** The combined external view is the default; the others are filters. */
export const DATA_SCOPES = [
    { value: "continuum", label: "Continuum (edge + cloud)", short: "Continuum" },
    { value: "edge", label: "Edge only", short: "Edge" },
    { value: "cloud", label: "Cloud only", short: "Cloud" },
];

export const DEFAULT_SCOPE = "continuum";

/**
 * A trailing-window predicate the storage layer can actually push down.
 *
 * `timestamp` is an indexed epoch-seconds bigint. Wrapping it in
 * `FROM_UNIXTIME(...)` — as these dashboards used to — hides the column behind a
 * function, so no bound reaches MongoDB and PrestoDB has to stream every
 * document in both collections through its own heap before discarding almost
 * all of them. With ten simulated sensors writing ten records a second that is
 * hundreds of thousands of documents per chart, which exhausted Presto's heap
 * and took the whole query engine down with it, leaving every card blank.
 *
 * Comparing the raw column against a folded bigint literal keeps the window
 * evaluated on the server clock while letting the connector answer it from the
 * `timestamp` index.
 */
export function timeWindowSql(hours, column = "timestamp") {
    const span = Math.max(1, Math.round(Number(hours) || 1));
    return (
        `${column} >= CAST(to_unixtime(now() - INTERVAL '${span}' HOUR) AS BIGINT) ` +
        `AND ${column} < CAST(to_unixtime(now()) AS BIGINT)`
    );
}

/** The same idea for "since local midnight". */
export function todayWindowSql(column = "timestamp") {
    return `${column} >= CAST(to_unixtime(date_trunc('day', now())) AS BIGINT)`;
}
