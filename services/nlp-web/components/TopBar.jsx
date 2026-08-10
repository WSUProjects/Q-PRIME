"use client";

import Link from "next/link";
import Image from "next/image";
import React, { useState, useEffect } from "react";

import { refreshRates } from "@/constants/data";

import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { SidebarTrigger } from "@/components/ui/sidebar";

import { withBasePath } from "@/lib/basePath";

const TopBar = () => {
    const [refreshRate, setRefreshRate] = useState(30);
    const [now, setNow] = useState(new Date());

    useEffect(() => {
        const t = setInterval(() => setNow(new Date()), 1000);
        return () => clearInterval(t);
    }, []);

    const formatDateTime = (d) => {
        const dateStr = new Intl.DateTimeFormat(undefined, {
            weekday: "short",
            day: "2-digit",
            month: "short",
            year: "numeric",
        }).format(d);
        const timeStr = new Intl.DateTimeFormat(undefined, {
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit",
            hour12: false,
        }).format(d);
        return `${dateStr} • ${timeStr}`;
    };

    return (
        <div className="rounded-xl border shadow-sm bg-white/60 supports-[backdrop-filter]:bg-white/30 backdrop-blur p-2 md:p-4">
            <div className="grid grid-cols-1 md:grid-cols-3 items-center gap-3 md:gap-4">
                <div className="flex items-center gap-3">
                    <div className="w-10 h-10 flex items-center justify-center md:hidden">
                        <Image
                            src={withBasePath("/icon.png")}
                            alt="Lab Icon"
                            width={400}
                            height={400}
                        />
                    </div>
                    <div className="md:hidden">
                        <div className="font-medium text-sm leading-tight">
                            IoT Sensor Monitoring
                        </div>
                        <div className="font-medium text-sm leading-tight">
                            SDC Lab WSU
                        </div>
                    </div>
                    <div className="flex gap-2 ml-4 md:ml-0">
                        <SidebarTrigger className="hidden md:block hover:cursor-pointer py-2" />
                        <Button asChild className="md:hidden">
                            <Link href="/queries" className="font-semibold">
                                Queries
                            </Link>
                        </Button>
                        <Button asChild variant="outline" className="md:hidden">
                            <Link href="/qprime" className="font-semibold">
                                Q-PRIME Dashboard
                            </Link>
                        </Button>
                    </div>
                </div>

                {/* center: only date/time */}
                <div className="flex justify-center text-sm">
                    <span
                        className="inline-flex items-center gap-2 rounded-full border px-3 py-1 bg-white/70 supports-[backdrop-filter]:bg-white/40 backdrop-blur text-muted-foreground font-mono"
                        title={now.toString()}
                    >
                        <span
                            className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse"
                            aria-hidden
                        />
                        {formatDateTime(now)}
                    </span>
                </div>

                {/* right: refresh controls (centered on mobile, right-aligned on md+) */}
                <div className="flex items-center gap-2 md:gap-3 text-sm justify-center md:justify-end">
                    <Button asChild className="md:block hidden">
                        <Link href="/queries" className="font-semibold">
                            Queries
                        </Link>
                    </Button>
                    <Button asChild variant="outline" className="md:block hidden">
                        <Link href="/qprime" className="font-semibold">
                            Q-PRIME Dashboard
                        </Link>
                    </Button>
                    {/* <Select
                        value={refreshRate.toString()}
                        onValueChange={(value) =>
                            setRefreshRate(parseInt(value))
                        }
                    >
                        <SelectTrigger className="w-32">
                            <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                            {refreshRates.map((rate) => (
                                <SelectItem
                                    key={rate.value}
                                    value={rate.value.toString()}
                                >
                                    {rate.label}
                                </SelectItem>
                            ))}
                        </SelectContent>
                    </Select>
                    <Button
                        variant="default"
                        size="sm"
                        onClick={() => {
                            refreshSensorData();
                            refreshTimeSeriesData();
                        }}
                    >
                        Refresh Now
                    </Button> */}
                </div>
            </div>
        </div>
    );
};

export default TopBar;
