import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Layout from './components/Layout';
import Dashboard from './components/Dashboard';
import JobsTable from './components/JobsTable';
import CreateJob from './components/CreateJob';
import DLQView from './components/DLQView';
import JobDetail from './components/JobDetail';
import WorkflowCreate from './components/WorkflowCreate';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<Dashboard />} />
          <Route path="/jobs" element={<JobsTable />} />
          <Route path="/jobs/:id" element={<JobDetail />} />
          <Route path="/create" element={<CreateJob />} />
          <Route path="/dlq" element={<DLQView />} />
          <Route path="/workflows" element={<WorkflowCreate />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
