"use client";

import { useState, ReactNode } from "react";

interface CollapsibleSectionProps {
    title: string;
    icon?: ReactNode;
    defaultOpen?: boolean;
    children: ReactNode;
    headerColor?: string;
}

export default function CollapsibleSection({
    title,
    icon,
    defaultOpen = true,
    children,
    headerColor = "text-blue-400"
}: CollapsibleSectionProps) {
    const [isOpen, setIsOpen] = useState(defaultOpen);

    return (
        <div className="bg-zinc-900 border border-zinc-800 rounded-2xl overflow-hidden">
            {/* Header */}
            <button
                onClick={() => setIsOpen(!isOpen)}
                className="w-full p-6 flex items-center justify-between hover:bg-zinc-800/50 transition-colors"
            >
                <h2 className={`text-xl font-semibold flex items-center gap-2 ${headerColor}`}>
                    {icon}
                    {title}
                </h2>
                <svg
                    className={`w-5 h-5 text-zinc-400 transition-transform duration-200 ${isOpen ? "rotate-180" : ""
                        }`}
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                >
                    <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M19 9l-7 7-7-7"
                    />
                </svg>
            </button>

            {/* Content */}
            <div
                className={`transition-all duration-300 ease-in-out ${isOpen ? "max-h-[2000px] opacity-100" : "max-h-0 opacity-0 overflow-hidden"
                    }`}
            >
                <div className="p-6 pt-0">{children}</div>
            </div>
        </div>
    );
}
