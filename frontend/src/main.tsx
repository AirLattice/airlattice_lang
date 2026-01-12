import ReactDOM from "react-dom/client";
import App from "./App.tsx";
import "./index.css";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { StrictMode } from "react";
import { QueryClient, QueryClientProvider } from "react-query";
import { NotFound } from "./components/NotFound.tsx";
import { AuthGate } from "./components/AuthGate.tsx";
import { Login } from "./pages/Login.tsx";
import { MemoryPage } from "./pages/Memory.tsx";
import { Signup } from "./pages/Signup.tsx";

const queryClient = new QueryClient();

ReactDOM.createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/signup" element={<Signup />} />
          <Route element={<AuthGate />}>
            <Route path="/thread/:chatId" element={<App />} />
            <Route path="/memory" element={<MemoryPage />} />
            <Route
              path="/assistant/:assistantId/edit"
              element={<App edit={true} />}
            />
            <Route path="/assistant/:assistantId" element={<App />} />
            <Route path="/" element={<App />} />
            <Route path="*" element={<NotFound />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
