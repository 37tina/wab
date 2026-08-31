import { afterEach, describe, expect, it, vi } from "vitest";
import { checkCodeArts, checkWorkspaceDir, createCodeArtsSession, fetchAgentStatus, formatApiError, isAbsoluteWindowsPath, loadTestWorkspaceDir, saveTestWorkspaceDir, updateAgentTarget } from "./codearts";

function jsonResponse(status: number, body: unknown) {
  return new Response(typeof body === "string" ? body : JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("formatApiError", () => {
  it("透传网关 502 的 error 与 detail", () => {
    const data = { error: "CodeArts Agent 服务不可达", detail: "connect ECONNREFUSED 127.0.0.1:27546" };
    expect(formatApiError(data, "fallback")).toBe("CodeArts Agent 服务不可达：connect ECONNREFUSED 127.0.0.1:27546");
  });

  it("只有 detail 时也展示真实原因", () => {
    expect(formatApiError({ detail: "boom" }, "fallback")).toBe("boom");
  });

  it("解析 Agent 自身的 message / error_msg / error.data.message", () => {
    expect(formatApiError({ message: "bad request" }, "fallback")).toBe("bad request");
    expect(formatApiError({ error_msg: "内部错误" }, "fallback")).toBe("内部错误");
    expect(formatApiError({ error: { data: { message: "会话不存在" } } }, "fallback")).toBe("会话不存在");
  });

  it("字符串原样返回，其余回落 fallback", () => {
    expect(formatApiError("直接错误", "fallback")).toBe("直接错误");
    expect(formatApiError(undefined, "fallback")).toBe("fallback");
    expect(formatApiError({}, "fallback")).toBe("fallback");
  });
});

describe("checkCodeArts", () => {
  it("网关 502 时保留 detail、hint 与目标地址", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse(502, {
      error: "CodeArts Agent 服务不可达",
      detail: "connect ECONNREFUSED 127.0.0.1:27546",
      target: "http://127.0.0.1:27546",
      hint: "目标端口没有服务在监听",
    })));
    const result = await checkCodeArts();
    expect(result.connected).toBe(false);
    expect(result.status).toBe(502);
    expect(result.message).toContain("ECONNREFUSED");
    expect(result.hint).toBe("目标端口没有服务在监听");
    expect(result.target).toBe("http://127.0.0.1:27546");
  });

  it("401 表示 Agent 在线但认证失败", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse(401, { error: "unauthorized" })));
    const result = await checkCodeArts();
    expect(result.connected).toBe(false);
    expect(result.message).toContain("认证失败");
  });

  it("健康检查通过时返回已连接", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse(200, { healthy: true, service: "AgentKernel", version: "1.0.0" })));
    const result = await checkCodeArts();
    expect(result.connected).toBe(true);
    expect(result.version).toBe("1.0.0");
  });

  it("网关本身不可达时给出可操作提示", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => {
      throw new TypeError("Failed to fetch");
    }));
    const result = await checkCodeArts();
    expect(result.connected).toBe(false);
    expect(result.status).toBe(0);
    expect(result.message).toContain("backend");
  });
});

describe("fetchAgentStatus / updateAgentTarget", () => {
  it("fetchAgentStatus 返回网关聚合状态", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse(200, {
      target: "http://127.0.0.1:16217",
      source: "discovered",
      reachable: true,
      healthy: true,
      latencyMs: 12,
      checkedAt: "2026-08-31T00:00:00.000Z",
      discovered: { port: 16217, pid: 24468, pidAlive: true },
    })));
    const status = await fetchAgentStatus();
    expect(status?.source).toBe("discovered");
    expect(status?.discovered?.port).toBe(16217);
  });

  it("fetchAgentStatus 在网关不可达时返回 null 而不是抛错", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => {
      throw new TypeError("Failed to fetch");
    }));
    expect(await fetchAgentStatus()).toBeNull();
  });

  it("updateAgentTarget 成功与后端校验失败两条路径", async () => {
    vi.stubGlobal("fetch", vi.fn(async (_url: string, init?: RequestInit) => {
      const body = JSON.parse(String(init?.body ?? "{}"));
      return body.baseUrl.includes("10.0.0.1")
        ? jsonResponse(400, { error: "Agent 与网关同机运行，地址只能是 127.0.0.1 / localhost / [::1]" })
        : jsonResponse(200, { manual: body.baseUrl });
    }));
    expect((await updateAgentTarget("http://127.0.0.1:16217")).ok).toBe(true);
    const rejected = await updateAgentTarget("http://10.0.0.1:80");
    expect(rejected.ok).toBe(false);
    expect(rejected.error).toContain("同机");
  });
});

describe("workspace directory helpers", () => {
  it("createCodeArtsSession 把目录放进查询参数并用正斜杠传递", async () => {
    const captured: { url?: string; body?: string } = {};
    vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
      captured.url = String(url);
      captured.body = String(init?.body ?? "");
      return jsonResponse(200, { id: "ses_new", title: "t" });
    }));
    const result = await createCodeArtsSession("标题", { username: "codearts", password: "" }, { directory: "D:\\测试" });
    expect(result.accepted).toBe(true);
    expect(captured.url).toBe(`/api/codearts/session?directory=${encodeURIComponent("D:/测试")}`);
    expect(captured.body).not.toContain("directory");
  });

  it("isAbsoluteWindowsPath 只接受盘符开头的本机绝对路径", () => {
    expect(isAbsoluteWindowsPath("D:\\code\\workspace")).toBe(true);
    expect(isAbsoluteWindowsPath("d:/code/workspace")).toBe(true);
    expect(isAbsoluteWindowsPath("code/workspace")).toBe(false);
    expect(isAbsoluteWindowsPath("\\\\server\\share")).toBe(false);
    expect(isAbsoluteWindowsPath("")).toBe(false);
  });

  it("测试工作区目录写入并读回 localStorage", () => {
    saveTestWorkspaceDir("D:\\code\\test-ws");
    expect(loadTestWorkspaceDir()).toBe("D:\\code\\test-ws");
    saveTestWorkspaceDir("");
    expect(loadTestWorkspaceDir()).toBe("");
  });

  it("checkWorkspaceDir 返回网关的存在性检查结果", async () => {
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      const path = decodeURIComponent(String(url).split("path=")[1] ?? "");
      return jsonResponse(200, { path, exists: path.includes("exists"), isDirectory: true });
    }));
    expect(await checkWorkspaceDir("D:\\exists-dir")).toEqual({ path: "D:\\exists-dir", exists: true, isDirectory: true });
    expect((await checkWorkspaceDir("D:\\missing-dir"))?.exists).toBe(false);
    vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("Failed to fetch"); }));
    expect(await checkWorkspaceDir("D:\\whatever")).toBeNull();
  });
});
