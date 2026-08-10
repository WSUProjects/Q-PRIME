import {
    Tooltip,
    TooltipContent,
    TooltipTrigger,
} from "@/components/ui/tooltip";

import { Separator } from "@/components/ui/separator";
import { SidebarTrigger } from "@/components/ui/sidebar";

export function ChatHeader({ title, hideCloseButton, onClose }) {
    return (
        <header className="flex h-(--header-height) shrink-0 items-center gap-2 border-b transition-[width,height] ease-linear group-has-data-[collapsible=icon]/sidebar-wrapper:h-(--header-height)">
            <div className="flex w-full items-center gap-1 px-4 lg:gap-2 lg:px-6">
                <SidebarTrigger className="-ml-2 hover:cursor-pointer" />
                <Separator
                    orientation="vertical"
                    className="mx-2 data-[orientation=vertical]:h-6"
                />
                <h1 className="text-base font-medium">{title}</h1>
                <div className="ml-auto flex items-center gap-2">
                    {!hideCloseButton && (
                        <Tooltip>
                            <TooltipTrigger
                                onClick={onClose}
                                className="hidden sm:flex hover:cursor-pointer"
                            >
                                Close
                            </TooltipTrigger>
                            <TooltipContent>
                                <p>Close chat</p>
                            </TooltipContent>
                        </Tooltip>
                    )}
                </div>
            </div>
        </header>
    );
}
