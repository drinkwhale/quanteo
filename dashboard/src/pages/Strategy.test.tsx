import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../api/client";
import { StrategyPage } from "./Strategy";

// T087 완료조건: 킬스위치 클릭 → dialog 열림 → 확인 → API 호출, ESC → dialog 닫힘 + API 미호출
vi.mock("../api/client", () => ({
  api: {
    kill: vi.fn(),
  },
}));

describe("StrategyPage 킬스위치 확인 다이얼로그", () => {
  beforeEach(() => {
    vi.mocked(api.kill).mockReset();
  });

  it("킬스위치 클릭 → dialog 열림 → 확인 클릭 → kill API 호출", async () => {
    vi.mocked(api.kill).mockResolvedValue({ success: true, message: "완료" });
    const user = userEvent.setup();
    const onKill = vi.fn();

    render(
      <StrategyPage
        logs={[]}
        positions={[]}
        stockNames={new Map()}
        onKill={onKill}
      />,
    );

    const dialog = document.querySelector("dialog") as HTMLDialogElement;
    expect(dialog.hasAttribute("open")).toBe(false);

    await user.click(screen.getByRole("button", { name: "킬스위치" }));
    expect(dialog.hasAttribute("open")).toBe(true);

    await user.click(screen.getByRole("button", { name: "킬스위치 활성화" }));

    await waitFor(() => expect(api.kill).toHaveBeenCalledTimes(1));
    expect(onKill).toHaveBeenCalledTimes(1);
  });

  it("ESC(cancel 이벤트) → dialog 닫힘 + kill API 미호출", async () => {
    const user = userEvent.setup();

    render(
      <StrategyPage
        logs={[]}
        positions={[]}
        stockNames={new Map()}
        onKill={vi.fn()}
      />,
    );

    await user.click(screen.getByRole("button", { name: "킬스위치" }));

    const dialog = document.querySelector("dialog") as HTMLDialogElement;
    expect(dialog.hasAttribute("open")).toBe(true);

    // jsdom은 native ESC → cancel 이벤트를 자동 발생시키지 않으므로 수동 dispatch
    fireEvent(dialog, new Event("cancel", { cancelable: true }));

    await waitFor(() => expect(dialog.hasAttribute("open")).toBe(false));
    expect(api.kill).not.toHaveBeenCalled();
  });
});
