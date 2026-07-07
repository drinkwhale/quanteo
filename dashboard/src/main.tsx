import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
// 가변 폰트 + 유니코드 레인지 동적 서브셋 — 실제 렌더링에 쓰인 한글 음절 블록만 다운로드된다
import "pretendard/dist/web/variable/pretendardvariable-dynamic-subset.css";
import "./index.css";

const root = document.getElementById("root");
if (!root) throw new Error("#root element not found");

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
