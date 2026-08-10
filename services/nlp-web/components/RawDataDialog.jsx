"use client";

import React from "react";
import {
    AlertDialog,
    AlertDialogAction,
    AlertDialogContent,
    AlertDialogDescription,
    AlertDialogFooter,
    AlertDialogHeader,
    AlertDialogTitle,
} from "@/components/ui/alert-dialog";

export default function RawDataDialog({
    open,
    data,
    onOpenChange,
    title = "Raw Data",
}) {
    const handleOpenChange = (val) => {
        if (onOpenChange) onOpenChange(val);
    };

    return (
        <AlertDialog open={!!open} onOpenChange={handleOpenChange}>
            <AlertDialogContent>
                <AlertDialogHeader>
                    <AlertDialogTitle>{title}</AlertDialogTitle>
                    <AlertDialogDescription>
                        Raw JSON Output
                    </AlertDialogDescription>
                </AlertDialogHeader>
                <div
                    style={{
                        maxHeight: "60vh",
                        overflow: "auto",
                        paddingTop: 8,
                    }}
                >
                    <pre
                        style={{
                            whiteSpace: "pre-wrap",
                            wordBreak: "break-word",
                            fontFamily:
                                "ui-monospace, SFMono-Regular, Menlo, Monaco, 'Roboto Mono', 'Courier New', monospace",
                            fontSize: 12,
                            margin: 0,
                        }}
                    >
                        {JSON.stringify(data, null, 2)}
                    </pre>
                </div>
                <AlertDialogFooter>
                    <AlertDialogAction
                        className="hover:cursor-pointer"
                        onClick={() => handleOpenChange(false)}
                    >
                        Close
                    </AlertDialogAction>
                </AlertDialogFooter>
            </AlertDialogContent>
        </AlertDialog>
    );
}
