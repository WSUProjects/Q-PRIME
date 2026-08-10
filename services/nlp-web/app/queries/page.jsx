"use client";

import { useState, useMemo, useRef, useEffect } from "react";

import { exampleQueryTypes } from "@/constants/data.js";

import ChatInput from "@/components/ChatInput.jsx";
import { ChatHeader } from "@/components/ChatHeader";
import { QuerySidebar } from "@/components/QuerySidebar";
import QueryInterface from "@/components/QueryInterface";
import ApiErrorDialog from "@/components/ApiErrorDialog.jsx";
import IoTDataVisualization from "@/components/ChatCards";
import TemperatureLineChart from "@/components/TemperatureLineChart";
import TemporalChart from "@/components/TemporalChart";
import DeleteChatDialog from "@/components/DeleteChatDialog.jsx";
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";
import RawDataDialog from "@/components/RawDataDialog";
import BeautifyResponse from "@/components/BeautifyResponse";
import { DEFAULT_SCOPE } from "@/lib/sql";

import { withBasePath } from "@/lib/basePath";

// Persistence chat history
const STORAGE_KEY = "queriesPage.v1";
const defaultState = { chats: [], activeChatId: null };

function loadState() {
    try {
        const raw = localStorage.getItem(STORAGE_KEY);
        if (!raw) return defaultState;
        const parsed = JSON.parse(raw);
        if (!parsed || !Array.isArray(parsed.chats)) return defaultState;
        return {
            chats: parsed.chats,
            activeChatId: parsed.activeChatId ?? null,
        };
    } catch {
        return defaultState;
    }
}

function saveState(state) {
    try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    } catch {}
}

