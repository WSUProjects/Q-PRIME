// Chat queries are answered by the Q-PRIME AI/NLP service. That service
// generates SQL and delegates reads to the user's configured query API.

const LLM_API = (process.env.LLM_API || "http://qprime-nlp:5500").replace(
    /\/$/,
    ""
);

export async function POST(req) {
    try {
        const { input, queryType, dataScope, isCloudLayer } = await req.json();

        if (!input || input.trim() === "") {
            return Response.json(
                { error: "Query input is empty" },
                { status: 400 }
            );
        }

        if (queryType !== "sql" && queryType !== "natural") {
            return Response.json({ error: "Invalid query type" }, { status: 400 });
        }

        // "continuum" (default) | "edge" | "cloud"; isCloudLayer is kept for
        // compatibility with the original deployment's payload.
        const scope = dataScope ?? isCloudLayer ?? "continuum";

        const response = await fetch(`${LLM_API}/api/query`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                query: input,
                type: queryType,
                scope,
                isCloud: scope,
            }),
        });

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            return Response.json(
                {
                    error:
                        errorData?.status?.message ||
                        errorData.message ||
                        `Assistant service error! status: ${response.status}`,
                },
                { status: response.status }
            );
        }

        return Response.json(await response.json(), { status: 200 });
    } catch (error) {
        console.error("Assistant error:", error);
        return Response.json({ error: error.message }, { status: 500 });
    }
}
