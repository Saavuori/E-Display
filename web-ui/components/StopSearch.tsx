"use client";

import { useState } from "react";

interface Route {
    name: string;
    mode: string;
}

interface Stop {
    id: string;
    name: string;
    code: string;
    lat: number;
    lon: number;
    distance: number;
    routes: Route[];
}

interface SearchResult {
    location: string;
    coordinates: { lat: number; lon: number };
    radius: number;
    stops: Stop[];
    message?: string;
}

interface StopSearchProps {
    apiBase: string;
    onAddStop: (id: string, name: string, routes?: Route[]) => void;
    existingStopIds: string[];
}

export default function StopSearch({ apiBase, onAddStop, existingStopIds }: StopSearchProps) {
    const [query, setQuery] = useState("");
    const [radius, setRadius] = useState(500);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [result, setResult] = useState<SearchResult | null>(null);

    const handleSearch = async () => {
        if (!query.trim()) return;

        setLoading(true);
        setError(null);

        try {
            const res = await fetch(
                `${apiBase}/api/stops/search?q=${encodeURIComponent(query)}&radius=${radius}`
            );
            if (!res.ok) {
                const data = await res.json();
                throw new Error(data.detail || "Search failed");
            }
            const data = await res.json();
            setResult(data);
        } catch (err) {
            setError(err instanceof Error ? err.message : "Search failed");
            setResult(null);
        } finally {
            setLoading(false);
        }
    };

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === "Enter") {
            handleSearch();
        }
    };

    const getModeIcon = (mode: string) => {
        switch (mode) {
            case "TRAM":
                return "🚊";
            case "BUS":
                return "🚌";
            case "SUBWAY":
                return "🚇";
            case "RAIL":
                return "🚆";
            case "FERRY":
                return "⛴️";
            default:
                return "🚏";
        }
    };

    const getModeColor = (mode: string) => {
        switch (mode) {
            case "TRAM":
                return "bg-green-500/20 text-green-400 border-green-500/30";
            case "BUS":
                return "bg-blue-500/20 text-blue-400 border-blue-500/30";
            case "SUBWAY":
                return "bg-orange-500/20 text-orange-400 border-orange-500/30";
            case "RAIL":
                return "bg-purple-500/20 text-purple-400 border-purple-500/30";
            case "FERRY":
                return "bg-cyan-500/20 text-cyan-400 border-cyan-500/30";
            default:
                return "bg-zinc-500/20 text-zinc-400 border-zinc-500/30";
        }
    };

    return (
        <div className="space-y-4">
            {/* Search Input */}
            <div className="flex gap-2">
                <div className="flex-1 relative">
                    <input
                        type="text"
                        value={query}
                        onChange={(e) => setQuery(e.target.value)}
                        onKeyDown={handleKeyDown}
                        placeholder="Search by address (e.g. Mannerheimintie 10)"
                        className="w-full px-4 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white placeholder-zinc-500 focus:outline-none focus:border-blue-500"
                    />
                    <svg
                        className="absolute right-3 top-1/2 -translate-y-1/2 w-5 h-5 text-zinc-500"
                        fill="none"
                        viewBox="0 0 24 24"
                        stroke="currentColor"
                    >
                        <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
                        />
                    </svg>
                </div>
                <select
                    value={radius}
                    onChange={(e) => setRadius(parseInt(e.target.value))}
                    className="px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white focus:outline-none focus:border-blue-500"
                >
                    <option value={200}>200m</option>
                    <option value={500}>500m</option>
                    <option value={1000}>1km</option>
                    <option value={2000}>2km</option>
                </select>
                <button
                    onClick={handleSearch}
                    disabled={loading || !query.trim()}
                    className="px-4 py-2 bg-blue-500 hover:bg-blue-600 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg font-medium transition-colors flex items-center gap-2"
                >
                    {loading ? (
                        <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                            <circle
                                className="opacity-25"
                                cx="12"
                                cy="12"
                                r="10"
                                stroke="currentColor"
                                strokeWidth="4"
                                fill="none"
                            />
                            <path
                                className="opacity-75"
                                fill="currentColor"
                                d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                            />
                        </svg>
                    ) : (
                        "Search"
                    )}
                </button>
            </div>

            {/* Error */}
            {error && (
                <div className="p-3 bg-red-500/10 border border-red-500/30 rounded-lg text-red-400 text-sm">
                    {error}
                </div>
            )}

            {/* Results */}
            {result && (
                <div className="space-y-3">
                    {/* Location info */}
                    <div className="text-sm text-zinc-400">
                        Found <span className="text-white font-semibold">{result.stops.length}</span> stops within{" "}
                        {result.radius}m of <span className="text-blue-400">{result.location}</span>
                    </div>

                    {/* Stops list */}
                    {result.stops.length > 0 ? (
                        <div className="space-y-2 max-h-80 overflow-y-auto">
                            {result.stops.map((stop) => {
                                const isAdded = existingStopIds.includes(stop.id);
                                return (
                                    <div
                                        key={stop.id}
                                        className={`p-3 rounded-lg border transition-colors ${isAdded
                                            ? "bg-green-500/10 border-green-500/30"
                                            : "bg-zinc-800 border-zinc-700 hover:border-zinc-600"
                                            }`}
                                    >
                                        <div className="flex items-start justify-between gap-3">
                                            <div className="flex-1 min-w-0">
                                                <div className="flex items-center gap-2">
                                                    <span className="font-semibold text-white">{stop.name}</span>
                                                    <span className="text-xs text-zinc-500 bg-zinc-700 px-1.5 py-0.5 rounded">
                                                        {stop.code}
                                                    </span>
                                                </div>
                                                <div className="text-xs text-zinc-500 mt-1">
                                                    {stop.id} • {stop.distance}m away
                                                </div>
                                                {/* Routes */}
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
                                            </div>
                                            <button
                                                onClick={() => onAddStop(stop.id, stop.name, stop.routes)}
                                                disabled={isAdded}
                                                className={`px-3 py-1 text-sm rounded-lg transition-colors flex-shrink-0 ${isAdded
                                                    ? "bg-green-500/20 text-green-400 cursor-default"
                                                    : "bg-blue-500 hover:bg-blue-600 text-white"
                                                    }`}
                                            >
                                                {isAdded ? "✓ Added" : "+ Add"}
                                            </button>
                                        </div>
                                    </div>
                                );
                            })}
                        </div>
                    ) : (
                        <div className="text-sm text-zinc-500 text-center py-4">
                            No stops found. Try increasing the search radius.
                        </div>
                    )}
                </div>
            )}

            {/* Help text */}
            {!result && !error && (
                <div className="text-xs text-zinc-500">
                    Enter an address or place name to find nearby bus and tram stops.
                </div>
            )}
        </div>
    );
}
