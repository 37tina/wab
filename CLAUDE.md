# CLAUDE.md / AGENTS.md — 项目约定

## Design System

This project uses a design system defined in `DESIGN.md` at the project root.
Always refer to that file when generating or modifying any UI component.

1. Use only colors, fonts, and spacing values defined in DESIGN.md.
2. Do not invent new values or use defaults from any framework.
3. Match component states (hover, focus, active, disabled) to the patterns in DESIGN.md.
4. Follow the typographic scale and weight assignments in DESIGN.md.

@DESIGN.md

## 项目结构与启动

- `web/`（Vite + React，端口 5173）、`backend/`（Express 网关，端口 8080）、`skill-snapshot/`（完整 skill 快照，勿改）
- 启动：两个目录分别 `npm run dev` / `npm start`；状态锚点见 `HANDOFF.md`
- 测试：`cd web && npm test`（20 个）；构建：`npm run build`
