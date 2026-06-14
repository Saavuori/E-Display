"use client";

import { useState, useRef, useEffect, MouseEvent } from "react";

interface LayoutConfig {
    top_line_y: number;
    line_gap: number;
    clock_x: number;
    clock_y: number;
    route_col_x: number;
    route_col_width: number;
    destination_col_x: number;
    time_col_x: number;
    time_col_width: number;
    header_y: number;
    alert_y: number;
    alert_width: number;
    font_clock: number;
    font_numbers: number;
    font_text: number;
    font_header: number;
    font_small: number;
    weather_x?: number;
    weather_y?: number;
}

interface LayoutElement {
    id: string;
    name: string;
    type: "text" | "line" | "area";
    x: number;
    y: number;
    width: number;
    height: number;
    anchor?: string;
    font?: string;
    sample?: string;
    fontSize?: number;
}

interface Arrival {
    route: string;
    destination: string;
    time: string;
}

interface Alert {
    header: string;
    severity: string;
}

interface ArrivalsData {
    arrivals: Arrival[];
    alerts: Alert[];
}

interface LayoutPreviewProps {
    layout: LayoutConfig;
    maxItems: number;
    arrivalsData?: ArrivalsData | null;
    selectedElement: string | null;
    onSelectElement: (id: string | null) => void;
    onElementDrag: (id: string, deltaX: number, deltaY: number) => void;
}

const DISPLAY_WIDTH = 800;
const DISPLAY_HEIGHT = 480;

function calcX(x: number, width: number, anchor: string): number {
    // Handle horizontal anchoring
    // First character: l=left, m=middle, r=right
    // Second character: t=top, a=ascender (baseline)
    const hAlign = anchor.charAt(0);
    if (hAlign === 'r') return x - width;       // Right-aligned: right edge at x
    if (hAlign === 'm') return x - width / 2;   // Middle-aligned: center at x
    return x;  // Left-aligned (l): left edge at x
}

