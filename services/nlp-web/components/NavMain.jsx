"use client";

import React from "react";
import Link from "next/link";

import { IconCirclePlusFilled, IconDashboard } from "@tabler/icons-react";
import {
    SidebarGroup,
    SidebarGroupContent,
    SidebarMenu,
    SidebarMenuButton,
    SidebarMenuItem,
} from "@/components/ui/sidebar";

export function NavMain({ items, onNewChat }) {
    // Fallback icons if caller passed only titles (keeps visuals consistent)
    const iconMap = {
        Dashboard: IconDashboard,
    };

    return (
        <SidebarGroup>
            <SidebarGroupContent className="flex flex-col gap-2">
                {/* Static Nav Items */}
                <SidebarMenu>
                    {items.map((item) => {
                        const Icon = item.icon || iconMap[item.title] || null;
                        return (
                            <SidebarMenuItem key={item.title}>
                                <SidebarMenuButton
                                    tooltip={item.title}
                                    className="w-full px-2 py-2 rounded border-l-4 border-transparent hover:bg-gray-100 hover:border-primary/40 focus:outline-none focus:ring-2 focus:ring-primary/40"
                                >
                                    <Link
                                        href={item.url}
                                        className="flex items-center gap-2 w-full text-sm text-gray-900"
                                        aria-label={item.title}
                                    >
                                        {Icon && (
                                            <span className="text-primary">
                                                <Icon size={18} />
                                            </span>
                                        )}
                                        <span className="truncate">
                                            {item.title}
                                        </span>
                                    </Link>
                                </SidebarMenuButton>
                            </SidebarMenuItem>
                        );
                    })}
                </SidebarMenu>
                {/* New Chat Button */}
                <SidebarMenu>
                    <SidebarMenuItem>
                        <SidebarMenuButton
                            tooltip="Quick Create"
                            className="w-full px-2 py-2 rounded bg-gray-50 border-l-4 border-transparent hover:bg-gray-100 hover:border-primary/40 hover:cursor-pointer focus:outline-none focus:ring-2 focus:ring-primary/40"
                            onClick={onNewChat}
                        >
                            <div className="flex items-center gap-2 w-full text-sm text-gray-900">
                                <span className="text-primary">
                                    <IconCirclePlusFilled size={18} />
                                </span>
                                <span className="truncate">Open New Chat</span>
                            </div>
                        </SidebarMenuButton>
                    </SidebarMenuItem>
                </SidebarMenu>
            </SidebarGroupContent>
        </SidebarGroup>
    );
}
