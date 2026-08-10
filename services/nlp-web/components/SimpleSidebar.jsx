import {
    Sidebar,
    SidebarHeader,
    SidebarFooter,
    SidebarContent,
    SidebarMenu,
} from "@/components/ui/sidebar";
import SimpleHeader from "./SimpleHeader";
import TimeRangeSelector from "./TimeRangeSelector";
import DataSourceSelector from "./DataSourceSelector";

export function SimpleSidebar({ databaseLayer, setDatabaseLayer, timeRange, setTimeRange }) {
    return (
        <Sidebar collapsible="offcanvas">
            <SidebarHeader>
                <SimpleHeader />
            </SidebarHeader>

            <SidebarContent>
                <SidebarMenu>
                    <DataSourceSelector
                        databaseLayer={databaseLayer}
                        setDatabaseLayer={setDatabaseLayer}
                    />
                    <TimeRangeSelector
                        timeRange={timeRange}
                        setTimeRange={setTimeRange}
                    />
                </SidebarMenu>
            </SidebarContent>

            {/* <SidebarFooter></SidebarFooter> */}
        </Sidebar>
    );
}
