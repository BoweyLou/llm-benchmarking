import React from "react";

const DEFAULT_TABS = [
  { id: "finder", label: "Use Case Finder", icon: "🔍" },
  { id: "browser", label: "Model Browser", icon: "📊" },
  { id: "compare", label: "Compare", icon: "⚖️" },
  { id: "history", label: "History", icon: "🕐" },
];

export default function TabNav({ activeTab, onTabChange, tabs = DEFAULT_TABS }) {
  return (
    <div className="sticky top-0 z-10 border-b border-gray-200 bg-white">
      <div className="mx-auto flex max-w-6xl gap-0 overflow-x-auto px-4">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            type="button"
            onClick={() => onTabChange?.(tab.id)}
            className={`flex items-center gap-1.5 whitespace-nowrap border-b-2 px-4 py-3 text-sm font-medium transition-all ${
              activeTab === tab.id
                ? "border-indigo-600 text-indigo-600"
                : "border-transparent text-gray-500 hover:border-gray-300 hover:text-gray-700"
            }`}
          >
            <span>{tab.icon}</span>
            <span>{tab.label}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
