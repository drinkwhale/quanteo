import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";
import "@testing-library/jest-dom/vitest";

// globals: true를 켜지 않았으므로 RTL의 자동 afterEach(cleanup) 등록이 동작하지 않음 — 명시적으로 등록
afterEach(() => {
  cleanup();
});

// jsdom은 HTMLDialogElement의 showModal/close를 구현하지 않으므로 테스트용 stub 필요
if (!HTMLDialogElement.prototype.showModal) {
  HTMLDialogElement.prototype.showModal = function showModal(
    this: HTMLDialogElement,
  ) {
    this.setAttribute("open", "");
  };
}
if (!HTMLDialogElement.prototype.close) {
  HTMLDialogElement.prototype.close = function close(this: HTMLDialogElement) {
    this.removeAttribute("open");
    this.dispatchEvent(new Event("close"));
  };
}
