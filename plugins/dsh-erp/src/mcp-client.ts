/**
 * Client MCP tối giản, không phụ thuộc thư viện nào.
 *
 * VÌ SAO TỰ VIẾT THAY VÌ DÙNG SDK
 * --------------------------------
 * Phần này phải đúng bất kể DeepSeek Harness đổi API thế nào. Nó chỉ nói
 * JSON-RPC 2.0 qua HTTP tới `/mcp/` của máy chủ Marketing Agent — một giao
 * thức đã chốt, không phải một API đang ở developer preview.
 *
 * Toàn bộ phần chưa xác minh được nằm ở `index.ts`, tách hẳn ra khỏi đây.
 *
 * RANH GIỚI
 * ---------
 * Chỉ gọi công cụ ĐỌC. Danh sách nằm ở `cong-cu.json`, và có test Python
 * (`tests/test_plugin_dsh_erp.py`) canh để nó không lẫn công cụ ghi vào.
 */

export interface CauHinhMcp {
  /** Ví dụ: "http://127.0.0.1:8000" */
  goc: string;
  /** MCP_TOKEN. Sinh bằng `python -m scripts.sinh_token MCP_TOKEN`. */
  token: string;
  /** Bỏ cuộc sau bao nhiêu mili-giây. Mặc định 10 giây. */
  hanCho?: number;
}

export class LoiMcp extends Error {
  // Khai báo trường tường minh, KHÔNG dùng parameter property
  // (`constructor(readonly maLoi: number)`).
  //
  // Parameter property cần trình biên dịch TypeScript đầy đủ. Node bóc kiểu
  // sẵn (`node file.ts`) và các bộ gói ở chế độ strip-only đều từ chối nó:
  //   ERR_UNSUPPORTED_TYPESCRIPT_SYNTAX
  // Tránh nó là đổi lấy việc file này chạy và kiểm được mà không cần dựng
  // toolchain — đáng, cho một plugin chỉ có hai file.
  readonly maLoi?: number;

  constructor(message: string, maLoi?: number) {
    super(message);
    this.name = "LoiMcp";
    this.maLoi = maLoi;
  }
}

export class ClientMcp {
  private soThuTu = 0;
  private readonly cauHinh: CauHinhMcp;

  constructor(cauHinh: CauHinhMcp) {
    this.cauHinh = cauHinh;
    if (!cauHinh.token) {
      // Nổ ngay lúc dựng chứ không để tới lời gọi đầu tiên: thiếu token thì
      // máy chủ trả 401 và thông báo đó dễ bị hiểu nhầm thành "sai đường dẫn".
      throw new LoiMcp(
        "Thiếu MCP_TOKEN. Sinh bằng: python -m scripts.sinh_token MCP_TOKEN",
      );
    }
  }

  /** Gọi một công cụ MCP. Trả về phần `content` đã bóc khỏi vỏ JSON-RPC. */
  async goiCongCu(ten: string, thamSo: Record<string, unknown> = {}): Promise<unknown> {
    return this.goi("tools/call", { name: ten, arguments: thamSo });
  }

  /** Liệt kê công cụ máy chủ đang có. Dùng để kiểm khớp lúc khởi động. */
  async danhSachCongCu(): Promise<string[]> {
    const kq = (await this.goi("tools/list", {})) as { tools?: { name: string }[] };
    return (kq.tools ?? []).map((t) => t.name);
  }

  private async goi(phuongThuc: string, thamSo: unknown): Promise<unknown> {
    const huy = new AbortController();
    const dongHo = setTimeout(() => huy.abort(), this.cauHinh.hanCho ?? 10_000);

    try {
      const res = await fetch(new URL("/mcp/", this.cauHinh.goc), {
        method: "POST",
        headers: {
          "content-type": "application/json",
          // Máy chủ mount streamable-http; nó đòi client nhận được cả hai.
          accept: "application/json, text/event-stream",
          authorization: `Bearer ${this.cauHinh.token}`,
        },
        body: JSON.stringify({
          jsonrpc: "2.0",
          id: ++this.soThuTu,
          method: phuongThuc,
          params: thamSo,
        }),
        signal: huy.signal,
      });

      if (res.status === 401) {
        throw new LoiMcp("MCP_TOKEN sai hoặc đã đổi.", 401);
      }
      if (res.status === 404) {
        throw new LoiMcp("MCP chưa bật trên máy chủ (thiếu MCP_TOKEN bên đó).", 404);
      }
      if (!res.ok) {
        throw new LoiMcp(`Máy chủ MCP trả ${res.status}`, res.status);
      }

      const goi = bocPhanHoi(await res.text());
      if (goi.error) {
        throw new LoiMcp(goi.error.message ?? "Lỗi MCP không rõ", goi.error.code);
      }
      return goi.result;
    } finally {
      clearTimeout(dongHo);
    }
  }
}

interface PhanHoiJsonRpc {
  result?: unknown;
  error?: { code?: number; message?: string };
}

/**
 * Bóc thân phản hồi: có thể là JSON thuần, có thể là Server-Sent Events.
 *
 * Máy chủ dùng transport `streamable-http`, nên cùng một endpoint trả JSON
 * hoặc `text/event-stream` tuỳ lúc. Chỉ `JSON.parse` thẳng là hỏng ở dạng
 * thứ hai — và hỏng theo kiểu khó lần, vì nó chỉ xảy ra với một số lời gọi.
 *
 * Hàm này để `export` là có chủ ý: nó chứa phần logic dễ sai nhất trong file
 * và cần test được mà không cần máy chủ.
 */
export function bocPhanHoi(than: string): PhanHoiJsonRpc {
  const cat = than.trim();
  if (!cat.startsWith("event:") && !cat.startsWith("data:")) {
    return JSON.parse(cat) as PhanHoiJsonRpc;
  }
  // SSE: lấy dòng `data:` cuối cùng có nội dung.
  const dong = cat
    .split("\n")
    .map((d) => d.trim())
    .filter((d) => d.startsWith("data:"))
    .map((d) => d.slice("data:".length).trim())
    .filter((d) => d && d !== "[DONE]");
  if (dong.length === 0) {
    throw new LoiMcp("Phản hồi SSE không có dòng dữ liệu nào");
  }
  return JSON.parse(dong[dong.length - 1]) as PhanHoiJsonRpc;
}
