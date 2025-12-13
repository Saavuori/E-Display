"use client";

import { useState, useEffect } from "react";
import Image from "next/image";

interface DisplayPreviewProps {
    apiBase: string;
}

export default function DisplayPreview({ apiBase }: DisplayPreviewProps) {
    const [imageData, setImageData] = useState<string | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

    useEffect(() => {
        const fetchPreview = async () => {
            setLoading(true);
            try {
                const res = await fetch(`${apiBase}/api/preview/base64`);
                if (!res.ok) throw new Error("Failed to fetch preview");
                const data = await res.json();
                setImageData(data.image);
                setLastUpdated(new Date());
                setError(null);
            } catch (err) {
                setError("Could not load preview. Make sure the backend is running.");
                console.error(err);
            } finally {
                setLoading(false);
            }
        };

        fetchPreview();
    }, [apiBase]);

    if (loading) {
        return (
            <div className="aspect-[5/3] bg-zinc-800 rounded-xl flex items-center justify-center">
                <div className="text-center">
                    <svg className="animate-spin h-8 w-8 mx-auto mb-3 text-blue-400" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                    </svg>
                    <p className="text-zinc-400">Generating preview...</p>
                </div>
            </div>
        );
    }

    if (error) {
        return (
            <div className="aspect-[5/3] bg-zinc-800 rounded-xl flex items-center justify-center border-2 border-dashed border-red-500/30">
                <div className="text-center p-6">
                    <svg className="w-12 h-12 mx-auto mb-3 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                    </svg>
                    <p className="text-red-400 mb-2">Preview Error</p>
                    <p className="text-sm text-zinc-500">{error}</p>
                </div>
            </div>
        );
    }

    return (
        <div>
            {/* E-Paper Frame */}
            <div className="relative bg-zinc-950 rounded-2xl p-4 shadow-2xl">
                {/* Display bezel */}
                <div className="absolute inset-0 rounded-2xl bg-gradient-to-br from-zinc-700 to-zinc-900 p-1">
                    <div className="w-full h-full rounded-xl bg-zinc-950" />
                </div>

                {/* Screen content */}
                <div className="relative rounded-xl overflow-hidden bg-white shadow-inner">
                    {imageData && (
                        <img
                            src={imageData}
                            alt="E-Paper Display Preview"
                            className="w-full h-auto"
                            style={{ imageRendering: "auto" }}
                        />
                    )}
                </div>
            </div>

            {/* Status bar */}
            <div className="mt-4 flex items-center justify-between text-sm text-zinc-500">
                <div className="flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
                    <span>Preview Active</span>
                </div>
                {lastUpdated && (
                    <span>
                        Last updated: {lastUpdated.toLocaleTimeString()}
                    </span>
                )}
            </div>

            {/* Display specs */}
            <div className="mt-4 grid grid-cols-3 gap-4 p-4 bg-zinc-800/50 rounded-xl text-center text-sm">
                <div>
                    <div className="text-zinc-400">Resolution</div>
                    <div className="font-mono font-semibold">800×480</div>
                </div>
                <div>
                    <div className="text-zinc-400">Colors</div>
                    <div className="font-mono font-semibold">B/W/R</div>
                </div>
                <div>
                    <div className="text-zinc-400">Size</div>
                    <div className="font-mono font-semibold">7.5&quot;</div>
                </div>
            </div>
        </div>
    );
}
