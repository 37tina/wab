import { beforeEach, describe, expect, it, vi } from "vitest";
import { MockMigrationServiceImpl } from "./mockService";

describe("MockMigrationService", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.useFakeTimers();
  });

  it("runs a phase until the human review gate", () => {
    const service = new MockMigrationServiceImpl();
    const project = service.createProject({ name: "测试迁移", sourceType: "github", sourceValue: "https://github.com/example/app" });

    vi.advanceTimersByTime(6000);
    const updated = service.getProject(project.id);

    expect(updated?.phases[0].status).toBe("review_required");
    expect(updated?.phases[0].events.length).toBeGreaterThan(3);
    expect(updated?.status).toBe("review");
  });

  it("continues to the next phase after approval and increments revisions on changes", () => {
    const service = new MockMigrationServiceImpl();
    const project = service.createProject({ name: "审核流程", sourceType: "zip", sourceValue: "android-app.zip" });

    vi.advanceTimersByTime(6000);
    service.reviewPhase(project.id, 1, { decision: "changes_requested", comment: "补充异常场景", reviewer: "测试员", reviewedAt: new Date().toISOString() });
    vi.advanceTimersByTime(700);
    expect(service.getProject(project.id)?.phases[0].revision).toBe(2);
    expect(service.getProject(project.id)?.phases[0].status).toBe("running");

    vi.advanceTimersByTime(6000);
    service.reviewPhase(project.id, 1, { decision: "approved", comment: "通过", reviewer: "测试员", reviewedAt: new Date().toISOString() });
    vi.advanceTimersByTime(700);
    const next = service.getProject(project.id);
    expect(next?.currentPhase).toBe(2);
    expect(next?.phases[0].status).toBe("approved");
    expect(next?.phases[1].status).toBe("running");
  });

  it("persists project snapshots in localStorage", () => {
    const service = new MockMigrationServiceImpl();
    const project = service.createProject({ name: "持久化项目", sourceType: "github", sourceValue: "https://github.com/example/persist" });
    const persisted = JSON.parse(localStorage.getItem("tuotaihuangu_projects_v1") ?? "[]") as Array<{ id: string }>;

    expect(persisted.some((item) => item.id === project.id)).toBe(true);
  });

  it("stores the user-specified CodeArts workspace directory on the project", () => {
    const service = new MockMigrationServiceImpl();
    const project = service.createProject({ name: "指定工作区", sourceType: "github", sourceValue: "https://github.com/example/ws", executionMode: "codearts-agentteam", workspaceDir: "D:\\code\\migration-ws" });

    expect(service.getProject(project.id)?.workspaceDir).toBe("D:\\code\\migration-ws");
    const persisted = JSON.parse(localStorage.getItem("tuotaihuangu_projects_v1") ?? "[]") as Array<{ id: string; workspaceDir?: string }>;
    expect(persisted.find((item) => item.id === project.id)?.workspaceDir).toBe("D:\\code\\migration-ws");
  });

  it("keeps a real AgentTeam phase running until CodeArts returns", () => {
    const service = new MockMigrationServiceImpl();
    const project = service.createProject({ name: "真实 AgentTeam", sourceType: "github", sourceValue: "https://github.com/example/real", executionMode: "codearts-agentteam" });

    vi.advanceTimersByTime(6000);
    expect(service.getProject(project.id)?.phases[0].status).toBe("running");
    expect(service.getProject(project.id)?.phases[0].events).toHaveLength(1);

    service.recordCodeArtsExecution(project.id, 1, { mode: "codearts-agentteam", status: "succeeded", sessionId: "ses_real", response: "真实构建完成" });
    const updated = service.getProject(project.id);
    expect(updated?.phases[0].status).toBe("review_required");
    expect(updated?.phases[0].execution?.sessionId).toBe("ses_real");
    expect(updated?.phases[0].events.some((event) => event.message.includes("真实会话结果"))).toBe(true);
  });
});
