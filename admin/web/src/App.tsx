import { useQuery } from "@tanstack/react-query";
import { Navigate, Route, Routes } from "react-router-dom";
import { api } from "@/lib/api";
import Layout from "@/components/Layout";
import { Skeleton } from "@/components/ui/primitives";
import Login from "@/pages/Login";
import Dashboard from "@/pages/Dashboard";
import Users from "@/pages/Users";
import Send from "@/pages/Send";
import Tariffs from "@/pages/Tariffs";

function Gate() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["me"],
    queryFn: api.me,
    retry: false,
  });
  if (isLoading) {
    return (
      <div className="space-y-3 p-8">
        <Skeleton className="h-8 w-40" />
        <Skeleton className="h-32 w-full" />
      </div>
    );
  }
  if (error || !data) return <Navigate to="/login" replace />;
  return <Layout mail={data.mail} />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route element={<Gate />}>
        <Route path="/" element={<Dashboard />} />
        <Route path="/users" element={<Users />} />
        <Route path="/send" element={<Send />} />
        <Route path="/tariffs" element={<Tariffs />} />
      </Route>
    </Routes>
  );
}
