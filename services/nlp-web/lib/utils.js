import { clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs) {
    return twMerge(clsx(inputs));
}

export function parseTHPContext(ctx) {
    /**
     * Parse a THP context value which may be an object, JSON string, or
     * a custom key=value comma-separated string like
     * "{distance=null, ..., humidity=44, pressure=1013, temperature=23.4}"
     * Returns a normalized object with lower-cased keys and numeric values where possible.
     */
    if (!ctx) return {};
    if (typeof ctx === "object") return ctx;

    if (typeof ctx === "string") {
        const s = ctx.trim();
        try {
            if ((s.startsWith("{") && s.includes(":")) || s.startsWith("[")) {
                return JSON.parse(s);
            }
        } catch (e) {
            // fall through to custom parser
        }

        const out = {};
        const re = /([^=,\s\{\}]+)\s*=\s*([^,\}]+)/g;
        let m;
        while ((m = re.exec(s)) !== null) {
            const key = String(m[1]).trim().toLowerCase();
            let val = String(m[2]).trim();
            if (val === "null") {
                out[key] = null;
                continue;
            }
            val = val.replace(/[,}\]]+$/g, "");
            if (/^-?\d+(?:\.\d+)?$/.test(val)) {
                out[key] = Number(val);
            } else {
                out[key] = val;
            }
        }
        return out;
    }

    return {};
}
