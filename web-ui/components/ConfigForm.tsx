"use client";

import { useState, useEffect } from "react";
import StopSearch from "./StopSearch";

interface Route {
    name: string;
    mode: string;
}

interface Stop {
    id: string;
    name: string;
    routes?: Route[] | null;
}

interface DisplaySettings {
    max_items: number;
    show_arrival_minutes_threshold: number;
    hide_arrival_before_minutes: number;
}

interface Config {
    hsl_api_url: string;
    hsl_api_key: string;
    stops: Stop[];
    refresh_interval_seconds: number;
    display: DisplaySettings;
}

interface ConfigFormProps {
    config: Config;
    onSave: (config: Config) => void;
    saving: boolean;
    apiBase?: string;
}

export default function ConfigForm({ config, onSave, saving, apiBase = "http://localhost:8000" }: ConfigFormProps) {
    const [formData, setFormData] = useState<Config>(config);

    // Track if form has changes
    const hasChanges = JSON.stringify(formData) !== JSON.stringify(config);

    useEffect(() => {
        setFormData(config);
    }, [config]);

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        onSave(formData);
    };

    const addStopFromSearch = (id: string, name: string, routes?: Route[]) => {
        // Don't add if already exists
        if (formData.stops.some(s => s.id === id)) return;

        setFormData({
            ...formData,
            stops: [...formData.stops, { id, name, routes }],
        });
    };

    const removeStop = (index: number) => {
        setFormData({
            ...formData,
            stops: formData.stops.filter((_, i) => i !== index),
        });
    };

    const updateDisplay = (field: keyof DisplaySettings, value: number) => {
        setFormData({
            ...formData,
            display: { ...formData.display, [field]: value },
        });
    };

    const getModeIcon = (mode: string) => {
        switch (mode) {
            case "TRAM": return "🚊";
            case "BUS": return "🚌";
            case "SUBWAY": return "🚇";
            case "RAIL": return "🚆";
            case "FERRY": return "⛴️";
            default: return "🚏";
        }
    };

    const getModeColor = (mode: string) => {
        switch (mode) {
            case "TRAM": return "bg-green-500/20 text-green-400 border-green-500/30";
            case "BUS": return "bg-blue-500/20 text-blue-400 border-blue-500/30";
            case "SUBWAY": return "bg-orange-500/20 text-orange-400 border-orange-500/30";
            case "RAIL": return "bg-purple-500/20 text-purple-400 border-purple-500/30";
            case "FERRY": return "bg-cyan-500/20 text-cyan-400 border-cyan-500/30";
            default: return "bg-zinc-500/20 text-zinc-400 border-zinc-500/30";
        }
    };

    const inputClass =
        "w-full px-4 py-3 bg-zinc-800 border border-zinc-700 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all";
    const labelClass = "block text-sm font-medium text-zinc-300 mb-2";

    return (
        <form onSubmit={handleSubmit} className="space-y-6">
            {/* API Configuration */}
            <section>
                <h3 className="text-sm font-semibold text-zinc-400 uppercase tracking-wide mb-4">
                    API Settings
                </h3>
                <div className="space-y-4">
                    {/* API URL hidden as it's static */}
                    <div>
                        <label className={labelClass}>API Key</label>
                        <input
                            type="password"
                            value={formData.hsl_api_key}
                            onChange={(e) => setFormData({ ...formData, hsl_api_key: e.target.value })}
                            className={inputClass}
                        />
                    </div>
                </div>
            </section>

            {/* Stops */}
            <section>
                <div className="flex items-center justify-between mb-4">
                    <h3 className="text-sm font-semibold text-zinc-400 uppercase tracking-wide">
                        Bus Stops
                    </h3>
                </div>

                {/* Stop Search */}
                <div className="mb-4">
                    <StopSearch
                        apiBase={apiBase}
                        onAddStop={addStopFromSearch}
                        existingStopIds={formData.stops.map(s => s.id)}
                    />
                </div>

                <div className="space-y-3">
                    {formData.stops.map((stop, index) => (
                        <div
                            key={index}
                            className="flex items-start gap-3 p-3 bg-zinc-800/50 rounded-lg border border-zinc-700"
                        >
                            <div className="flex-1 min-w-0">
                                <div className="font-medium">{stop.name}</div>
                                <div className="text-xs text-zinc-500 font-mono">{stop.id}</div>
                                {/* Route badges */}
                                {stop.routes && stop.routes.length > 0 && (
                                    <div className="flex flex-wrap gap-1 mt-2">
                                        {stop.routes.map((route, idx) => (
                                            <span
                                                key={idx}
                                                className={`text-xs px-2 py-0.5 rounded border ${getModeColor(route.mode)}`}
                                            >
                                                {getModeIcon(route.mode)} {route.name}
                                            </span>
                                        ))}
                                    </div>
                                )}
                            </div>
                            <button
                                type="button"
                                onClick={() => removeStop(index)}
                                className="p-2 text-red-400 hover:bg-red-500/20 rounded-lg transition-colors flex-shrink-0"
                            >
                                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                                </svg>
                            </button>
                        </div>
                    ))}
                </div>
            </section>

            {/* Display Settings */}
            <section>
                <h3 className="text-sm font-semibold text-zinc-400 uppercase tracking-wide mb-4">
                    Display Settings
                </h3>
                <div className="grid grid-cols-2 gap-4">
                    <div>
                        <label className={labelClass}>Refresh Interval (seconds)</label>
                        <input
                            type="number"
                            min="60"
                            max="3600"
                            value={formData.refresh_interval_seconds}
                            onChange={(e) =>
                                setFormData({ ...formData, refresh_interval_seconds: parseInt(e.target.value) })
                            }
                            className={inputClass}
                        />
                    </div>
                    <div>
                        <label className={labelClass}>Max Items</label>
                        <input
                            type="number"
                            min="1"
                            max="10"
                            value={formData.display.max_items}
                            onChange={(e) => updateDisplay("max_items", parseInt(e.target.value))}
                            className={inputClass}
                        />
                    </div>
                    <div>
                        <label className={labelClass}>Show Minutes Threshold</label>
                        <input
                            type="number"
                            min="1"
                            max="60"
                            value={formData.display.show_arrival_minutes_threshold}
                            onChange={(e) =>
                                updateDisplay("show_arrival_minutes_threshold", parseInt(e.target.value))
                            }
                            className={inputClass}
                        />
                    </div>
                    <div>
                        <label className={labelClass}>Hide Before (minutes)</label>
                        <input
                            type="number"
                            min="0"
                            max="30"
                            value={formData.display.hide_arrival_before_minutes}
                            onChange={(e) =>
                                updateDisplay("hide_arrival_before_minutes", parseInt(e.target.value))
                            }
                            className={inputClass}
                        />
                    </div>
                </div>
            </section>

            {/* Save Button */}
            <button
                type="submit"
                disabled={saving || !hasChanges}
                className="w-full py-3 bg-blue-500 hover:bg-blue-600 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg font-medium transition-colors flex items-center justify-center gap-2"
            >
                {saving ? (
                    <>
                        <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24">
                            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                        </svg>
                        Saving...
                    </>
                ) : (
                    "Save Configuration"
                )}
            </button>
        </form>
    );
}
