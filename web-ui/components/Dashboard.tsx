"use client";

import { useState, useEffect, useCallback } from "react";
import ConfigForm from "@/components/ConfigForm";
import DisplayPreview from "@/components/DisplayPreview";
import CollapsibleSection from "@/components/CollapsibleSection";
import LayoutEditor from "@/components/LayoutEditor";

interface Stop {
    id: string;
    name: string;
}

interface DisplaySettings {
    max_items: number;
    show_arrival_minutes_threshold: number;
    hide_arrival_before_minutes: number;
}

interface LayoutConfig {
    top_line_y: number;
    line_gap: number;
    clock_x: number;
    clock_y: number;
    route_col_x: number;
    destination_col_x: number;
    time_col_x: number;
    header_y: number;
    alert_y: number;
    font_clock: number;
    font_numbers: number;
    font_text: number;
    font_header: number;
    font_small: number;
}

interface Config {
    hsl_api_url: string;
    hsl_api_key: string;
    stops: Stop[];
    refresh_interval_seconds: number;
    display: DisplaySettings;
    layout?: LayoutConfig;
    weather?: {
        enabled: boolean;
        location: string;
        cache_minutes: number;
    };
}

interface WeatherStatus {
    enabled: boolean;
    temperature: number | null;
    description: string | null;
    location: string | null;
}

interface DashboardProps {
    apiBase: string;
}

export default function Dashboard({ apiBase }: DashboardProps) {
    const [config, setConfig] = useState<Config | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [saving, setSaving] = useState(false);
    const [previewKey, setPreviewKey] = useState(0);
    const [weather, setWeather] = useState<WeatherStatus | null>(null);
    const [weatherLoading, setWeatherLoading] = useState(false);

    const fetchConfig = useCallback(async () => {
        try {
            const res = await fetch(`${apiBase}/api/config`);
            if (!res.ok) throw new Error("Failed to fetch config");
            const data = await res.json();
            setConfig(data);
            setError(null);
        } catch (err) {
            setError("Could not connect to API. Make sure the backend is running.");
            console.error(err);
        } finally {
            setLoading(false);
        }
    }, [apiBase]);

    const fetchWeather = useCallback(async () => {
        setWeatherLoading(true);
        try {
            const res = await fetch(`${apiBase}/api/weather`);
            if (res.ok) {
                const data = await res.json();
                setWeather(data);
            }
        } catch {
            // Weather is non-critical, don't show error
        } finally {
            setWeatherLoading(false);
        }
    }, [apiBase]);

    useEffect(() => {
        fetchConfig();
        fetchWeather();
    }, [fetchConfig, fetchWeather]);

    const handleSave = async (newConfig: Config) => {
        setSaving(true);
        try {
            const res = await fetch(`${apiBase}/api/config`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(newConfig),
            });
            if (!res.ok) throw new Error("Failed to save config");
            setConfig(newConfig);
            setPreviewKey((k) => k + 1); // Refresh preview
            setError(null);
        } catch (err) {
            setError("Failed to save configuration");
            console.error(err);
        } finally {
            setSaving(false);
        }
    };

    const handleRefresh = () => {
        setPreviewKey((k) => k + 1);
    };

    const handleLayoutSaved = () => {
        setPreviewKey((k) => k + 1);
    };

    if (loading) {
        return (
            <div className="min-h-screen flex items-center justify-center">
                <div className="animate-pulse text-xl text-zinc-400">Loading...</div>
            </div>
        );
    }

    return (
        <main className="min-h-screen p-8">
            {/* Header */}
            <header className="mb-8">
                <div className="flex items-start justify-between">
                    <div>
                        <h1 className="text-3xl font-bold bg-gradient-to-r from-blue-400 to-orange-400 bg-clip-text text-transparent">
                            E-Display Control Panel
                        </h1>
                        <p className="text-zinc-400 mt-2">
                            Configure and preview your e-paper bus schedule display
                        </p>
                    </div>
                    {/* Weather Status Card */}
                    {weather?.enabled && (
                        <div className="flex items-center gap-3 px-5 py-3 bg-zinc-800/80 border border-zinc-700 rounded-xl backdrop-blur-sm">
                            <div className="text-3xl">
                                {weatherLoading ? "⏳" : "🌡"}
                            </div>
                            <div>
                                {weatherLoading ? (
                                    <div className="text-zinc-400 text-sm">Fetching weather…</div>
                                ) : weather.temperature !== null ? (
                                    <>
                                        <div className="text-2xl font-bold text-white">
                                            {weather.temperature > 0 ? "+" : ""}{weather.temperature?.toFixed(1)}°C
                                        </div>
                                        <div className="text-xs text-zinc-400">
                                            {weather.description} · {weather.location}
                                        </div>
                                    </>
                                ) : (
                                    <div className="text-zinc-500 text-sm">Weather unavailable</div>
                                )}
                            </div>
                            <button
                                id="weather-refresh-btn"
                                onClick={fetchWeather}
                                title="Refresh weather"
                                className="ml-2 p-1.5 text-zinc-400 hover:text-white hover:bg-zinc-700 rounded-lg transition-colors"
                            >
                                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                                </svg>
                            </button>
                        </div>
                    )}
                </div>
            </header>

            {/* Debug Info */}
            <div className="mb-4 text-xs text-zinc-600 font-mono text-center">
                API Target: {apiBase}
            </div>

            {/* Error Banner */}
            {error && (
                <div className="mb-6 p-4 bg-red-500/10 border border-red-500/30 rounded-lg text-red-400">
                    {error}
                </div>
            )}

            {/* Configuration & Preview Section */}
            <div className="mb-8">
                <CollapsibleSection
                    title="Configuration & Preview"
                    defaultOpen={true}
                    headerColor="text-blue-400"
                    icon={
                        <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                        </svg>
                    }
                >
                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
                        {/* Configuration Column */}
                        <div className="space-y-4">
                            <h3 className="text-lg font-medium text-zinc-300">Settings</h3>
                            {config && (
                                <ConfigForm
                                    config={config}
                                    onSave={handleSave}
                                    saving={saving}
                                />
                            )}
                        </div>

                        {/* Preview Column */}
                        <div>
                            <div className="flex items-center justify-between mb-4">
                                <h3 className="text-lg font-medium text-zinc-300">Live Preview</h3>
                                <button
                                    onClick={handleRefresh}
                                    className="flex items-center gap-2 px-4 py-2 bg-zinc-800 hover:bg-zinc-700 rounded-lg transition-colors text-sm"
                                >
                                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                                    </svg>
                                    Refresh
                                </button>
                            </div>
                            <DisplayPreview key={previewKey} apiBase={apiBase} />
                        </div>
                    </div>
                </CollapsibleSection>
            </div>

            {/* Bottom Row: Layout Editor - Full Width */}
            <CollapsibleSection
                title="Layout Editor"
                defaultOpen={true}
                headerColor="text-purple-400"
                icon={
                    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 5a1 1 0 011-1h14a1 1 0 011 1v2a1 1 0 01-1 1H5a1 1 0 01-1-1V5zM4 13a1 1 0 011-1h6a1 1 0 011 1v6a1 1 0 01-1 1H5a1 1 0 01-1-1v-6zM16 13a1 1 0 011-1h2a1 1 0 011 1v6a1 1 0 01-1 1h-2a1 1 0 01-1-1v-6z" />
                    </svg>
                }
            >
                <LayoutEditor apiBase={apiBase} onLayoutSaved={handleLayoutSaved} />
            </CollapsibleSection>
        </main >
    );
}
