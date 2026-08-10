import React from "react";

import {
    IconFall,
    IconDrone,
    IconSandbox,
    IconArrowUp,
    IconWindmill,
    IconArrowDown,
    IconDoorEnter,
    IconTemperature,
    IconDropletFilled,
    IconDeviceCctvFilled,
    IconShieldExclamation,
} from "@tabler/icons-react";

import {
    Card,
    CardTitle,
    CardAction,
    CardFooter,
    CardHeader,
    CardContent,
} from "@/components/ui/card";

const EdgeCards = ({
    soilCondition,
    intruderCount,
    doorEventCount,
    thpTemp,
    thpHumidity,
    thpPressure,
}) => {
    return (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4 py-2 md:gap-4 md:py-2">
            {/* Lab camera */} {/* Data Not connected yet */}
            <Card className="">
                <CardHeader>
                    <CardTitle className="text-3xl font-bold tabular-nums @[250px]/card:text-4xl">
                        5
                    </CardTitle>
                    <CardAction>
                        <IconDeviceCctvFilled className="mt-1 size-7 text-slate-700" />
                    </CardAction>
                </CardHeader>
                <CardContent>
                    <div className="font-medium">Camera Detections</div>
                </CardContent>
                <CardFooter className="">
                    <div className="line-clamp-1 flex text-muted-foreground">
                        {/* <IconArrowDown className="mt-1 size-4" />
                        -4 from yesterday */}
                    </div>
                </CardFooter>
            </Card>
            {/* Tello Drone Card */} {/* Data Not connected yet */}
            <Card className="">
                <CardHeader>
                    <CardTitle className="text-3xl font-bold tabular-nums @[250px]/card:text-4xl">
                        32
                    </CardTitle>
                    <CardAction>
                        <IconDrone className="mt-1 size-7 text-lime-700" />
                    </CardAction>
                </CardHeader>
                <CardContent>
                    <div className="font-medium">Drone Detections</div>
                </CardContent>
                <CardFooter className="">
                    <div className="line-clamp-1 flex text-muted-foreground">
                        {/* <IconArrowUp className="mt-1 size-4" />
                        +5 from yesterday */}
                    </div>
                </CardFooter>
            </Card>
            {/* Intruders Count Card */}
            <Card className="">
                <CardHeader>
                    <CardTitle className="text-3xl font-bold tabular-nums @[250px]/card:text-4xl">
                        {intruderCount}
                    </CardTitle>
                    <CardAction>
                        <IconShieldExclamation className="mt-1 size-7 text-red-500" />
                    </CardAction>
                </CardHeader>
                <CardContent>
                    <div className="font-medium">Intruders</div>
                </CardContent>
                <CardFooter className="">
                    <div className="line-clamp-1 flex text-muted-foreground">
                        {/* <IconArrowDown className="mt-1 size-4" />
                        -3 from last hour */}
                    </div>
                </CardFooter>
            </Card>
            {/* Door Event Count Card */}
            <Card className="">
                <CardHeader>
                    <CardTitle className="text-3xl font-bold tabular-nums @[250px]/card:text-4xl">
                        {doorEventCount}
                    </CardTitle>
                    <CardAction>
                        <IconDoorEnter className="mt-1 size-7 text-cyan-500" />
                    </CardAction>
                </CardHeader>
                <CardContent>
                    <div className="font-medium">Door Openings</div>
                </CardContent>
                <CardFooter className="">
                    <div className="line-clamp-1 flex text-muted-foreground" />
                </CardFooter>
            </Card>
            {/* Moisture Sensor Card */}
            <Card className="">
                <CardHeader>
                    <CardTitle className="text-3xl font-bold tabular-nums @[250px]/card:text-4xl">
                        <span
                            className={
                                soilCondition === "WET"
                                    ? "text-blue-500"
                                    : "text-yellow-500"
                            }
                        >
                            {soilCondition}
                        </span>
                    </CardTitle>
                    <CardAction>
                        <IconSandbox className="mt-1 size-7 text-yellow-500" />
                    </CardAction>
                </CardHeader>
                <CardContent>
                    <div className="font-medium">Soil Condition</div>
                </CardContent>
                {/* <CardFooter className="">
                        <div className="line-clamp-1 flex text-muted-foreground">
                            <IconArrowUp className="mt-1 size-4" />
                            +1 from yesterday
                        </div>
                    </CardFooter> */}
            </Card>
            {/* Temperature Card */}
            <Card className="">
                <CardHeader>
                    <CardTitle className="text-3xl font-bold tabular-nums @[250px]/card:text-4xl">
                        {thpTemp}&#176;C
                    </CardTitle>
                    <CardAction>
                        <IconTemperature className="mt-1 size-7 text-amber-600" />
                    </CardAction>
                </CardHeader>
                <CardContent>
                    <div className="font-medium">Temperature</div>
                </CardContent>
                <CardFooter className="">
                    <div className="line-clamp-1 flex text-muted-foreground">
                        {/* <IconArrowUp className="mt-1 size-4" />
                        {1.2}&#176;C from last hour */}
                    </div>
                </CardFooter>
            </Card>
            {/* Humidity Card */}
            <Card className="">
                <CardHeader>
                    <CardTitle className="text-3xl font-bold tabular-nums @[250px]/card:text-4xl">
                        {thpHumidity}%
                    </CardTitle>
                    <CardAction>
                        <IconDropletFilled className="mt-1 size-7 text-blue-500" />
                    </CardAction>
                </CardHeader>
                <CardContent>
                    <div className="font-medium">Humidity Level</div>
                </CardContent>
                <CardFooter className="">
                    <div className="line-clamp-1 flex text-muted-foreground">
                        {/* <IconArrowDown className="mt-1 size-4" />
                        {6.1}% from last hour */}
                    </div>
                </CardFooter>
            </Card>
            {/* Fall Sensor */} {/* Data Not connected yet */}
            <Card className="">
                <CardHeader>
                    <CardTitle className="text-3xl font-bold tabular-nums @[250px]/card:text-4xl">
                        -1
                    </CardTitle>
                    <CardAction>
                        <IconFall className="mt-1 size-7 text-red-500" />
                    </CardAction>
                </CardHeader>
                <CardContent>
                    <div className="font-medium">Fall Count</div>
                </CardContent>
                <CardFooter className="">
                    <div className="line-clamp-1 flex text-muted-foreground">
                        {/* <IconArrowUp className="mt-1 size-4" />
                        +1 from yesterday */}
                    </div>
                </CardFooter>
            </Card>
            {/* Air Quality Sensor */} {/* Data Not connected yet */}
            {/* <Card className="">
                <CardHeader>
                    <CardTitle className="text-3xl font-bold tabular-nums @[250px]/card:text-4xl">
                        -1
                    </CardTitle>
                    <CardAction>
                        <IconWindmill className="mt-1 size-7 text-emerald-500" />
                    </CardAction>
                </CardHeader>
                <CardContent>
                    <div className="font-medium">AQI</div>
                </CardContent>
                <CardFooter className="">
                    <div className="line-clamp-1 flex text-muted-foreground">
                        <IconArrowDown className="mt-1 size-4" />
                        -4 from yesterday
                    </div>
                </CardFooter>
            </Card> */}
        </div>
    );
};

export default EdgeCards;