function generateElements(layout: LayoutConfig, maxItems: number, arrivalsData?: ArrivalsData | null): LayoutElement[] {
    // Helper to estimate text width
    const measure = (text: string, size: number) => Math.max(size, text.length * size * 0.6); // 0.6 aspect ratio approx

    // Standard widths for different content types (approximate character widths)
    // Standard widths for different content types (approximate character widths)
    // ROUTE_WIDTH and TIME_WIDTH are now in layout config

    // Get alerts from data if available
    const alertsText = arrivalsData?.alerts?.map(a => a.header).join(" | ") || "Alerts Area";

    const weatherX = layout.weather_x !== undefined ? layout.weather_x : 790;
    const weatherY = layout.weather_y !== undefined ? layout.weather_y : 15;
    const tempText = "+12.5°C";
    const tempWidth = measure(tempText, layout.font_header);
    const tempHeight = layout.font_header;

    // Anchor is "ra" (right-aligned), so left edge is weatherX - tempWidth
    const tempLeft = calcX(weatherX, tempWidth, "ra");
    const iconSize = 46;
    const iconLeft = weatherX - tempWidth - 10 - iconSize;

    const elements: LayoutElement[] = [
        {
            id: "clock",
            name: "Clock",
            type: "text",
            // Clock is middle-aligned (mt)
            x: calcX(layout.clock_x, measure("12:34", layout.font_clock), "mt"),
            y: layout.clock_y,
            width: measure("12:34", layout.font_clock),
            height: layout.font_clock,
            anchor: "mt",
            font: "clock",
            sample: "12:34",
            fontSize: layout.font_clock
        },
        {
            id: "weather_temp",
            name: "Weather Temp",
            type: "text",
            x: tempLeft,
            y: weatherY,
            width: tempWidth,
            height: tempHeight,
            anchor: "ra",
            font: "header",
            sample: tempText,
            fontSize: layout.font_header
        },
        {
            id: "weather_icon",
            name: "Weather Icon",
            type: "area",
            x: iconLeft,
            y: weatherY,
            width: iconSize,
            height: iconSize,
            sample: "☀️"
        },
        {
            id: "header_route",
            name: "H: Route",
            type: "text",
            // Left-aligned (la)
            x: calcX(layout.route_col_x, measure("Linja", layout.font_header), "la"),
            y: layout.header_y,
            width: measure("Linja", layout.font_header),
            height: layout.font_header,
            anchor: "la",
            font: "header",
            sample: "Linja",
            fontSize: layout.font_header
        },
        {
            id: "header_destination",
            name: "H: Destination",
            type: "text",
            // Left-aligned (la)
            x: calcX(layout.destination_col_x, measure("Määränpää", layout.font_header), "la"),
            y: layout.header_y,
            width: measure("Määränpää", layout.font_header),
            height: layout.font_header,
            anchor: "la",
            font: "header",
            sample: "Määränpää",
            fontSize: layout.font_header
        },
        {
            id: "header_time",
            name: "H: Time",
            type: "text",
            // Right-aligned (ra)
            x: calcX(layout.time_col_x, measure("Aika", layout.font_header), "ra"),
            y: layout.header_y,
            width: measure("Aika", layout.font_header),
            height: layout.font_header,
            anchor: "ra",
            font: "header",
            sample: "Aika",
            fontSize: layout.font_header
        },
        {
            id: "grid_top",
            name: "Grid Top Line",
            type: "line",
            x: 0,
            y: layout.top_line_y,
            width: 800,
            height: 4
        },
        {
            id: "grid_bottom",
            name: "Grid Bottom Line",
            type: "line",
            x: 0,
            y: layout.top_line_y + maxItems * layout.line_gap,
            width: 800,
            height: 4
        },
        {
            id: "alerts",
            name: "Alerts Area",
            type: "area",
            x: (800 - layout.alert_width) / 2,
            y: layout.alert_y,
            width: layout.alert_width,
            height: layout.font_small * 2,
            sample: alertsText
        }
    ];

    // Add arrival row elements
    for (let i = 0; i < maxItems; i++) {
        // Y position logic matches display.py: top_line_y - 5 + idx * line_gap
        const y_base = layout.top_line_y - 5 + i * layout.line_gap;

        // Get data for this row if available
        const arrival = arrivalsData?.arrivals?.[i];
        const route = arrival?.route || "550";
        const destination = arrival?.destination || "Itäkeskus via Päärautatieasema";
        const time = arrival?.time || "12:34";

        elements.push(
            {
                id: `row_${i}_route`,
                name: `Row ${i + 1}: Route`,
                type: "text",
                // Left-aligned at route_col_x (formerly Middle-aligned)
                x: calcX(layout.route_col_x, layout.route_col_width, "la"),
                y: y_base,
                width: layout.route_col_width, // Use configured width
                height: layout.font_numbers,
                anchor: "la",
                font: "numbers",
                sample: route,
                fontSize: layout.font_numbers
            },
            {
                id: `row_${i}_destination`,
                name: `Row ${i + 1}: Destination`,
                type: "text",
                // Left-aligned at destination_col_x, vertically offset +15
                x: calcX(layout.destination_col_x, measure(destination, layout.font_text), "la"),
                y: y_base + 15, // Matches display.py +15 offset
                width: measure(destination, layout.font_text),
                height: layout.font_text,
                anchor: "la",
                font: "text",
                sample: destination,
                fontSize: layout.font_text
            },
            {
                id: `row_${i}_time`,
                name: `Row ${i + 1}: Time`,
                type: "text",
                // Right-aligned at time_col_x
                x: calcX(layout.time_col_x, layout.time_col_width, "ra"),
                y: y_base,
                width: layout.time_col_width, // Use configured width
                height: layout.font_numbers,
                anchor: "ra",
                font: "numbers",
                sample: time,
                fontSize: layout.font_numbers
            }
        );
    }

    return elements;
}

