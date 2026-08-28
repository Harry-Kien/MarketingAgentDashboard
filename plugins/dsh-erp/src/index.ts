/**
 * Điểm vào plugin cho DeepSeek Harness.
 *
 * ============================================================
 *  PHẦN NÀY CHƯA XÁC MINH ĐƯỢC. ĐỌC README TRƯỚC KHI DÙNG.
 * ============================================================
 *
 * `mcp-client.ts` nói JSON-RPC qua HTTP — một giao thức đã chốt, đúng bất kể
 * dsh đổi thế nào. File NÀY thì khác: nó phải khớp khuôn plugin Cordis của
 * dsh, mà khuôn đó chưa kiểm được (trang tài liệu là SPA không fetch được,
 * raw README trả 404, và dsh đang ở developer preview nên API sẽ đổi).
 *
 * Nên hàm dưới đây viết theo mô tả chung "plugin là một hàm nhận Cordis
 * context, khai báo thứ nó cung cấp và thứ nó cần". Tên service và chữ ký
 * `ctx.*` PHẢI đối chiếu với bản dsh bạn cài trước khi chạy thật.
 *
 * Nếu dsh đã có sẵn plugin MCP client, hãy bỏ hẳn file này và chỉ khai báo
 * máy chủ MCP trong cấu hình dsh — ít mã hơn thì ít thứ hỏng hơn.
 */

import keKhai from "../cong-cu.json";
import { ClientMcp, LoiMcp } from "./mcp-client.js";

export interface CauHinhPlugin {
  goc?: string;
  token?: string;
}

/** Cordis context. `unknown` vì chữ ký thật chưa xác minh — xem đầu file. */
type CordisContext = Record<string, any>;

export const name = keKhai.ten;

export function apply(ctx: CordisContext, cauHinh: CauHinhPlugin = {}): void {
  const client = new ClientMcp({
    goc: cauHinh.goc ?? process.env.MARKETING_AGENT_URL ?? "http://127.0.0.1:8000",
    token: cauHinh.token ?? process.env.MCP_TOKEN ?? "",
  });

  // Đối chiếu kê khai với máy chủ NGAY lúc nạp plugin.
  //
  // Không có bước này thì đổi tên một công cụ bên Python chỉ lộ ra lúc người
  // dùng hỏi câu đầu tiên, dưới dạng "tool not found" — và người dùng thì
  // không biết đó là lỗi cấu hình hay lỗi mạng.
  void client
    .danhSachCongCu()
    .then((coThat) => {
      const thieu = keKhai.cong_cu.filter((t) => !coThat.includes(t));
      if (thieu.length > 0) {
        ctx.logger?.warn?.(
          `[${keKhai.ten}] máy chủ không có các công cụ đã khai: ${thieu.join(", ")}`,
        );
      }
    })
    .catch((loi: unknown) => {
      const thongDiep = loi instanceof LoiMcp ? loi.message : String(loi);
      ctx.logger?.warn?.(`[${keKhai.ten}] chưa nối được máy chủ MCP: ${thongDiep}`);
    });

  for (const ten of keKhai.cong_cu) {
    ctx.tool?.(ten, (thamSo: Record<string, unknown>) => client.goiCongCu(ten, thamSo));
  }
}

export default { name, apply };
