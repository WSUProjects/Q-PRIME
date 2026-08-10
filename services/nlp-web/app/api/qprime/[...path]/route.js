const QPRIME_API_URL = (process.env.QPRIME_API_URL || "http://qprime-analysis:5005").replace(/\/$/, "");

async function relay(request, context) {
    try {
        const { path = [] } = await context.params;
        const incoming = new URL(request.url);
        const target = new URL(`${QPRIME_API_URL}/api/${path.join("/")}`);
        target.search = incoming.search;
        const init = {
            method: request.method,
            cache: "no-store",
            headers: { "Content-Type": request.headers.get("content-type") || "application/json" },
        };
        if (!["GET", "HEAD"].includes(request.method)) init.body = await request.text();
        const response = await fetch(target, init);
        const text = await response.text();
        return new Response(text, {
            status: response.status,
            headers: { "Content-Type": response.headers.get("content-type") || "application/json" },
        });
    } catch (error) {
        return Response.json({ error: `Q-PRIME API unavailable: ${error.message}` }, { status: 502 });
    }
}

export const dynamic = "force-dynamic";
export const GET = relay;
export const POST = relay;
export const PUT = relay;
