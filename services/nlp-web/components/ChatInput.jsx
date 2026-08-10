import { useState, useEffect } from "react";

import { Send } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent } from "@/components/ui/card";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";

import { DATA_SCOPES, DEFAULT_SCOPE } from "@/lib/sql";

export default function ChatInput({
    onQuery,
    className,
    exampleQuery,
    dataScope = DEFAULT_SCOPE,
    setDataScope,
    queryType,
    setQueryType,
}) {
    const [query, setQuery] = useState(exampleQuery);
    const [isLoading, setIsLoading] = useState(false);

    useEffect(() => {
        setQuery(exampleQuery);
    }, [exampleQuery]);

    const placeholderText =
        queryType === "sql"
            ? "Write SQL queries here to query sensor data..."
            : "Ask questions about your IoT sensor data in natural language...";

    const handleSubmit = async () => {
        // e.preventDefault();
        // if (!input.trim()) return;
        // console.log("Submitting query: ", query);
        // console.log("Submitting query: ", e.target.value);
        // console.log(queryType, " ", dataScope);
        setIsLoading(true);
        await onQuery({
            query,
            queryType,
            dataScope,
        });
        setQuery("");
        setIsLoading(false);
    };

    return (
        <Card className={`${className} flex py-4 gap-2`}>
            <CardContent className="px-4 mr-0">
                <div className="space-y-4">
                    <Textarea
                        placeholder={placeholderText}
                        value={query}
                        onChange={(e) => setQuery(e.target.value)}
                        className="min-h-20 resize-none bg-background border-none"
                        rows={3}
                    />
                    <div className="flex items-center justify-between">
                        <div className="flex items-center gap-4">
                            {/* Query Type Toggle */}
                            <div className="flex items-center space-x-2">
                                {/* <Label className="text-sm">Query Type:</Label> */}
                                <ToggleGroup
                                    type="single"
                                    value={queryType}
                                    onValueChange={(value) =>
                                        value && setQueryType(value)
                                    }
                                    className="border rounded-md"
                                >
                                    <ToggleGroupItem
                                        value="sql"
                                        className="flex-none min-w-fit px-3 whitespace-nowrap text-sm cursor-pointer data-[state=on]:bg-primary data-[state=on]:text-white"
                                    >
                                        SQL
                                    </ToggleGroupItem>
                                    <ToggleGroupItem
                                        value="natural"
                                        className="flex-none min-w-fit px-3 whitespace-nowrap text-sm cursor-pointer data-[state=on]:bg-primary data-[state=on]:text-white"
                                    >
                                        Natural
                                    </ToggleGroupItem>
                                </ToggleGroup>
                            </div>

                            {/* Continuum scope: the whole continuum by
                                default, one tier when explicitly filtered */}
                            <div className="flex items-center space-x-2">
                                <ToggleGroup
                                    type="single"
                                    value={dataScope}
                                    onValueChange={(value) =>
                                        value && setDataScope?.(value)
                                    }
                                    className="border rounded-md"
                                >
                                    {DATA_SCOPES.map(({ value, short, label }) => (
                                        <ToggleGroupItem
                                            key={value}
                                            variant="default"
                                            value={value}
                                            title={label}
                                            className="flex-none min-w-fit px-3 whitespace-nowrap text-sm cursor-pointer data-[state=on]:bg-primary data-[state=on]:text-white"
                                        >
                                            {short}
                                        </ToggleGroupItem>
                                    ))}
                                </ToggleGroup>
                            </div>
                        </div>

                        <Button
                            onClick={handleSubmit}
                            disabled={
                                isLoading ||
                                !(typeof query === "string" && query.trim())
                            }
                            className="hover:cursor-pointer"
                        >
                            {isLoading ? (
                                <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin mr-2" />
                            ) : (
                                <Send className="w-4 h-4 mr-2" />
                            )}
                            {isLoading ? "Processing..." : "Send Query"}
                        </Button>
                    </div>
                </div>
            </CardContent>
        </Card>
    );
}
