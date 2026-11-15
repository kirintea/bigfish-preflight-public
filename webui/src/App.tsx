import { lazy, Suspense, useState } from "react";
import {
  BrowserRouter,
  NavLink,
  Navigate,
  Route,
  Routes,
} from "react-router-dom";
import {
  FlaskConical,
  MessageSquare,
  Palmtree,
  Globe,
  Heart,
  Users,
  Briefcase,
  CloudSun,
  Package,
  Factory,
  BookOpen,
  Workflow,
  Link2,
  ChevronDown,
  AlertCircle,
} from "lucide-react";
import { useTestRun } from "./hooks/useTestRun";
import { Testbench } from "./pages/testbench";
const Prologue = lazy(() =>
  import("./pages/prologue").then((module) => ({ default: module.Prologue })),
);
const navigation = [
  ["world", "世界", Globe],
  ["needs", "身体与需求", Heart],
  ["body", "身体状态", Heart],
  ["social", "关系与性格", Users],
  ["activity", "任务与行动", Briefcase],
  ["environment", "环境", CloudSun],
  ["resources", "资源与物品", Package],
  ["groups", "群体", Users],
  ["production", "生产", Factory],
  ["events", "事件与知识", BookOpen],
  ["conversation", "会话", MessageSquare],
  ["hooks", "Hooks", Workflow],
  ["action_result", "动作结果", Workflow],
  ["scenarios", "场景与重放", BookOpen],
] as const;
function Shell() {
  const lab = useTestRun();
  const [section, setSection] = useState("needs");
  const [token, setToken] = useState("");
  const [showAuth, setShowAuth] = useState(
    window.location.pathname.startsWith("/testbench"),
  );
  return (
    <div className="app">
      <aside className="sidebar">
        <NavLink to="/testbench" className="brand">
          <span className="brand-mark">
            <FlaskConical size={22} />
          </span>
          <span>
            NPC LAB<small>BIGFISH / PREFLIGHT</small>
          </span>
        </NavLink>
        <div className="environment-label">
          <span className="status-dot" />
          隔离测试环境
          <ChevronDown size={13} />
        </div>
        <div className="nav-caption">工作空间</div>
        <nav>
          <NavLink
            to="/prologue"
            title="海滩序章"
            aria-label="海滩序章"
            className="scene-nav"
          >
            <Palmtree size={17} />
            海滩序章<span className="nav-tag">PLAY</span>
          </NavLink>
          {navigation.map(([key, label, Icon]) => (
            <NavLink
              key={key}
              to="/testbench"
              title={label}
              aria-label={key === "conversation" ? "会话 2+" : label}
              className={({ isActive }) =>
                `${isActive && section === key ? "selected" : ""}`
              }
              onClick={() => setSection(key)}
            >
              <Icon size={17} />
              <span>{label}</span>
              {key === "conversation" && <span className="nav-count">2+</span>}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-footer">
          <span className="status-dot" />
          Agent 运行状态<small>离线保底 / 可切换真实模型</small>
        </div>
      </aside>
      <main className="app-main">
        <header className="topbar">
          <div className="breadcrumb">
            爱、荒岛和大肥鱼 <span>/</span> NPC LAB
          </div>
          <button
            className="connection-button"
            aria-label="测试连接设置"
            onClick={() => setShowAuth(!showAuth)}
          >
            <Link2 size={14} />
            {lab.connected ? "测试服务已连接" : "连接测试服务"}
          </button>
        </header>
        {showAuth && (
          <form
            className="auth-bar"
            onSubmit={(e) => {
              e.preventDefault();
              void lab.connect(token).then(() => {
                setToken("");
              });
            }}
          >
            <label>
              测试凭据
              <input
                type="password"
                autoComplete="off"
                aria-label="测试凭据"
                value={token}
                placeholder="当前会话使用"
                onChange={(e) => setToken(e.target.value)}
              />
            </label>
            <button
              className="primary"
              disabled={!token || lab.busy}
              type="submit"
            >
              连接测试服务
            </button>
            {lab.connected && (
              <button
                type="button"
                className="text-button"
                onClick={() => setShowAuth(false)}
              >
                收起
              </button>
            )}
          </form>
        )}
        {lab.error && (
          <div role="alert" className="error-banner">
            <AlertCircle size={16} />
            <span>
              {lab.error === "revision_conflict"
                ? "版本冲突。草稿已保留，请刷新确认值后重新处理差异。"
                : lab.error}
            </span>
            <button className="text-button" onClick={() => lab.setError("")}>
              关闭
            </button>
          </div>
        )}
        <Routes>
          <Route
            path="/testbench"
            element={
              <Testbench lab={lab} section={section} setSection={setSection} />
            }
          />
          <Route
            path="/prologue"
            element={
              <Suspense fallback={<div className="empty">加载海滩…</div>}>
                <Prologue lab={lab} />
              </Suspense>
            }
          />
          <Route path="*" element={<Navigate to="/prologue" replace />} />
        </Routes>
      </main>
    </div>
  );
}
export default function App() {
  return (
    <BrowserRouter>
      <Shell />
    </BrowserRouter>
  );
}
