/**
 * 캔들(OHLCV) 데이터 항목
 */
export interface CandleItem {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

/**
 * 캔들 데이터 조회 응답
 */
export interface CandleList {
  items: CandleItem[];
}

/**
 * 캔들 조회 API 에러
 */
export class CandleApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public details?: unknown,
  ) {
    super(message);
    this.name = "CandleApiError";
  }
}

/**
 * 캔들 조회 파라미터 검증
 */
function validateCandleParams(
  symbol: string,
  interval: "1m" | "1d",
  count: number,
): void {
  if (!symbol || !/^\d{6}$/.test(symbol)) {
    throw new Error("종목코드는 6자리 숫자여야 합니다");
  }

  if (!["1m", "1d"].includes(interval)) {
    throw new Error('interval은 "1m" 또는 "1d"만 지원합니다');
  }

  if (!Number.isInteger(count) || count < 1 || count > 200) {
    throw new Error("count는 1~200 사이의 정수여야 합니다");
  }
}

/**
 * 캔들 데이터 응답 검증
 */
function validateCandleResponse(data: unknown): asserts data is CandleList {
  if (!data || typeof data !== "object") {
    throw new Error("유효하지 않은 응답 형식입니다");
  }

  const obj = data as Record<string, unknown>;
  if (!Array.isArray(obj.items)) {
    throw new Error("응답에 items 배열이 없습니다");
  }

  obj.items.forEach((item, index) => {
    if (!item || typeof item !== "object") {
      throw new Error(`items[${index}]이 유효하지 않습니다`);
    }

    const candle = item as Record<string, unknown>;
    const required = ["timestamp", "open", "high", "low", "close", "volume"];
    for (const field of required) {
      if (!(field in candle)) {
        throw new Error(`items[${index}].${field} 필드가 누락되었습니다`);
      }
    }

    if (typeof candle.timestamp !== "string") {
      throw new Error(`items[${index}].timestamp은 문자열이어야 합니다`);
    }

    const numFields = ["open", "high", "low", "close", "volume"];
    for (const field of numFields) {
      if (typeof candle[field] !== "number") {
        throw new Error(`items[${index}].${field}은 숫자여야 합니다`);
      }
    }
  });
}

/**
 * Toss OpenAPI에서 캔들 데이터 조회
 *
 * @param symbol 종목코드 (6자리 숫자, 예: "005930")
 * @param interval 시간단위 ("1m" | "1d")
 * @param count 조회 개수 (1~200, 기본값 100)
 * @param before 조회 종료 시점 (ISO 8601, 선택사항)
 * @param adjusted 수정주가 적용 여부 (기본값 true)
 * @returns 캔들 데이터 목록
 * @throws CandleApiError 백엔드 에러 또는 네트워크 오류
 */
export async function getCandles(
  symbol: string,
  interval: "1m" | "1d" = "1d",
  count: number = 100,
  before?: string,
  adjusted: boolean = true,
): Promise<CandleList> {
  // 입력값 검증
  validateCandleParams(symbol, interval, count);

  // 요청 파라미터 구성
  const params = new URLSearchParams({
    symbol,
    interval,
    count: String(count),
    adjusted: String(adjusted),
  });

  if (before) {
    params.append("before", before);
  }

  const url = `/api/candles?${params.toString()}`;

  try {
    const response = await fetch(url);

    if (!response.ok) {
      let details: unknown;
      try {
        details = await response.json();
      } catch {
        // JSON 파싱 실패 시 무시
      }

      const message =
        response.status === 503
          ? "시장 데이터 서비스를 사용할 수 없습니다"
          : response.status === 502
            ? "백엔드 서비스 오류가 발생했습니다"
            : response.status === 422
              ? "요청 파라미터가 유효하지 않습니다"
              : `캔들 조회 실패 (${response.status})`;

      throw new CandleApiError(message, response.status, details);
    }

    const data = await response.json();

    // 응답 형식 검증
    validateCandleResponse(data);

    return data;
  } catch (error) {
    if (error instanceof CandleApiError) {
      throw error;
    }

    if (error instanceof TypeError && error.message.includes("fetch")) {
      throw new CandleApiError(
        "네트워크 오류로 캔들 데이터를 조회할 수 없습니다",
        0,
        error,
      );
    }

    if (error instanceof SyntaxError) {
      throw new CandleApiError(
        "캔들 데이터 형식이 유효하지 않습니다",
        200,
        error,
      );
    }

    if (error instanceof Error) {
      throw new CandleApiError(error.message, 0, error);
    }

    throw new CandleApiError("알 수 없는 오류가 발생했습니다", 0, error);
  }
}
