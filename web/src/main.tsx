import "@fontsource/hanken-grotesk/400.css";
import "@fontsource/hanken-grotesk/500.css";
import "@fontsource/hanken-grotesk/600.css";
import "@fontsource/hanken-grotesk/700.css";
import "@fontsource/jetbrains-mono/400.css";
import "@fontsource/jetbrains-mono/500.css";
import "@fontsource/jetbrains-mono/600.css";
import "./styles.css";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { Link, RouterProvider, createBrowserRouter } from "react-router";
import Layout from "./components/Layout";
import { ToastProvider } from "./components/ui";
import BookmarkEdit from "./pages/BookmarkEdit";
import Bookmarks from "./pages/Bookmarks";
import Dashboard from "./pages/Dashboard";
import Settings from "./pages/Settings";
import Sync from "./pages/Sync";
import Tags from "./pages/Tags";
import TopicPage from "./pages/TopicPage";
import Topics from "./pages/Topics";

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 10_000, refetchOnWindowFocus: true, retry: 1 } },
});

function NotFound() {
  return (
    <div className="py-16 text-center">
      <div className="lbl">404</div>
      <h1 className="mt-2 text-3xl font-semibold">Nothing here</h1>
      <Link to="/" className="btn mt-6">Back to dashboard</Link>
    </div>
  );
}

const router = createBrowserRouter([
  {
    element: <Layout />,
    children: [
      { path: "/", element: <Dashboard /> },
      { path: "/topics", element: <Topics /> },
      { path: "/topics/:id", element: <TopicPage /> },
      { path: "/bookmarks", element: <Bookmarks /> },
      { path: "/bookmarks/new", element: <BookmarkEdit /> },
      { path: "/bookmarks/:id", element: <BookmarkEdit /> },
      { path: "/tags", element: <Tags /> },
      { path: "/settings", element: <Settings /> },
      { path: "/sync", element: <Sync /> },
      { path: "*", element: <NotFound /> },
    ],
  },
]);

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <RouterProvider router={router} />
      </ToastProvider>
    </QueryClientProvider>
  </StrictMode>,
);
