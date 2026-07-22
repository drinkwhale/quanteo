import { useState } from "react";

interface SymbolQuickPickProps {
  onSymbolSelect: (symbol: string) => void;
  recentSymbols?: string[];
}

export function SymbolQuickPick({
  onSymbolSelect,
  recentSymbols = [],
}: SymbolQuickPickProps) {
  const [inputValue, setInputValue] = useState("");

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setInputValue(e.currentTarget.value.toUpperCase());
  };

  const handleInputKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" && inputValue.trim().length === 6) {
      onSymbolSelect(inputValue.trim());
      setInputValue("");
    }
  };

  const handleChipClick = (symbol: string) => {
    onSymbolSelect(symbol);
  };

  return (
    <div className="space-y-3">
      <input
        type="text"
        placeholder="종목 코드 입력 (예: 005930)"
        value={inputValue}
        onChange={handleInputChange}
        onKeyDown={handleInputKeyDown}
        className="w-full px-3 py-2 bg-midnight-panel border border-border rounded text-white placeholder-muted focus:outline-none focus:border-signal-blue"
      />

      {recentSymbols.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {recentSymbols.map((symbol) => (
            <button
              key={symbol}
              onClick={() => handleChipClick(symbol)}
              className="px-2 py-1 bg-structural-line text-sm rounded hover:bg-signal-blue transition-colors"
            >
              {symbol}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
