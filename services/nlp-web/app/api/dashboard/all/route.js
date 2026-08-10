// app/api/dashboard/all/route.js
// Read-only query delegated to the configured external endpoint.
import { queryContinuum } from "@/lib/continuum";

export async function POST(request) {
    return queryContinuum(request);
}
