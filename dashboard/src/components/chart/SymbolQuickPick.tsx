import { useId, useState } from "react";
import { cn } from "../../lib/utils";

const SYMBOL_LENGTH = 6;

interface SymbolQuickPickProps {
  /** 보유·최근 거래 종목 — 클릭 한 번으로 차트를 바꾼다 */
  symbols: string[];
  names: Map<string, string>;
  selected: string | null;
  onSymbolSelect: (symbol: string) => void;
}

export function SymbolQuickPick({
  symbols,
  names,
  selected,
  onSymbolSelect,
}: SymbolQuickPickProps) {
  const [inputValue, setInputValue] = useState("");
  const inputId = useId();
  const isValid = inputValue.length === SYMBOL_LENGTH;

  return (
    <>
      <form
        className="border-b border-line p-3"
        onSubmit={(e) => {
          e.preventDefault();
          if (!isValid) return;
          onSymbolSelect(inputValue);
          setInputValue("");
        }}
      >
        <label htmlFor={inputId} className="mb-1 block text-xs text-muted">
          종목코드로 조회
        </label>
        <div className="flex gap-2">
          <input
            id={inputId}
            type="text"
            placeholder="005930"
            maxLength={SYMBOL_LENGTH}
            value={inputValue}
            onChange={(e) =>
              setInputValue(e.currentTarget.value.trim().toUpperCase())
            }
            className="field font-mono"
          />
          <button type="submit" disabled={!isValid} className="btn shrink-0">
            조회
          </button>
        </div>
      </form>

      {symbols.length === 0 ? (
        <p className="state-msg">
          보유·거래 종목이 생기면 여기에 바로가기가 만들어집니다.
        </p>
      ) : (
        <ul className="no-scrollbar flex gap-1 overflow-x-auto p-2 lg:flex-col lg:gap-0.5 lg:overflow-visible">
          {symbols.map((symbol) => {
            const name = names.get(symbol);
            const isSelected = symbol === selected;
            return (
              <li key={symbol} className="shrink-0">
                <button
                  type="button"
                  aria-pressed={isSelected}
                  onClick={() => onSymbolSelect(symbol)}
                  className={cn(
                    "flex w-full items-baseline justify-between gap-3 rounded-md px-2.5 py-1.5 text-left text-data transition-colors duration-150",
                    isSelected
                      ? "bg-raised font-semibold text-ink"
                      : "text-dim hover:bg-raised/60 hover:text-ink",
                  )}
                >
                  <span className="truncate">{name ?? symbol}</span>
                  {name && (
                    <span className="font-mono text-2xs text-muted">
                      {symbol}
                    </span>
                  )}
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </>
  );
}
