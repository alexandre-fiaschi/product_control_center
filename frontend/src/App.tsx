import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Toaster } from "sonner";
import AppLayout from "./components/layout/AppLayout";
import Dashboard from "./views/Dashboard";
import { dk } from "./lib/constants";

function PipelinePlaceholder() {
  return (
    <div className="text-center py-20" style={{ color: dk.textDim }}>
      Pipeline view — coming in Block F3
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppLayout />}>
          <Route index element={<Dashboard />} />
          <Route path="pipeline" element={<PipelinePlaceholder />} />
        </Route>
      </Routes>
      <Toaster position="bottom-right" theme="dark" richColors />
    </BrowserRouter>
  );
}