export default function LayoutPreview({
    layout,
    maxItems,
    arrivalsData,
    selectedElement,
    onSelectElement,
    onElementDrag,
}: LayoutPreviewProps) {
    const [dragging, setDragging] = useState(false);
    const [dragStart, setDragStart] = useState({ x: 0, y: 0 });
    const containerRef = useRef<HTMLDivElement>(null);
    const [containerWidth, setContainerWidth] = useState(800);

    const scale = (containerWidth - 4) / DISPLAY_WIDTH;

    useEffect(() => {
        const updateWidth = () => {
            if (containerRef.current) {
                setContainerWidth(containerRef.current.offsetWidth);
            }
        };

        updateWidth();
        window.addEventListener("resize", updateWidth);
        return () => window.removeEventListener("resize", updateWidth);
    }, []);

    const elements = generateElements(layout, maxItems, arrivalsData);

    const handleMouseDown = (e: MouseEvent, elementId: string) => {
        e.preventDefault();
        e.stopPropagation();
        onSelectElement(elementId);
        setDragging(true);
        setDragStart({ x: e.clientX, y: e.clientY });
    };

    const handleMouseMove = (e: MouseEvent) => {
        if (!dragging || !selectedElement) return;

        const deltaX = (e.clientX - dragStart.x) / scale;
        const deltaY = (e.clientY - dragStart.y) / scale;

        if (Math.abs(deltaX) > 1 || Math.abs(deltaY) > 1) {
            onElementDrag(selectedElement, deltaX, deltaY);
            setDragStart({ x: e.clientX, y: e.clientY });
        }
    };

    const handleMouseUp = () => {
        setDragging(false);
    };

    const handleBackgroundClick = () => {
        onSelectElement(null);
    };

    const getElementColor = (type: string, isSelected: boolean) => {
        if (isSelected) return "border-blue-500 bg-blue-500/20";
        switch (type) {
            case "text":
                return "border-green-500/50 bg-green-500/10 hover:border-green-400";
            case "line":
                return "border-red-500/50 bg-red-500/10 hover:border-red-400";
            case "area":
                return "border-yellow-500/50 bg-yellow-500/10 hover:border-yellow-400";
            default:
                return "border-zinc-500/50 bg-zinc-500/10";
        }
    };

    return (
        <div ref={containerRef} className="w-full">
            {/* Display Canvas */}
            <div className="relative bg-zinc-900 rounded-xl p-4">
                <div
                    className="relative bg-white rounded-lg shadow-inner border-2 border-zinc-600"
                    style={{
                        width: "100%",
                        aspectRatio: `${DISPLAY_WIDTH} / ${DISPLAY_HEIGHT}`,
                    }}
                    onClick={handleBackgroundClick}
                    onMouseMove={handleMouseMove}
                    onMouseUp={handleMouseUp}
                    onMouseLeave={handleMouseUp}
                >
                    <div className="absolute inset-0 bg-gray-100 select-none rounded-lg">
                        {elements.map((element) => {
                            const isSelected = selectedElement === element.id;
                            return (
                                <div
                                    key={element.id}
                                    className={`absolute border-2 rounded cursor-pointer transition-colors ${getElementColor(
                                        element.type,
                                        isSelected
                                    )}`}
                                    style={{
                                        left: `${(element.x / DISPLAY_WIDTH) * 100}%`,
                                        top: `${(element.y / DISPLAY_HEIGHT) * 100}%`,
                                        width: `${(element.width / DISPLAY_WIDTH) * 100}%`,
                                        height: `${(element.height / DISPLAY_HEIGHT) * 100}%`,
                                    }}
                                    onMouseDown={(e) => handleMouseDown(e, element.id)}
                                    title={element.name}
                                >
                                    <div
                                        className="absolute -top-5 left-0 text-xs whitespace-nowrap px-1 rounded"
                                        style={{
                                            fontSize: `${Math.max(8, 10 * scale)}px`,
                                            backgroundColor: isSelected ? "rgb(59 130 246)" : "rgb(39 39 42)",
                                            color: "white",
                                        }}
                                    >
                                        {element.name}
                                    </div>

                                    {element.type === "text" && element.sample && (
                                        <div
                                            className={`w-full h-full flex items-center text-gray-600 font-mono overflow-hidden px-1 ${element.anchor?.charAt(0) === 'r' ? 'justify-end' :
                                                element.anchor?.charAt(0) === 'm' ? 'justify-center' :
                                                    'justify-start'
                                                }`}
                                            style={{
                                                fontSize: element.fontSize
                                                    ? `${element.fontSize * scale * 0.7}px`
                                                    : `${Math.max(8, 14 * scale)}px`,
                                            }}
                                        >
                                            {element.sample}
                                        </div>
                                    )}
                                </div>
                            );
                        })}
                    </div>
                </div>
            </div>

            {/* Legend */}
            <div className="mt-4 flex flex-wrap items-center gap-4 text-sm text-zinc-400">
                <div className="flex items-center gap-2">
                    <div className="w-3 h-3 rounded border-2 border-green-500 bg-green-500/20" />
                    <span>Text</span>
                </div>
                <div className="flex items-center gap-2">
                    <div className="w-3 h-3 rounded border-2 border-red-500 bg-red-500/20" />
                    <span>Line</span>
                </div>
                <div className="flex items-center gap-2">
                    <div className="w-3 h-3 rounded border-2 border-yellow-500 bg-yellow-500/20" />
                    <span>Area</span>
                </div>
                <div className="flex items-center gap-2">
                    <div className="w-3 h-3 rounded border-2 border-blue-500 bg-blue-500/20" />
                    <span>Selected</span>
                </div>
            </div>

            {/* Selected element info */}
            {selectedElement && (
                <div className="mt-4 p-3 bg-blue-500/10 border border-blue-500/30 rounded-lg">
                    <p className="text-sm text-blue-400">
                        <strong>Selected:</strong>{" "}
                        {elements.find((e) => e.id === selectedElement)?.name}
                    </p>
                    <p className="text-xs text-zinc-500 mt-1">
                        Drag to reposition • Use sliders below for precise control
                    </p>
                </div>
            )}
        </div>
    );
}
