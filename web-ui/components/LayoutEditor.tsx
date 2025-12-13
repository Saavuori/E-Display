"use client";

import { useState, useEffect, useCallback } from "react";
import LayoutPreview from "./LayoutPreview";

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
}

const DEFAULT_LAYOUT: LayoutConfig = {
    top_line_y: 90,
    line_gap: 60,
    clock_x: 400,
    clock_y: 10,
    route_col_x: 40,
    route_col_width: 100,
    destination_col_x: 100,
    time_col_x: 770,
    time_col_width: 180,
    header_y: 50,
    alert_y: 390,
    alert_width: 780,
    font_clock: 100,
    font_numbers: 60,
    font_text: 30,
    font_header: 30,
    font_small: 22,
};

interface LayoutEditorProps {
    apiBase: string;
    onLayoutSaved?: () => void;
}

interface SliderConfig {
    key: keyof LayoutConfig;
    label: string;
    min: number;
    max: number;
    step?: number;
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

export default function LayoutEditor({ apiBase, onLayoutSaved }: LayoutEditorProps) {
    const [layout, setLayout] = useState<LayoutConfig>(DEFAULT_LAYOUT);
    const [originalLayout, setOriginalLayout] = useState<LayoutConfig>(DEFAULT_LAYOUT);
    const [maxItems, setMaxItems] = useState(5);
    const [arrivalsData, setArrivalsData] = useState<ArrivalsData | null>(null);
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [selectedElement, setSelectedElement] = useState<string | null>(null);
    const [hasChanges, setHasChanges] = useState(false);

    const fetchLayout = useCallback(async () => {
        setLoading(true);
        try {
            // Fetch layout, config and arrivals
            const [layoutRes, configRes, arrivalsRes] = await Promise.all([
                fetch(`${apiBase}/api/layout`),
                fetch(`${apiBase}/api/config`),
                fetch(`${apiBase}/api/arrivals`)
            ]);

            if (!layoutRes.ok || !configRes.ok) throw new Error("Failed to fetch");

            const layoutData = await layoutRes.json();
            const configData = await configRes.json();
            const arrivalsData = await arrivalsRes.json();

            setLayout(layoutData);
            setOriginalLayout(layoutData);
            setMaxItems(configData.display?.max_items || 5);
            setArrivalsData(arrivalsRes.ok ? arrivalsData : null);

            setError(null);
            setHasChanges(false);
        } catch (err) {
            setError("Could not load layout configuration");
            console.error(err);
        } finally {
            setLoading(false);
        }
    }, [apiBase]);

    useEffect(() => {
        fetchLayout();
    }, [fetchLayout]);

    useEffect(() => {
        // Check if layout has changed from original
        const changed = Object.keys(layout).some(
            (key) => layout[key as keyof LayoutConfig] !== originalLayout[key as keyof LayoutConfig]
        );
        setHasChanges(changed);
    }, [layout, originalLayout]);

    const handleChange = (key: keyof LayoutConfig, value: number) => {
        setLayout((prev) => ({ ...prev, [key]: value }));
    };

    const handleElementDrag = (elementId: string, deltaX: number, deltaY: number) => {
        // Map element IDs to layout properties
        const mapping: Record<string, { x?: keyof LayoutConfig; y?: keyof LayoutConfig }> = {
            clock: { x: "clock_x", y: "clock_y" },
            header_route: { x: "route_col_x" },
            header_destination: { x: "destination_col_x" },
            header_time: { x: "time_col_x" },
            grid_top: { y: "top_line_y" },
        };

        // For row elements, update the column positions
        if (elementId.startsWith("row_")) {
            if (elementId.includes("_route")) {
                handleChange("route_col_x", Math.round(layout.route_col_x + deltaX));
            } else if (elementId.includes("_destination")) {
                handleChange("destination_col_x", Math.round(layout.destination_col_x + deltaX));
            } else if (elementId.includes("_time")) {
                handleChange("time_col_x", Math.round(layout.time_col_x + deltaX));
            }
            return;
        }

        const props = mapping[elementId];
        if (props) {
            if (props.x) handleChange(props.x, Math.round(layout[props.x] + deltaX));
            if (props.y) handleChange(props.y, Math.round(layout[props.y] + deltaY));
        }
    };

    const handleSave = async () => {
        setSaving(true);
        try {
            const res = await fetch(`${apiBase}/api/layout`, {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(layout),
            });
            if (!res.ok) throw new Error("Failed to save layout");
            setOriginalLayout(layout);
            setHasChanges(false);
            setError(null);
            if (onLayoutSaved) onLayoutSaved();
        } catch (err) {
            setError("Failed to save layout");
            console.error(err);
        } finally {
            setSaving(false);
        }
    };

    const handleReset = () => {
        setLayout(DEFAULT_LAYOUT);
    };

    const handleRevert = () => {
        setLayout(originalLayout);
    };

    const gridSettings: SliderConfig[] = [
        { key: "top_line_y", label: "Top Line Y", min: 50, max: 150 },
        { key: "line_gap", label: "Row Gap", min: 40, max: 100 },
    ];

    const clockSettings: SliderConfig[] = [
        { key: "clock_x", label: "X Position", min: 100, max: 700 },
        { key: "clock_y", label: "Y Position", min: 0, max: 50 },
    ];

    const columnSettings: SliderConfig[] = [
        { key: "route_col_x", label: "Route Center X", min: 10, max: 100 },
        { key: "route_col_width", label: "Route Width", min: 20, max: 200 },
        { key: "destination_col_x", label: "Destination X", min: 50, max: 300 },
        { key: "time_col_x", label: "Time End X", min: 600, max: 790 },
        { key: "time_col_width", label: "Time Width", min: 20, max: 300 },
        { key: "header_y", label: "Header Row Y", min: 30, max: 80 },
    ];

    const alertSettings: SliderConfig[] = [
        { key: "alert_y", label: "Alert Area Y", min: 350, max: 450 },
        { key: "alert_width", label: "Alert Width", min: 200, max: 800 },
    ];

    const fontSettings: SliderConfig[] = [
        { key: "font_clock", label: "Clock Font", min: 60, max: 150 },
        { key: "font_numbers", label: "Numbers Font", min: 30, max: 100 },
        { key: "font_text", label: "Text Font", min: 16, max: 50 },
        { key: "font_header", label: "Header Font", min: 16, max: 50 },
        { key: "font_small", label: "Small Font", min: 12, max: 30 },
    ];

    const renderSliderGroup = (title: string, settings: SliderConfig[]) => (
        <div className="mb-6">
            <h4 className="text-sm font-semibold text-zinc-300 mb-3">{title}</h4>
            <div className="space-y-3">
                {settings.map((setting) => (
                    <div key={setting.key} className="flex items-center gap-4">
                        <label className="text-sm text-zinc-400 w-32">{setting.label}</label>
                        <input
                            type="range"
                            min={setting.min}
                            max={setting.max}
                            step={setting.step || 1}
                            value={layout[setting.key]}
                            onChange={(e) => handleChange(setting.key, parseInt(e.target.value))}
                            className="flex-1 accent-blue-500"
                        />
                        <input
                            type="number"
                            min={setting.min}
                            max={setting.max}
                            value={layout[setting.key]}
                            onChange={(e) => handleChange(setting.key, parseInt(e.target.value) || 0)}
                            className="w-16 px-2 py-1 bg-zinc-800 border border-zinc-700 rounded text-sm text-center"
                        />
                    </div>
                ))}
            </div>
        </div>
    );

    if (loading) {
        return (
            <div className="flex items-center justify-center py-12">
                <div className="animate-pulse text-zinc-400">Loading layout editor...</div>
            </div>
        );
    }

    return (
        <div className="space-y-6">
            {/* Visual Preview */}
            <div>
                <h3 className="text-lg font-semibold text-zinc-200 mb-4 flex items-center gap-2">
                    <svg className="w-5 h-5 text-purple-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 5a1 1 0 011-1h14a1 1 0 011 1v2a1 1 0 01-1 1H5a1 1 0 01-1-1V5zM4 13a1 1 0 011-1h6a1 1 0 011 1v6a1 1 0 01-1 1H5a1 1 0 01-1-1v-6zM16 13a1 1 0 011-1h2a1 1 0 011 1v6a1 1 0 01-1 1h-2a1 1 0 01-1-1v-6z" />
                    </svg>
                    Visual Layout
                </h3>
                <LayoutPreview
                    layout={layout}
                    maxItems={maxItems}
                    arrivalsData={arrivalsData}
                    selectedElement={selectedElement}
                    onSelectElement={setSelectedElement}
                    onElementDrag={handleElementDrag}
                />
            </div>

            {/* Error Banner */}
            {error && (
                <div className="p-4 bg-red-500/10 border border-red-500/30 rounded-lg text-red-400">
                    {error}
                </div>
            )}

            {/* Sliders */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6 p-4 bg-zinc-800/50 rounded-xl">
                <div>
                    {renderSliderGroup("📐 Grid Settings", gridSettings)}
                    {renderSliderGroup("🕐 Clock Position", clockSettings)}
                    {renderSliderGroup("📍 Column Positions", columnSettings)}
                </div>
                <div>
                    {renderSliderGroup("⚠️ Alert Area", alertSettings)}
                    {renderSliderGroup("🔤 Font Sizes", fontSettings)}
                </div>
            </div>

            {/* Actions */}
            <div className="flex items-center justify-between pt-4 border-t border-zinc-700">
                <div className="flex gap-2">
                    <button
                        onClick={handleReset}
                        className="px-4 py-2 text-sm bg-zinc-700 hover:bg-zinc-600 rounded-lg transition-colors"
                    >
                        Reset to Defaults
                    </button>
                    <button
                        onClick={handleRevert}
                        disabled={!hasChanges}
                        className="px-4 py-2 text-sm bg-zinc-700 hover:bg-zinc-600 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                        Revert Changes
                    </button>
                </div>
                <button
                    onClick={handleSave}
                    disabled={!hasChanges || saving}
                    className="px-6 py-2 bg-gradient-to-r from-blue-500 to-purple-500 hover:from-blue-600 hover:to-purple-600 rounded-lg font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                >
                    {saving ? (
                        <>
                            <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                            </svg>
                            Saving...
                        </>
                    ) : (
                        <>
                            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                            </svg>
                            Apply Changes
                        </>
                    )}
                </button>
            </div>

            {/* Change indicator */}
            {hasChanges && (
                <div className="text-sm text-yellow-400 flex items-center gap-2">
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                    </svg>
                    You have unsaved changes
                </div>
            )}
        </div>
    );
}
