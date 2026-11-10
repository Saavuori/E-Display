"use client";

import { useCallback, useEffect, useState } from "react";
import { formatPrice, hhmm, isoDate, priceLevel, type PriceLevel } from "@/lib/prices";
import type { PricesData, PriceStats } from "@/lib/types";

interface PricesCardProps {
    apiBase: string;
    // Bumped by the dashboard after a settings save, so VAT and thresholds update.
    refreshKey: number;
}

const LEVEL_TEXT: Record<PriceLevel, string> = {
    cheap: "text-emerald-400",
    normal: "text-zinc-100",
    expensive: "text-red-400",
};

const LEVEL_BAR: Record<PriceLevel, string> = {
    cheap: "fill-emerald-500/70",
    normal: "fill-zinc-400",
    expensive: "fill-red-500",
};

function StatsRow({ label, stats }: { label: string; stats: PriceStats | null }) {
    return (
        <div className="flex items-baseline justify-between gap-4 py-2 border-b border-zinc-800 last:border-0">
            <span className="text-sm text-zinc-400 w-24">{label}</span>
            {stats ? (
                <span className="flex-1 grid grid-cols-3 gap-2 text-sm tabular-nums">
                    <span>min <b>{formatPrice(stats.min)}</b> <span className="text-zinc-500">{hhmm(stats.min_at)}</span></span>
                    <span>avg <b>{formatPrice(stats.avg)}</b></span>
                    <span>max <b>{formatPrice(stats.max)}</b> <span className="text-zinc-500">{hhmm(stats.max_at)}</span></span>
                </span>
            ) : (
                <span className="flex-1 text-sm text-zinc-500">Published around 14:00</span>
            )}
        </div>
    );
}

export default function PricesCard({ apiBase, refreshKey }: PricesCardProps) {
    const [data, setData] = useState<PricesData | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [loading, setLoading] = useState(true);

    const fetchPrices = useCallback(async () => {
        setLoading(true);
        try {
            const res = await fetch(`${apiBase}/api/prices`);
            if (!res.ok) throw new Error(`Status ${res.status}`);
            setData(await res.json());
            setError(null);
        } catch (err) {
            setError("Spot prices are unavailable right now.");
            console.error(err);
        } finally {
            setLoading(false);
        }
    }, [apiBase]);

    useEffect(() => {
        fetchPrices();
    }, [fetchPrices, refreshKey]);

    if (loading && !data) {
        return <div className="animate-pulse text-zinc-400 py-6">Loading spot prices…</div>;
    }
    if (error || !data) {
        return <div className="p-4 bg-red-500/10 border border-red-500/30 rounded-lg text-red-400">{error}</div>;
    }

    const level = (p: number) => priceLevel(p, data.cheap_threshold, data.expensive_threshold);
    const prices = data.points.map((p) => p.price);
    const top = Math.max(1, ...prices);
    const bottom = Math.min(0, ...prices);
    const range = top - bottom;
    const barWidth = 100 / Math.max(data.points.length, 1);
    const zeroY = (top / range) * 100;

    return (
        <div className="space-y-5">
            <div className="flex flex-wrap items-end gap-6">
                <div>
                    <div className="text-xs uppercase tracking-wide text-zinc-500">
                        Now{data.current && ` · ${hhmm(data.current.start)}–${hhmm(data.current.end)}`}
                    </div>
                    <div className={`text-5xl font-bold tabular-nums ${data.current ? LEVEL_TEXT[level(data.current.price)] : "text-zinc-500"}`}>
                        {data.current ? formatPrice(data.current.price) : "–"}
                        <span className="text-xl font-normal text-zinc-400 ml-2">c/kWh</span>
                    </div>
                </div>
                {data.cheapest && (
                    <div className="px-4 py-2 rounded-lg bg-emerald-500/10 border border-emerald-500/30">
                        <div className="text-xs uppercase tracking-wide text-emerald-400">
                            Cheapest {data.cheapest.hours} h
                        </div>
                        <div className="text-lg tabular-nums">
                            {isoDate(data.cheapest.start) !== isoDate(data.current?.start ?? data.cheapest.start) && "tomorrow "}
                            {hhmm(data.cheapest.start)}–{hhmm(data.cheapest.end)} · avg {formatPrice(data.cheapest.avg)}
                        </div>
                    </div>
                )}
                <button
                    onClick={fetchPrices}
                    title="Refresh prices"
                    className="ml-auto p-2 text-zinc-400 hover:text-white hover:bg-zinc-700 rounded-lg transition-colors"
                >
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                    </svg>
                </button>
            </div>

            {/* Today and tomorrow at the panel's quarter-hour resolution */}
            <svg viewBox="0 0 100 40" preserveAspectRatio="none" className="w-full h-32 bg-zinc-900/60 rounded-lg" role="img" aria-label="Spot prices today and tomorrow">
                {data.points.map((p, i) => {
                    const y = ((top - Math.max(p.price, 0)) / range) * 40;
                    const h = (Math.abs(p.price) / range) * 40;
                    const isNow = data.current?.start === p.start;
                    return (
                        <rect
                            key={p.start}
                            x={i * barWidth}
                            y={p.price >= 0 ? y : (zeroY / 100) * 40}
                            width={barWidth * 0.8}
                            height={Math.max(h, 0.2)}
                            className={isNow ? "fill-blue-400" : LEVEL_BAR[level(p.price)]}
                        >
                            <title>{`${hhmm(p.start)} ${formatPrice(p.price)} c/kWh`}</title>
                        </rect>
                    );
                })}
            </svg>

            <div>
                <StatsRow label="Today" stats={data.today} />
                <StatsRow label="Tomorrow" stats={data.tomorrow} />
            </div>

            <p className="text-xs text-zinc-500">
                c/kWh including VAT · day-ahead prices from ENTSO-E via fingrid-viewer
                {data.stale && <span className="text-yellow-400"> · last updated {new Date(data.fetched_at).toLocaleTimeString("fi-FI", { hour: "2-digit", minute: "2-digit" })}</span>}
            </p>
        </div>
    );
}
