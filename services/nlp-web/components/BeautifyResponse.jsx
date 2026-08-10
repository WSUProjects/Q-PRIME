"use client";

import React from "react";

function splitTryAlso(text) {
    const split = text.split(/^\s*try also:\s*/im);
    return {
        summaryRaw: split[0] ? split[0].trim() : "",
        suggestionsRaw: split[1] ? split[1].trim() : "",
    };
}

export default function BeautifyResponse({ text }) {
    if (!text) return null;

    const { summaryRaw: rawSummaryInitial, suggestionsRaw } =
        splitTryAlso(text);

    // Remove leading "Summary" text if present
    const summaryRaw = rawSummaryInitial.replace(/^\s*summary\s*\n?/i, "");

    // only extract teh first summaryLine
    const firstLineEnd = summaryRaw.indexOf("\n");
    const summaryRawFinal =
        firstLineEnd !== -1
            ? summaryRaw.slice(0, firstLineEnd).trim()
            : summaryRaw.trim();
    // console.log("BeautifyResponse summaryRaw:", summaryRawFinal);

    // Build paragraphs from the summary (preserve blank lines)
    const paras = summaryRaw
        .split(/\n{2,}/)
        .map((p) => p.trim())
        .filter(Boolean)
        .map((p, i) => (
            <p
                key={i}
                className="mb-2"
                dangerouslySetInnerHTML={{ __html: p.replace(/\n/g, "<br/>") }}
            />
        ));

    // Extract suggestion lines
    let suggestionLines = suggestionsRaw
        .split(/\r?\n/)
        .map((s) => s.trim())
        .filter(Boolean);

    if (suggestionLines.length <= 1 && /-\s+/.test(suggestionsRaw)) {
        suggestionLines = suggestionsRaw
            .split(/\s+-\s+/)
            .slice(1)
            .map((s) => s.trim());
    }

    const deviceLabel = /misty/i.test(summaryRaw) ? "Misty" : "device";
    const normalizedSuggestions = suggestionLines.map((s) =>
        s.replace(/\bdevice\b/gi, deviceLabel).replace(/^[-•]\s*/, "")
    );

    return (
        <div>
            <h3 className="text-lg font-semibold">Summary</h3>
            <div className="mt-2 text-[15px] leading-relaxed">{summaryRawFinal}</div>

            {/* {normalizedSuggestions.length > 0 && (
                <div>
                    <hr className="my-3" />
                    <h3 className="text-base font-semibold">Try:</h3>
                    <ul className="mt-2 space-y-1">
                        {normalizedSuggestions.map((s, i) => (
                            <li key={i}>{s}</li>
                        ))}
                    </ul>
                </div>
            )} */}
        </div>
    );
}
