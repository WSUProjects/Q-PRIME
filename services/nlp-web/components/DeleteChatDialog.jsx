"use client";

import React from "react";

import {
    AlertDialog,
    AlertDialogAction,
    AlertDialogCancel,
    AlertDialogContent,
    AlertDialogDescription,
    AlertDialogFooter,
    AlertDialogHeader,
    AlertDialogTitle,
} from "@/components/ui/alert-dialog";

const DeleteChatDialog = ({
    open,
    onCancel,
    onConfirm,
    title = "Delete Chat",
    description = "Are you sure you want to delete this chat?",
}) => {
    const handleOpenChange = (isOpen) => {
        if (!isOpen && typeof onCancel === "function") onCancel();
    };

    const handleConfirm = () => {
        if (typeof onConfirm === "function") onConfirm();
    };

    return (
        <AlertDialog open={open} onOpenChange={handleOpenChange}>
            <AlertDialogContent>
                <AlertDialogHeader>
                    <AlertDialogTitle>{title}</AlertDialogTitle>
                    <AlertDialogDescription>
                        {description}
                    </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                    <AlertDialogCancel className="hover:bg-gray-100 hover:cursor-pointer">
                        Cancel
                    </AlertDialogCancel>
                    <AlertDialogAction
                        onClick={handleConfirm}
                        className="text-white hover:cursor-pointer "
                    >
                        Delete
                    </AlertDialogAction>
                </AlertDialogFooter>
            </AlertDialogContent>
        </AlertDialog>
    );
};

export default DeleteChatDialog;
