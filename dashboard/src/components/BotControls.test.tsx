import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../api/client";
import type { BotStatus } from "../api/types";
import { BotControls } from "./BotControls";

vi.mock("../api/client", () => ({
  api: {
    kill: vi.fn(),
    pause: vi.fn(),
    resume: vi.fn(),
  },
}));

const RUNNING: BotStatus = {
  running: true,
  halt_level: "none",
  env: "vps",
  market: "domestic",
  uptime_seconds: 60,
  started_at: null,
};

describe("BotControls", () => {
  beforeEach(() => {
    vi.mocked(api.kill).mockReset();
    vi.mocked(api.pause).mockReset();
    vi.mocked(api.resume).mockReset();
  });

  // T087 완료조건: 킬스위치 클릭 → dialog 열림 → 확인 → API 호출
  it("킬스위치 클릭 → dialog 열림 → 확인 클릭 → kill API 호출 후 상태를 다시 읽는다", async () => {
    vi.mocked(api.kill).mockResolvedValue({ success: true, message: "완료" });
    const user = userEvent.setup();
    const onAction = vi.fn();

    render(<BotControls status={RUNNING} onAction={onAction} />);

    const dialog = document.querySelector("dialog") as HTMLDialogElement;
    expect(dialog.hasAttribute("open")).toBe(false);

    await user.click(screen.getByRole("button", { name: "킬스위치" }));
    expect(dialog.hasAttribute("open")).toBe(true);

    await user.click(screen.getByRole("button", { name: "킬스위치 활성화" }));

    await waitFor(() => expect(api.kill).toHaveBeenCalledTimes(1));
    expect(onAction).toHaveBeenCalledTimes(1);
  });

  // T087 완료조건: ESC → dialog 닫힘 + API 미호출
  it("ESC(cancel 이벤트) → dialog 닫힘 + kill API 미호출", async () => {
    const user = userEvent.setup();

    render(<BotControls status={RUNNING} onAction={vi.fn()} />);

    await user.click(screen.getByRole("button", { name: "킬스위치" }));

    const dialog = document.querySelector("dialog") as HTMLDialogElement;
    expect(dialog.hasAttribute("open")).toBe(true);

    // jsdom은 native ESC → cancel 이벤트를 자동 발생시키지 않으므로 수동 dispatch
    fireEvent(dialog, new Event("cancel", { cancelable: true }));

    await waitFor(() => expect(dialog.hasAttribute("open")).toBe(false));
    expect(api.kill).not.toHaveBeenCalled();
  });

  it("가동 중에는 일시정지를, 정지 상태에서는 재개를 보여준다", () => {
    const { rerender } = render(
      <BotControls status={RUNNING} onAction={vi.fn()} />,
    );
    expect(screen.getByRole("button", { name: "일시정지" })).toBeEnabled();
    expect(screen.queryByRole("button", { name: "재개" })).toBeNull();

    rerender(
      <BotControls
        status={{ ...RUNNING, halt_level: "kill" }}
        onAction={vi.fn()}
      />,
    );
    expect(screen.getByRole("button", { name: "재개" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "킬스위치" })).toBeDisabled();
  });

  it("API가 실패하면 실패 메시지를 남기고 상태를 다시 읽지 않는다", async () => {
    vi.mocked(api.pause).mockRejectedValue(
      new Error("503 Service Unavailable"),
    );
    const user = userEvent.setup();
    const onAction = vi.fn();

    render(<BotControls status={RUNNING} onAction={onAction} />);

    await user.click(screen.getByRole("button", { name: "일시정지" }));
    // 다이얼로그 확인 버튼도 이름이 "일시정지"라 dialog 안에서 찾는다
    const dialog = document.querySelector("dialog") as HTMLDialogElement;
    const confirm = Array.from(dialog.querySelectorAll("button")).find(
      (b) => b.textContent === "일시정지",
    ) as HTMLButtonElement;
    await user.click(confirm);

    await waitFor(() =>
      expect(screen.getByRole("status")).toHaveTextContent(
        "503 Service Unavailable",
      ),
    );
    expect(onAction).not.toHaveBeenCalled();
  });
});
