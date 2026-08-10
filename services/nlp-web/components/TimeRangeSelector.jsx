"use client";

import React, { useState, useEffect } from "react";

import { Plus, Minus } from "lucide-react";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { timeRangeOptions } from "@/constants/data";

const TimeRangeSelector = ({ timeRange, setTimeRange }) => {
    //  console.log("[TRS] typeof setTimeRange:", typeof setTimeRange, "timeRange:", timeRange);
    if (typeof setTimeRange !== "function") {
        console.trace(
            "[TRS] setTimeRange is NOT a function here (showing owner stack)"
        );
    }

    const [selectedButton, setSelectedButton] = useState(
        timeRange?.hours ?? 24
    );
    const [timeRangeExpanded, setTimeRangeExpanded] = useState(true);
    const [customStart, setCustomStart] = useState("");
    const [customEnd, setCustomEnd] = useState("");

    // Keep local button highlight in sync if parent changes timeRange externally
    useEffect(() => {
        if (timeRange && typeof timeRange.hours === "number") {
            setSelectedButton(timeRange.hours);
        }
    }, [timeRange]);

    // Quick range now updates parent state
    const handleQuickRange = (hours, label) => {
        setSelectedButton(hours);
        // Reset custom date inputs when a quick range is selected
        setCustomStart("");
        setCustomEnd("");
        const end = new Date();
        const start = new Date(end.getTime() - hours * 60 * 60 * 1000);
        setTimeRange({ hours, label, start, end });
    };
    // Custom range now updates parent state
    const handleCustomRange = () => {
        if (!customStart || !customEnd) return;

        const start = new Date(customStart);
        const end = new Date(customEnd);

        if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime()))
            return;
        if (start > end) {
            console.log("Start must be before end");
            return;
        }

        setSelectedButton(null);
        const hours = Math.max(1, Math.round((end - start) / (1000 * 60 * 60))); // Derive hours approx

        setTimeRange({
            hours,
            label: `Custom: ${start.toISOString()} → ${end.toISOString()}`,
            start,
            end,
        });
    };

    return (
        <div className="flex-1 md:p-6 space-y-6">
            <button
                onClick={() => setTimeRangeExpanded(!timeRangeExpanded)}
                className="flex items-center justify-between w-full mb-3 text-left"
            >
                <h4 className="text-sm font-medium">Time Range</h4>
                {timeRangeExpanded ? (
                    <Minus className="h-4 w-4 text-muted-foreground hover:cursor-pointer hover:text-primary" />
                ) : (
                    <Plus className="h-4 w-4 text-muted-foreground hover:cursor-pointer hover:text-primary" />
                )}
            </button>
            {timeRangeExpanded && (
                <div className="space-y-4">
                    <div className="grid grid-cols-3 gap-2 md:grid-cols-1">
                        {timeRangeOptions.map((option) => (
                            <Button
                                key={option.hours}
                                variant={
                                    selectedButton === option.hours
                                        ? "default"
                                        : "ghost"
                                }
                                size="sm"
                                onClick={() =>
                                    handleQuickRange(option.hours, option.label)
                                } //Added label
                                className="w-full justify-start text-sm hover:cursor-pointer border"
                            >
                                {option.label}
                            </Button>
                        ))}
                    </div>

                    {/* Custom DateTime Range */}
                    <div className="pt-3 border-t border-sidebar-border/50 space-y-3">
                        <div className="flex flex-row md:space-y-2 gap-2 md:flex-col md:gap-0">
                            <div className="flex-1 space-y-2">
                                <Label className="text-xs">Start</Label>
                                <Input
                                    type="datetime-local"
                                    value={customStart}
                                    onChange={(e) =>
                                        setCustomStart(e.target.value)
                                    }
                                    className="text-xs hover:cursor-pointer hover:text-primary"
                                />
                            </div>
                            <div className="flex-1 space-y-2">
                                <Label className="text-xs">End</Label>
                                <Input
                                    type="datetime-local"
                                    value={customEnd}
                                    onChange={(e) =>
                                        setCustomEnd(e.target.value)
                                    }
                                    className="text-xs hover:cursor-pointer hover:text-primary"
                                />
                            </div>
                        </div>
                        <Button
                            onClick={handleCustomRange}
                            className="w-full hover:cursor-pointer"
                            size="sm"
                        >
                            Apply
                        </Button>
                    </div>
                </div>
            )}
        </div>
    );
};

export default TimeRangeSelector;
