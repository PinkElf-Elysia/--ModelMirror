import { Navigate, Route, Routes } from "react-router-dom";
import AgentsPage from "./pages/AgentsPage";
import ChatPage from "./pages/ChatPage";
import ComingSoonPage from "./pages/ComingSoonPage";
import ExpertTeamPage from "./pages/ExpertTeamPage";
import McpBrowserPage from "./pages/McpBrowserPage";
import ModelListPage from "./pages/ModelListPage";
import StudioHomePage from "./pages/StudioHomePage";
import RagPage from "./pages/RagPage";
import SkillBrowserPage from "./pages/SkillBrowserPage";
import WorkflowClassicPage from "./pages/WorkflowClassicPage";
import WorkflowEditorPage from "./pages/WorkflowEditorPage";

export default function App() {
  return (
    <Routes>
      <Route element={<Navigate replace to="/models" />} path="/" />
      <Route element={<ModelListPage />} path="/models" />
      <Route element={<StudioHomePage />} path="/studio" />
      <Route element={<AgentsPage />} path="/agents" />
      <Route element={<ExpertTeamPage />} path="/expert-team" />
      <Route element={<McpBrowserPage />} path="/mcps" />
      <Route element={<SkillBrowserPage />} path="/skills" />
      <Route element={<ComingSoonPage resource="prompts" />} path="/prompts" />
      <Route element={<RagPage />} path="/rag" />
      <Route element={<ChatPage />} path="/chat/:modelId" />
      <Route element={<WorkflowEditorPage />} path="/workflow" />
      <Route element={<WorkflowClassicPage />} path="/workflow/classic" />
      <Route element={<WorkflowClassicPage />} path="/workflow/classic/:id" />
      <Route element={<WorkflowEditorPage />} path="/workflow/new" />
      <Route element={<WorkflowEditorPage />} path="/workflow/:id" />
      <Route element={<Navigate replace to="/models" />} path="*" />
    </Routes>
  );
}
