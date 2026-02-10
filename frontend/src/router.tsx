import { createBrowserRouter, Navigate } from 'react-router-dom'
import AppLayout from './ui/AppLayout'
import LoginPage from './pages/LoginPage'
import NewCheckPage from './pages/NewCheckPage'
import TasksPage from './pages/TasksPage'
import HistoryPage from './pages/HistoryPage'
import ResultPage from './pages/ResultPage'
import PromptsPage from './pages/PromptsPage'
import StatsPage from './pages/StatsPage'

const router = createBrowserRouter([
  {
    path: '/login',
    element: <LoginPage />,
  },
  {
    path: '/',
    element: <AppLayout />,
    children: [
      { index: true, element: <Navigate to="/checks" replace /> },
      { path: 'checks/new', element: <NewCheckPage /> },
      { path: 'checks', element: <TasksPage /> },
      { path: 'history', element: <HistoryPage /> },
      { path: 'results/:id', element: <ResultPage /> },
      { path: 'prompts', element: <PromptsPage /> },
      { path: 'stats', element: <StatsPage /> },
    ],
  },
])

export default router

