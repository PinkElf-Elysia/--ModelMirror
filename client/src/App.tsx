import { Navigate, Route, Routes } from "react-router-dom";
import AgentsPage from "./pages/AgentsPage";
import ChatPage from "./pages/ChatPage";
import ComingSoonPage from "./pages/ComingSoonPage";
import ExpertTeamPage from "./pages/ExpertTeamPage";
import McpBrowserPage from "./pages/McpBrowserPage";
import MetaAgentPage from "./pages/MetaAgentPage";
import ModelListPage from "./pages/ModelListPage";
import RuntimeOpsPage from "./pages/RuntimeOpsPage";
import StudioHomePage from "./pages/StudioHomePage";
import RagPage from "./pages/RagPage";
import SkillBrowserPage from "./pages/SkillBrowserPage";
import SystemSettingsPage from "./pages/SystemSettingsPage";
import WorkflowClassicPage from "./pages/WorkflowClassicPage";
import WorkflowNativePage from "./pages/WorkflowNativePage";
import XpertChatPage from "./pages/XpertChatPage";
import XpertCreatePage from "./pages/XpertCreatePage";
import XpertStudioIndexPage from "./pages/XpertStudioIndexPage";
import XpertStudioPage from "./pages/XpertStudioPage";

export default function App() {
  return (
    <Routes>
      <Route element={<Navigate replace to="/models" />} path="/" />
      <Route element={<ModelListPage />} path="/models" />
      <Route element={<StudioHomePage />} path="/studio" />
      <Route element={<AgentsPage />} path="/agents" />
      <Route element={<MetaAgentPage />} path="/agents/meta-agent" />
      <Route element={<XpertStudioIndexPage />} path="/agents/studio" />
      <Route element={<XpertCreatePage />} path="/agents/studio/new" />
      <Route element={<XpertStudioPage />} path="/agents/studio/:xpertId" />
      <Route element={<XpertChatPage />} path="/agents/xpert/:xpertId/chat" />
      <Route element={<ExpertTeamPage />} path="/expert-team" />
      <Route element={<McpBrowserPage />} path="/mcps" />
      <Route element={<SkillBrowserPage />} path="/skills" />
      <Route element={<RuntimeOpsPage />} path="/runtime" />
      <Route element={<ComingSoonPage resource="prompts" />} path="/prompts" />
      <Route element={<RagPage />} path="/rag" />
      <Route element={<ChatPage />} path="/chat/:modelId" />
      <Route element={<WorkflowClassicPage />} path="/workflow" />
      <Route element={<WorkflowClassicPage />} path="/workflow/:id" />
      <Route element={<WorkflowClassicPage />} path="/workflow/classic" />
      <Route element={<WorkflowClassicPage />} path="/workflow/classic/:id" />
      <Route element={<WorkflowNativePage />} path="/workflow-native" />
      <Route element={<WorkflowNativePage />} path="/workflow-native/:id" />
      <Route element={<SystemSettingsPage />} path="/settings" />
      <Route element={<Navigate replace to="/models" />} path="*" />
    </Routes>
  );
}
