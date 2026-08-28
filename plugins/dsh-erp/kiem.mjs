/**
 * Kiểm mã TypeScript của plugin, không cần dựng toolchain.
 *
 * Chạy: node kiem.mjs      (Node >= 22.18 bóc kiểu TypeScript sẵn)
 *
 * VÌ SAO KHÔNG DÙNG VITEST HAY JEST
 * ---------------------------------
 * Bộ test của dự án là pytest. Thêm một bộ chạy test thứ hai kèm
 * node_modules cho hai file TypeScript là chi phí lớn hơn thứ nó canh.
 *
 * `tests/test_plugin_dsh_erp.py` gọi file này qua `node`, và BỎ QUA nếu máy
 * không có node — để CI không đỏ vì lý do không liên quan, nhưng máy nào có
 * node thì vẫn được canh.
 *
 * Chỉ kiểm phần LOGIC THUẦN. Phần gọi mạng và phần khuôn plugin Cordis nằm
 * ngoài tầm — xem README.
 */
import { ClientMcp, LoiMcp, bocPhanHoi } from "./src/mcp-client.ts";

let ok = 0;
const hong = [];

function kiem(ten, f) {
  try {
    f();
    ok++;
  } catch (e) {
    hong.push(`${ten}: ${e.message}`);
  }
}

function bang(a, b) {
  const x = JSON.stringify(a);
  const y = JSON.stringify(b);
  if (x !== y) throw new Error(`${x} != ${y}`);
}

function phaiNem(f) {
  try {
    f();
  } catch (e) {
    if (e instanceof LoiMcp) return;
    throw new Error(`ném sai loại: ${e.constructor.name}`);
  }
  throw new Error("lẽ ra phải ném LoiMcp");
}

// --- bocPhanHoi: chỗ dễ sai nhất trong file -------------------------
// Máy chủ dùng transport streamable-http nên CÙNG một endpoint trả JSON
// thuần hoặc text/event-stream tuỳ lúc. Chỉ JSON.parse thẳng là hỏng ở dạng
// thứ hai — và hỏng theo kiểu khó lần, vì chỉ xảy ra với một số lời gọi.

kiem("JSON thuần", () => bang(bocPhanHoi('{"result":{"x":1}}').result, { x: 1 }));

kiem("SSE một dòng data", () =>
  bang(bocPhanHoi('event: message\ndata: {"result":{"x":2}}\n\n').result, { x: 2 }));

kiem("SSE nhiều gói thì lấy gói cuối", () =>
  bang(bocPhanHoi('data: {"result":1}\n\ndata: {"result":9}\n\n').result, 9));

kiem("SSE bỏ qua [DONE]", () =>
  bang(bocPhanHoi('data: {"result":5}\n\ndata: [DONE]\n').result, 5));

kiem("SSE không có dòng dữ liệu nào thì ném", () =>
  phaiNem(() => bocPhanHoi("event: ping\n")));

kiem("giữ nguyên error của JSON-RPC", () =>
  bang(bocPhanHoi('{"error":{"code":-32601,"message":"x"}}').error.code, -32601));

// --- ClientMcp: nổ sớm khi thiếu token ------------------------------
// Nổ lúc dựng chứ không để tới lời gọi đầu: thiếu token thì máy chủ trả 401,
// và thông báo đó rất dễ bị hiểu nhầm thành "sai đường dẫn".

kiem("thiếu token thì ném ngay lúc dựng", () =>
  phaiNem(() => new ClientMcp({ goc: "http://x", token: "" })));

kiem("có token thì dựng được", () => {
  new ClientMcp({ goc: "http://x", token: "t" });
});

// --- Báo cáo --------------------------------------------------------

if (hong.length > 0) {
  console.error(`${hong.length} HỎNG:`);
  for (const d of hong) console.error("  - " + d);
  process.exit(1);
}
console.log(`${ok} phép kiểm đều xanh`);
