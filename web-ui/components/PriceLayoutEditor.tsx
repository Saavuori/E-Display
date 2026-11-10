"use client";

import { useCallback, useEffect, useState } from "react";
import DisplayPreview from "@/components/DisplayPreview";
import type { PriceLayoutConfig } from "@/lib/types";

interface PriceLayoutEditorProps {
    apiBase: string;
    onLayoutSaved?: () => void;
}

interface Field {
    key: keyof PriceLayoutConfig;
    label: string;
    min: number;
    max: number;
}

const GROUPS: { title: string; fields: Field[] }[] = [
    {
        title: "🕐 Clock & Date",
        fields: [
            { key: "clock_x", label: "Clock X", min: 0, max: 400 },
            { key: "clock_y", label: "Clock Y", min: 0, max: 100 },
            { key: "date_y", label: "Date Y", min: 40, max: 140 },
        ],
    },
    {
        title: "⚡ Current Price",
        fields: [
            { key: "price_x", label: "Right Edge X", min: 200, max: 700 },
            { key: "price_y", label: "Y Position", min: 0, max: 100 },
            { key: "header_line_y", label: "Header Line Y", min: 60, max: 200 },
        ],
    },
    {
        title: "📊 Stats",
        fields: [
            { key: "stats_x", label: "Label X", min: 0, max: 200 },
            { key: "stats_value_x", label: "Values X", min: 60, max: 400 },
            { key: "stats_y", label: "First Line Y", min: 100, max: 300 },
            { key: "stats_line_gap", label: "Line Gap", min: 16, max: 60 },
        ],
    },
    {
        title: "📈 Chart",
        fields: [
            { key: "chart_x", label: "Left X", min: 0, max: 200 },
            { key: "chart_y", label: "Top Y", min: 120, max: 400 },
            { key: "chart_width", label: "Width", min: 200, max: 800 },
            { key: "chart_height", label: "Height", min: 60, max: 400 },
        ],
    },
    {
        title: "🌤️ Weather Position",
        fields: [
            { key: "weather_x", label: "X Position", min: 100, max: 795 },
            { key: "weather_y", label: "Y Position", min: 0, max: 150 },
        ],
    },
    {
        title: "🔤 Font Sizes",
        fields: [
            { key: "font_clock", label: "Clock", min: 40, max: 150 },
            { key: "font_price", label: "Price", min: 40, max: 150 },
            { key: "font_unit", label: "Unit", min: 12, max: 50 },
            { key: "font_stats", label: "Stats", min: 12, max: 40 },
            { key: "font_axis", label: "Chart Axis", min: 10, max: 30 },
            { key: "font_small", label: "Small", min: 12, max: 30 },
        ],
    },
];

// Edits the spot-price screen's layout. Unlike the tram layout there is no
// drag preview: the real server-rendered frame is shown instead, refreshed
// after each save.
export default function PriceLayoutEditor({ apiBase, onLayoutSaved }: PriceLayoutEditorProps) {
    const [layout, setLayout] = useState<PriceLayoutConfig | null>(null);
    const [original, setOriginal] = useState<PriceLayoutConfig | null>(null);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [previewKey, setPreviewKey] = useState(0);

    const fetchLayout = useCallback(async () => {
        try {
            const res = await fetch(`${apiBase}/api/layout/prices`);
            if (!res.ok) throw new Error("Failed to fetch");
            const data = await res.json();
            setLayout(data);
            setOriginal(data);
            setError(null);
        } catch (err) {
            setError("Could not load the price screen layout");
            console.error(err);
        }
    }, [apiBase]);

    useEffect(() => {
        fetchLayout();
    }, [fetchLayout]);

    // An empty body resets every field to the backend's defaults, which live
    // only in PriceLayoutConfig.
    const save = async (body: Partial<PriceLayoutConfig>) => {
        setSaving(true);
        try {
            const res = await fetch(`${apiBase}/api/layout/prices`, {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(body),
            });
            if (!res.ok) throw new Error("Failed to save layout");
            await fetchLayout();
            setPreviewKey((k) => k + 1);
            onLayoutSaved?.();
        } catch (err) {
            setError("Failed to save layout");
            console.error(err);
        } finally {
            setSaving(false);
        }
    };

    if (!layout || !original) {
        return error ? (
            <div className="p-4 bg-red-500/10 border border-red-500/30 rounded-lg text-red-400">{error}</div>
        ) : (
            <div className="animate-pulse text-zinc-400 py-12 text-center">Loading layout editor...</div>
        );
    }

    const hasChanges = JSON.stringify(layout) !== JSON.stringify(original);
    const set = (key: keyof PriceLayoutConfig, value: number) => setLayout({ ...layout, [key]: value });

    return (
        <div className="space-y-6">
            <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-x-6 p-4 bg-zinc-800/50 rounded-xl">
                    {GROUPS.map((group) => (
                        <div key={group.title} className="mb-6">
                            <h4 className="text-sm font-semibold text-zinc-300 mb-3">{group.title}</h4>
                            <div className="space-y-3">
                                {group.fields.map((f) => (
                                    <div key={f.key} className="flex items-center gap-3">
                                        <label className="text-sm text-zinc-400 w-28">{f.label}</label>
                                        <input
                                            type="range"
                                            min={f.min}
                                            max={f.max}
                                            value={layout[f.key]}
                                            onChange={(e) => set(f.key, parseInt(e.target.value))}
                                            className="flex-1 accent-blue-500"
                                        />
                                        <input
                                            type="number"
                                            min={f.min}
                                            max={f.max}
                                            value={layout[f.key]}
                                            onChange={(e) => set(f.key, parseInt(e.target.value) || 0)}
                                            className="w-16 px-2 py-1 bg-zinc-800 border border-zinc-700 rounded text-sm text-center"
                                        />
                                    </div>
                                ))}
                            </div>
                        </div>
                    ))}
                </div>
                <div>
                    <h4 className="text-sm font-semibold text-zinc-300 mb-3">Rendered on the server · updates when you apply</h4>
                    <DisplayPreview key={previewKey} apiBase={apiBase} />
                </div>
            </div>

            {error && (
                <div className="p-4 bg-red-500/10 border border-red-500/30 rounded-lg text-red-400">{error}</div>
            )}

            <div className="flex items-center justify-between pt-4 border-t border-zinc-700">
                <div className="flex gap-2">
                    <button
                        onClick={() => save({})}
                        disabled={saving}
                        className="px-4 py-2 text-sm bg-zinc-700 hover:bg-zinc-600 rounded-lg transition-colors disabled:opacity-50"
                    >
                        Reset to Defaults
                    </button>
                    <button
                        onClick={() => setLayout(original)}
                        disabled={!hasChanges}
                        className="px-4 py-2 text-sm bg-zinc-700 hover:bg-zinc-600 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                        Revert Changes
                    </button>
                </div>
                <button
                    onClick={() => save(layout)}
                    disabled={!hasChanges || saving}
                    className="px-6 py-2 bg-gradient-to-r from-blue-500 to-purple-500 hover:from-blue-600 hover:to-purple-600 rounded-lg font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                    {saving ? "Saving..." : "Apply Changes"}
                </button>
            </div>
        </div>
    );
}
