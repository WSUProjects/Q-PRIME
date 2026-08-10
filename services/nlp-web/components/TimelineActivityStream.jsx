import React from "react";

import { Clock } from "lucide-react";

export default function TimelineActivityStream({ events = [] }) {
    if (!events.length) {
        return <div className="text-gray-400 text-sm">No activity data.</div>;
    }
    return (
        <div className="w-full max-w-2xl mx-auto pl-4">
            <div className="relative border-l-2 border-gray-200 pl-4">
                {events.map((evt, idx) => (
                    <div key={idx} className="mb-4 flex items-start group">
                        <span className="absolute -left-3 flex items-center justify-center w-6 h-6 rounded-full bg-emerald-500 text-white font-bold text-xs border-2 border-white shadow">
                            {idx + 1}
                        </span>
                        <div className="flex-1">
                            <div className="flex items-center gap-2">
                                <Clock className="w-4 h-4 text-gray-400" />
                                <span className="text-xs text-gray-500">
                                    {/* {new Date(
                                        evt.timestamp * 1000
                                    ).toLocaleString()} */}
                                    {new Date(
                                        evt.timestamp * 1000
                                    ).toLocaleTimeString()}
                                </span>
                                <span className="ml-2 text-xs text-clip font-semibold text-gray-700">
                                    {/* {evt.device_name} */}
                                    {evt.device_name &&
                                    evt.device_name.length > 20
                                        ? evt.device_id
                                        : evt.device_name || evt.device_id}
                                </span>
                                <span className="ml-2 text-xs px-2 py-0.5 rounded bg-gray-100 text-gray-700 border border-gray-200">
                                    {evt.type === "65"
                                        ? "Open/Close"
                                        : evt.type === "61"
                                          ? "Smoke"
                                          : evt.type === "54"
                                            ? evt.temperature + "°" + evt.event
                                            : evt.event || "event"}
                                </span>
                            </div>
                            {evt.person && (
                                <div className="mt-1 text-xs text-blue-700">
                                    Person:{" "}
                                    <span className="font-medium">
                                        {evt.person}
                                    </span>
                                </div>
                            )}
                            {/* {evt.distance && (
                                <div className="mt-1 text-xs text-gray-600">
                                    Distance: {evt.distance}cm
                                </div>
                            )} */}
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
}
