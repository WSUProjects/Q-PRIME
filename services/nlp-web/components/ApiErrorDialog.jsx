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

const ApiErrorDialog = ({ error, onClose, title = "API Error" }) => {
    const handleOpenChange = (open) => {
        if (!open && typeof onClose === "function") onClose();
    };
    return (
        <AlertDialog open={!!error} onOpenChange={handleOpenChange}>
            <AlertDialogContent>
                <AlertDialogHeader>
                    <AlertDialogTitle className="text-red-600">
                        {title}
                    </AlertDialogTitle>
                    <AlertDialogDescription asChild>
                        <div className="whitespace-pre-wrap break-words text-left bg-gray-50 p-3 rounded border max-h-64 overflow-auto font-mono">
                            {error ? String(error) : ""}
                        </div>
                    </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                    <AlertDialogAction
                        onClick={onClose}
                        className="hover:cursor-pointer"
                    >
                        Close
                    </AlertDialogAction>
                </AlertDialogFooter>
            </AlertDialogContent>
        </AlertDialog>
    );
};

export default ApiErrorDialog;
