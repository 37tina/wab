import { useEffect, useState } from "react";
import { fetchAgentStatus, type AgentStatus } from "./codearts";

// 模块级共享连接状态：任何组件挂载都会订阅同一份数据，轮询在全局只跑一份。
// 状态点（顶栏）、连接对话框、运行控制台看到的是同一个结果，不再各查各的。

const POLL_MS = 20_000;

let current: AgentStatus | null = null;
let inflight: Promise<void> | null = null;
let pollTimer: number | undefined;
const listeners = new Set<(status: AgentStatus | null) => void>();

function emit() {
  listeners.forEach((listener) => listener(current));
}

/** 立即刷新一次状态（并发调用合并为一次请求） */
export function refreshAgentStatus(): Promise<void> {
  if (inflight) return inflight;
  inflight = fetchAgentStatus()
    .then((status) => {
      current = status;
      emit();
    })
    .finally(() => {
      inflight = null;
    });
  return inflight;
}

function startPolling() {
  if (pollTimer !== undefined) return;
  pollTimer = window.setInterval(() => {
    void refreshAgentStatus();
  }, POLL_MS);
  window.addEventListener("focus", handleFocus);
  window.addEventListener("online", handleFocus);
}

function handleFocus() {
  void refreshAgentStatus();
}

export function useAgentConnection() {
  const [status, setStatus] = useState<AgentStatus | null>(current);
  const [refreshing, setRefreshing] = useState(false);
  useEffect(() => {
    listeners.add(setStatus);
    startPolling();
    setRefreshing(true);
    void refreshAgentStatus().finally(() => setRefreshing(false));
    return () => {
      listeners.delete(setStatus);
    };
  }, []);
  const refresh = () => {
    setRefreshing(true);
    return refreshAgentStatus().finally(() => setRefreshing(false));
  };
  return { status, refreshing, refresh };
}

/** 把 source 翻成界面文案 */
export function agentSourceLabel(source: AgentStatus["source"] | undefined): string {
  switch (source) {
    case "env":
      return "环境变量指定";
    case "manual":
      return "手动指定";
    case "discovered":
      return "自动发现";
    default:
      return "默认端口";
  }
}

/** 从 target 提取 host:port 展示 */
export function agentTargetLabel(target: string | undefined): string {
  if (!target) return "未知";
  try {
    const url = new URL(target);
    return `${url.hostname}:${url.port || "80"}`;
  } catch {
    return target;
  }
}
