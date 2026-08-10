"use client";

import React, { useState } from "react";

import { Button } from "@/components/ui/button";
import { Server, Cloud, Layers, Plus, Minus } from "lucide-react";

import { DATA_SCOPES } from "@/lib/sql";

const ICONS = { continuum: Layers, edge: Server, cloud: Cloud };

const HINTS = {
    continuum: "Combined Q-PRIME Edge and Cloud view",
    edge: "Records currently queryable from the Edge tier",
    cloud: "Records currently queryable from the Cloud tier",
};

/**
 * The combined continuum is the default; Edge and Cloud are optional filters.
 */
const DataSourceSelector = ({ databaseLayer, setDatabaseLayer }) => {
    const [dataSourcesExpanded, setDataSourcesExpanded] = useState(true);
    const active = databaseLayer || "continuum";

    return (
        <div className="flex-1 mb-4 md:p-6 md:pb-0">
            <div>
                <button
                    onClick={() => setDataSourcesExpanded(!dataSourcesExpanded)}
                    className="flex items-center justify-between w-full mb-3 text-left"
                >
                    <h4 className="text-sm font-medium">Data Source</h4>
                    {dataSourcesExpanded ? (
                        <Minus className="h-4 w-4 text-muted-foreground hover:cursor-pointer hover:text-primary" />
                    ) : (
                        <Plus className="h-4 w-4 text-muted-foreground hover:cursor-pointer hover:text-primary" />
                    )}
                </button>
                {dataSourcesExpanded && (
                    <div className="flex flex-row md:flex-col gap-2">
                        {DATA_SCOPES.map(({ value, label }) => {
                            const Icon = ICONS[value];
                            return (
                                <Button
                                    key={value}
                                    variant={active === value ? "default" : "ghost"}
                                    size="sm"
                                    title={HINTS[value]}
                                    onClick={() => setDatabaseLayer(value)}
                                    className="flex-1 justify-start gap-2 md:flex-none hover:cursor-pointer border"
                                >
                                    <Icon className="h-4 w-4" />
                                    {label}
                                </Button>
                            );
                        })}
                    </div>
                )}
            </div>
        </div>
    );
};

export default DataSourceSelector;
