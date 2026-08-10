import Image from "next/image";

import { withBasePath } from "@/lib/basePath";

const SimpleHeader = () => {
    return (
        <div className="p-4 border-b border-sidebar-border">
            <div className="flex items-center gap-3">
                <div className="w-10 h-10 flex items-center justify-center">
                    <Image
                        src={withBasePath("/icon.png")}
                        alt="Lab Icon"
                        width={400}
                        height={400}
                    />
                </div>
                <div>
                    <div className="font-medium text-sm leading-tight">
                        IoT Healthcare Monitoring
                    </div>
                    <div className="font-medium text-sm leading-tight">
                        SDC Lab WSU
                    </div>
                </div>
            </div>
        </div>
    );
};

export default SimpleHeader;
