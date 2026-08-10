import { useState } from "react";

import { Card } from "@/components/ui/card";
import ChatInput from "@/components/ChatInput.jsx";

import { withBasePath } from "@/lib/basePath";

const QueryInterface = ({
    ref,
    onQuery,
    exampleQueryTypes,
    dataScope,
    setDataScope,
    queryType,
    setQueryType,
}) => {
    const [exampleQuery, setExampleQuery] = useState("");

    let exampleQueries = exampleQueryTypes["sql_cloud"];
    if (queryType === "natural") {
        exampleQueries = exampleQueryTypes["natural"];
    } else if (dataScope === "edge") {
        exampleQueries = exampleQueryTypes["sql_edge"];
    }

    return (
        <div className="flex flex-1 flex-col items-center justify-center min-h-[60vh] text-center">
            <div className="mb-8">
                <img
                    src={withBasePath("/icon.png")}
                    alt="IoT AI Visualiser"
                    className="mx-auto w-24 h-24 rounded-full shadow-lg border-2"
                />
            </div>
            <h2 className="text-3xl font-bold mb-2 text-primary">
                Welcome to IoT Data Visualiser
            </h2>

            <p className="text-gray-600 mb-6 max-w-2xl mx-auto">
                Start a new conversation to query your IoT sensor data using{" "}
                {queryType === "sql" ? "SQL" : "natural language"}.
            </p>
            {/* Example Queries */}
            <div className="mt-4 max-w-2xl mx-auto">
                <p className="text-sm text-muted-foreground mb-3">
                    Try these example queries:
                </p>
                <div className="space-y-2">
                    {exampleQueries.map((example, index) => (
                        <Card
                            key={index}
                            className="p-3 cursor-pointer hover:bg-background transition-colors"
                            onClick={() => setExampleQuery(example)}
                        >
                            <p className="text-sm text-left">{example}</p>
                        </Card>
                    ))}
                </div>
            </div>

            <div className="mt-16 max-w-2xl md:max-w-2xl lg:max-w-3xl xl:max-w-5xl mx-auto w-full">
                <ChatInput
                    ref={ref}
                    onQuery={onQuery}
                    exampleQuery={exampleQuery}
                    queryType={queryType}
                    setQueryType={setQueryType}
                    dataScope={dataScope}
                    setDataScope={setDataScope}
                />
            </div>
        </div>
    );
};

export default QueryInterface;
