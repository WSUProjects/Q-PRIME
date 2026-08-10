"use client";

import React, { useEffect, useState } from "react";

import TopBar from "@/components/TopBar";
import CardsSection from "@/components/CardsSection";
import { SimpleSidebar } from "@/components/SimpleSidebar";
import TimeRangeSelector from "@/components/TimeRangeSelector";
import DataSourceSelector from "@/components/DataSourceSelector";
import SimpleTimelineChart from "@/components/SimpleTimelineChart";
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";

import { DEFAULT_SCOPE } from "@/lib/sql";
import { withBasePath } from "@/lib/basePath";

export default function Home() {
    // combined continuum data, unless the user filters to one tier
    const [databaseLayer, setDatabaseLayer] = useState(DEFAULT_SCOPE);
    const [dataSourceConfigured, setDataSourceConfigured] = useState(null);

    useEffect(() => {
        fetch(withBasePath("/api/data-source"), { cache: "no-store" })
            .then((response) => response.json())
            .then((payload) => setDataSourceConfigured(Boolean(payload.configured)))
            .catch(() => setDataSourceConfigured(false));
    }, []);

    // central time-range state
    const defaultHours = 1; // default: Last 1 hour
    const now = new Date();
    const [timeRange, setTimeRange] = useState({
        hours: defaultHours,
        label: `Last ${defaultHours} hour`,
        start: new Date(now.getTime() - defaultHours * 60 * 60 * 1000),
        end: now,
    });

    return (
        <SidebarProvider
            style={{
                "--sidebar-width": "calc(var(--spacing) * 72)",
                "--header-height": "calc(var(--spacing) * 12)",
            }}
            defaultOpen={false}
        >
            {/* Sidebar */}
            <SimpleSidebar
                databaseLayer={databaseLayer}
                setDatabaseLayer={setDatabaseLayer}
                timeRange={timeRange} // Added this
                setTimeRange={setTimeRange} // Added this
            />

            {/* Main content */}
            <SidebarInset>
                <div className="md:block flex-1">
                    <div className="p-6 space-y-4">
                        {/* Top Bar */}
                        <TopBar />

                        {dataSourceConfigured === false && (
                            <div className="rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-100">
                                Q-PRIME query service is unavailable. Check the core
                                service and QUERY_API_URL configuration.
                            </div>
                        )}

                        {/* Controls */}
                        <div className="md:hidden">
                            <DataSourceSelector
                                databaseLayer={databaseLayer}
                                setDatabaseLayer={setDatabaseLayer}
                            />
                            <TimeRangeSelector
                                timeRange={timeRange}
                                setTimeRange={setTimeRange}
                            />
                        </div>

                        <div className="space-y-6 hidden md:block">
                            <CardsSection databaseLayer={databaseLayer} />
                        </div>

                        {/* Chart Section */}
                        <SimpleTimelineChart
                            databaseLayer={databaseLayer}
                            timeRange={timeRange}
                        />
                    </div>
                </div>
            </SidebarInset>
        </SidebarProvider>
    );
}