export default function QueriesPage() {
    // Chat state
    const [sensorData, setSensorData] = useState();
    const [sensorDataHeader, setSensorDataHeader] = useState();
    const [chats, setChats] = useState([]);
    const [activeChatId, setActiveChatId] = useState(null);
    // combined external data, unless the user filters to one tier
    const [dataScope, setDataScope] = useState(DEFAULT_SCOPE);
    // natural language is the default; SQL is for people who want it
    const [queryType, setQueryType] = useState("natural");

    // Delete modal state
    const [deleteModalOpen, setDeleteModalOpen] = useState(false);
    const [chatToDelete, setChatToDelete] = useState(null);
    const [apiError, setApiError] = useState(null);
    // Headers visibility per-history-entry
    const [metaOpen, setMetaOpen] = useState({});
    const [chartOpen, setChartOpen] = useState({});
    const [sqlOpen, setSqlOpen] = useState({});

    const [rawDialogOpen, setRawDialogOpen] = useState(false);
    const [rawDialogData, setRawDialogData] = useState(null);

    const toggleMeta = (i) =>
        setMetaOpen((prev) => ({ ...prev, [i]: !prev?.[i] }));
    const toggleChart = (i) =>
        setChartOpen((prev) => ({ ...prev, [i]: !prev?.[i] }));
    const toggleSql = (i) =>
        setSqlOpen((prev) => ({ ...prev, [i]: !prev?.[i] }));

    // Focusing input automatically
    const inputRef = useRef(null);

    // Load once on mount
    const hasLoadedRef = useRef(false);
    useEffect(() => {
        if (hasLoadedRef.current) return;
        hasLoadedRef.current = true;

        const { chats, activeChatId } = loadState();
        setChats(chats);
        // If nothing saved, keep null
        setActiveChatId(activeChatId ?? chats[0]?.id ?? null);
    }, []);

    // Save on change
    useEffect(() => {
        if (!hasLoadedRef.current) return; // avoid saving the empty initial state
        saveState({ chats, activeChatId });
    }, [chats, activeChatId]);

    // Auto-focus input whenever active chat changes
    useEffect(() => {
        inputRef.current?.focus();
    }, [activeChatId]);

    // Get the active chat object
    const activeChat = useMemo(
        () => chats.find((c) => c.id === activeChatId),
        [chats, activeChatId]
    );

    // Create new chat
    const handleNewChat = () => {
        const newChat = {
            id: Date.now().toString(),
            title: `Chat ${chats.length + 1}`,
            history: [],
        };
        setChats((prev) => [...prev, newChat]);
        setActiveChatId(newChat.id);
    };

    // Select chat
    const handleSelectChat = (chatId) => setActiveChatId(chatId);

    // Confirm delete
    const confirmDeleteChat = (chatId) => {
        console.log("Confirm delete clicked for chat:", chatId);
        setChatToDelete(chatId);
        setDeleteModalOpen(true);
    };

    // Perform delete
    const handleDeleteChat = () => {
        if (!chatToDelete) return;

        setChats((prev) => {
            const remaining = prev.filter((c) => c.id !== chatToDelete);

            // Switch active chat if current is deleted
            const nextActive =
                activeChatId === chatToDelete
                    ? remaining.length > 0
                        ? remaining[remaining.length - 1].id
                        : null
                    : activeChatId;

            setActiveChatId(nextActive);
            return remaining;
        });

        setDeleteModalOpen(false);
        setChatToDelete(null);
    };

    const handleCancelDelete = () => {
        console.log("Delete dialog cancelled");
        setDeleteModalOpen(false);
        setChatToDelete(null);
    };

    // Handle user query
    const handleQuery = async (queryData) => {
        // console.log("=== QueriesPage received from QueryInterface ===");
        // console.log("Full queryData object:", queryData);
        // console.log("Query text:", queryData.query);
        // console.log("Query Type:", queryData.queryType);
        // console.log("Data scope:", queryData.dataScope);
        // console.log("Current local queryType state:", queryType);
        // console.log("=================================================");

        // Keep backward compatibility
        const input =
            typeof queryData === "string" ? queryData : queryData.query;
        const chosenQueryType =
            typeof queryData === "object" && queryData?.queryType
                ? queryData.queryType
                : queryType;
        const chosenScope =
            typeof queryData === "object" && queryData?.dataScope !== undefined
                ? queryData.dataScope
                : dataScope;

        let targetId = activeChatId;

        // Create first chat if none exists
        if (!targetId) {
            targetId = Date.now().toString();
            const newChat = {
                id: targetId,
                title: `Chat ${chats.length + 1}`,
                history: [],
            };
            setChats((prev) => [...prev, newChat]);
            setActiveChatId(targetId);
        }

        // Ask the assistant (services/nlp) via the API route
        let data;
        try {
            const res = await fetch(withBasePath("/api/query"), {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    input,
                    queryType: chosenQueryType,
                    dataScope: chosenScope,
                }),
            });

            // Attempt to parse JSON (may throw)
            data = await res.json();

            // Handle HTTP-level errors or an error payload
            if (!res.ok || data?.error) {
                const msg =
                    data?.error || `HTTP ${res.status} ${res.statusText}`;
                // console.error("API Error:", msg);
                setApiError(msg);
                return;
            }
        } catch (err) {
            console.error("Network/Fetch error:", err);
            setApiError(err?.message || String(err));
            return;
        }
        // new format
        // console.log("Which layer:", data["layer"]);

        // if length of data["sensor-data"]["data"] is 1, show just that object
        let chat_data, chat_headers;
        const rows =
            data["sensor-data"]?.["result"] ??
            data["sensor-data"]?.["results"] ??
            [];
        if (rows.length === 1) {
            chat_data = [rows[0]];
            chat_headers = [];
        } else {
            chat_data = rows;
            chat_headers = data["sensor-data"]?.["headers"] || [];
        }

        // Extract headers from the first object in the data array if available
        if (chat_data.length > 0 && chat_headers.length === 0) {
            chat_headers = Object.keys(chat_data[0]);
        }

        // setSensorData(data["sensor-data"]);
        // setSensorDataHeader(data["headers"]);
        console.log("Frontend Result:", data["sensor-data"]);  // check what it is before sending to chat history
        // console.log("Headers:", chat_headers);

        setSensorData(chat_data);
        setSensorDataHeader(chat_headers);

        // handle visual for specific layer
        const showSqlForEntry = chosenQueryType === "natural";
        const entrySql = showSqlForEntry ? data["sql-query"] || null : null;

        // Append query to the active chat, store headers too
        setChats((prevChats) =>
            prevChats.map((chat) =>
                chat.id === targetId
                    ? {
                          ...chat,
                          history: [
                              ...chat.history,
                              {
                                  input,
                                  //   result: data["data"],
                                  result: chat_data,
                                  headers: chat_headers,
                                  inferredResults:
                                      data["inferred-results"]?.["text"] ??
                                      data["inferred-results"],
                                  edgeCount: data["edge-count"] ?? 0,
                                  cloudCount: data["cloud-count"] ?? 0,
                                  scope: data["scope"] ?? chosenScope,
                                  sqlQuery: entrySql,
                                  queryType: chosenQueryType,
                              },
                          ],
                      }
                    : chat
            )
        );
    };

    const handleCloseApiError = () => setApiError(null);

    return (
        <SidebarProvider
            style={{
                "--sidebar-width": "calc(var(--spacing) * 72)",
                "--header-height": "calc(var(--spacing) * 12)",
            }}
        >
            {/* Sidebar */}
            <QuerySidebar
                chats={chats}
                activeChatId={activeChatId}
                onNewChat={handleNewChat}
                onSelectChat={handleSelectChat}
                onDeleteChat={confirmDeleteChat}
                setChats={setChats}
            />

            {/* Main chat area */}
            <SidebarInset>
                {/* Header */}
                <div className="sticky top-0 z-10 bg-white border-b">
                    <ChatHeader
                        title={activeChat?.title}
                        hideCloseButton={!activeChatId}
                        onClose={() => setActiveChatId(null)}
                    />
                </div>

                {/* Main Content */}
                {activeChatId ? (
                    <>
                        {/* Chat Messages History */}
                        <div className="flex-1 overflow-y-auto">
                            <div className="p-4">
                                {activeChat?.history.length > 0 &&
                                    activeChat.history.map((entry, idx) => {
                                        const canShowChart =
                                            Array.isArray(entry.result) &&
                                            entry.result.length > 1 &&
                                            entry.result[0] &&
                                            (entry.result[0].timestamp ||
                                                entry.result[0].ts ||
                                                entry.result[0].time ||
                                                entry.result[0].date);
                                        const chartRows = canShowChart
                                            ? entry.result.map((r) => ({
                                                  ...r,
                                                  ts:
                                                      r.ts ??
                                                      r.timestamp ??
                                                      r.time ??
                                                      r.date,
                                              }))
                                            : [];
                                        const chartExpanded =
                                            chartOpen[idx] !== false;
                                        const allowSqlToggle =
                                            entry.queryType === "natural" &&
                                            entry.sqlQuery;
                                        const sqlExpanded = !!sqlOpen[idx];
                                        return (
                                            <div key={idx} className="mb-6">
                                                <div className="mb-2 text-right">
                                                    <span className="inline-block px-3 py-1 bg-gray-50 border border-gray-200 rounded shadow-sm text-sm">
                                                        <strong className="text-gray-500 font-normal">
                                                            Your query:
                                                        </strong>{" "}
                                                        {entry.input}
                                                    </span>
                                                </div>
                                                <div className="">
                                                    {/* <p className="rounded-lg p-2">Summary:</p> */}
                                                    <div className="rounded-lg p-3 border border-gray-200 bg-white">
                                                        <BeautifyResponse
                                                            text={
                                                                entry.inferredResults
                                                            }
                                                        />
                                                    </div>
                                                    <div className="rounded-lg p-2">
                                                        <div
                                                            style={{
                                                                display: "flex",
                                                                justifyContent:
                                                                    "space-between",
                                                                alignItems:
                                                                    "center",
                                                            }}
                                                        >
                                                            <div
                                                                style={{
                                                                    display:
                                                                        "flex",
                                                                    gap: 12,
                                                                    alignItems:
                                                                        "center",
                                                                }}
                                                            >
                                                                {/* <div
                                                                    style={{
                                                                        fontSize: 12,
                                                                        color: "#2563eb",
                                                                        cursor: "pointer",
                                                                    }}
                                                                    onClick={() =>
                                                                        toggleMeta(
                                                                            idx
                                                                        )
                                                                    }
                                                                >
                                                                    {metaOpen[
                                                                        idx
                                                                    ]
                                                                        ? "Headers ▾"
                                                                        : "Headers ▸"}
                                                                </div> */}
                                                                {canShowChart ? (
                                                                    <div
                                                                        style={{
                                                                            fontSize: 12,
                                                                            color: "#2563eb",
                                                                            cursor: "pointer",
                                                                        }}
                                                                        onClick={() =>
                                                                            toggleChart(
                                                                                idx
                                                                            )
                                                                        }
                                                                    >
                                                                        {chartExpanded
                                                                            ? "Chart ▾"
                                                                            : "Chart ▸"}
                                                                    </div>
                                                                ) : null}
                                                                {allowSqlToggle ? (
                                                                    <div
                                                                        style={{
                                                                            fontSize: 12,
                                                                            color: "#2563eb",
                                                                            cursor: "pointer",
                                                                        }}
                                                                        onClick={() =>
                                                                            toggleSql(
                                                                                idx
                                                                            )
                                                                        }
                                                                    >
                                                                        {sqlExpanded
                                                                            ? "Converted SQL ▾"
                                                                            : "Converted SQL ▸"}
                                                                    </div>
                                                                ) : null}

                                                                <div
                                                                    style={{
                                                                        fontSize: 12,
                                                                        color: "#2563eb",
                                                                        cursor: "pointer",
                                                                    }}
                                                                    onClick={() => {
                                                                        setRawDialogData(
                                                                            entry.result ??
                                                                                entry
                                                                        );
                                                                        setRawDialogOpen(
                                                                            true
                                                                        );
                                                                    }}
                                                                >
                                                                    View raw
                                                                    data
                                                                </div>
                                                            </div>
                                                        </div>
                                                        {/* {metaOpen[idx] ? (
                                                            <div
                                                                style={{
                                                                    marginTop: 8,
                                                                }}
                                                            >
                                                                <div
                                                                    style={{
                                                                        fontSize: 12,
                                                                        color: "#374151",
                                                                    }}
                                                                >
                                                                    Headers:{" "}
                                                                    {JSON.stringify(
                                                                        entry.headers
                                                                    )}
                                                                </div>
                                                            </div>
                                                        ) : null} */}
                                                        {allowSqlToggle &&
                                                        sqlExpanded ? (
                                                            <div
                                                                style={{
                                                                    marginTop: 12,
                                                                    fontSize: 12,
                                                                    color: "#1f2937",
                                                                    background:
                                                                        "#f9fafb",
                                                                    border: "1px solid #e5e7eb",
                                                                    borderRadius: 6,
                                                                    padding: 12,
                                                                    whiteSpace:
                                                                        "pre-wrap",
                                                                    fontFamily:
                                                                        "ui-monospace, SFMono-Regular, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace",
                                                                }}
                                                            >
                                                                {entry.sqlQuery}
                                                            </div>
                                                        ) : null}

                                                        {/* visual: if rows have timestamp, show temporal chart */}
                                                        {canShowChart &&
                                                        chartExpanded ? (
                                                            <div
                                                                style={{
                                                                    marginTop: 12,
                                                                }}
                                                            >
                                                                <TemporalChart
                                                                    rows={
                                                                        chartRows
                                                                    }
                                                                    bin="minute"
                                                                    title="Events over time"
                                                                />
                                                            </div>
                                                        ) : null}
                                                    </div>
                                                </div>
                                            </div>
                                        );
                                    })}
                            </div>
                        </div>

                        {/* Query Input */}
                        <div className="sticky bottom-0 z-10">
                            <ChatInput
                                ref={inputRef}
                                onQuery={handleQuery}
                                className="border-none rounded-none shadow-none"
                                dataScope={dataScope}
                                setDataScope={setDataScope}
                                queryType={queryType}
                                setQueryType={setQueryType}
                            />
                        </div>
                    </>
                ) : (
                    // Initial page (no chat is selected)

                    <QueryInterface
                        ref={inputRef}
                        onQuery={handleQuery}
                        exampleQueryTypes={exampleQueryTypes}
                        dataScope={dataScope}
                        setDataScope={setDataScope}
                        queryType={queryType}
                        setQueryType={setQueryType}
                    />
                )}
            </SidebarInset>

            {/* Delete Chat Dialog */}
            <DeleteChatDialog
                open={deleteModalOpen}
                onCancel={handleCancelDelete}
                onConfirm={handleDeleteChat}
            />

            {/* API Error Dialog */}
            <ApiErrorDialog error={apiError} onClose={handleCloseApiError} />
            {/* Raw data dialog (opened when user clicks View raw) */}
            <RawDataDialog
                open={rawDialogOpen}
                data={rawDialogData}
                onOpenChange={(v) => setRawDialogOpen(!!v)}
            />
        </SidebarProvider>
    );
}
