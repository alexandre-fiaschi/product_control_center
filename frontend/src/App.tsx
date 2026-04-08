import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Toaster } from "sonner";
import AppLayout from "./components/layout/AppLayout";
import Dashboard from "./views/Dashboard";
import Pipeline from "./views/Pipeline";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppLayout />}>
          <Route index element={<Dashboard />} />
          <Route path="pipeline" element={<Pipeline />} />
        </Route>
      </Routes>
      <Toaster position="bottom-right" theme="dark" richColors />
    </BrowserRouter>
  );
}
