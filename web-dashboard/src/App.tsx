import { Outlet, NavLink } from 'react-router-dom';
import { LayoutDashboard, List, Beaker, Settings } from 'lucide-react';

export default function App() {
  return (
    <div className="app-layout">
      <aside className="sidebar">
        <div className="sidebar-logo">VSRS Dashboard</div>
        <ul className="sidebar-nav">
          <li>
            <NavLink to="/dashboard" className={({ isActive }) => isActive ? 'active' : ''}>
              <LayoutDashboard size={18} /> Dashboard
            </NavLink>
          </li>
          <li>
            <NavLink to="/" end className={({ isActive }) => isActive ? 'active' : ''}>
              <List size={18} /> Runs
            </NavLink>
          </li>
          <li>
            <NavLink to="/benchmarks" className={({ isActive }) => isActive ? 'active' : ''}>
              <Beaker size={18} /> Benchmarks
            </NavLink>
          </li>
          <li>
            <NavLink to="/settings" className={({ isActive }) => isActive ? 'active' : ''}>
              <Settings size={18} /> Settings
            </NavLink>
          </li>
        </ul>
      </aside>
      <main className="main-content">
        <Outlet />
      </main>
    </div>
  );
}
