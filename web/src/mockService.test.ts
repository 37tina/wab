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
});
