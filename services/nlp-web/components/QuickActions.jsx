import { Button } from "./ui/button";

import { quickActions } from "../constants/data";
export function QuickActions({ onActionClick, selectedAction }) {
    return (
        <div className="">
            <select
                className="w-full p-2 border border-primary rounded text-sm hover:cursor-pointer"
                value={selectedAction}
                onChange={(e) => {
                    const selected = quickActions.find(
                        (a) => a.id === e.target.value
                    );
                    if (selected) onActionClick(selected);
                }}
            >
                {quickActions.map((action) => (
                    <option key={action.id} value={action.id} className="hover:cursor-pointer">
                        {action.label}
                    </option>
                ))}
            </select>
        </div>
    );
}
