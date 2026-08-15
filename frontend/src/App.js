import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Toaster } from "sonner";
import { LangProvider } from "./context/LangContext";
import Landing from "./pages/Landing";
import Wizard from "./pages/Wizard";
import Pay from "./pages/Pay";
import MockPay from "./pages/MockPay";
import Track from "./pages/Track";
import AdminLogin from "./pages/AdminLogin";
import AdminDashboard from "./pages/AdminDashboard";
import "./i18n";

function App() {
  return (
    <LangProvider>
      <BrowserRouter>
        <Toaster position="top-center" richColors />
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/create" element={<Wizard />} />
          <Route path="/pay/mock" element={<MockPay />} />
          <Route path="/pay/:orderId" element={<Pay />} />
          <Route path="/track" element={<Track />} />
          <Route path="/track/:orderId" element={<Track />} />
          <Route path="/admin/login" element={<AdminLogin />} />
          <Route path="/admin" element={<AdminDashboard />} />
        </Routes>
      </BrowserRouter>
    </LangProvider>
  );
}

export default App;
