export async function GET() {
    return Response.json({
        configured: Boolean((process.env.QUERY_API_URL || "").trim()),
    });
}
