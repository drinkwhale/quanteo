import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../api/client";
import { WatchlistPage } from "./WatchlistPage";

vi.mock("../api/client", () => ({
  api: {
    getWatchlist: vi.fn(),
  },
}));

describe("WatchlistPage", () => {
  beforeEach(() => {
    vi.mocked(api.getWatchlist).mockReset();
  });

  it("등록된 종목이 없으면 빈 상태 안내를 보여준다", async () => {
    vi.mocked(api.getWatchlist).mockResolvedValue({ items: [] });

    render(<WatchlistPage />);

    await waitFor(() =>
      expect(
        screen.getByText(/아직 등록된 관심종목이 없습니다/),
      ).toBeInTheDocument(),
    );
  });

  it("등록된 종목을 종목명·등록일·출처·스코어와 함께 표로 보여준다", async () => {
    vi.mocked(api.getWatchlist).mockResolvedValue({
      items: [
        {
          symbol: "005930",
          name: "삼성전자",
          added_at: "2026-09-17T09:00:00+00:00",
          source: "screener",
          score_snapshot: { growth: 4, valuation: 2 },
        },
      ],
    });

    render(<WatchlistPage />);

    await waitFor(() =>
      expect(screen.getByText("삼성전자")).toBeInTheDocument(),
    );
    expect(screen.getByText("005930")).toBeInTheDocument();
    expect(screen.getByText("screener")).toBeInTheDocument();
    expect(screen.getByText("growth 4 · valuation 2")).toBeInTheDocument();
  });

  it("API 에러 시 에러 메시지를 보여준다", async () => {
    vi.mocked(api.getWatchlist).mockRejectedValue(
      new Error("500 Internal Server Error"),
    );

    render(<WatchlistPage />);

    await waitFor(() =>
      expect(screen.getByText("500 Internal Server Error")).toBeInTheDocument(),
    );
  });
});
