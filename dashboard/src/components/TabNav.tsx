type Tab = {
  id: string;
  label: string;
};

interface TabNavProps {
  tabs: Tab[];
  activeTab: string;
  onTabChange: (id: string) => void;
}

export function TabNav({ tabs, activeTab, onTabChange }: TabNavProps) {
  return (
    <nav
      role="tablist"
      className="flex gap-6 border-b border-border px-4 py-2"
      aria-label="탭 네비게이션"
    >
      {tabs.map((tab) => (
        <button
          key={tab.id}
          role="tab"
          aria-selected={activeTab === tab.id}
          aria-controls={`tabpanel-${tab.id}`}
          onClick={() => onTabChange(tab.id)}
          className={`
            px-0.5 py-2 text-sm font-medium transition-colors
            border-b-2 -mb-2
            focus-visible:outline-signal-blue focus-visible:outline-offset-2
            ${
              activeTab === tab.id
                ? "border-accent text-white"
                : "border-transparent text-muted hover:text-white"
            }
          `}
        >
          {tab.label}
        </button>
      ))}
    </nav>
  );
}
