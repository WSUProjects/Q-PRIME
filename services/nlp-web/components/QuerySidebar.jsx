"use client";

import { useState } from "react";
import { IconTrash } from "@tabler/icons-react";
import {
    Sidebar,
    SidebarHeader,
    SidebarContent,
    SidebarMenu,
    SidebarMenuItem,
    SidebarMenuButton,
} from "@/components/ui/sidebar";
import { NavMain } from "@/components/NavMain";

const data = {
    navMain: [{ title: "Dashboard", url: "/" }],
};

export function QuerySidebar({
    chats,
    activeChatId,
    onNewChat,
    onSelectChat,
    onDeleteChat,
    setChats,
    ...props
}) {
    const [editingChatId, setEditingChatId] = useState(null);
    const [editTitle, setEditTitle] = useState("");

    const startEditing = (chatId, currentTitle) => {
        setEditingChatId(chatId);
        setEditTitle(currentTitle);
    };

    const saveEdit = (chatId) => {
        if (!editTitle.trim()) return;
        setChats((prev) =>
            prev.map((chat) =>
                chat.id === chatId ? { ...chat, title: editTitle } : chat
            )
        );
        setEditingChatId(null);
        setEditTitle("");
    };

    return (
        <Sidebar collapsible="offcanvas" {...props}>
            <SidebarHeader>
                <div className="pl-2 font-bold text-lg">IoT Chatbot</div>
            </SidebarHeader>

            <SidebarContent>
                {/* Static navigation (includes New Chat button) */}
                <NavMain items={data.navMain} onNewChat={onNewChat} />

                {/* Chat list */}
                <SidebarMenu className="mt-4 pl-2">
                    {chats.map((chat) => (
                        <SidebarMenuItem key={chat.id}>
                            <div className="flex items-center justify-between w-full">
                                {editingChatId === chat.id ? (
                                    <input
                                        autoFocus
                                        value={editTitle}
                                        onChange={(e) =>
                                            setEditTitle(e.target.value)
                                        }
                                        onBlur={() => saveEdit(chat.id)}
                                        onKeyDown={(e) =>
                                            e.key === "Enter" &&
                                            saveEdit(chat.id)
                                        }
                                        className="flex-1 px-2 py-1 border rounded"
                                    />
                                ) : (
                                    <SidebarMenuButton
                                        onClick={() => onSelectChat(chat.id)}
                                        onDoubleClick={() =>
                                            startEditing(chat.id, chat.title)
                                        }
                                        className={`flex-1 text-left rounded hover:cursor-pointer ${
                                            chat.id === activeChatId
                                                ? "bg-primary font-bold text-white/90 hover:bg-primary/90 hover:text-white"
                                                : "hover:bg-primary/5"
                                        }`}
                                    >
                                        {chat.title}
                                        {chat.history?.length > 0 && (
                                            <span
                                                className={`ml-2 text-xs hover:cursor-pointer ${
                                                    chat.id === activeChatId
                                                        ? "text-white"
                                                        : "hover:bg-primary/5"
                                                }`}
                                            >
                                                ({chat.history.length})
                                            </span>
                                        )}
                                    </SidebarMenuButton>
                                )}

                                <button
                                    onClick={() => onDeleteChat(chat.id)}
                                    className="ml-2 pr-2 text-gray-500 hover:text-primary hover:cursor-pointer"
                                    title="Delete"
                                >
                                    <IconTrash size={16} />
                                </button>
                            </div>
                        </SidebarMenuItem>
                    ))}
                </SidebarMenu>
            </SidebarContent>
        </Sidebar>
    );
}
