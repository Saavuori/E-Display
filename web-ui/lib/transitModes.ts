// Icon and badge colours for HSL transport modes (GTFS `mode` values).

export function getModeIcon(mode: string): string {
    switch (mode) {
        case "TRAM": return "🚊";
        case "BUS": return "🚌";
        case "SUBWAY": return "🚇";
        case "RAIL": return "🚆";
        case "FERRY": return "⛴️";
        default: return "🚏";
    }
}

export function getModeColor(mode: string): string {
    switch (mode) {
        case "TRAM": return "bg-green-500/20 text-green-400 border-green-500/30";
        case "BUS": return "bg-blue-500/20 text-blue-400 border-blue-500/30";
        case "SUBWAY": return "bg-orange-500/20 text-orange-400 border-orange-500/30";
        case "RAIL": return "bg-purple-500/20 text-purple-400 border-purple-500/30";
        case "FERRY": return "bg-cyan-500/20 text-cyan-400 border-cyan-500/30";
        default: return "bg-zinc-500/20 text-zinc-400 border-zinc-500/30";
    }
}
